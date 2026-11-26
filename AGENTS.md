# AGENTS.md

Instructions for coding agents working in this repository. Read this file first,
then the guide for the area you are touching. `CONTRIBUTING.md` holds the
human contributor process; the rules below are specific to automated work.

## Project

Chore Tracker is a self-hosted chore tracker for a single household. FastAPI +
SQLite backend, React 19 + Vite frontend, Docker Compose and single-replica
Kubernetes deployment assets. Deliberately small: one backend process, one
SQLite file, one household.

Read [`README.md`](README.md) for scope and
[`docs/architecture.md`](docs/architecture.md) for the data model and invariants
before changing behavior.

## Non-negotiables

1. **Never edit an applied Alembic revision.** History is forward-only: add a new
   revision under `migrations/versions/`. Existing databases in the wild must
   still upgrade cleanly.
2. **Never mutate historical rows.** `weekly_assignments`,
   `assignment_checklist_items`, `daily_checklist_completions`,
   `daily_chore_claims`, `weekly_reports`, `weekly_report_entries`,
   `weekly_report_days`, and `weekly_report_rewards` are protected by database
   triggers. Do not weaken a trigger or write a query that updates/deletes them;
   generate a new week instead.
3. **Respect the layer boundaries.** `src/chore_tracker/api/` must not import
   `sqlite3` or `chore_tracker.adapters`, must not execute SQL, and must not
   manage transactions. `src/chore_tracker/application/` must not import
   `fastapi`, `starlette`, `sqlite3`, or concrete adapters. Adapters must not
   import the API layer. `tests/architecture/` fails on violations.
4. **One backend process, one writer.** Do not add Uvicorn workers, a second
   backend replica, or concurrent SQLite writers. The API process owns the
   Monday rollover scheduler.
5. **The application never migrates at startup.** Migrations are explicit
   (`alembic upgrade head`). `GET /health/ready` stays at 503 until the schema is
   at head.
6. **Themes are presentation only.** A theme change must not alter assignment,
   completion, report, or authentication behavior. Unknown or retired theme ids
   fall back to Homestead; the API stores raw values.
7. **Child-facing endpoints are unauthenticated by design.** Profile selection is
   convenience, not auth. Do not "fix" this by adding child accounts. Do keep
   administrator state-changing requests protected (session + trusted `Origin`).
8. **Secrets never enter the repo.** `.env*` (except the examples), `secrets/`,
   `compose.override.yaml`, and passkey/SMTP material are gitignored. `VITE_*`
   values are compiled into public browser assets and are never secrets.
9. **Stay in scope.** One issue per change. Do not add currencies, reward
   economies, persistent XP, or Sticker Club mappings; those are tracked
   separately. Quest's derived XP mapping is maintained in its own module and
   documented in `docs/themes.md`.
10. **Update the docs in the same change.** User-visible behavior belongs in
    `docs/`. Keep links relative and run `python scripts/check-docs-links.py`.

## Setup

Requirements: Python 3.15+ (<4.0), Node.js 22+, npm 10+. Docker, Helm, Tilt, and
`kubeconform` are optional.

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
python -m chore_tracker          # API on 127.0.0.1:8000

cd frontend && npm ci && npm run dev   # Vite on localhost:5173
```

Use `http://localhost:5173` in a browser, never `127.0.0.1:5173`: passkey
relying-party/origin checks are configured for `localhost`. `uv.lock` is used by
the container images; local and CI installs use pip.

## Quality gates

Run these before declaring work done. CI runs the same commands.

```bash
# Backend, from the repo root
ruff format --check .
ruff check .
mypy
pytest

# Frontend, from frontend/
npm run lint
npm run typecheck
npm test
npm run build

# Heavier checks
cd frontend && npm run test:e2e
python scripts/check-docs-links.py
./scripts/verify-backup-restore.sh
./scripts/compose-smoke-test.sh
./scripts/kubernetes-manifest-test.sh
```

- `mypy` covers `src/chore_tracker` only; `pytest` includes migration and
  architecture tests, so it needs a working `alembic` environment.
- Playwright starts its own backend and Vite on ports 8001/5174 with a disposable
  database under `frontend/.playwright-data/`. Do not point it at your dev
  database, and do not rely on the live scheduler — e2e uses test-only controls
  to freeze dates and run rollover.
- If you change formatting only, still run `ruff format` so CI passes.

## Where things live

| Path | Change here when… |
| --- | --- |
| `src/chore_tracker/api/routes/` | adding/changing HTTP endpoints or response shapes |
| `src/chore_tracker/application/services/` | changing business rules, rotation, rollover, auth policy |
| `src/chore_tracker/adapters/sqlite/` | changing SQL, transactions, readiness probes |
| `src/chore_tracker/config.py` | adding a `CHORE_TRACKER_*` setting (also `.env.example`, docs) |
| `migrations/versions/` | changing the schema (new revision only) |
| `frontend/src/` | family flow, admin UI, themes, API client |
| `frontend/e2e/` | Playwright specs and deterministic fixtures |
| `tests/` | backend behavior, migration, and architecture tests |
| `docs/` | any user-visible or operational behavior |
| `deploy/kubernetes/chore-tracker/` | chart values/templates |
| `scripts/` | CI verification scripts |

## Conventions

- Python: Ruff, line length 88, rules `E,F,I,UP,B`, target `py315`. Type hints on
  public functions; no `# type: ignore` unless unavoidable.
- TypeScript: `strict`, `noUnusedLocals`, `noUnusedParameters`,
  `verbatimModuleSyntax`. Use `import type` for type-only imports. No formatter is
  configured — match surrounding style.
- Commits: imperative subject, optional `[Area]` prefix as used in PR titles, body
  wrapped near 80 columns explaining *why*. Keep one logical change per commit
  and one issue per PR.
- Tests: add a backend test for every behavior change (table-driven is fine) and a
  Vitest/Playwright test for user-visible frontend behavior. Pin API paths and
  methods in client tests.
- API paths in docs are written without the `/api` prefix; the frontend proxies
  `/api/*` to the API.

## Validate before asking

- If a request conflicts with the invariants above, stop and explain instead of
  changing the invariant.
- Ask before: schema migrations that rewrite data, changing rollover or rotation
  semantics, adding a runtime dependency, altering CI, or touching deployment
  defaults.
- Otherwise, make the smallest change that satisfies the request, run the gates,
  and report what changed and what you ran.
