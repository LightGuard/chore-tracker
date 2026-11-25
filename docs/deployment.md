# Deployment

Chore Tracker ships with two deployment paths:

- **Docker Compose** for a local or small homelab install.
- **Kubernetes** through the Helm chart in
  [`deploy/kubernetes/chore-tracker`](../deploy/kubernetes/chore-tracker/README.md).

Both run the same images:

- **Backend** - FastAPI, Uvicorn, Alembic, and SQLite.
- **Frontend** - nginx serving the built React application and proxying `/api`
  and `/health` to the backend.

The backend is intentionally single-instance because SQLite has one writer and
the API process owns the weekly rollover. Neither deployment path supports
multi-replica backend scaling.

Tilt is a separate local development workflow that runs host processes. It is
not a deployment path; see [Development](development.md#tilt-workflow).

## Docker Compose

Production-style images and a Compose deployment are included. The backend image
installs the exact versions in `uv.lock`; the frontend image installs the exact
versions in `package-lock.json` and serves the built static application through
nginx.

The deployment requires Docker Engine with Compose v2, or a compatible Podman
and Compose installation.

### Start the deployment

Copy the Docker environment example, review the public origin, and start:

```bash
cp .env.docker.example .env.docker
docker compose --env-file .env.docker up --detach --build
```

Open `http://localhost:8080`. The default is suitable for local Docker use;
WebAuthn treats `localhost` as a secure origin.

The one-shot `migrate` service runs `alembic upgrade head` before the API starts.
The backend waits for that service to complete successfully, and the frontend
waits for the backend readiness check. The application never migrates
automatically during startup. Check progress with:

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --follow backend
```

By default the frontend binds to `127.0.0.1:8080`. Set
`CHORE_TRACKER_BIND_ADDRESS=0.0.0.0` in `.env.docker` to publish on the LAN, and
set `CHORE_TRACKER_PUBLIC_ORIGIN` to the exact origin browsers use. Put a
TLS-terminating reverse proxy in front of the deployment for any non-local
hostname; WebAuthn requires HTTPS outside `localhost`.

### Stop the deployment and keep data

```bash
docker compose --env-file .env.docker down
```

This removes the containers and network but keeps the named
`chore-tracker-data` volume. Starting again with the command above reuses the
same database. `docker compose --env-file .env.docker down --volumes` also
deletes the volume and all stored data; use it only when intentionally resetting
the deployment.

SQLite is stored at `/data/chore-tracker.db` on the volume, never in the image
or the writable container layer. The `migrate` and `backend` containers run as
UID/GID `10001` and share the volume. The frontend nginx container runs as its
unprivileged image user. Only the frontend publishes a host port; the API is
reachable only through the internal Compose network.

### Runtime configuration and secrets

Application settings are read from `.env.docker` at runtime through the Compose
`env_file` mechanism. Container-specific values are fixed by `compose.yaml`:
the API binds `0.0.0.0:8000`, SQLite uses `/data/chore-tracker.db`, and the
application and passkey origins use `CHORE_TRACKER_PUBLIC_ORIGIN`. Other
`CHORE_TRACKER_*` settings in the file, including optional SMTP configuration
and the reporting timezone, are passed through.

`CHORE_TRACKER_PUBLIC_ORIGIN`, `CHORE_TRACKER_BIND_ADDRESS`,
`CHORE_TRACKER_HTTP_PORT`, and `CHORE_TRACKER_PASSKEY_RP_ID` are Compose
deployment values. `VITE_API_BASE_URL` is a public build argument fixed to
`/api`; never put secrets in `VITE_*` values because they are compiled into
browser assets.

Secrets are injected at runtime and are not copied into either image. The root
`.dockerignore` and `frontend/.dockerignore` exclude environment files. When
email delivery is enabled, prefer a mounted SMTP password file over a password
environment variable. Compose automatically reads a local
`compose.override.yaml`; for example:

```yaml
services:
  backend:
    environment:
      CHORE_TRACKER_SMTP_PASSWORD_FILE: /run/secrets/smtp_password
    volumes:
      - ./secrets/smtp_password:/run/secrets/smtp_password:ro
```

Create the file with permissions readable by UID `10001`, then start normally
with the same `--env-file` command. Do not commit the override file or its
secret. `.env.docker.example` also documents the SMTP settings.

Email delivery is optional. Leave the SMTP settings unset to run without email;
supplying the SMTP host and sender enables SMTP automatically. Invalid or
incomplete email settings stop startup with a clear error, and the backend logs
the resolved state at startup. The MVP does not send weekly report email. See
[Known limitations](operations.md#known-limitations).

For a production-style deployment, terminate TLS before the frontend, set
`CHORE_TRACKER_ENVIRONMENT=production`, use HTTPS application and passkey
origins, and set a real passkey relying-party domain. Email settings are
optional in production but are validated when supplied. The application rejects
development-only production configuration at startup.

### Health checks

The backend image's Docker `HEALTHCHECK` calls `GET /health/live`, which reports
process liveness without touching SQLite. Compose overrides the backend check
with `GET /health/ready` so dependent services wait for an accessible database
upgraded to the current Alembic head. The frontend health check calls
`GET /healthz` and does not depend on the API. The published frontend also
proxies `/health` and `/health/*` to the API for smoke tests and monitoring.

```bash
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
curl http://localhost:8080/healthz
```

Liveness returns HTTP 200 while the process is running. Readiness returns HTTP
200 with `{"status":"ok"}` only after migrations are current, and HTTP 503 with
`{"status":"not_ready"}` otherwise.

### Container smoke test

Run the same end-to-end check used by CI:

```bash
./scripts/compose-smoke-test.sh
```

The script builds both images, starts an isolated Compose project, verifies
liveness, readiness, the frontend, and the API proxy, checks that the application
containers are non-root, writes a sentinel to the volume, restarts the
deployment, and verifies the sentinel survived. It removes its own volume on
exit. Set `CHORE_TRACKER_HTTP_PORT` if port 8080 is already in use. Set
`DOCKER_COMPOSE` when the Compose command is not `docker compose`, for example
`DOCKER_COMPOSE="podman compose"`.

### Backups

See [Backup and restore](backup-restore.md#docker-compose) for live backup and
restore commands against the named volume. Take a backup before every upgrade.

## Publishing release images

Pushing a version tag builds both Dockerfiles and publishes them to the GitHub
Container Registry. The
[publish workflow](../.github/workflows/publish-images.yml) runs for tags such
as `v1.2.3`, which match `v*.*.*`:

```bash
git tag v1.2.3
git push origin v1.2.3
```

It publishes two images for `linux/amd64` and `linux/arm64`:

- `ghcr.io/lightguard/chore-tracker-backend` from `Dockerfile`
- `ghcr.io/lightguard/chore-tracker-frontend` from `frontend/Dockerfile`

Each image gets the exact version as its tag (`1.2.3`), a moving minor tag
(`1.2`), and `latest`. A prerelease tag such as `v1.2.3-rc.1` is published as
`1.2.3-rc.1` only, so `latest` and the moving minor tag never point at an
unfinished build. Because the tag push is the only trigger, publishing a GitHub
Release for that tag does not build a second time; re-run the workflow from the
Actions tab to rebuild an existing tag.

The workflow authenticates with the repository `GITHUB_TOKEN` and needs no
repository secrets. Publishing from a workflow links each package to this
repository automatically, so both images appear under **Packages** in the
repository sidebar and inherit its permissions. Package visibility is separate
from repository visibility and starts private: set it to public in the package
settings if the images must be pullable without credentials. Otherwise the
cluster needs a read token in the chart's `imagePullSecrets`, because a
`GITHUB_TOKEN` from a workflow expires with the run.

If either image name was pushed by hand before the first workflow run, link that
existing package to this repository first. The workflow's `GITHUB_TOKEN` can
only push to a package that is connected to this repository.

Pull an image directly:

```bash
docker pull ghcr.io/lightguard/chore-tracker-backend:1.2.3
```

To deploy a published build, point the Helm chart at it:

```bash
helm upgrade --install chore-tracker deploy/kubernetes/chore-tracker \
  --namespace chore-tracker \
  --values my-values.yaml \
  --set backend.image.repository=ghcr.io/lightguard/chore-tracker-backend \
  --set backend.image.tag=1.2.3 \
  --set frontend.image.repository=ghcr.io/lightguard/chore-tracker-frontend \
  --set frontend.image.tag=1.2.3
```

The Compose deployment in this repository still builds from source and is not
affected by the published images.

## Kubernetes

The Helm chart for the homelab Traefik environment is in
[`deploy/kubernetes/chore-tracker`](../deploy/kubernetes/chore-tracker). It
deploys the backend and frontend images, migrates SQLite in an init container,
persists the database on a ReadWriteOnce volume, and configures liveness and
readiness probes against `/health/live` and `/health/ready`.

The chart takes the IngressClass, hostname, wildcard TLS Secret, image
repository, storage class, secrets, and resource requests/limits as values; it
does not install an ingress controller or create secret material. The backend
is deliberately limited to one replica with the `Recreate` strategy because
SQLite supports one writer.

A quick install looks like:

```bash
helm upgrade --install chore-tracker ./deploy/kubernetes/chore-tracker \
  --namespace chore-tracker --create-namespace \
  --values my-values.yaml --wait --timeout 5m
```

See the [chart README](../deploy/kubernetes/chore-tracker/README.md) for:

- image publishing and registry options;
- namespace/Secret creation;
- environment-specific values;
- the disposable test-cluster procedure;
- ingress and TLS;
- online backup, rollout, and rollback;
- resource sizing and the values reference.

The `kubernetes` CI job lints the chart and validates all rendered objects with
`kubeconform`:

```bash
./scripts/kubernetes-manifest-test.sh
```

Migrations run in the chart's init container before the backend starts. If the
backend pod does not start, inspect the migration container:

```bash
kubectl --namespace chore-tracker logs deployment/chore-tracker-backend -c migrate
```

For database backup and restore in Kubernetes, see
[Backup and restore](backup-restore.md#kubernetes). For upgrade and rollback
behavior, see [Upgrades and migrations](operations.md#upgrades-and-migrations).

## Choosing a deployment

| Need | Recommendation |
| --- | --- |
| Local development with hot reload | Host processes or Tilt; see [Development](development.md) |
| Single host, simple install | Docker Compose |
| Homelab with Traefik, TLS, and persistent storage | Helm chart |
| Multiple backend replicas or zero-downtime backend deploys | Not supported with SQLite; see [Known limitations](operations.md#known-limitations) |

## Production checklist

- [ ] TLS terminates in front of the frontend, and the browser origin is HTTPS.
- [ ] `CHORE_TRACKER_ENVIRONMENT=production`.
- [ ] `CHORE_TRACKER_APP_ORIGIN` and `CHORE_TRACKER_PASSKEY_ORIGIN` are the exact
      HTTPS origin.
- [ ] `CHORE_TRACKER_PASSKEY_RP_ID` is the real hostname, not `localhost`.
- [ ] Email delivery is intentionally disabled, or the SMTP settings are valid
      (the backend logs the resolved state at startup).
- [ ] The database is on a persistent volume, and the volume is backed up.
- [ ] Exactly one backend process/replica runs against the database.
- [ ] Readiness and liveness checks are wired to monitoring.
- [ ] The first administrator is claimed and the second administrator is
      enrolled as a recovery path.
- [ ] The restore procedure has been practiced on a test cluster or with the
      verification script.
