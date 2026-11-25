# Chore Tracker Helm chart

This chart deploys the Chore Tracker API and frontend to Kubernetes. It is
designed for a single-replica homelab deployment behind an existing Traefik
ingress and wildcard TLS certificate.

The chart uses the images built from the repository Dockerfiles:

- Backend: FastAPI, Uvicorn, Alembic, and the SQLite database.
- Frontend: nginx serving the built React application and proxying `/api` to the
  backend Service.

The chart does not create or render secret material. When SMTP authentication
is enabled, it can mount an existing Kubernetes Secret containing the SMTP
password.

## Prerequisites

- Kubernetes 1.25 or newer.
- Helm 3.12 or newer (Helm 4 is also supported).
- A default StorageClass, or an existing ReadWriteOnce PVC.
- Images available to the cluster. Build and push the repository images first:

```bash
docker build -t registry.example.test/chore-tracker-backend:0.1.0 .
docker build -t registry.example.test/chore-tracker-frontend:0.1.0 frontend
docker push registry.example.test/chore-tracker-backend:0.1.0
docker push registry.example.test/chore-tracker-frontend:0.1.0
```

Use `registry.example.test` only as a placeholder. For a private registry, add
the pull secret through `imagePullSecrets` in your values file.

## Create the namespace and secret

```bash
kubectl create namespace chore-tracker

# Only needed when SMTP authentication uses a password.
kubectl --namespace chore-tracker create secret generic chore-tracker-smtp \
  --from-file=smtp-password=/path/to/smtp-password
```

The chart mounts the `smtp-password` key as
`/run/secrets/smtp_password` and sets
`CHORE_TRACKER_SMTP_PASSWORD_FILE` when an SMTP host is configured. Set
`secrets.existingSecret` to `chore-tracker-smtp`, or leave it empty when email
is disabled or SMTP authentication is not used. Never commit the password or a
values file containing secret material. After rotating the Secret, restart the
backend so it reads the new file:

```bash
kubectl --namespace chore-tracker rollout restart deployment/chore-tracker-backend
```

## Configure values

Start from an environment-specific values file. Do not edit the chart defaults
with cluster-specific names.

```yaml
# my-values.yaml
backend:
  image:
    repository: registry.example.test/chore-tracker-backend
    tag: "0.1.0"
frontend:
  image:
    repository: registry.example.test/chore-tracker-frontend
    tag: "0.1.0"

ingress:
  host: chores.example.test
  tls:
    secretName: wildcard-example-tls
  # Keep the existing Traefik IngressClass or select another one.
  className: traefik

config:
  environment: production
  reportTimezone: America/Denver

persistence:
  storageClassName: local-path
  size: 1Gi
```

Email delivery is optional and disabled by default. To enable SMTP delivery,
add the SMTP settings to the values file:

```yaml
config:
  emailTransport: smtp
  emailFromAddress: chores@example.test
  smtpHost: mail.example.test
  smtpPort: 587
  smtpUsername: mailer

secrets:
  existingSecret: chore-tracker-smtp
```

Leave the email values empty to run without email. Supplying the SMTP host and
sender is enough to enable SMTP; `emailTransport` is only needed to select
`console` explicitly. Incomplete or conflicting settings stop startup with an
error naming the variables to fix, and the backend logs the resolved state at
startup.

The publish workflow builds both images for `linux/amd64` and `linux/arm64` and
pushes them to GitHub Container Registry as
`ghcr.io/lightguard/chore-tracker-backend` and
`ghcr.io/lightguard/chore-tracker-frontend`. Use those repositories with a
release tag (for example `"1.2.3"`) instead of a private registry path. The
chart defaults (`chore-tracker-backend:local` and
`chore-tracker-frontend:local`) refer to images built locally, so they only work
on a cluster that can pull from the machine that built them.

`config.appOrigin`, `config.passkeyOrigin`, and `config.passkeyRpId` are derived
from `ingress.host` and `ingress.tls.enabled`. Set them explicitly only when
ingress is disabled or an external proxy terminates TLS:

```yaml
config:
  appOrigin: https://chores.example.test
  passkeyOrigin: https://chores.example.test
  passkeyRpId: chores.example.test
ingress:
  enabled: false
```

The application's production mode requires HTTPS origins and a non-localhost
passkey relying-party ID. Email delivery is optional and disabled by default.
The backend logs whether email delivery is disabled, uses the console transport,
or uses SMTP at startup. For a non-TLS test cluster, use `development` instead.

## Install or upgrade

```bash
helm upgrade --install chore-tracker ./deploy/kubernetes/chore-tracker \
  --namespace chore-tracker \
  --values my-values.yaml \
  --wait \
  --timeout 5m
```

A Kubernetes init container runs `alembic upgrade head` before the backend
starts. The backend readiness probe calls `GET /health/ready`; the liveness
probe calls `GET /health/live` and is independent of SQLite. Readiness returns
HTTP 503 until the database is accessible and at the current migration head. If
the backend pod does not start, inspect the migration container:

```bash
kubectl --namespace chore-tracker logs deployment/chore-tracker-backend -c migrate
```

## Verify startup and persistence

```bash
kubectl --namespace chore-tracker get pods,pvc,service,ingress
kubectl --namespace chore-tracker rollout status deployment/chore-tracker-backend
kubectl --namespace chore-tracker exec deployment/chore-tracker-backend -- \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').read().decode())"
curl --fail --show-error https://chores.example.test/health/ready
```

To prove the volume survives pod replacement, write a sentinel into SQLite,
delete the backend pod, wait for the replacement, and read it again:

```bash
kubectl --namespace chore-tracker exec -i deployment/chore-tracker-backend -- python - <<'PY'
import sqlite3

with sqlite3.connect("/data/chore-tracker.db") as connection:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS kubernetes_smoke_test ("
        "id INTEGER PRIMARY KEY, note TEXT NOT NULL)"
    )
    connection.execute("DELETE FROM kubernetes_smoke_test")
    connection.execute(
        "INSERT INTO kubernetes_smoke_test (note) VALUES ('persisted')"
    )
PY

kubectl --namespace chore-tracker delete pod \
  -l app.kubernetes.io/component=backend
kubectl --namespace chore-tracker rollout status deployment/chore-tracker-backend

kubectl --namespace chore-tracker exec -i deployment/chore-tracker-backend -- python - <<'PY'
import sqlite3

with sqlite3.connect("/data/chore-tracker.db") as connection:
    row = connection.execute("SELECT note FROM kubernetes_smoke_test").fetchone()
assert row == ("persisted",), row
PY
```

The new pod runs the migration init container again; the sentinel must still be
present. Remove the test table when finished.

## Ingress and TLS

The chart creates a standard `networking.k8s.io/v1` Ingress and only routes to
the frontend Service. The frontend nginx proxies `/api` and `/health` to the
backend Service using the `API_UPSTREAM` environment variable.

Set `ingress.className` to the existing Traefik IngressClass (default
`traefik`) and `ingress.tls.secretName` to the existing wildcard certificate
Secret. No namespace, hostname, certificate name, or Traefik middleware name is
hard-coded in the templates. Add any required Traefik annotations through
`ingress.annotations`.

If a separate proxy terminates TLS before Traefik, disable `ingress.tls` and
set the external HTTPS origins explicitly as shown above.

## SQLite, backups, and rollback

The backend intentionally runs with exactly one replica and the `Recreate`
strategy. SQLite allows only one writer; do not add a HorizontalPodAutoscaler
or scale the backend Deployment above one. The PVC must remain ReadWriteOnce.
The frontend is stateless and may be scaled by setting
`frontend.replicaCount`.

Back up the database before every upgrade or rollback. A safe online backup uses
SQLite's backup API:

```bash
pod="$(kubectl --namespace chore-tracker get pod \
  -l app.kubernetes.io/component=backend \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl --namespace chore-tracker exec -i "${pod}" -- python - <<'PY'
import sqlite3

source = sqlite3.connect("/data/chore-tracker.db")
target = sqlite3.connect("/tmp/chore-tracker-backup.db")
source.backup(target)
target.close()
source.close()
PY

kubectl --namespace chore-tracker cp \
  "${pod}:/tmp/chore-tracker-backup.db" ./chore-tracker-backup.db
```

PVC snapshots are also suitable when the StorageClass supports them. A cold
copy after scaling the backend to zero is acceptable for a small homelab, but
the online backup above avoids downtime.

For verified backup and restore procedures, including the temporary restore pod
and the tested host-level verification script, see
[Backup and restore](../../../docs/backup-restore.md#kubernetes). For
administrator setup, rollover recovery, and upgrade guidance, see
[Operations](../../../docs/operations.md).

Helm does not own the database schema. A `helm rollback` rolls back Kubernetes
objects, not the SQLite schema. Migrations are forward-only; after a schema
change, an older image may fail its migration init container or readiness check
against the newer database. Restore the pre-upgrade backup, or deploy an image
that understands the current schema. Practice the recovery path on a test
cluster.

`helm uninstall` removes the chart-managed PVC and its data. For data that must
survive an uninstall, create the PVC separately and set
`persistence.existingClaim`.

### Rollback commands

```bash
helm --namespace chore-tracker history chore-tracker
helm --namespace chore-tracker rollback chore-tracker <revision>
kubectl --namespace chore-tracker rollout status deployment/chore-tracker-backend
```

Take a backup first, then verify readiness and the database after the rollback.

## Resource sizing

Defaults are deliberately conservative for a low-memory NUC:

| Component | CPU request | Memory request | CPU limit | Memory limit |
| --- | --- | --- | --- | --- |
| Backend | 50m | 128Mi | 500m | 512Mi |
| Frontend | 10m | 32Mi | 200m | 128Mi |

Override `backend.resources` and `frontend.resources` for the actual node. The
backend needs enough memory for Python, Uvicorn, and the SQLite page cache; the
frontend is mostly static nginx. Add `nodeSelector`, `tolerations`, or
`affinity` through the matching values when the homelab needs scheduling
constraints.

## Lint and schema validation

The repository's `kubernetes` CI job installs Helm and `kubeconform`, then runs:

```bash
./scripts/kubernetes-manifest-test.sh
```

The script lints the chart, renders the default, smoke, secret, no-ingress,
existing-PVC, and no-TLS variants, checks the single-replica/probe invariants,
and validates every object against the upstream Kubernetes schemas. Install
`kubeconform` locally and pass `KUBECONFORM=/path/to/kubeconform` if it is not
on `PATH`.

## Test-cluster procedure

A disposable cluster can validate startup, persistence, and probes without
touching the homelab:

```bash
kind create cluster --name chore-tracker-test

docker build -t chore-tracker-backend:local .
docker build -t chore-tracker-frontend:local frontend
kind load docker-image chore-tracker-backend:local --name chore-tracker-test
kind load docker-image chore-tracker-frontend:local --name chore-tracker-test

helm upgrade --install chore-tracker ./deploy/kubernetes/chore-tracker \
  --namespace chore-tracker --create-namespace \
  --values deploy/kubernetes/chore-tracker/values.smoke.yaml \
  --set ingress.enabled=false \
  --wait --timeout 5m

kubectl --namespace chore-tracker port-forward service/chore-tracker-frontend 8080:80
# In another terminal:
curl --fail http://localhost:8080/health/ready
curl --fail http://localhost:8080/healthz
```

Then run the sentinel persistence test above. To validate ingress and TLS,
install Traefik in the test cluster and use a disposable self-signed secret:

```bash
host=chore-tracker.127.0.0.1.nip.io

openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout /tmp/chore-tracker-test.key \
  -out /tmp/chore-tracker-test.crt \
  -days 1 -subj "/CN=${host}" \
  -addext "subjectAltName=DNS:${host}"
kubectl --namespace chore-tracker create secret tls chore-tracker-test-tls \
  --cert=/tmp/chore-tracker-test.crt \
  --key=/tmp/chore-tracker-test.key

helm repo add traefik https://traefik.github.io/charts
helm repo update
helm install traefik traefik/traefik --namespace traefik --create-namespace \
  --set ingressClass.enabled=true --wait --timeout 5m

helm upgrade --install chore-tracker ./deploy/kubernetes/chore-tracker \
  --namespace chore-tracker \
  --values deploy/kubernetes/chore-tracker/values.smoke.yaml \
  --set ingress.enabled=true \
  --set ingress.className=traefik \
  --set ingress.host="${host}" \
  --set ingress.tls.enabled=true \
  --set ingress.tls.secretName=chore-tracker-test-tls \
  --set config.appOrigin="https://${host}" \
  --set config.passkeyOrigin="https://${host}" \
  --set config.passkeyRpId="${host}" \
  --wait --timeout 5m

kubectl --namespace traefik port-forward service/traefik 18443:443
# In another terminal:
curl -kfsS --resolve "${host}:18443:127.0.0.1" \
  "https://${host}:18443/health/ready"
curl -kfsS --resolve "${host}:18443:127.0.0.1" \
  "https://${host}:18443/api/family-members/active"
```

The chart intentionally does not install an ingress controller. The commands
above are only for a disposable test cluster; the homelab chart should point at
its existing Traefik IngressClass and wildcard TLS Secret.

## Values reference

| Value | Default | Purpose |
| --- | --- | --- |
| `backend.image.repository` / `tag` | `chore-tracker-backend:local` | Backend image, or `ghcr.io/lightguard/chore-tracker-backend` |
| `frontend.image.repository` / `tag` | `chore-tracker-frontend:local` | Frontend image, or `ghcr.io/lightguard/chore-tracker-frontend` |
| `imagePullSecrets` | `[]` | Private registry pull secrets |
| `persistence.existingClaim` | `""` | Use an existing ReadWriteOnce PVC |
| `persistence.storageClassName` | `""` | StorageClass for the managed PVC |
| `persistence.size` | `1Gi` | Requested SQLite volume size |
| `config.environment` | `production` | Application environment |
| `config.reportTimezone` | `America/Denver` | Reporting timezone |
| `config.emailTransport` | `""` | `""` (disabled), `console`, or `smtp` |
| `config.emailFromAddress` | `""` | Sender address; with `smtpHost`, enables SMTP |
| `config.smtpHost` | `""` | SMTP host; with `emailFromAddress`, enables SMTP |
| `config.smtpPort` | `587` | SMTP port |
| `config.smtpUsername` | `""` | Optional SMTP username; pair with the secret |
| `config.smtpStarttls` | `true` | Enable STARTTLS for SMTP |
| `config.extraEnv` | `{}` | Extra non-secret environment variables |
| `secrets.existingSecret` | `""` | Secret containing the SMTP password, when SMTP authentication uses one |
| `secrets.smtpPasswordKey` | `smtp-password` | Key in the existing Secret |
| `ingress.enabled` | `true` | Create the Ingress |
| `ingress.className` | `traefik` | Existing IngressClass |
| `ingress.host` | `chore-tracker.example.test` | Browser-facing hostname |
| `ingress.tls.enabled` | `true` | Add TLS to the Ingress |
| `ingress.tls.secretName` | `wildcard-example-tls` | Existing wildcard TLS Secret |
| `ingress.annotations` | `{}` | Traefik or environment annotations |
| `backend.resources` | see above | Backend requests and limits |
| `frontend.resources` | see above | Frontend requests and limits |
| `frontend.replicaCount` | `1` | Stateless frontend replicas |
