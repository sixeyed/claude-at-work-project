# shellcheck shell=bash
# Preview environments — sourced by scripts/deploy.sh after common.sh, never executed.
#
# The parts of `deploy.sh preview` that can be proven without a cluster: the
# branch → namespace rule, and starting, detecting and stopping the two
# cloudflared quick tunnels. They are tested from pytest, through /bin/bash
# (src/services/testkit/tests/unit/test_preview_script.py).
#
# Callers that capture a function's output must not rely on `die` inside `$(…)`
# ending the script: assign on its own line so `set -e` turns the status into one.

# Lowercase, every byte outside [a-z0-9] a dash, runs collapsed, ends trimmed. LC_ALL=C
# so macOS and Linux agree whatever the locale. May print nothing.
preview_slug() {
    printf '%s' "$1" | LC_ALL=C tr 'A-Z' 'a-z' | LC_ALL=C tr -c 'a-z0-9' '-' |
        tr -s '-' | sed 's/^-//; s/-$//'
}

# First 6 hex characters of the SHA-1 of $1.
_preview_hash6() {
    local hex
    if command -v sha1sum >/dev/null 2>&1; then
        hex="$(printf '%s' "$1" | sha1sum)"
    else
        hex="$(printf '%s' "$1" | shasum -a 1)"
    fi
    printf '%s' "${hex:0:6}"
}

# preview-<slug>, within a namespace's 63 characters. Longer is cut to 56, trimmed of a
# trailing dash and suffixed with the branch's hash, so two long branches that share
# a slug prefix don't share a namespace.
preview_namespace() {
    local slug name
    slug="$(preview_slug "$1")"
    [ -n "$slug" ] || die "branch '$1' has no letters or digits to name a preview after"
    name="preview-$slug"
    if [ ${#name} -gt 63 ]; then
        name="${name:0:56}"
        name="${name%-}"
        name="$name-$(_preview_hash6 "$1")"
    fi
    printf '%s' "$name"
}

# The tag a preview's images are pushed at. A dirty tag names only the commit, and
# every worktree branched from one commit shares it — so previews left up side by
# side would pull each other's images on a restart. The namespace goes in before
# `-dirty`, which stays last: cmd_app restarts a dirty tag's pods on an upgrade. A
# clean tag is one build of one commit, and is shared.
preview_image_tag() {
    case "$1" in
        *-dirty) printf '%s-%s-dirty' "${1%-dirty}" "$2" ;;
        *) printf '%s' "$1" ;;
    esac
}

# $BRANCH, else the branch checked out in $1 (default: the repo this script is in).
preview_branch() {
    local dir="${1:-$REPO_ROOT}" branch
    if [ -n "${BRANCH:-}" ]; then
        printf '%s' "$BRANCH"
        return 0
    fi
    branch="$(git -C "$dir" symbolic-ref --quiet --short HEAD 2>/dev/null)" || branch=""
    [ -n "$branch" ] || die "HEAD is detached — set BRANCH to name the preview"
    printf '%s' "$branch"
}

# Inside .git, so never tracked and shared by every worktree: a preview belongs to a
# branch, and `down` has to work from any checkout of it.
preview_state_dir() {
    local root="${PREVIEW_STATE_ROOT:-}" common
    if [ -z "$root" ]; then
        common="$(cd "$REPO_ROOT" && cd "$(git rev-parse --git-common-dir)" && pwd)"
        root="$common/collabhub-previews"
    fi
    printf '%s/%s' "$root" "$1"
}

# The first quick-tunnel URL in a cloudflared log. The hyphen rule excludes
# api.trycloudflare.com, which error lines name.
tunnel_url_from_log() {
    local url
    url="$(grep -Eo 'https://[a-z0-9]+(-[a-z0-9]+)+\.trycloudflare\.com' "$1" 2>/dev/null | head -n 1)"
    [ -n "$url" ] || return 1
    printf '%s\n' "$url"
}

# Polls a log once a second for a URL, for up to $2 seconds.
preview_wait_for_url() {
    local log="$1" seconds="$2" waited=0
    while :; do
        tunnel_url_from_log "$log" && return 0
        [ "$waited" -lt "$seconds" ] || return 1
        sleep 1
        waited=$((waited + 1))
    done
}

# True when the pid file names a running process whose command is cloudflared. A pid
# file can outlive its process, and a reboot can hand the pid to something else.
tunnel_alive() {
    local pid command
    [ -f "$1" ] || return 1
    pid="$(cat "$1" 2>/dev/null)"
    case "$pid" in '' | *[!0-9]*) return 1 ;; esac
    kill -0 "$pid" 2>/dev/null || return 1
    command="$(ps -p "$pid" -o command= 2>/dev/null)"
    case "$command" in
        *"cloudflared tunnel"*) return 0 ;;
    esac
    return 1
}

_preview_url_in() { [ -s "$1" ]; }

# True when the tunnel's public URL still reaches Cloudflare's end of it. A running
# process is not enough: when its connection drops for long enough — the laptop
# sleeps — Cloudflare deletes a quick tunnel, its hostname stops resolving, and the
# process retries for ever with "Tunnel not found". No answer at all, or 530 (a
# tunnel with no connection), is dead; any other status is the instance answering,
# Garage's 403 at its root and a 502 mid-rollout included.
tunnel_url_answers() {
    local url code
    url="$(cat "$1" 2>/dev/null)"
    [ -n "$url" ] || return 1
    code="$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --max-time 10 "$url" 2>/dev/null)" || true
    case "$code" in '' | 000 | 530) return 1 ;; esac
}

# Both tunnels running, both URLs recorded, and both answering. The cheap process
# checks come first, so a killed tunnel costs no network round trip.
preview_tunnels_live() {
    tunnel_alive "$1/app.pid" && tunnel_alive "$1/s3.pid" &&
        _preview_url_in "$1/app.url" && _preview_url_in "$1/s3.url" &&
        tunnel_url_answers "$1/app.url" && tunnel_url_answers "$1/s3.url"
}

# Starts the two tunnels to the k3d load balancer, each with its own log, and waits
# up to $2 seconds (default 30) for both URLs. A miss stops both.
preview_start_tunnels() {
    local dir="$1" seconds="${2:-30}" role waited=0 app="" s3=""
    mkdir -p "$dir"
    rm -f "$dir/app.url" "$dir/s3.url"
    for role in app s3; do
        # Output goes to the log and stdin to /dev/null, so no pipe of the caller's
        # stays open behind a process that outlives it.
        nohup cloudflared tunnel --no-autoupdate --url "$K3D_ORIGIN" \
            >"$dir/$role.log" 2>&1 </dev/null &
        echo $! >"$dir/$role.pid"
    done
    while :; do
        app="$(tunnel_url_from_log "$dir/app.log")" || app=""
        s3="$(tunnel_url_from_log "$dir/s3.log")" || s3=""
        [ -n "$app" ] && [ -n "$s3" ] && break
        if [ "$waited" -ge "$seconds" ]; then
            if [ -z "$app" ]; then role=app; else role=s3; fi
            preview_stop_tunnels "$dir"
            printf 'error: no quick-tunnel URL from the %s tunnel in %ss — see %s\n' \
                "$role" "$seconds" "$dir/$role.log" >&2
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    printf '%s\n' "$app" >"$dir/app.url"
    printf '%s\n' "$s3" >"$dir/s3.url"
}

# TERM, then KILL after 5 s, for each tunnel a pid file names — and only when
# tunnel_alive accepts it, so a reused pid is never signalled. Keeps the logs.
preview_stop_tunnels() {
    local dir="$1" role pid waited
    for role in app s3; do
        if tunnel_alive "$dir/$role.pid"; then
            pid="$(cat "$dir/$role.pid")"
            kill -TERM "$pid" 2>/dev/null || true
            waited=0
            while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt 50 ]; do
                sleep 0.1
                waited=$((waited + 1))
            done
            if kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$dir/$role.pid" "$dir/$role.url"
    done
    return 0
}

# The Helm arguments that give a preview's Dex its own password: PREVIEW_PASSWORD, bcrypted,
# as the deps chart's dex.passwordHash, one argument a line. Nothing without it — the k3d
# values' shared `collabhub` stands. The password goes to htpasswd on stdin, never in argv,
# where `ps` would show it. (Handoff 09, decision 10: random only when Slack can carry it.)
preview_password_args() {
    [ -n "${PREVIEW_PASSWORD:-}" ] || return 0
    require_cmd htpasswd
    local hash
    hash="$(printf '%s\n' "$PREVIEW_PASSWORD" | htpasswd -niBC 10 "" | tr -d ':\n')"
    [ -n "$hash" ] || die "htpasswd gave no hash for PREVIEW_PASSWORD"
    printf '%s\n' --set-string "dex.passwordHash=$hash"
}
