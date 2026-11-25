# Architecture

Chore Tracker is a single-household web application. It deliberately uses one
process and one SQLite database so the deployment stays small enough to operate
on a homelab. This guide explains the system boundaries, data model, and
invariants. Operational procedures live in [Operations](operations.md).

## System context

```text
+-------------+       HTTPS        +-----------------------+
|  Browser    | -----------------> | nginx (frontend image)|
| React app   |                    | - serves static assets|
+-------------+                    | - proxies /api,       |
                                   |   /health, /health/*  |
                                   +-----------+-----------+
                                               |
                                               v
                                   +-----------------------+
                                   | FastAPI + Uvicorn     |
                                   | one process, one      |
                                   | weekly rollover owner |
                                   +-----------+-----------+
                                               |
                                               v
                                   +-----------------------+
                                   | SQLite file           |
                                   | catalog, assignments, |
                                   | completions, reports, |
                                   | administrators        |
                                   +-----------------------+
```

In development, Vite replaces nginx and proxies `/api` to
`http://127.0.0.1:8000`. In Compose and Kubernetes, nginx serves the built
frontend and proxies `/api` and the health endpoints to the API.

The API is not published directly in the Docker deployment. The single
browser-facing port serves the frontend, API proxy, and health endpoints.

## Design constraints

- **One household, no child accounts.** Profile selection is a convenience for
  a shared device, not authentication. Child-facing endpoints are intentionally
  unauthenticated.
- **Exactly one backend process.** SQLite permits one writer, and the API
  process owns the rollover scheduler. Do not run multiple Uvicorn workers, add
  a backend autoscaler, or run two backend replicas against one database file.
- **Forward-only schema history.** Alembic migrations are explicit and applied
  before the API starts. The application never migrates on startup, and
  readiness fails until the schema head matches.
- **History is immutable.** Assignments, their checklist snapshots, completion
  history, and weekly reports are protected by database triggers. Catalog edits
  never rewrite past weeks.
- **Presentation is separate.** Themes read existing data and persist only a
  per-identity theme preference. No theme changes assignment, completion,
  report, or authentication behavior.

## Backend layers

The backend follows a ports-and-adapters structure. Architecture tests enforce
the dependency direction.

| Layer | Location | Responsibility |
| --- | --- | --- |
| API | `src/chore_tracker/api/routes/` | HTTP endpoints, request validation, response mapping, dependencies |
| Application | `src/chore_tracker/application/services/` | Business rules, use cases, scheduling policy, domain errors |
| Adapters | `src/chore_tracker/adapters/sqlite/` | SQLite queries, transactions, readiness probes |
| Configuration | `src/chore_tracker/config.py` | Typed environment, secret-file loading, environment validation |
| Composition | `src/chore_tracker/main.py` | Wires services into FastAPI application state |
| Entry point | `src/chore_tracker/__main__.py` | Runs Uvicorn with the configured host, port, and development reload |

The `api` layer must not reach into SQLite directly, and the application layer
must not import FastAPI. The migration tests and architecture tests in
`tests/architecture/` guard both rules.

## Frontend structure

The frontend is React 19, TypeScript, Vite, and the ReShaped component library.
React Router provides browser routes:

| Route | Purpose |
| --- | --- |
| `/` | Child profile selection, current assignment, checklist, and completion history |
| `/admin` | First-run setup, passkey sign-in, family/chore management, administrator invitation |
| `/admin/reports` | Administrator-only report history |
| `/admin/reports/:weekStart` | Administrator-only report detail with entry pagination |
| `/admin/enroll#token=...` | Second-administrator passkey enrollment |

The family and administrator theme contexts are separate. A child's saved theme
never affects signed-in administrator screens, and an administrator's theme
never affects family screens. See [Themes](themes.md).

Browser storage is limited to convenience:

- `chore-tracker.theme.last-child` restores the last child only after that child
  has a saved theme.
- `chore-tracker.theme.child.<id>` and `chore-tracker.theme.admin.<id>` cache
  the last known theme per identity.
- `chore-tracker.theme.last-theme` is a bootstrap mirror used before React
  paints.

Server responses reconcile the cache. An unset or unavailable theme falls back
to Homestead in the frontend; the API stores and returns the raw value.

## Data model

All timestamps are stored as UTC text. Local dates are ISO calendar dates in
`CHORE_TRACKER_REPORT_TIMEZONE`.

### Catalog and identity

| Table | Purpose |
| --- | --- |
| `administrators` | Administrator email, active flag, and saved theme |
| `administrator_passkey_credentials` | WebAuthn credential ID, public key, signature counter, and transport metadata |
| `administrator_sessions` | Hashed opaque session tokens with expiry |
| `authentication_challenges` | One-use registration/authentication challenges with expiry |
| `administrator_enrollment_tokens` | One-use second-administrator invitation tokens |
| `family_members` | Deactivatable child profiles and saved theme |
| `chores` | Deactivatable chore catalog entries |
| `chore_checklist_items` | Ordered, deactivatable checklist definitions |

No private key material is stored. A passkey's private key stays with the
authenticator.

### Assignment and completion history

| Table | Purpose |
| --- | --- |
| `assignment_rotation_state` | The immutable rotation anchor: the first generated Monday |
| `weekly_assignment_generations` | Which weeks have been generated and their anchor |
| `weekly_assignments` | One immutable assignment per child and week, including chore name/description snapshots |
| `assignment_checklist_items` | Ordered checklist label snapshots for an assignment, optionally linked to a source catalog item |
| `daily_checklist_completions` | One row per assignment checklist item and local calendar date |

The assignment tables are protected against updates and deletes. The
`source_checklist_item_id` link is informational: removing a catalog item sets
only that link to `NULL`; the snapshot label and completion rows remain.

Completion rows are constrained to the assignment's Monday-Sunday week by
database triggers. Reads do not create completion rows. A date with no saved
row is `not_yet_recorded` in history and `not_recorded` in derived statistics.

### Weekly reports

| Table | Purpose |
| --- | --- |
| `weekly_reports` | One immutable report per week with family-wide totals and timestamps |
| `weekly_report_entries` | Per-assignment snapshot: child name, chore name/description, weekly totals |
| `weekly_report_days` | Seven `complete` or `incomplete` statuses per entry |
| `report_deliveries` | Reserved durable per-administrator delivery state; email delivery is optional and not implemented in the MVP |

A report is generated from persisted assignment snapshots and completion rows,
not from the current catalog. It is written in one transaction. Reports and all
descendant rows are immutable. Only finalized reports are readable through the
API.

### Rollover state

| Table | Purpose |
| --- | --- |
| `weekly_rollover_state` | Single-row durable checkpoint: newest week whose report and assignments both committed |

The checkpoint cannot move backwards or be deleted. This is what makes missed
Mondays recoverable after a restart.

## Invariants

These contracts are enforced in code, tests, and database triggers.

1. **Assignment snapshots are immutable.** Chore name, description, checklist
   labels, and order remain as assigned even after catalog edits or
   deactivation.
2. **Completion history is append/update-only per item and date.** Unchecking
   one item does not remove other items' records or other dates.
3. **Report snapshots are immutable.** Repeated generation for a week returns
   the existing report; it never replaces data.
4. **Completion dates stay inside the assignment week.** The database rejects
   out-of-week rows.
5. **The rotation anchor never changes.** Later weeks use the original anchor
   and the then-current active catalog.
6. **The rollover checkpoint advances only after both steps commit.** A failure
   leaves earlier committed work readable and safely retryable.
7. **A week is generated at most once.** Unique constraints and idempotent
   service behavior prevent duplicate assignments and reports.
8. **Unknown or retired theme ids never block use.** The frontend falls back to
   Homestead; the API returns the raw stored value.

## Weekly rotation

The full algorithm is in [Weekly rotation policy](weekly-rotation.md). The
short version:

- Active members and chores are ordered case-insensitively by name, then ID.
- The anchor is the first Monday on or after the initial generation date.
- For member index `i` and whole weeks since the anchor `W`, the assigned chore
  position is `(W + i) modulo M`, where `M` is the active chore count.
- Generation requires at least as many active chores as active members.
- Catalog changes affect the next generated week, never an existing assignment.

## Weekly rollover

The API process owns the schedule. It runs at
`CHORE_TRACKER_REPORT_DELIVERY_TIME` (default Monday 03:00) in
`CHORE_TRACKER_REPORT_TIMEZONE`.

For assignment week `W`:

1. Generate and commit the report for `W - 1`, the week that just ended.
2. Generate and commit the assignment set for `W`.
3. Advance the durable checkpoint to `W`.

Each step has its own SQLite transaction. If a step fails, earlier committed
work remains readable, the checkpoint does not advance, and the next attempt
repeats the failed step. Report and assignment generation return existing
records for an already-processed week rather than duplicating or replacing
them.

On first run with no checkpoint, only the most recent due Monday is processed.
After later downtime, every unprocessed Monday up to the latest due delivery
time is replayed in order. Failed attempts retry after five minutes while the
process runs; every restart checks for missed weeks again. The scheduler
rechecks the wall clock at least hourly so a suspended process or clock change
does not skip a due Monday.

Only one API process may run this scheduler against a database. If you disable
`CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED`, another process must own the schedule,
or assignments and reports will not be generated.

## Health and readiness

- `GET /health/live` reports process liveness and never opens SQLite. Use it for
  container liveness and process supervision.
- `GET /health/ready` (and its alias `GET /health`) checks that the database
  file exists, is accessible, and has the current Alembic revision. It returns
  HTTP 503 with `{"status":"not_ready"}` otherwise.
- A healthy response is HTTP 200 with `{"status":"ok"}`.
- Readiness responses do not expose filesystem paths or database errors.
- Email configuration is optional and is not part of readiness. The startup
  log records whether email delivery is disabled, uses the console transport,
  or uses SMTP.
- Apply migrations before expecting readiness. The application never migrates
  during startup.

## Deployment shape

| Environment | Frontend | Backend | Database |
| --- | --- | --- | --- |
| Development | Vite on port 5173 | Uvicorn on port 8000 with reload | `./data/chore-tracker.db` |
| Compose | nginx on published port 8080 | One container on internal network | Named `chore-tracker-data` volume |
| Kubernetes | nginx Deployment | One backend replica, `Recreate` strategy | ReadWriteOnce PVC |

In Compose and Kubernetes, a one-shot migration step runs before the API:
the Compose `migrate` service and the Kubernetes init container. Both apply
`alembic upgrade head`. See [Deployment](deployment.md).
