# Local Kubernetes on k3d with a dev-only dependency chart

- **Status:** Accepted
- **Date:** 2026-09-14

## Context

CollabHub deploys to Kubernetes with one Helm chart, `charts/collabhub`, and that
chart deliberately deploys only CollabHub's own workloads. Postgres, Redis,
Elasticsearch and Garage are expected to exist already, because bundling them
would make `helm uninstall` a data-loss command. The chart has no Secrets either —
components name theirs in `envFromSecrets` — and no Ingress, because routing is
per-environment and `/api/v1/internal/` must never be public (Conventions §5.5).

As a result the chart had never been installed anywhere. There was no environment
that supplied what it expects, so nobody knew whether its migration story, image
references or security contexts worked. Locally, everything ran on Docker Compose,
which exercises the images but not the chart.

A deploy script needed a real target, and it had to be one a developer could run
on a laptop and CI could run on a runner. Two settled decisions constrain it.
Register D22 puts the refresh token in a `SameSite=Strict` cookie, so the SPA and
the API must be same-site. Register D5 makes Auth federate to an upstream IdP, so
the environment needs Dex with an issuer URL the browser and Auth agree on.
`docs/platform/versions.md` pins Kubernetes to the 1.36 track and pins every
platform image.

## Decision

We will deploy locally to a **k3d cluster**, created by `scripts/deploy.sh` from
`scripts/k3d/cluster.yaml` with k3s pinned to `v1.36.4-k3s1`. The environment
around the app comes from a second chart, **`charts/collabhub-local`**, which is
development only and is never installed anywhere else.

- **Cluster.** k3d creates a registry on `localhost:5500` alongside the cluster,
  with a mirror so the same image name works for the host pushing and the node
  pulling. Creating the cluster never switches the developer's kubectl context, and
  every script call names `k3d-collabhub` explicitly.
- **Dependencies.** The local chart runs Postgres, three Redis instances,
  Elasticsearch, Garage, Dex and the OTel collector as plain manifests, using the
  same pinned images as `docker-compose.yml`. Repo files it needs — the Postgres
  init SQL, `garage.toml` and the collector config — arrive with `--set-file`
  rather than as copies. A post-install Job bootstraps Garage through its admin
  API: layout, bucket, key and grant.
- **Secrets.** It renders the `collabhub-<component>` Secrets the app chart names.
  Auth's RS256 signing key is generated in the chart and kept across upgrades with
  `lookup`, so both Auth replicas sign with one key.
- **One origin.** A Traefik Ingress serves the SPA, the public API prefixes and
  Dex from `http://localhost:8080`. That satisfies D22 with no CORS at all, and
  nothing routes `/api/v1/internal/`.

The app chart gained what its first install needed: a release-wide `image.registry`
and `image.tag`, migration Jobs for Auth and Messaging as `pre-install,pre-upgrade`
hooks (with `RUN_MIGRATIONS` off in the pods, as the entrypoints always
prescribed), and `values-k3d.yaml`. Gaps an install finds get fixed in that chart,
never worked around in the local one.

## Consequences

The app chart is now installed and exercised on every deploy, including multiple
replicas of Auth and Messaging, migrations as a release step, and the chart's
non-root security contexts. What `charts/collabhub-local` provides is also a
working checklist of what a real environment must supply.

Versions stay single-sourced. The local chart uses the images `versions.md` pins,
so the stack-update checker's watermarks cover it with no second list.

Some configuration is now duplicated on purpose. The local chart's credentials
repeat `.env.example`, which cannot be read directly because it carries Compose
hostnames and `$$` escaping. Dex's config is a third copy beside
`docker/dex/config.yaml` and `config.test.yaml`, because Dex reads its issuer and
redirect URIs only from its file. All three must change together.

The frontend image is environment-specific: the `VITE_*` URLs are inlined at build
time, and `build.sh` defaults them to the k3d origin.

Traefik balances across pods itself and ignores anything a Service says about
affinity. Since Socket.IO became WebSocket-only (register D30) that costs nothing —
a connection stays on the pod it reached. When Canvas gains real-time it will also
want `/socket.io`, which Messaging already holds on this origin.

The environment also has to satisfy what the app chart asks of every environment:
KEDA installed for the Worker pools, and NetworkPolicy peers that are actually
right, because k3s enforces NetworkPolicy. `deploy.sh infra` installs KEDA pinned
to `versions.md`, and `values-k3d.yaml` names each peer — Traefik as the ingress
controller, and the local chart's pods for everything else.

The environment is heavy. With Elasticsearch included, running k3d beside the
Compose development stack is two of everything. `deploy.sh down` deletes all data
by design.

## Alternatives Considered

### Community Helm charts for the dependencies

Installing Bitnami's PostgreSQL and Redis charts, ECK for Elasticsearch and
`dex/dex` would mean far less YAML to own. But each chart brings its own images and
version cadence, which would drift from `versions.md` and from Compose, and
Bitnami's image distribution changed in 2025 in a way that makes it an unreliable
default. The local chart's manifests are simple because they only ever serve one
laptop.

### Pointing k3d workloads at the Compose data stores

Running only CollabHub's workloads in k3d, and reaching Postgres, Redis and Dex in
Compose through `host.k3d.internal`, would add the least new infrastructure. It
would not be a self-contained environment CI could create and discard, and Dex's
issuer would have to be an address that both the browser and pods inside the
cluster resolve identically, which is where this approach gets fiddly.

### Compose as the only deploy target

Treating `docker compose up` as "deploy" would have been easy, but it would leave
the Helm chart — the thing that actually ships — untested until the first real
environment.

### kind, minikube or Docker Desktop's Kubernetes

k3d runs k3s in Docker, starts in seconds, comes with Traefik and a load balancer,
and creates a registry with the cluster from one config file. kind needs an
ingress controller and registry wiring added by hand. minikube and Docker Desktop's
built-in cluster are harder to pin to a Kubernetes version and harder to create
and destroy from a script CI can also run.
