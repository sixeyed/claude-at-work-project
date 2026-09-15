#!/usr/bin/env bash
# Run CollabHub's checks. Developers and CI run this same script.
#
#   scripts/test.sh                    lint, unit, then integration
#   scripts/test.sh lint unit          only these layers, in this order
#   scripts/test.sh unit -- -x -k auth anything after -- goes to pytest
#   scripts/test.sh all                every layer, e2e included — what CI runs
#   scripts/test.sh e2e -- --headed -k channels
#
#   lint         ruff, the CollabHub convention checks, eslint, tsc, helm lint
#   unit         pytest, nothing that needs Docker
#   integration  pytest against real containers — needs Docker
#   e2e          the Gherkin journeys in tests/bdd, in a real browser, against
#                the throwaway test stack it brings up and takes down — needs
#                Docker and .env. Not in the default run, because it is slow.
#
#   KEEP_STACK=1 leaves the e2e test stack running afterwards, for iterating on
#                steps. See "Acceptance tests" in README.md.
#
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

layers=()
pytest_args=()
while [ $# -gt 0 ]; do
    case "$1" in
        lint | unit | integration | e2e) layers+=("$1") ;;
        all) layers+=(lint unit integration e2e) ;;
        --)
            shift
            pytest_args=("$@")
            break
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) die "unknown layer '$1' (expected lint, unit, integration, e2e or all)" ;;
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

# The *test* stack, never the development one. The suite truncates the messaging
# tables before every scenario, so docker-compose.test.yml gives this stack its
# own project name, volumes and host ports, and it runs alongside a development
# stack without touching it.
E2E_COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.test.yml)
# No journey touches search yet, and two of everything is real memory on a
# laptop. Delete this line when a search journey lands: it needs both.
E2E_SCALE=(--scale elasticsearch=0 --scale worker=0)

e2e_down() {
    log "e2e: taking the test stack down (KEEP_STACK=1 leaves it up)"
    # `down`, not `down -v`: the suite truncates per scenario anyway, and keeping
    # the volume saves re-running every migration on the next run.
    "${E2E_COMPOSE[@]}" down ||
        log "e2e: teardown failed — check 'docker compose -p collabhub-test ps'"
}

# Runs when the script exits during the e2e layer — a failed `up`, a failed
# scenario, Ctrl-C. It takes the exit status first and exits with it again, so
# the teardown can neither hide a failure nor invent one.
e2e_on_exit() {
    local status=$?
    trap - EXIT
    e2e_down
    exit "$status"
}

layer_e2e() {
    require_cmd docker
    docker info >/dev/null 2>&1 || die "e2e tests need Docker, and the daemon is not reachable"
    [ -f .env ] ||
        die "e2e tests need .env at the repo root, which the Compose files read: cp .env.example .env"

    if [ "${KEEP_STACK:-}" = 1 ]; then
        log "e2e: KEEP_STACK=1 — the test stack stays up afterwards"
    else
        trap e2e_on_exit EXIT
    fi

    log "e2e: bringing the test stack up"
    # --wait holds until every container with a healthcheck is healthy, and the
    # frontend has one for exactly this reason. The timeout turns a container that
    # never gets there into a failure rather than a hung run.
    "${E2E_COMPOSE[@]}" up -d --build --wait --wait-timeout 300 "${E2E_SCALE[@]}"

    log "e2e: installing Chromium for Playwright"
    uv run playwright install chromium

    log "e2e tests"
    # Pointed at tests/bdd so the run does not collect every service's tests only
    # to deselect them. Under `set -e` a failure exits here, through the trap.
    uv run pytest tests/bdd -m bdd ${pytest_args[@]+"${pytest_args[@]}"}

    if [ "${KEEP_STACK:-}" != 1 ]; then
        trap - EXIT
        e2e_down
    fi
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
