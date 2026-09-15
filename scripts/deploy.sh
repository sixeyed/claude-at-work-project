#!/usr/bin/env bash
# Deploy CollabHub to a local k3d cluster with Helm. Developers and CI run this
# same script.
#
#   scripts/deploy.sh [up]     cluster, then infra, then app. Re-run to upgrade
#   scripts/deploy.sh cluster  create the k3d cluster and its image registry
#   scripts/deploy.sh infra    KEDA, then data stores, Dex, Secrets, Ingress (charts/collabhub-local)
#   scripts/deploy.sh app      CollabHub itself (charts/collabhub) at IMAGE_TAG
#   scripts/deploy.sh status   releases, pods and jobs
#   scripts/deploy.sh down     delete the cluster, its registry and all its data
#
# The images must already be in the registry — run scripts/build.sh --push
# first. CollabHub is then served at http://localhost:8080.
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

APP_RELEASE=collabhub
LOCAL_RELEASE=collabhub-local

# Every call names its context. A developer's current context may be a real
# cluster, and none of this should ever follow it there.
kube() { kubectl --context "$KUBE_CONTEXT" --namespace "$NAMESPACE" "$@"; }
helm_ns() { helm --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE" "$@"; }

is_local_cluster() { [ "$KUBE_CONTEXT" = "k3d-$K3D_CLUSTER" ]; }

# charts/collabhub-local carries throwaway credentials and a Dex full of demo
# accounts, and `down` deletes everything. Neither may touch a shared cluster.
require_local_cluster() {
    is_local_cluster || die "'$1' only targets the local k3d cluster, and KUBE_CONTEXT is '$KUBE_CONTEXT'"
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
    require_local_cluster infra
    require_cmd helm

    # A cluster add-on rather than part of either chart: charts/collabhub refuses
    # to render without the keda.sh/v1alpha1 API its Worker pools scale with.
    log "installing KEDA $KEDA_VERSION"
    helm --kube-context "$KUBE_CONTEXT" upgrade --install keda keda \
        --repo https://kedacore.github.io/charts --version "$KEDA_VERSION" \
        --namespace keda --create-namespace \
        --wait --timeout 10m

    log "installing $LOCAL_RELEASE — data stores, Dex, Secrets and Ingress"
    helm_ns upgrade --install "$LOCAL_RELEASE" "$REPO_ROOT/charts/collabhub-local" \
        --create-namespace \
        "${LOCAL_CHART_FILES[@]}" \
        --wait --timeout 10m
}

cmd_app() {
    require_cmd helm kubectl docker curl

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

    log "installing $APP_RELEASE at $IMAGE_TAG"
    helm_ns upgrade --install "$APP_RELEASE" "$REPO_ROOT/charts/collabhub" \
        --create-namespace \
        --values "$REPO_ROOT/charts/collabhub/values-k3d.yaml" \
        --set-string "image.registry=$IMAGE_REGISTRY" \
        --set-string "image.tag=$IMAGE_TAG" \
        --wait --timeout 10m

    # Every rebuild from one dirty commit reuses the same tag, so Helm sees an
    # unchanged pod spec and would leave the old pods running.
    if $upgrading && [[ "$IMAGE_TAG" == *-dirty ]]; then
        log "restarting workloads to pick up the rebuilt $IMAGE_TAG images"
        kube rollout restart deployment --selector "app.kubernetes.io/instance=$APP_RELEASE"
        kube rollout status deployment --selector "app.kubernetes.io/instance=$APP_RELEASE" --timeout 5m
    fi

    if is_local_cluster; then
        check_origin
    fi
}

# Through the Ingress, so this proves routing as well as the pods: the SPA, and
# Auth's JWKS, which every other service needs to verify a token.
check_origin() {
    local path
    for path in / /.well-known/jwks.json; do
        curl --fail --silent --show-error --output /dev/null \
            --retry 30 --retry-delay 2 --retry-all-errors \
            "$K3D_ORIGIN$path" || die "$K3D_ORIGIN$path is not answering"
    done
    log "CollabHub is up at $K3D_ORIGIN — sign in as ada@collabhub.dev with password collabhub"
}

cmd_status() {
    require_cmd helm kubectl
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

case "${1:-up}" in
    up | cluster | infra | app | status | down) "cmd_${1:-up}" ;;
    -h | --help) usage ;;
    *) die "unknown command '$1' (expected up, cluster, infra, app, status or down)" ;;
esac
