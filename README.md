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
  `{ "id": integer, "display_name": string }`, ordered by display name (case-insensitive)
  and then ID. Inactive profiles are excluded.
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
pytest
```

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
library. React Router provides browser-based client-side routing. The administrator
screen is available at `/admin` and performs first-run setup, passkey sign-in, and
second-administrator enrollment.

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

### Frontend configuration

- `VITE_API_BASE_URL` sets the API base URL compiled into the frontend. It defaults
  to the same-origin path `/api`; set it to an absolute URL only when the deployment
  requires a separately hosted API.
- `API_PROXY_TARGET` sets the development proxy destination. It defaults to
  `http://127.0.0.1:8000` and is used by Vite only.

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

Both services run on the host through Tilt's local-process resources. Docker and
Podman are therefore not involved and neither is required. The same `tilt up` setup
works on machines that have Docker, Podman, or neither installed; no container socket
or `DOCKER_HOST` setting is needed. The referenced Tilt Podman extension provides
Podman image builds for container-based workloads, which this local-process setup does
not use.

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

For local development, the defaults support `http://localhost:5173` and the
`localhost` relying-party ID. For LAN deployment, configure `CHORE_TRACKER_APP_ORIGIN`
and `CHORE_TRACKER_PASSKEY_ORIGIN` to the exact HTTPS origin used in the browser and
set `CHORE_TRACKER_PASSKEY_RP_ID` to its hostname (without scheme or port). Apply
migrations explicitly with `alembic upgrade head` before starting the application.
