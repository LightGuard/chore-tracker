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
