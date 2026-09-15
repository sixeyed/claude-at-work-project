#!/usr/bin/env bash
# Run CollabHub's checks. Developers and CI run this same script.
#
#   scripts/test.sh                    lint, unit, then integration
#   scripts/test.sh lint unit          only these layers, in this order
#   scripts/test.sh unit -- -x -k auth anything after -- goes to pytest
#
#   lint         ruff, the CollabHub convention checks, eslint, tsc, helm lint
#   unit         pytest, nothing that needs Docker
#   integration  pytest against real containers — needs Docker
#
# The Gherkin suite in tests/bdd is not run here: it needs its own stack brought
# up first. See "Acceptance tests" in README.md.
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

layers=()
pytest_args=()
while [ $# -gt 0 ]; do
    case "$1" in
        lint | unit | integration) layers+=("$1") ;;
        all) layers+=(lint unit integration) ;;
        --)
            shift
            pytest_args=("$@")
            break
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) die "unknown layer '$1' (expected lint, unit, integration or all)" ;;
    esac
    shift
done
[ ${#layers[@]} -gt 0 ] || layers=(lint unit integration)

require_cmd uv
cd "$REPO_ROOT"

ensure_node_modules() {
    # CI always installs clean; a developer's existing install is trusted.
    if [ -n "${CI:-}" ] || [ ! -d src/frontend/node_modules ]; then
        log "installing frontend dependencies"
        (cd src/frontend && npm ci)
    fi
}

layer_lint() {
    require_cmd npm helm git python3

    log "lint: ruff"
    uv run ruff check .
    uv run ruff format --check .

    log "lint: CollabHub conventions"
    # With no arguments conventions.py checks only what differs from HEAD, which
    # in a CI checkout is nothing — so hand it every tracked Python file.
    git ls-files -z '*.py' | xargs -0 python3 .claude/hooks/checks/conventions.py

    log "lint: frontend"
    ensure_node_modules
    (cd src/frontend && npm run --silent lint && npm run --silent typecheck)

    log "lint: helm"
    # values.yaml leaves the NetworkPolicy peers to each environment and fails the
    # render without them, and `helm lint` cannot be told the KEDA API exists. So
    # the defaults lint with both of those off, the k3d values lint with
    # autoscaling off, and the k3d values render once more with the KEDA API
    # declared, so the ScaledObjects are checked too.
    helm lint --quiet charts/collabhub \
        --set networkPolicy.enabled=false \
        --set components.worker.autoscaling.enabled=false
    helm lint --quiet charts/collabhub --values charts/collabhub/values-k3d.yaml \
        --set components.worker.autoscaling.enabled=false
    helm template collabhub charts/collabhub --values charts/collabhub/values-k3d.yaml \
        --api-versions keda.sh/v1alpha1 >/dev/null
    helm lint --quiet charts/collabhub-local "${LOCAL_CHART_FILES[@]}"
}

layer_unit() {
    log "unit tests"
    uv run pytest -m unit --cov --cov-report=term:skip-covered --cov-report=xml \
        ${pytest_args[@]+"${pytest_args[@]}"}
}

layer_integration() {
    require_cmd docker
    docker info >/dev/null 2>&1 || die "integration tests need Docker, and the daemon is not reachable"
    log "integration tests"
    uv run pytest -m integration ${pytest_args[@]+"${pytest_args[@]}"}
}

log "syncing the Python workspace"
# --all-packages, because a plain sync installs only the root's dev group, not
# each member's. Messaging's dev group is where the Socket.IO async client and
# aiohttp come from, and without them its real-time tests fail to connect.
uv sync --locked --all-packages --quiet

for layer in "${layers[@]}"; do
    "layer_$layer"
done

log "passed: ${layers[*]}"
