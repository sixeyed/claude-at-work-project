# shellcheck shell=bash
# Shared by scripts/build.sh, deploy.sh and test.sh — sourced, never executed.
#
# Everything a CI pipeline might need to change is an environment variable with a
# local default, so the pipeline runs the same scripts a developer does and
# overrides only these:
#
#   IMAGE_REGISTRY  where images are tagged and pushed. Default: the registry
#                   `deploy.sh cluster` creates. Set it empty for bare
#                   `collabhub/<component>` names.
#   IMAGE_TAG       default: the short commit SHA, plus `-dirty` when the
#                   worktree has uncommitted changes. Never `latest`.
#   KUBE_CONTEXT    default: the k3d cluster's context. Nothing here falls back
#                   to kubectl's current context, which might be a real cluster.
#
# Written for bash 3.2, which is what macOS ships: no associative arrays, and an
# empty array is expanded as ${arr[@]+"${arr[@]}"} because `set -u` rejects it
# otherwise.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

COMPONENTS=(auth messaging canvas asset worker frontend)

K3D_CLUSTER=collabhub
# The only published port. The Ingress puts the SPA, the APIs and Dex behind this
# one origin, which is what register D22's SameSite=Strict cookie needs.
K3D_ORIGIN=http://localhost:8080
NAMESPACE=collabhub

# `-` not `:-` so an explicitly empty registry stays empty.
IMAGE_REGISTRY="${IMAGE_REGISTRY-localhost:5500}"
KUBE_CONTEXT="${KUBE_CONTEXT:-k3d-$K3D_CLUSTER}"

# Worked out once, when the script starts, so a build that runs for minutes
# cannot straddle an edit and tag half its images differently.
if [ -z "${IMAGE_TAG:-}" ]; then
    IMAGE_TAG="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
    if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
        IMAGE_TAG="${IMAGE_TAG}-dirty"
    fi
fi

# Files charts/collabhub-local reads from the repo rather than keeping a copy of.
# Helm cannot reach outside a chart's directory, so they arrive as --set-file.
LOCAL_CHART_FILES=(
    --set-file "postgres.initSql=$REPO_ROOT/docker/postgres/init.sql"
    --set-file "garage.config=$REPO_ROOT/docker/garage/garage.toml"
    --set-file "otelCollector.config=$REPO_ROOT/docker/otel-collector/config.yaml"
)

if [ -t 2 ]; then
    _bold=$'\033[1m' _red=$'\033[31m' _reset=$'\033[0m'
else
    _bold='' _red='' _reset=''
fi

log() { printf '%s==> %s%s\n' "$_bold" "$*" "$_reset" >&2; }
die() {
    printf '%serror:%s %s\n' "$_red" "$_reset" "$*" >&2
    exit 1
}

# Prints the comment block at the top of the calling script, minus the `#`s.
usage() { sed -n '2,/^[^#]/s/^# \{0,1\}//p' "$0" | sed '$d'; }

require_cmd() {
    local cmd
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || die "'$cmd' is required and is not on PATH"
    done
}

is_component() {
    local c
    for c in "${COMPONENTS[@]}"; do
        [ "$c" = "$1" ] && return 0
    done
    return 1
}

image_ref() { printf '%scollabhub/%s:%s' "${IMAGE_REGISTRY:+$IMAGE_REGISTRY/}" "$1" "$IMAGE_TAG"; }
