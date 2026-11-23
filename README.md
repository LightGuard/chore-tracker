# chore-tracker

Basic chore tracker app for my family.

## Backend

The backend is a FastAPI application with SQLite persistence, administrator passkey
authentication, and health endpoints.

### Requirements

- Python 3.15 or newer (below 4.0)

### Set up the development environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate the environment with
`.venv\\Scripts\\Activate.ps1`.

Copy `.env.example` to `.env` if you need to override application configuration.
The development defaults are suitable for a local run.

### Run locally

```bash
python -m chore_tracker
```

The API is available at `http://127.0.0.1:8000`. The health endpoints distinguish
process liveness from application readiness:

- `GET /health/live` reports that the API process is running. It does not access
  the database.
- `GET /health/ready` reports readiness only when the configured SQLite database
  is accessible and has been upgraded to the current Alembic migration head.
- `GET /health` is retained as an alias for the readiness endpoint.

A healthy endpoint returns HTTP 200 and `{"status":"ok"}`. Readiness returns HTTP
503 and `{"status":"not_ready"}` when the database is unavailable or its schema is
not current. The response does not include filesystem paths or database errors.
Apply migrations explicitly with `alembic upgrade head` before expecting readiness
to succeed; the application does not migrate the database during startup.

### Child-facing API

Child-facing endpoints intentionally do not require an administrator session or
child authentication. The household trust model uses profile selection rather than
individual child accounts.

- `GET /family-members/active` returns active profiles as an array of
  `{ "id": integer, "display_name": string, "theme_id": string | null }`, ordered by
  display name (case-insensitive) and then ID. Inactive profiles are excluded. A
  `theme_id` of `null` means the child has never saved a theme.
- `GET /family-members/{family_member_id}/current-assignment` returns the selected
  active child's assignment for the current Monday–Sunday week in the configured
  `CHORE_TRACKER_REPORT_TIMEZONE`. The response includes the immutable chore name
  and description snapshots, ordered checklist snapshots, each item's completion
  state for today's local date, and an `is_complete` value that is true only when
  every checklist item is complete.

The current-assignment endpoint returns HTTP 404 when the profile does not exist or
has no assignment for the current week, and HTTP 409 when the profile exists but is
inactive. Error responses use FastAPI's standard `{"detail":"..."}` shape. The
response schemas and error status codes are also published in the generated OpenAPI
document at `/openapi.json`.

These read-only endpoints do not create assignments. The weekly assignment
generation service must have generated the current week's assignments before a
child can view one.

- `GET /family-members/{family_member_id}/assignments/{assignment_id}/completion?completion_date=YYYY-MM-DD`
  returns the assigned checklist and its completion state for that local calendar date.
- `PUT /family-members/{family_member_id}/assignments/{assignment_id}/checklist-items/{checklist_item_id}/completion`
  accepts `{ "completion_date": "YYYY-MM-DD", "is_completed": true|false }`
  and idempotently sets that item's state for the date.

The completion date is interpreted as a calendar date in
`CHORE_TRACKER_REPORT_TIMEZONE`; callers send the local date, not a UTC timestamp.
A date must fall within the assignment's Monday–Sunday week. Reads do not create
completion rows, so a date with no saved state returns every item as unchecked.
Unchecking an item updates only that item's record for that date; records for other
dates remain intact. The daily `is_complete` result is derived from the immutable
assignment checklist and is true only when every checklist item is checked.
Completion writes acquire a SQLite write reservation before reading and updating,
so concurrent requests are serialized. These endpoints remain unauthenticated under
the child-facing household trust model.

- `GET /family-members/{family_member_id}/completion-history?limit=50&offset=0`
  returns historical daily records for every persisted weekly assignment belonging to
  the selected profile. Each assignment contributes one record for each day in its
  Monday–Sunday week, including days with no saved completion rows. Records are ordered
  newest date first, with assignment ID as a deterministic tie-breaker. Pagination
  defaults to 50 records and accepts a limit from 1 through 100 and a non-negative
  offset. The response contains `items`, the total number of available daily records,
  and the effective pagination values.

Each history record includes the assignment ID, week boundaries, immutable chore name
and description snapshots, local calendar date, and `completion_status`. Status is
`complete` only when every checklist snapshot item has a saved completed record;
`incomplete` when at least one completion record exists but the full checklist is
not complete; and `not_yet_recorded` when no completion record exists for that day.
The endpoint does not create completion rows or infer a result from a missing row.
Historical records remain available when a family profile or chore is inactive, and
catalog edits do not change the assignment snapshots. An unknown profile returns HTTP
404; a known profile with no assignments returns HTTP 200 with an empty page.

### Theme catalog and preferences

Themes are visual and layout variants. The API is the source of truth for which
themes are available; preview images are frontend assets, and the API publishes only
their public paths.

`GET /themes` is public and returns entries in display order:

```json
[
  {
    "id": "homestead",
    "name": "Homestead",
    "preview_image": "/theme-previews/homestead.png"
  }
]
```

Only `homestead` is available in this ticket. Its stable id is also the default
theme. Unknown or unset saved values are treated as Homestead by the frontend; the
API deliberately returns the raw saved value so the server remains the durable source
of truth.

- `GET /family-members/active` includes the child's raw `theme_id` or `null`.
- `GET /auth/me` includes the administrator's raw `theme_id` or `null`.
- `PUT /family-members/{family_member_id}/theme` accepts
  `{ "theme_id": "homestead" }`, is idempotent, and returns
  `{ "theme_id": "homestead" }`. Child theme writes follow the existing
  unauthenticated household trust model. An unknown child returns 404, an inactive
  child 409, and an unavailable theme 422.
- `PUT /auth/me/theme` accepts the same body, requires an authenticated
  administrator, enforces the existing same-origin check, is idempotent, and returns
  `{ "theme_id": "homestead" }`. Preferences are stored per administrator row.
  An unavailable theme returns 422.

Migration `0008_theme_preferences` adds nullable `theme_id` columns to
`family_members` and `administrators`. It does not assign a theme to existing rows.
There is no theme table; the catalog is application-owned. No assignment, completion,
report, or authentication behavior depends on the theme value.

#### Adding a theme

1. Add a stable lowercase id, display name, and frontend preview path to
   `THEME_CATALOG` in `src/chore_tracker/application/services/themes.py`.
2. Add the preview image under `frontend/public/theme-previews/`.
3. Add a scoped `theme-<id>` token block and layout rules in
   `frontend/src/styles.css`, keeping ReShaped components as the substrate.
4. Add the theme to backend API tests and frontend catalog fixtures, then cover its
   picker/dropdown rendering and responsive behavior.
5. Never reuse an id for a different visual direction; saved ids are durable.

### Application configuration

Configuration is loaded and validated when the application starts. All settings use
the `CHORE_TRACKER_` environment-variable prefix. The root `.env.example` documents
the available settings.

| Setting | Development default | Purpose |
| --- | --- | --- |
| `CHORE_TRACKER_ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `CHORE_TRACKER_APP_HOST` | `127.0.0.1` | API bind address |
| `CHORE_TRACKER_APP_PORT` | `8000` | API bind port |
| `CHORE_TRACKER_APP_ORIGIN` | `http://localhost:5173` | Browser origin allowed to call the API |
| `CHORE_TRACKER_DATABASE_PATH` | `./data/chore-tracker.db` | SQLite file path; set to a persistent mounted volume in deployments |
| `CHORE_TRACKER_PASSKEY_RP_ID` | `localhost` | Passkey relying-party ID |
| `CHORE_TRACKER_PASSKEY_ORIGIN` | `http://localhost:5173` | Origin used for passkey validation |
| `CHORE_TRACKER_EMAIL_TRANSPORT` | `console` | Initial transports: `console` or `smtp` |
| `CHORE_TRACKER_REPORT_TIMEZONE` | `America/Denver` | IANA timezone used for reports and child-facing local dates |
| `CHORE_TRACKER_REPORT_DELIVERY_TIME` | `03:00` | Monday report delivery time in the reporting timezone (`HH:MM`) |
| `CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED` | `true` | Run the durable Monday report and assignment rollover from the API process |

The development email transport writes messages to the application console and does
not send email. To use SMTP, set `CHORE_TRACKER_EMAIL_TRANSPORT=smtp`,
`CHORE_TRACKER_SMTP_HOST`, and `CHORE_TRACKER_EMAIL_FROM_ADDRESS`. SMTP authentication
is optional; when used, username and password must be supplied together. The
application does not select or depend on a particular email provider.

Secrets can be supplied through environment variables or mounted secret files. For
SMTP, set `CHORE_TRACKER_SMTP_PASSWORD` directly, or set
`CHORE_TRACKER_SMTP_PASSWORD_FILE` to the path of a mounted file containing the
password. Secret values are represented as secret types and are not included in
settings representations or validation messages. Do not commit `.env` files or secret
files.

Production startup rejects development-only configuration: application and passkey
origins must use HTTPS, the passkey relying-party ID must not be `localhost`, and a
non-console email transport must be configured. Administrator identity is established
through the first-run browser setup and is not supplied through environment variables.
Validation errors identify the missing setting without echoing secret values.

### Quality checks

Run these commands from the repository root:

```bash
ruff format --check .
ruff check .
mypy
pytest
```

`mypy` checks the `src/chore_tracker` package using the configuration in
`pyproject.toml`. The pytest suite includes the Alembic migration tests; CI also
runs those migration tests as a separate pre-test step for visibility.

### Backend layout

- `src/chore_tracker/api/routes/`: HTTP endpoints and response mapping.
- `src/chore_tracker/application/services/`: application-level operations.
- `src/chore_tracker/adapters/`: infrastructure adapters, including future
  persistence implementations.
- `src/chore_tracker/config.py`: typed environment and secret configuration.

The layers are kept separate so HTTP concerns do not become coupled to application
behavior or infrastructure.

## Frontend

The frontend is a React, TypeScript, and Vite application using the ReShaped component
library. React Router provides browser-based client-side routing. The home screen at
`/` lets a child select their profile, work through this week's chore checklist, and
open their historical daily completion records grouped by week. Profile selection is
a household convenience, not authentication. The administrator screen is available
at `/admin` and provides first-run passkey setup, passkey sign-in, second-administrator
enrollment, family-member management, and chore/checklist catalog management. Admin
management is rendered only for an authenticated administrator, and an expired
session returns the user to sign-in with an explanation.

### Requirements

- Node.js 22 or newer
- npm 10 or newer

### Set up and run locally

In a second terminal, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

The frontend is served at `http://localhost:5173`. The Vite development server proxies
requests under `/api` to `http://127.0.0.1:8000` by default.

Open the frontend at `http://localhost:5173`, not `http://127.0.0.1:5173`.
Administrator state-changing requests validate the browser `Origin`, and the default
passkey relying-party ID is `localhost`; using the IP address causes an
`Request origin is not allowed` response and is not valid for passkey registration.

### Frontend configuration

- `VITE_API_BASE_URL` sets the API base URL compiled into the frontend. It defaults
  to the same-origin path `/api`; set it to an absolute URL only when the deployment
  requires a separately hosted API.
- `API_PROXY_TARGET` sets the development proxy destination. It defaults to
  `http://127.0.0.1:8000` and is used by Vite only.

### Themes, fonts, and previews

The family flow is child-first. Before a child is selected the page renders in
Homestead and the header theme control is disabled. A child with a saved theme sees
their assignment immediately after selection. A child with no valid saved theme sees
the Homestead-selected picker before any assignment content; choosing a theme saves it
immediately and reveals the assignment. Choosing another child from the dismissible
Switch child step leaves the current child active until a new child is selected.

The header and picker use `GET /themes` for names and preview images. Header changes
save immediately for the active child or signed-in administrator. A failed save keeps
the previous theme and surfaces an actionable retry; a failed first-time picker save
stays on the picker.

Browser storage is limited to convenience and flash avoidance:

- `chore-tracker.theme.last-child` is written only after a child has a saved theme
  and drives reload restoration.
- `chore-tracker.theme.child.<id>` and `chore-tracker.theme.admin.<id>` cache the last
  known theme per identity.
- `chore-tracker.theme.last-theme` is a small bootstrap mirror used before React paints.
  Unknown ids are ignored. Server responses reconcile the cache: a valid saved theme
  updates it, while an unset or unavailable theme clears the per-identity entry and
  falls back to Homestead.

Family and admin route contexts are separate. Child themes never theme signed-in
admin screens, and administrator themes never theme family screens. Signing out
returns the admin context to Homestead and disables the theme control.

Homestead uses bundled WOFF2 assets, not a font CDN:

| Use | Font | Files |
| --- | --- | --- |
| Headings | Source Serif 4 | `frontend/public/fonts/source-serif-4-*.woff2` |
| Body | Nunito Sans | `frontend/public/fonts/nunito-sans-*.woff2` |
| Handwritten notes | Caveat | `frontend/public/fonts/caveat-*.woff2` |
| Small labels | JetBrains Mono | `frontend/public/fonts/jetbrains-mono-*.woff2` |

Font licenses are in `frontend/public/fonts/licenses/`; `fonts.css` declares the
self-hosted faces and is linked from `frontend/index.html`.

The committed Homestead phone assignment preview is
`frontend/public/theme-previews/homestead.png`, served at
`/theme-previews/homestead.png`. It is generated from the running frontend against
the deterministic preview fixture in `frontend/e2e/backend_server.py`:

```bash
cd frontend
PREVIEW_BASE_URL=http://localhost:5174 npm run theme:preview
```

The generation browser must be installed; set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` when using a pre-installed Chromium. The
scripted fixture starts from a clean database and always uses the four-child,
three-item Homestead assignment, so the image is reproducible. The seven-child /
six-checklist-item stress case is a separate test-only scenario.

Copy `frontend/.env.example` to `frontend/.env` to override the defaults for local
development. Do not put secrets in `VITE_*` variables; those values are exposed to
browser code.

### Frontend quality checks

Run these commands from the `frontend` directory:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

### Browser tests

Playwright covers the primary family flow against the real frontend and backend.
Install Chromium once, then run the browser suite:

```bash
npm run test:e2e:install
npm run test:e2e
```

The Playwright configuration starts both services itself on isolated ports
(`5174` for Vite and `8001` for FastAPI), creates a disposable SQLite database at
`frontend/.playwright-data/chore-tracker-e2e.db`, applies migrations, and seeds the
current week's assignments plus prior-week history samples. Backend dependencies
must already be installed in the repository's `.venv`, or `PYTHON` can point at
another interpreter with the backend dependencies available. Each browser spec
resets its own baseline, and lifecycle tests use test-only controls in
`frontend/e2e/backend_server.py` to set a deterministic date, generate assignments,
and run the Monday rollover without starting the live scheduler. The fixture's
child-facing date starts at Monday, 2026-11-09; the live scheduler is disabled.

The suite covers child selection, picker-before-assignment, saving Homestead,
remembered-child restoration, switch-child cancellation, ordered checklist display,
checking and unchecking items, reload persistence, the no-assignment state, grouped
completion history, empty history, history switching when the selected child changes,
a phone-sized viewport, the next-day fresh checklist with the prior day retained in
history, deterministic one-chore-per-child assignment generation, and repeated Monday
rollover without duplicate reports or assignments. Theme coverage includes cold-load
default, disabled controls, preview image loading, dropdown keyboard operation,
seven-child / six-item responsiveness at phone/tablet/desktop widths, the preview
fixture, and the committed preview image. Administrator browser coverage uses
Playwright's virtual WebAuthn authenticator to exercise real passkey registration,
sign-in, second-administrator enrollment, invalid and reused invitation handling,
protected-screen denial, representative family/chore CRUD, report history/detail,
administrator theme saving, sign-out reverting to Homestead, and disabled controls
after sign-out against the running application.

These browser tests are separate from `npm test`, which runs the component and
integration-style Vitest suite.

### Continuous integration

The [quality-gate workflow](.github/workflows/ci.yml) runs on pull requests and pushes
to `main`:

- `backend`: Ruff formatting/lint, `mypy`, migration tests, and the full pytest suite.
- `frontend`: ESLint, TypeScript type checking, Vitest, and the production build.
- `e2e`: installs Chromium, runs the Playwright suite against the real FastAPI and Vite
  processes with an isolated SQLite database, then uploads the HTML report, traces,
  and screenshots as the `playwright-diagnostics` artifact.
- `docker`: builds both images and runs the Compose smoke test.
- `kubernetes`: lints the Helm chart and validates rendered objects with
  `kubeconform`.

The backend, frontend, and browser commands documented above are the same commands
used by those jobs. The browser artifact is uploaded even when tests pass; on failure
it contains the retained traces and screenshots needed to diagnose the run.

## Docker deployment

Production-style images and a Compose deployment are included for local and
homelab use. The backend image installs the exact versions in `uv.lock`; the
frontend image installs the exact versions in `package-lock.json` and serves the
built static application through nginx. The API is not published to the host:
nginx serves the frontend, proxies `/api` to the API, and exposes the health
endpoints on the single published port.

The deployment requires Docker Engine with Compose v2 (or a compatible Podman
and Compose installation).

### Start the deployment

Copy the Docker deployment environment example, review the public origin, and
start the services:

```bash
cp .env.docker.example .env.docker
docker compose --env-file .env.docker up --detach --build
```

Open `http://localhost:8080`. The default configuration is suitable for local
Docker use; WebAuthn treats `localhost` as a secure origin.

The one-shot `migrate` service runs `alembic upgrade head` before the API
starts. The backend waits for that service to complete successfully, the
frontend waits for the backend readiness check, and the application never runs
migrations automatically during startup. Check progress with:

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

Application settings are read from `.env.docker` at runtime through the
Compose `env_file` mechanism. Container-specific values are fixed by
`compose.yaml`: the API binds `0.0.0.0:8000`, SQLite uses
`/data/chore-tracker.db`, and the application and passkey origins use
`CHORE_TRACKER_PUBLIC_ORIGIN`. Other `CHORE_TRACKER_*` settings in the file,
including SMTP configuration and the reporting timezone, are passed through.

`CHORE_TRACKER_PUBLIC_ORIGIN`, `CHORE_TRACKER_BIND_ADDRESS`,
`CHORE_TRACKER_HTTP_PORT`, and `CHORE_TRACKER_PASSKEY_RP_ID` are Compose
deployment values. `VITE_API_BASE_URL` is a public build argument fixed to
`/api`; never put secrets in `VITE_*` values because they are compiled into
browser assets.

Secrets are injected at runtime and are not copied into either image. The root
`.dockerignore` and `frontend/.dockerignore` exclude environment files. Prefer
a mounted SMTP password file over a password environment variable. Compose
automatically reads a local `compose.override.yaml`; for example:

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
secret. The example file `.env.docker.example` also documents the SMTP settings.

For a production-style deployment, terminate TLS before the frontend, set
`CHORE_TRACKER_ENVIRONMENT=production`, use HTTPS application and passkey
origins, set a real passkey relying-party domain, and configure SMTP delivery.
The application rejects development-only production configuration at startup.

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
liveness, readiness, the frontend, and the API proxy, checks that the
application containers are non-root, writes a sentinel to the volume, restarts
the deployment, and verifies the sentinel survived. It removes its own volume
on exit. Set `CHORE_TRACKER_HTTP_PORT` if port 8080 is already in use.

## Kubernetes deployment

A Helm chart for the homelab Traefik environment is in
[`deploy/kubernetes/chore-tracker`](deploy/kubernetes/chore-tracker). It deploys
the backend and frontend images, migrates SQLite in an init container, persists
the database on a ReadWriteOnce volume, and configures liveness/readiness
probes against `/health/live` and `/health/ready`.

The chart takes the IngressClass, hostname, wildcard TLS Secret, image
repository, storage class, secrets, and resource requests/limits as values; it
does not install an ingress controller or create secret material. The backend
is deliberately limited to one replica with the `Recreate` strategy because
SQLite supports one writer.

See the [chart README](deploy/kubernetes/chore-tracker/README.md) for image
publishing, installation, the test-cluster procedure, backups, and rollback.
A quick install looks like:

```bash
helm upgrade --install chore-tracker ./deploy/kubernetes/chore-tracker \
  --namespace chore-tracker --create-namespace \
  --values my-values.yaml --wait --timeout 5m
```

The `kubernetes` CI job lints the chart and validates all rendered objects with
`kubeconform`.

## Tilt development environment

Tilt starts the API and frontend directly as local processes. It installs the backend
editable package and frontend npm dependencies when their dependency manifests
change. Python's virtual environment must be active in the terminal before running
Tilt so the backend dependencies are installed into that environment.

```bash
source .venv/bin/activate
# On Windows PowerShell: .venv\\Scripts\\Activate.ps1
tilt up
```

Tilt exposes the API at `http://127.0.0.1:8000` and the frontend at
`http://localhost:5173`. Uvicorn reloads the API when Python files change, and Vite
provides frontend hot-module replacement. Stop the environment with `Ctrl+C` or
`tilt down`.

Both services run on the host through Tilt's local-process resources. This is
separate from the Docker deployment above: Docker and Podman are not involved in
Tilt and neither is required. The same `tilt up` setup works on machines that have
Docker, Podman, or neither installed; no container socket or `DOCKER_HOST` setting
is needed. The referenced Tilt Podman extension provides Podman image builds for
container-based workloads, which this local-process setup does not use.

## SQLite persistence and schema migrations

The backend uses SQLite with Alembic for versioned schema migrations. Alembic is a
widely used Python migration tool and supports SQLite. Migrations are explicit,
reviewable Python revisions containing the schema changes. The application uses the
Python standard-library `sqlite3` adapter for repository connections, so normal
database access does not require an ORM.

Set `CHORE_TRACKER_DATABASE_PATH` to the SQLite file location. The default is
`./data/chore-tracker.db`; the parent directory is created when a database connection
is opened. Foreign-key enforcement is enabled on every application connection and on
the connection used by Alembic.

Install the project dependencies, then apply migrations explicitly from the repository
root:

```bash
alembic upgrade head
```

Inspect the current schema revision with:

```bash
alembic current
```

Migrations are not run automatically during application startup. Apply and review
schema changes as a deployment step before starting a version that requires them.
Forward migrations preserve existing records. Do not use destructive downgrades
against production data without a verified backup and recovery plan.

The schema keeps family members and chores as deactivatable records. Weekly
assignments retain references to those records and store chore name/description and
ordered checklist-item snapshots, so later catalog edits do not rewrite historical
assignments. Daily completion is stored per assigned checklist item and calendar date.
Weekly report snapshots and per-administrator delivery records provide durable,
unique delivery state for retries.

### Weekly completion reports

A weekly completion report is generated from the persisted weekly assignment
snapshots and daily completion records for one Monday–Sunday week.
`WeeklyReportService` normalizes the requested week, reads every assignment for
that week (including assignments belonging to later-deactivated family members),
and writes one `weekly_reports` header, one `weekly_report_entries` row per
assignment, and seven `weekly_report_days` rows per entry in a single transaction.

The header records the reporting week, generation/finalization timestamps, and
family-wide completed/incomplete day totals. Entries snapshot the child's display
name, assigned chore, and weekly totals. Each daily row snapshots `complete` or
`incomplete`; a day is complete only when the assignment has at least one
checklist snapshot item and every snapshot item has a persisted completion marked
complete for that day. Days without completion records are persisted as
incomplete rather than treated as errors.

Report header, entry, and day rows are immutable at the database level. Only
finalized reports are readable, and repeated generation for the same week returns
the existing report without replacing it. Report entries can be read independently
in bounded pages so the administrator report page can paginate without loading an
entire report.

Administrators browse persisted reports at `/admin/reports`. The history page lists
reports newest first with the reporting week, generation timestamp, and family totals.
Opening a report shows the week summary, each child's assigned chore, all seven daily
statuses, weekly totals, and Previous/Next pagination when more than five entries
exist. The history page shows an explicit empty state when no reports have been
generated. These pages require an administrator session; unauthenticated visitors see
the administrator sign-in screen.

The reporting API is administrator-only:

- `GET /reports` returns finalized report headers ordered by reporting week, newest
  first. Each item contains the report ID, Monday–Sunday week, generation timestamp,
  and family-wide completed/incomplete totals.
- `GET /reports/{week_start}?limit=25&offset=0` returns one finalized report header
  plus a bounded page of entries. Each entry contains the child and chore snapshots,
  weekly totals, and seven `complete` or `incomplete` daily statuses. `limit` ranges
  from 1 through 100 and `offset` must be non-negative.
- Both endpoints return HTTP 401 without an administrator session. An unknown week
  returns HTTP 404. Invalid pagination values return HTTP 422. Values are read from
  the persisted report snapshot, never recalculated from current household data.

### Scheduled Monday report and assignment rollover

The API process owns the weekly rollover. On startup it checks the durable
`weekly_rollover_state` checkpoint and recovers any due Monday runs, then waits until
the next configured Monday delivery time. The schedule therefore survives application
restarts and does not depend only on an in-memory timer.

A rollover for assignment week W runs in this order:

1. Generate and commit the report for W-1, the Monday–Sunday week that just ended.
2. Generate and commit the assignment set for W.
3. Advance the durable checkpoint to W.

The report and assignment steps each use their own SQLite transaction. If a step
fails, earlier committed work remains readable, the checkpoint does not advance, and
the next attempt safely repeats the failed step. Report and assignment generation
return existing records for an already-processed week rather than creating duplicates
or replacing an existing report. Overlapping scheduler executions serialize on
SQLite's write reservation and observe the same idempotent behavior.

On the first run there is no checkpoint, so only the most recent due Monday is
processed. After later downtime, every unprocessed Monday up to the most recent due
delivery time is replayed in order. A failed attempt is retried after five minutes
while the process remains running, and every process restart checks for missed weeks
again.

The scheduler uses `CHORE_TRACKER_REPORT_TIMEZONE` and
`CHORE_TRACKER_REPORT_DELIVERY_TIME` (Monday at `03:00` by default). While running,
it rechecks the wall clock at least hourly so a suspended process or clock adjustment
cannot skip a due Monday. Set `CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED=false` only when
another process owns the schedule or a fixture manages its own reports and
assignments. Operational logs record the reporting week, assignment week, and
completed/failed outcome without family member names.

Reports are only available to readers after their snapshot transaction commits. A
failure during the subsequent assignment step keeps the finalized report readable,
and retrying the rollover returns that same report instead of replacing it.

Chore catalog management is available to authenticated administrators through the
`/chores` API and the administration page. New chores are created inactive. A chore
cannot be activated until it has at least one active checklist item; an active chore
must be deactivated before its last active checklist item can be deactivated or
removed. Checklist items can be edited, removed, and reordered. Catalog changes never
update assignment snapshots or daily completion records. Removing a catalog checklist
item relies on the database's `ON DELETE SET NULL` behavior to clear only the
historical snapshot's source-item reference; the snapshot label and completion history
remain unchanged.

## Administrator identity and passkeys

Administrator setup is performed in the browser; no CLI bootstrap command or
administrator email environment variable is required. After applying migrations and
starting the application, open `/admin` on the local network. If no administrator
exists, the first visitor can claim the initial administrator account by entering an
email address and registering a passkey with the browser's authenticator. The initial
claim is serialized by SQLite so concurrent first visits cannot create competing
initial administrators. If registration is interrupted, returning to setup with the
same email resumes the pending enrollment; a different email cannot take over it.

The first administrator can create one additional administrator from the admin page.
The application returns a one-time enrollment link that expires after 24 hours. The
second administrator opens that link and registers their own passkey. The application
allows at most two administrator records. Once initial setup is complete, it cannot be
repeated through the unauthenticated setup endpoint.

Passkey registration and authentication challenges expire after five minutes and are
consumed once. The server validates WebAuthn responses against the configured relying-
party ID and exact browser origin. Only credential IDs, public keys, signature counters,
and transport metadata are stored; private authenticator key material remains with the
authenticator. Administrator sessions use random opaque tokens stored as hashes in
SQLite and HttpOnly, SameSite=Strict cookies; cookies are Secure when the configured
passkey origin uses HTTPS. State-changing authentication requests require the configured
browser Origin. Administrative API routes must declare both the `require_admin` and
`require_same_origin` dependencies for state-changing operations. Child-facing routes
must not use administrator authentication.

Administrator theme preference is stored per administrator and is changed only through
`PUT /auth/me/theme`, which requires both the authenticated administrator session and
the configured same-origin header. Signing out does not erase the stored preference,
but the next unsigned-in admin view renders Homestead and disables the theme control.

For local development, the defaults support `http://localhost:5173` and the
`localhost` relying-party ID. For LAN deployment, configure `CHORE_TRACKER_APP_ORIGIN`
and `CHORE_TRACKER_PASSKEY_ORIGIN` to the exact HTTPS origin used in the browser and
set `CHORE_TRACKER_PASSKEY_RP_ID` to its hostname (without scheme or port). Apply
migrations explicitly with `alembic upgrade head` before starting the application.