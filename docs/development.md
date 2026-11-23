# Development

This guide takes a clean checkout to a running local application and then
explains the configuration, Tilt workflow, and quality gates. For how the
application is put together, see [Architecture](architecture.md).

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| Python | 3.15 or newer, below 4.0 | Backend, migrations, scripts |
| Node.js | 22 or newer | Frontend, unit tests, browser tests |
| npm | 10 or newer | Frontend dependency installation |
| Tilt | Current release | Optional all-in-one local environment |
| Docker Engine with Compose v2, or Podman with Compose | Current release | Optional Compose smoke test and local containers |
| Helm | 3.12 or newer (Helm 4 also works) | Optional chart linting |
| `kubeconform` | 0.6.7 or compatible | Optional Kubernetes schema validation |
| Chromium | Installed by Playwright | Optional browser tests |

Docker, Kubernetes, Helm, and Tilt are not required to run the application
locally. The default workflow runs both services as host processes.

## Clean checkout setup

The application database is created by Alembic, not by application startup.
Run the migration step before starting the API so readiness checks succeed.

### Backend

```bash
python3.15 -m venv .venv
source .venv/bin/activate
# On Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
alembic upgrade head
python -m chore_tracker
```

The API listens on `http://127.0.0.1:8000` by default. Useful endpoints:

- `GET /health/live` - process liveness, does not touch SQLite.
- `GET /health/ready` - SQLite accessibility and Alembic head check.
- `GET /health` - alias for readiness.
- `/docs` - generated OpenAPI UI.
- `/openapi.json` - generated OpenAPI document.

Readiness returns HTTP 503 until the database exists and is at the current
migration head. See [Health and readiness](operations.md#health-and-readiness).

Copy `.env.example` to `.env` only when you need to override the development
defaults. `.env` is ignored by Git; do not commit it.

### Frontend

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

The frontend is served at `http://localhost:5173`. Vite proxies `/api` requests
to `http://127.0.0.1:8000` by default and strips the `/api` prefix.

Open <http://localhost:5173>, not `http://127.0.0.1:5173`. Administrator
state-changing requests validate the browser `Origin`, and the default passkey
relying-party ID is `localhost`; the IP form causes
`Request origin is not allowed` and cannot complete passkey registration.

The first visit to `/admin` can claim the initial administrator account. See
[Administrator setup](operations.md#administrator-bootstrap-and-passkeys).

## Configuration

Backend settings are loaded and validated at startup. All use the
`CHORE_TRACKER_` prefix. The root [`.env.example`](../.env.example) documents
the available settings.

| Setting | Development default | Purpose |
| --- | --- | --- |
| `CHORE_TRACKER_ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `CHORE_TRACKER_APP_HOST` | `127.0.0.1` | API bind address |
| `CHORE_TRACKER_APP_PORT` | `8000` | API bind port |
| `CHORE_TRACKER_APP_ORIGIN` | `http://localhost:5173` | Browser origin allowed to call the API |
| `CHORE_TRACKER_DATABASE_PATH` | `./data/chore-tracker.db` | SQLite file path; use a persistent mount in deployments |
| `CHORE_TRACKER_PASSKEY_RP_ID` | `localhost` | Passkey relying-party ID |
| `CHORE_TRACKER_PASSKEY_ORIGIN` | `http://localhost:5173` | Origin used for passkey validation |
| `CHORE_TRACKER_EMAIL_TRANSPORT` | `console` | Validated transport setting: `console` or `smtp` |
| `CHORE_TRACKER_EMAIL_FROM_ADDRESS` | unset | Sender address required when transport is `smtp` |
| `CHORE_TRACKER_SMTP_HOST` | unset | SMTP host required when transport is `smtp` |
| `CHORE_TRACKER_SMTP_PORT` | `587` | SMTP port |
| `CHORE_TRACKER_SMTP_USERNAME` | unset | Optional SMTP username; pair with a password |
| `CHORE_TRACKER_SMTP_PASSWORD` | unset | SMTP password |
| `CHORE_TRACKER_SMTP_PASSWORD_FILE` | unset | Mounted secret file containing the SMTP password |
| `CHORE_TRACKER_SMTP_STARTTLS` | `true` | Enable STARTTLS for SMTP |
| `CHORE_TRACKER_REPORT_TIMEZONE` | `America/Denver` | IANA timezone for reports, rollover, and local child dates |
| `CHORE_TRACKER_REPORT_DELIVERY_TIME` | `03:00` | Monday rollover time in the reporting timezone (`HH:MM`) |
| `CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED` | `true` | Run the durable Monday rollover from the API process |

Email transport settings are validated, but the MVP does not send report
email; reports are viewed in the administrator UI. Do not treat SMTP
configuration as a working notification path yet. See
[Known limitations](operations.md#known-limitations).

Secrets can come from environment variables or mounted files. Prefer
`CHORE_TRACKER_SMTP_PASSWORD_FILE` in deployments. Secret values are not
included in settings representations or validation messages.

Production startup rejects development-only configuration:

- application and passkey origins must use HTTPS;
- the passkey relying-party ID must not be `localhost`;
- a non-console email transport must be configured.

Administrator identity is established through browser setup, never through
environment variables.

### Frontend configuration

Copy `frontend/.env.example` to `frontend/.env` to override the defaults.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | API base URL compiled into the frontend |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite development proxy destination |

Never put secrets in `VITE_*` values. They are compiled into browser assets and
are public.

## Tilt workflow

The [Tiltfile](../Tiltfile) runs four host resources in dependency order:

1. `setup` installs the editable backend package and development dependencies.
2. `migrate` applies `alembic upgrade head`.
3. `backend` starts the API with reload enabled for development.
4. `frontend` installs npm dependencies and starts Vite.

`backend` waits for `setup` and `migrate`; `frontend` can start independently.
No container runtime, Kubernetes cluster, or `DOCKER_HOST` setting is required,
because all resources use Tilt's local-process resources.

```bash
source .venv/bin/activate
# On Windows PowerShell: .venv\Scripts\Activate.ps1
tilt up
```

If you prefer not to activate the environment, set `PYTHON` to the project
interpreter before running Tilt; the Tiltfile uses it for dependency
installation, migrations, and the API process.

Tilt exposes the API at `http://127.0.0.1:8000` and the frontend at
`http://localhost:5173`. Uvicorn reloads files under `src/` (not the frontend
tree or virtual environment when run from the repository root), and Vite
provides frontend hot-module replacement. Stop with `Ctrl+C` or `tilt down`.

If you change `pyproject.toml`, Tilt reinstalls the backend and restarts the
backend resource. If you change `alembic.ini` or `migrations/`, Tilt reapplies
migrations. Backend source changes are handled by Uvicorn's reloader, and
frontend source changes by Vite.

The migration resource does not run automatically when a developer deletes the
SQLite file outside Tilt. Trigger the `migrate` resource in the Tilt UI, or run
`alembic upgrade head` manually, then restart the backend.

## Quality gates

Every command below is part of CI or is run for documentation and operations
changes. Run them before opening a pull request.

### Backend

```bash
ruff format --check .
ruff check .
mypy
pytest
```

`mypy` checks `src/chore_tracker` with the configuration in `pyproject.toml`.
The pytest suite includes migration tests, architecture rules, and the
application/API behavior tests.

### Frontend

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

`npm test` runs the Vitest component and integration-style suite.

### Browser tests

Playwright runs the real frontend against the real FastAPI application:

```bash
cd frontend
npm run test:e2e:install   # once per machine
npm run test:e2e
```

The Playwright configuration starts both services on isolated ports (`5174` for
Vite and `8001` for FastAPI), creates a disposable database at
`frontend/.playwright-data/chore-tracker-e2e.db`, applies migrations, and seeds
the current week plus prior-week history. Backend dependencies must be
installed in the repository `.venv`, or `PYTHON` can point at another
interpreter that has them. Each spec resets its own baseline; lifecycle tests
use test-only controls to set a deterministic date, generate assignments, and
run the Monday rollover without the live scheduler.

The suite covers the family flow, themes, administrator passkey flows, report
history/detail, and repeated rollover idempotence. Failures retain traces and
screenshots, and CI uploads `frontend/playwright-report/` and
`frontend/test-results/`.

### Compose smoke test

With Docker or a Compose-compatible Podman available:

```bash
./scripts/compose-smoke-test.sh
```

The script builds both images, starts an isolated Compose project, verifies
health and the API proxy, checks non-root containers, writes a sentinel to the
volume, restarts the deployment, and verifies the sentinel survived. It removes
its own volume on exit. Set `CHORE_TRACKER_HTTP_PORT` if port 8080 is in use.

### Kubernetes manifest validation

```bash
./scripts/kubernetes-manifest-test.sh
```

The script lints the Helm chart, renders the supported value variants, checks
single-replica and probe invariants, and validates every object with
`kubeconform`. Set `KUBECONFORM=/path/to/kubeconform` when it is not on `PATH`.

### Documentation checks

```bash
python scripts/check-docs-links.py
./scripts/verify-backup-restore.sh
```

The link check validates relative file links in the README, `docs/`, and the
Helm chart README. The backup/restore script creates a sample database with
assignments, completions, a weekly report, and rollover state; backs it up;
destroys the source; restores the backup; and asserts the history survived.
See [Backup and restore](backup-restore.md#verification-script).

## Continuous integration

The [quality-gate workflow](../.github/workflows/ci.yml) runs on pull requests
and pushes to `main`:

- `backend` - Ruff formatting/lint, `mypy`, migration tests, and the full pytest
  suite.
- `frontend` - ESLint, TypeScript type checking, Vitest, and the production
  build.
- `e2e` - installs Chromium, runs Playwright against real FastAPI and Vite
  processes with an isolated database, and uploads diagnostics.
- `docs` - documentation link checks and the backup/restore verification.
- `docker` - builds both images and runs the Compose smoke test.
- `kubernetes` - lints the Helm chart and validates rendered objects with
  `kubeconform`.

Version tags are a separate workflow: pushing one builds both images and
publishes them to GitHub Container Registry. See
[Publishing release images](deployment.md#publishing-release-images).

## Troubleshooting local development

| Symptom | Likely cause and fix |
| --- | --- |
| `alembic: command not found` | The virtual environment is not active, or dependencies were not installed. Activate `.venv` and run `python -m pip install -e ".[dev]"`. |
| Readiness returns 503 | The database is missing or behind. Run `alembic upgrade head`, then retry `/health/ready`. |
| `Request origin is not allowed` | Open the frontend at `http://localhost:5173`, not the IP address, or set the app and passkey origins to the exact origin in use. |
| Passkey registration fails on a phone or LAN name | WebAuthn requires HTTPS outside `localhost`. Configure a real hostname, TLS, and matching `CHORE_TRACKER_PASSKEY_RP_ID` and origins. |
| Frontend calls fail with CORS or 404 | Check that the API is running on port 8000 and `API_PROXY_TARGET` points at it. |
| Port already in use | Stop the conflicting process or set `CHORE_TRACKER_APP_PORT` and `API_PROXY_TARGET` together. |
| Tilt migration fails on a clean checkout | Activate the virtual environment before `tilt up` so `python -m pip` and `python -m alembic` resolve to the project environment. |
