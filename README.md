# chore-tracker

Basic chore tracker app for my family.

## Backend

The backend is a minimal FastAPI application. It currently provides only a health
endpoint; domain behavior and persistence are intentionally not implemented yet.

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

### Run locally

```bash
uvicorn chore_tracker.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Check readiness with:

```bash
curl http://127.0.0.1:8000/health
```

A healthy application returns HTTP 200 and:

```json
{"status":"ok"}
```

### Quality checks

Run these commands from the repository root:

```bash
ruff format --check .
ruff check .
```

### Backend layout

- `src/chore_tracker/api/routes/`: HTTP endpoints and response mapping.
- `src/chore_tracker/application/services/`: application-level operations.
- `src/chore_tracker/adapters/`: infrastructure adapters, including future
  persistence implementations.

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
cp .env.example .env
npm ci
npm run dev
```

The frontend is served at `http://127.0.0.1:5173`. Run the FastAPI backend separately
using the backend instructions above. The Vite development server proxies requests
under `/api` to `http://127.0.0.1:8000` by default.

### Frontend configuration

- `VITE_API_BASE_URL` sets the API base URL compiled into the frontend. It defaults
  to the same-origin path `/api`; set it to an absolute URL only when the deployment
  requires a separately hosted API.
- `API_PROXY_TARGET` sets the development proxy destination. It defaults to
  `http://127.0.0.1:8000` and is used by Vite only.

Copy `.env.example` to `.env` to override the defaults for local development. Do not
put secrets in `VITE_*` variables; those values are exposed to browser code.

### Frontend quality checks

Run these commands from the `frontend` directory:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```
