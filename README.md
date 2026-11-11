# chore-tracker

Basic chore tracker app for my family.

## Backend

The backend is a FastAPI application. It currently provides only a health endpoint;
domain behavior and persistence are intentionally not implemented yet.

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

The API is available at `http://127.0.0.1:8000`. Check readiness with:

```bash
curl http://127.0.0.1:8000/health
```

A healthy application returns HTTP 200 and `{"status":"ok"}`.

### Application configuration

Configuration is loaded and validated when the application starts. All settings use
the `CHORE_TRACKER_` environment-variable prefix. The root `.env.example` documents
the available settings.

| Setting | Development default | Purpose |
| --- | --- | --- |
| `CHORE_TRACKER_ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `CHORE_TRACKER_APP_HOST` | `127.0.0.1` | API bind address |
| `CHORE_TRACKER_APP_PORT` | `8000` | API bind port |
| `CHORE_TRACKER_APP_ORIGIN` | `http://127.0.0.1:5173` | Browser origin allowed to call the API |
| `CHORE_TRACKER_DATABASE_PATH` | `./data/chore-tracker.db` | SQLite file path; set to a persistent mounted volume in deployments |
| `CHORE_TRACKER_ADMIN_EMAIL` | unset | Initial administrator identity setting for the identity feature |
| `CHORE_TRACKER_PASSKEY_RP_ID` | `localhost` | Passkey relying-party ID |
| `CHORE_TRACKER_PASSKEY_ORIGIN` | `http://127.0.0.1:5173` | Origin used for passkey validation |
| `CHORE_TRACKER_EMAIL_TRANSPORT` | `console` | Initial transports: `console` or `smtp` |
| `CHORE_TRACKER_REPORT_TIMEZONE` | `America/Denver` | IANA timezone used for reports |
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

Production startup rejects development-only configuration: administrator identity
must be set, application and passkey origins must use HTTPS, the passkey relying-party
ID must not be `localhost`, and a non-console email transport must be configured.
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
behavior or infrastructure. No persistence adapter is implemented in this bootstrap.

## Frontend

The frontend is a React, TypeScript, and Vite application using the ReShaped component
library. React Router provides browser-based client-side routing. The initial route is
only an application shell; feature screens are intentionally not part of this bootstrap.

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

The frontend is served at `http://127.0.0.1:5173`. The Vite development server proxies
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
`http://127.0.0.1:5173`. Uvicorn reloads the API when Python files change, and Vite
provides frontend hot-module replacement. Stop the environment with `Ctrl+C` or
`tilt down`.

Both services run on the host through Tilt's local-process resources. Docker and
Podman are therefore not involved and neither is required. The same `tilt up` setup
works on machines that have Docker, Podman, or neither installed; no container socket
or `DOCKER_HOST` setting is needed. The referenced Tilt Podman extension provides
Podman image builds for container-based workloads, which this local-process setup does
not use.
