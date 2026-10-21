#!/usr/bin/env bash
# Deploy CollabHub to Kubernetes with Helm. Developers and CI run this same
# script.
#
#   scripts/deploy.sh [up]     cluster, then infra, then app. Re-run to upgrade
#   scripts/deploy.sh cluster  create the k3d cluster and its image registry
#   scripts/deploy.sh infra    KEDA, then data stores, Dex, Secrets and Dex's Ingress
#   scripts/deploy.sh app      CollabHub itself (charts/collabhub) at IMAGE_TAG
#   scripts/deploy.sh status   releases, pods, jobs and ingresses
#   scripts/deploy.sh down     delete the k3d cluster, its registry and all its data
#
#   scripts/deploy.sh preview up    this branch's whole app in namespace preview-<slug>,
#                              public on two cloudflared quick tunnels (cloudflared
#                              on PATH): one for the app, one for object storage.
#                              Builds, pushes and deploys; prints both origins.
#                              A rerun reuses live tunnels, else starts new ones
#                              (new URLs, so sign in again; data is kept)
#   scripts/deploy.sh preview url   print APP_ORIGIN= and OBJECT_STORE_ORIGIN=
#   scripts/deploy.sh preview down  stop the tunnels, uninstall both releases and
#                              delete the namespace; the cluster and KEDA stay
#
#   BRANCH names the preview (default: the checked-out branch). Two `preview up`
#   runs at once are unsupported (both upgrade KEDA), as is `up` racing `down`.
#   Branches whose names differ only in separators share one preview.
#
#   scripts/deploy.sh infra -- --set-string postgres.password=...
#                              anything after -- goes to that command's helm call
#
# One instance per NAMESPACE, reached on APP_ORIGIN; DEPLOY_ENV picks the values
# files. Two instances on one k3d cluster:
#
#   NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh up
#   NAMESPACE=collabhub-b APP_ORIGIN=http://b.localhost:8080 scripts/deploy.sh up
#
# The images must already be in the registry — run scripts/build.sh --push
# first. With no overrides CollabHub is served at http://localhost:8080.
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
# shellcheck source=lib/preview.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/preview.sh"

APP_RELEASE=collabhub
DEPS_RELEASE=collabhub-deps

# Every call names its context. A developer's current context may be a real
# cluster, and none of this should ever follow it there.
kube() { kubectl --context "$KUBE_CONTEXT" --namespace "$NAMESPACE" "$@"; }
helm_ns() { helm --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE" "$@"; }

is_local_cluster() { [ "$KUBE_CONTEXT" = "k3d-$K3D_CLUSTER" ]; }

# `cluster` creates the k3d cluster and `down` deletes it, with everything in it.
# Neither may touch a shared cluster. `infra` and `app` are guarded by
# require_matching_context instead.
require_local_cluster() {
    is_local_cluster || die "'$1' only targets the local k3d cluster, and KUBE_CONTEXT is '$KUBE_CONTEXT'"
}

# Only k3d has a default origin. Anywhere else the origin is the environment's
# identity, and guessing localhost would install something nobody can reach.
resolve_origin() {
    if [ -z "$APP_ORIGIN" ]; then
        [ "$DEPLOY_ENV" = k3d ] || die "APP_ORIGIN is required when DEPLOY_ENV is '$DEPLOY_ENV'"
        APP_ORIGIN="$K3D_ORIGIN"
    fi
    APP_ORIGIN="$(normalize_origin APP_ORIGIN "$APP_ORIGIN")"
    if [ -n "$OBJECT_STORE_ORIGIN" ]; then
        OBJECT_STORE_ORIGIN="$(normalize_origin OBJECT_STORE_ORIGIN "$OBJECT_STORE_ORIGIN")"
    fi
}

# The environment and the cluster have to agree, in both directions: k3d values
# carry throwaway credentials that must not reach a shared cluster, and another
# environment's values would misconfigure the laptop's.
require_matching_context() {
    if [ "$DEPLOY_ENV" = k3d ]; then
        is_local_cluster || die "DEPLOY_ENV is k3d but KUBE_CONTEXT is '$KUBE_CONTEXT'"
    elif is_local_cluster; then
        die "DEPLOY_ENV is '$DEPLOY_ENV' but KUBE_CONTEXT is the local k3d cluster"
    fi
    local chart
    for chart in collabhub collabhub-deps; do
        [ -f "$REPO_ROOT/charts/$chart/values-$DEPLOY_ENV.yaml" ] \
            || die "no charts/$chart/values-$DEPLOY_ENV.yaml for DEPLOY_ENV '$DEPLOY_ENV'"
    done
}

cluster_exists() { k3d cluster get "$K3D_CLUSTER" >/dev/null 2>&1; }

cmd_cluster() {
    require_local_cluster cluster
    require_cmd k3d docker
    if cluster_exists; then
        log "k3d cluster '$K3D_CLUSTER' exists — making sure it is running"
        k3d cluster start "$K3D_CLUSTER"
    else
        log "creating k3d cluster '$K3D_CLUSTER'"
        k3d cluster create --config "$REPO_ROOT/scripts/k3d/cluster.yaml"
    fi
}

cmd_infra() {
    require_matching_context
    require_cmd helm

    # A cluster add-on rather than part of either chart: charts/collabhub refuses
    # to render without the keda.sh/v1alpha1 API its Worker pools scale with.
    log "installing KEDA $KEDA_VERSION"
    helm --kube-context "$KUBE_CONTEXT" upgrade --install keda keda \
        --repo https://kedacore.github.io/charts --version "$KEDA_VERSION" \
        --namespace keda --create-namespace \
        --wait --timeout 10m

    log "installing $DEPS_RELEASE into $NAMESPACE for $APP_ORIGIN — data stores, Dex, Secrets"
    helm_ns upgrade --install "$DEPS_RELEASE" "$REPO_ROOT/charts/collabhub-deps" \
        --create-namespace \
        --values "$REPO_ROOT/charts/collabhub-deps/values-$DEPLOY_ENV.yaml" \
        "${DEPS_CHART_FILES[@]}" \
        --set-string "origin=$APP_ORIGIN" \
        --set-string "objectStoreOrigin=$OBJECT_STORE_ORIGIN" \
        ${helm_args[@]+"${helm_args[@]}"} \
        --wait --timeout 10m
}

cmd_app() {
    require_matching_context
    require_cmd helm kubectl docker curl

    # The k3d registry is on the developer's machine, and nothing else can pull
    # from it: without this the pods sit in ImagePullBackOff until Helm times out.
    if [ "$DEPLOY_ENV" != k3d ]; then
        case "$IMAGE_REGISTRY" in
            "" | localhost* | 127.0.0.1*)
                die "IMAGE_REGISTRY is '$IMAGE_REGISTRY', which DEPLOY_ENV '$DEPLOY_ENV' cannot pull from — set it to a registry that cluster can reach"
                ;;
        esac
    fi

    # Checked up front: a missing image otherwise surfaces as ImagePullBackOff
    # and a Helm timeout ten minutes later.
    #
    # `buildx imagetools`, not `docker manifest inspect`: the latter needs
    # --insecure for the k3d registry's plain HTTP and answers "no such manifest"
    # without it. imagetools treats localhost as HTTP itself and uses the same
    # `docker login` credentials for a real registry, so CI needs no special case.
    local component ref missing=()
    for component in "${COMPONENTS[@]}"; do
        ref="$(image_ref "$component")"
        docker buildx imagetools inspect "$ref" >/dev/null 2>&1 || missing+=("$ref")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        die "not in the registry: ${missing[*]} — run scripts/build.sh --push first"
    fi

    local upgrading=false
    if helm_ns status "$APP_RELEASE" >/dev/null 2>&1; then
        upgrading=true
    fi

    log "installing $APP_RELEASE at $IMAGE_TAG into $NAMESPACE for $APP_ORIGIN"
    # Everything that depends on where this instance is reached, or which
    # namespace it is in, is set here — never in a values file — so one values
    # file serves any number of instances.
    #
    # REDIS_STREAMS_ADDRESS is read by KEDA's operator, which resolves it from its
    # own namespace, so it must be fully qualified.
    helm_ns upgrade --install "$APP_RELEASE" "$REPO_ROOT/charts/collabhub" \
        --create-namespace \
        --values "$REPO_ROOT/charts/collabhub/values-$DEPLOY_ENV.yaml" \
        --set-string "image.registry=$IMAGE_REGISTRY" \
        --set-string "image.tag=$IMAGE_TAG" \
        --set-string "origin=$APP_ORIGIN" \
        --set-string "ingress.host=$(origin_host "$APP_ORIGIN")" \
        --set-string "components.auth.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.auth.env.SPA_REDIRECT_URI=$APP_ORIGIN/auth/callback" \
        --set-string "components.messaging.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.canvas.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.asset.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.asset.env.OBJECT_STORE_PUBLIC_ENDPOINT=$(object_store_endpoint "$APP_ORIGIN" "$OBJECT_STORE_ORIGIN")" \
        --set-string "components.worker.env.REDIS_STREAMS_ADDRESS=redis-streams.$NAMESPACE.svc.cluster.local:6379" \
        ${helm_args[@]+"${helm_args[@]}"} \
        --wait --timeout 10m

    # Every rebuild from one dirty commit reuses the same tag, so Helm sees an
    # unchanged pod spec and would leave the old pods running.
    if $upgrading && [[ "$IMAGE_TAG" == *-dirty ]]; then
        log "restarting workloads to pick up the rebuilt $IMAGE_TAG images"
        kube rollout restart deployment --selector "app.kubernetes.io/instance=$APP_RELEASE"
        kube rollout status deployment --selector "app.kubernetes.io/instance=$APP_RELEASE" --timeout 5m
    fi

    check_origin
}

# Through the Ingress, so this proves routing as well as the pods: the SPA, and
# Auth's JWKS, which every other service needs to verify a token. Routing is
# what is most likely to be wrong in a new environment, so it runs everywhere.
check_origin() {
    local path
    for path in / /.well-known/jwks.json; do
        curl --fail --silent --show-error --output /dev/null \
            --retry 30 --retry-delay 2 --retry-all-errors \
            "$APP_ORIGIN$path" || die "$APP_ORIGIN$path is not answering"
    done
    if [ "$DEPLOY_ENV" = k3d ]; then
        log "CollabHub is up at $APP_ORIGIN — sign in as ada@collabhub.dev with password collabhub"
    else
        log "CollabHub is up at $APP_ORIGIN"
    fi
}

cmd_status() {
    require_cmd helm kubectl
    log "namespace $NAMESPACE, origin ${APP_ORIGIN:-(not set)}"
    helm_ns list
    kube get pods,jobs,ingress
}

cmd_down() {
    require_local_cluster down
    require_cmd k3d
    if cluster_exists; then
        log "deleting k3d cluster '$K3D_CLUSTER' and its registry"
        k3d cluster delete "$K3D_CLUSTER"
    else
        log "k3d cluster '$K3D_CLUSTER' does not exist — nothing to delete"
    fi
}

cmd_up() {
    cmd_cluster
    cmd_infra
    cmd_app
}

# --- preview: this branch's whole app, in its own namespace, on two quick tunnels

# What a preview owns. Each would be silently overwritten or contradict k3d's
# values, so it is refused rather than ignored. An explicit NAMESPACE=collabhub
# can't be told from the default, and is ignored like it.
preview_guard() {
    require_local_cluster preview
    [ -z "$APP_ORIGIN" ] || die "preview sets APP_ORIGIN itself from its tunnel — unset it"
    [ -z "$OBJECT_STORE_ORIGIN" ] || die "preview sets OBJECT_STORE_ORIGIN itself from its tunnel — unset it"
    [ "$NAMESPACE" = collabhub ] || die "preview names its own namespace — unset NAMESPACE (got '$NAMESPACE')"
    [ "$DEPLOY_ENV" = k3d ] || die "preview runs on k3d values only — DEPLOY_ENV is '$DEPLOY_ENV'"
    local branch
    branch="$(preview_branch)"
    NAMESPACE="$(preview_namespace "$branch")"
    PREVIEW_STATE="$(preview_state_dir "$NAMESPACE")"
}

cmd_preview_up() {
    preview_guard
    # cloudflared first: it is the tool a developer is likeliest not to have.
    require_cmd cloudflared
    require_cmd k3d docker helm kubectl curl
    log "preview $NAMESPACE"

    # The cluster comes before the build: build.sh --push pushes to the registry
    # the cluster creates.
    cmd_cluster
    IMAGE_TAG="$(preview_image_tag "$IMAGE_TAG" "$NAMESPACE")"
    IMAGE_TAG="$IMAGE_TAG" "$REPO_ROOT/scripts/build.sh" --push

    if preview_tunnels_live "$PREVIEW_STATE"; then
        log "reusing the running tunnels for $NAMESPACE"
    else
        preview_stop_tunnels "$PREVIEW_STATE"
        log "starting two quick tunnels"
        preview_start_tunnels "$PREVIEW_STATE"
    fi
    APP_ORIGIN="$(cat "$PREVIEW_STATE/app.url")"
    OBJECT_STORE_ORIGIN="$(cat "$PREVIEW_STATE/s3.url")"
    resolve_origin
    # PREVIEW_PASSWORD's hash goes to the deps chart only: helm_args is empty for a
    # preview, which refuses Helm arguments of its own.
    local password_args line
    password_args="$(preview_password_args)"
    while IFS= read -r line; do
        [ -z "$line" ] || helm_args+=("$line")
    done <<<"$password_args"
    cmd_infra
    helm_args=()
    cmd_app

    log "preview $NAMESPACE is up"
    printf 'APP_ORIGIN=%s\nOBJECT_STORE_ORIGIN=%s\n' "$APP_ORIGIN" "$OBJECT_STORE_ORIGIN"
}

cmd_preview_url() {
    preview_guard
    preview_tunnels_live "$PREVIEW_STATE" \
        || die "preview $NAMESPACE's tunnels are not running, or Cloudflare has dropped them — run scripts/deploy.sh preview up"
    printf 'APP_ORIGIN=%s\nOBJECT_STORE_ORIGIN=%s\n' \
        "$(cat "$PREVIEW_STATE/app.url")" "$(cat "$PREVIEW_STATE/s3.url")"
}

# Never creates or starts the cluster, and never touches keda or other namespaces.
cmd_preview_down() {
    preview_guard
    log "taking down preview $NAMESPACE"
    preview_stop_tunnels "$PREVIEW_STATE"
    if command -v k3d >/dev/null 2>&1 && cluster_exists; then
        require_cmd helm kubectl
        local release
        for release in "$APP_RELEASE" "$DEPS_RELEASE"; do
            if helm_ns status "$release" >/dev/null 2>&1; then
                helm_ns uninstall "$release" --wait
            fi
        done
        kubectl --context "$KUBE_CONTEXT" delete namespace "$NAMESPACE" --ignore-not-found --wait
    else
        log "no k3d cluster — only the tunnels and local state to remove"
    fi
    rm -rf "$PREVIEW_STATE"
}

command="${1:-up}"
[ $# -gt 0 ] && shift
preview_command=""
if [ "$command" = preview ]; then
    case "${1:-}" in
        up | url | down)
            preview_command="$1"
            shift
            ;;
        *) die "expected 'preview up', 'preview url' or 'preview down'" ;;
    esac
fi
helm_args=()
if [ "${1:-}" = -- ]; then
    shift
    helm_args=("$@")
elif [ $# -gt 0 ]; then
    die "unexpected argument '$1' (Helm arguments go after --)"
fi

case "$command" in
    up | cluster | infra | app | status | down | preview) ;;
    -h | --help)
        usage
        exit 0
        ;;
    *) die "unknown command '$command' (expected up, cluster, infra, app, status, down or preview)" ;;
esac

# Helm arguments belong to one chart. `up` installs two, and a credential for
# one would be silently ignored by the other.
if [ ${#helm_args[@]} -gt 0 ]; then
    case "$command" in
        infra | app) ;;
        preview) die "Helm arguments are not accepted by 'preview': it owns every value it sets" ;;
        *) die "Helm arguments go to 'infra' or 'app', not '$command'" ;;
    esac
fi

# Everything after -- lands after the context and namespace helm_ns sets, and
# Helm takes the last one given: these would carry a release past
# require_matching_context, onto whatever cluster they name.
for arg in ${helm_args[@]+"${helm_args[@]}"}; do
    case "$arg" in
        --kube-context | --kube-context=* | --namespace | --namespace=* | -n*)
            die "'$arg' cannot go to Helm — set KUBE_CONTEXT or NAMESPACE instead"
            ;;
    esac
done

# `cluster` and `down` concern only the k3d cluster, never an instance on it, so
# they neither need an origin nor should fail for the lack of one. `status` only
# reports the origin, so it runs without one where k3d's default does not apply.
case "$command" in
    cluster | down) ;;
    status)
        if [ -n "$APP_ORIGIN" ] || [ "$DEPLOY_ENV" = k3d ]; then
            resolve_origin
        fi
        ;;
    # A preview's origins are its tunnels', known only once they are up.
    preview) ;;
    *) resolve_origin ;;
esac
if [ "$command" = preview ]; then
    "cmd_preview_$preview_command"
else
    "cmd_$command"
fi
