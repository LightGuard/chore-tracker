# Contributing to Chore Tracker

Thanks for helping. Chore Tracker is a self-hosted chore tracker for one
household: a FastAPI + SQLite backend and a React + Vite frontend, deployed with
Docker Compose or a single-replica Kubernetes chart.

This guide covers the human workflow. Coding agents should also read
[`AGENTS.md`](AGENTS.md), and everyone should skim
[`docs/development.md`](docs/development.md) and
[`docs/architecture.md`](docs/architecture.md) before a first change.

## Before you start

The scope is intentionally small. Read the MVP scope and known limitations in
[`README.md`](README.md). In particular:

- Child-facing endpoints are unauthenticated by design.
- SQLite is single-writer: one backend process, one replica.
- Historical assignments, completions, and reports are immutable.
- Persistent XP, currencies, and Sticker Club mappings are out of scope. Quest
  derives XP from completion facts and the snapshot chore weight at read time;
  the weekly-report reward flag is an audit record, not a reward system.

If your change would broaden any of these, open an issue first so the tradeoff is
explicit.

## Setup

Prerequisites: Python 3.15 or newer (below 4.0), Node.js 22 or newer, npm 10 or
newer. Tilt, Docker, Helm, and `kubeconform` are optional.

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
alembic upgrade head
python -m chore_tracker
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>, not `http://127.0.0.1:5173`. Administrator
state-changing requests validate the browser origin and the default passkey
relying-party ID is `localhost`, so the IP form cannot complete registration.
The first visit to `/admin` claims the initial administrator with a passkey.

Migrations are never applied at startup. After pulling schema changes, run
`alembic upgrade head`; `GET /health/ready` returns 503 until you do.

Copy `.env.example` to `.env` only to override defaults. `.env` is gitignored.
The full setting list is in
[`docs/development.md`](docs/development.md#configuration).

`tilt up` runs setup, migrations, the API, and Vite as host processes; see
[`docs/development.md`](docs/development.md#tilt-workflow).

## Project layout

| Path | Contents |
| --- | --- |
| `src/chore_tracker/api/` | HTTP routes and request/response mapping |
| `src/chore_tracker/application/services/` | Business rules and use cases |
| `src/chore_tracker/adapters/sqlite/` | SQLite persistence and readiness |
| `src/chore_tracker/config.py` | Typed environment settings |
| `frontend/src/` | Family flow, administrator UI, themes, API client |
| `frontend/e2e/` | Playwright specs and fixtures |
| `migrations/versions/` | Alembic revisions, forward-only |
| `scripts/` | CI verification scripts |
| `deploy/kubernetes/chore-tracker/` | Helm chart |
| `docs/` | Contributor and operator guides |

The backend is ports-and-adapters. Architecture tests in `tests/architecture/`
enforce that `api` never imports `sqlite3` or `chore_tracker.adapters` and never
executes SQL or manages transactions, that `application` never imports
`fastapi`, `starlette`, `sqlite3`, or concrete adapters, and that adapters never
import `api`. Put persistence in `adapters/sqlite/` and business rules in
`application/services/`.

## Making a change

1. **Open or claim an issue.** Branches are named for the issue, e.g.
   `feat-92-chore-weight`, `feat/90-report-reward-tracking`, or
   `docs/24-operations-docs`. Keep one logical change per branch and PR.
2. **Write the test with the change.** Backend behavior belongs in `tests/`;
   frontend behavior in Vitest (`frontend/src/**/*.test.tsx`) or Playwright
   (`frontend/e2e/`) when it needs a real browser and API.
3. **Update the docs in the same PR.** User-visible or operational behavior
   changes belong in `docs/`. Add a row to the guide map in
   [`docs/README.md`](docs/README.md) if you add a guide.
4. **Run the quality gates** (below) before pushing.
5. **Open the PR** against `main` with a summary of the change, the motivation
   (link the issue), and the commands you ran. CI must be green.

## Schema changes

History is forward-only:

- Add a new revision under `migrations/versions/`; never edit a revision that has
  shipped.
- Never update or delete historical rows: assignments, their checklist snapshots,
  completions, reports, report days, and report rewards are protected by
  triggers. Extend behavior with new rows or new tables instead of rewriting
  history.
- Preserve the invariants listed in
  [`docs/architecture.md`](docs/architecture.md#invariants), and extend
  `tests/test_migrations.py` when a new table or trigger is added.
- If you add a setting, update `src/chore_tracker/config.py`, `.env.example`, and
  the configuration table in `docs/development.md`.

## Quality gates

Run these from the repository root unless stated otherwise. They are what CI
runs.

```bash
# Backend
ruff format --check .
ruff check .
mypy
pytest

# Frontend
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

Additional checks for changes that touch them:

```bash
cd frontend && npm run test:e2e     # browser flows (first run: npm run test:e2e:install)
python scripts/check-docs-links.py  # docs links and anchors
./scripts/verify-backup-restore.sh  # backup/restore procedure
./scripts/compose-smoke-test.sh     # images and Compose deployment
./scripts/kubernetes-manifest-test.sh  # Helm chart and rendered manifests
```

CI runs the backend, frontend, e2e, docs, docker, and kubernetes jobs defined in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml). Playwright starts its own
API and Vite on isolated ports with a disposable database; it never uses your
development data.

## Style

- Python: Ruff, 88-column lines, rules `E,F,I,UP,B`, target `py315`. Keep type
  hints on public functions and avoid `# type: ignore`.
- TypeScript: `strict` with `noUnusedLocals`, `noUnusedParameters`, and
  `verbatimModuleSyntax`; use `import type` for type-only imports. Match the
  surrounding style — there is no configured formatter.
- Commits: imperative subject, optional `[Area]` tag, body wrapped near 80
  columns explaining *why*. One logical change per commit.
- Theme work: themes change presentation only. Never couple assignment,
  completion, report, or authentication behavior to a theme.

## Reporting issues

Include steps to reproduce, expected vs. actual behavior, and relevant logs
(never paste secrets, passkey material, or a real database). For security
problems, do not open a public issue; contact the maintainer directly.

## License

Contributions are accepted under the terms of the repository [LICENSE](LICENSE).
