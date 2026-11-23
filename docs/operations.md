# Operations

This is the runbook for the household operator. It covers administrator setup,
family and chore configuration, the weekly report cycle, recovery, upgrades, and
the deployment contracts that keep history safe. For installation, see
[Deployment](deployment.md).

## Access model

| Audience | Entry point | Authentication |
| --- | --- | --- |
| Children and family | `/` | None; profile selection under the household trust model |
| Administrators | `/admin`, `/admin/reports` | Passkey session |
| Monitoring | `/health/live`, `/health/ready` | None |

The child-facing side is intentionally unauthenticated. Anyone who can reach
the app can choose a profile and change that day's checklist. Run the app on a
trusted home network, or put it behind TLS plus network-level access control if
it is reachable from outside the home.

Administrator routes, management APIs, and reports require a signed-in
administrator. There is no shared administrator password and no administrator
account supplied by environment variables.

## Administrator bootstrap and passkeys

### Before you begin

1. Apply migrations with `alembic upgrade head`.
2. Start the API and frontend.
3. Reach the app through the exact browser origin configured in
   `CHORE_TRACKER_APP_ORIGIN` and `CHORE_TRACKER_PASSKEY_ORIGIN`. For local
   development that is `http://localhost:5173`; use `localhost`, not
   `127.0.0.1`.
4. Make sure the browser supports passkeys/WebAuthn and the device has a
   platform authenticator, security key, or phone-based passkey available.

WebAuthn requires HTTPS except on `localhost`. For a LAN or public hostname,
terminate TLS in front of the app and set:

```bash
CHORE_TRACKER_APP_ORIGIN=https://chores.example.test
CHORE_TRACKER_PASSKEY_ORIGIN=https://chores.example.test
CHORE_TRACKER_PASSKEY_RP_ID=chores.example.test
```

`CHORE_TRACKER_PASSKEY_RP_ID` is the hostname only: no scheme, port, or path.

### Claim the first administrator

1. Open `/admin` in the browser.
2. If no administrator exists, the setup form asks for an email address.
3. Enter the address the administrator will use as their account identifier.
   The application does not send email at this stage; the address is a label and
   sign-in identifier.
4. Follow the browser's passkey prompt to create the credential.
5. The application creates the administrator and signs them in.

The initial claim is serialized by SQLite, so concurrent first visits cannot
create competing initial administrators. If registration is interrupted,
returning to setup with the same email resumes the pending enrollment; a
different email cannot take over it.

Do not put the administrator email or any credential in a committed file. The
only durable credential material is the passkey on the authenticator and the
non-secret credential metadata stored in SQLite.

### Invite the second administrator

The application supports at most two administrator records.

1. Sign in and open `/admin#administrator-access` (Administrator access).
2. Enter the second administrator's email.
3. Copy the one-time enrollment link immediately. The application displays the
   link; it does not send it by email.
4. Send the link to the second administrator through a channel you trust.
5. The second administrator opens the link, follows the passkey prompt, and is
   signed in.

The link expires after 24 hours and can be used once. The second administrator
should enroll before the link expires. If you lose the link before enrollment,
there is no reissue flow for that unenrolled record; restoring the database from
before the invitation, or an operator intervention in SQLite, is required. In
practice, create the invitation while the second administrator is ready.

### Sign in, session expiry, and sign out

- Sign-in uses the registered email plus the passkey. Challenges expire after
  five minutes and are consumed once.
- A session is an opaque token stored hashed in SQLite and sent as an
  `HttpOnly`, `SameSite=Strict` cookie. The cookie is `Secure` when the passkey
  origin uses HTTPS.
- When the session expires or is rejected, the administrator screen returns to
  sign-in with an explanation. Sign in again.
- Sign out deletes the session and clears the cookie. The saved theme
  preference is retained, but the unsigned-in view renders Homestead with the
  theme control disabled.

### Lost passkeys

There is no self-service passkey reset and no administrator password. Plan for
recovery:

- Enroll the second administrator before you need it, so one lost device does
  not lock out the household.
- Keep the backup procedure in [Backup and restore](backup-restore.md)
  practiced. Restoring a backup from before a lost credential restores the
  administrator rows and historical data to that point.
- If both passkeys are lost, the supported recovery is restoring a known-good
  backup or operator intervention in the SQLite database. Do not edit
  `administrator_passkey_credentials` or session rows without a backup and a
  clear understanding of the schema.

## Family and chore setup

Administrator setup and catalog changes happen at `/admin` under
**Family & chores**. All changes are administrator-only.

### Add family members

1. Open `/admin` and find **Family members**.
2. Enter a display name and choose whether the profile is active.
3. Save. Duplicate display names are allowed; the profile ID distinguishes
   them.

Inactive profiles are excluded from the child selector and from weekly
assignment generation. They keep their historical assignments and completion
records. Deactivating a profile is the supported way to retire it; there is no
delete operation.

### Add chores and checklist items

The rotation requires at least as many active chores as there are active
children. If there are fewer active chores, planning raises an error and the
week is not generated.

1. In **Chores**, create a chore with a name and optional description.
   New chores start inactive.
2. Add at least one checklist item.
3. Activate the chore. A chore cannot be activated without an active checklist
   item.
4. Repeat for each chore that should participate in the rotation.

The rotation uses only active chores and active checklist items. To retire a
chore, deactivate it. An active chore must be deactivated before its last active
checklist item can be deactivated or removed. Deletion of a catalog item is
allowed only when it is not the last active item of an active chore; the
historical snapshot keeps its label and completion rows.

Checklist order matters: the child sees the immutable snapshot order that was
captured when the weekly assignment was generated. Reordering later affects the
next generated week, not history.

### Initial setup order

Assignments are generated by the weekly rollover, not when you save a profile or
chore. Configure the family and catalog before the first rollover:

1. Apply migrations and start the application.
2. Claim the administrator.
3. Add every active family member.
4. Add every chore and its checklist items, then activate the chores.
5. Confirm there are at least as many active chores as active children.
6. Let the Monday rollover run.

If the application has already advanced the rollover checkpoint for a week,
catalog changes apply to the next generated week. There is no administrator
"generate now" control. To avoid the first-week gap on a new deployment, either
complete setup before the first scheduled Monday 03:00, or start with
`CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED=false`, configure the catalog, then
enable the scheduler and restart. On a fresh database with no checkpoint, the
restart processes the most recent due Monday and generates that week.

### Themes

Children choose a theme from the family flow; the choice is saved per profile.
Administrators choose a signed-in theme from the header. Theme preferences are
presentation-only and can be changed at any time. See [Themes](themes.md).

## Weekly cycle and reports

### What runs automatically

The API process owns the durable Monday rollover. By default it runs Monday at
03:00 in `CHORE_TRACKER_REPORT_TIMEZONE` (default `America/Denver`).

For assignment week `W` it:

1. generates the report for the week that just ended (`W - 1`);
2. generates assignments for `W`;
3. advances the durable checkpoint to `W`.

Reports are built from the persisted assignment snapshots and daily completion
rows. They are immutable snapshots, not live queries over current household
data. Report email is not implemented in the MVP; administrators view reports in
the UI.

### View reports

1. Sign in at `/admin`.
2. Open **Reports** (`/admin/reports`).
3. Select a week to see the summary, each child's assigned chore, all seven
   daily statuses, and weekly totals.
4. Use Previous/Next when a report has more than five entries.

The report list is newest week first. An empty state means no report has been
generated yet; it is expected before the first rollover completes.

Reports are readable only by authenticated administrators. The API returns HTTP
401 without a session. The records are persisted in SQLite and are included in
every database backup.

### Inspect persisted reports from the database

If the UI is unavailable, inspect the database read-only. Use the `sqlite3` CLI
on the configured database, or an equivalent read-only connection:

```bash
sqlite3 ./data/chore-tracker.db "
  SELECT week_start, week_end, generated_at,
         family_member_count, completed_days, total_days
  FROM weekly_reports
  ORDER BY week_start DESC;
"
```

```bash
sqlite3 ./data/chore-tracker.db "
  SELECT r.week_start, e.family_member_name_snapshot, e.chore_name_snapshot,
         e.completed_days, e.incomplete_days
  FROM weekly_report_entries e
  JOIN weekly_reports r ON r.id = e.report_id
  WHERE r.week_start = '2026-11-16'
  ORDER BY e.position;
"
```

```bash
sqlite3 ./data/chore-tracker.db "
  SELECT week_start, COUNT(*) AS assignments
  FROM weekly_assignments
  GROUP BY week_start
  ORDER BY week_start DESC;
"
```

```bash
sqlite3 ./data/chore-tracker.db "
  SELECT last_completed_week_start, completed_at
  FROM weekly_rollover_state;
"
```

These queries are read-only. Do not update or delete rows in
`weekly_assignments`, `assignment_checklist_items`,
`daily_checklist_completions`, `weekly_reports`, `weekly_report_entries`, or
`weekly_report_days`; triggers and application contracts assume they are
immutable. Do not delete the rollover checkpoint to force a rerun.

## Recovering a missed or failed rollover

### How the scheduler recovers itself

The scheduler is restart-safe:

- The checkpoint is durable in SQLite. It is not an in-memory timer.
- On startup, it checks the checkpoint and processes every unprocessed Monday up
  to the most recent due delivery time, in order.
- A failed attempt retries after five minutes while the process remains
  running.
- Every process restart checks for missed weeks again.
- Report and assignment generation are idempotent: an already-processed week
  returns existing records instead of creating duplicates.
- If the report step succeeds and the assignment step fails, the finalized
  report remains readable, the checkpoint does not advance, and the retry
  resumes safely. If the report step fails, no partial report is committed.

On a fresh database with no checkpoint, only the most recent due Monday is
processed. This is intentional first-run behavior, not a missed-week replay.

### Symptoms

- The expected report is missing from `/admin/reports`.
- The current week shows no assignment for an active child.
- Readiness is failing, so the scheduler has no valid schema to work against.
- Logs contain a rollover failure for a reporting or assignment week.

### Recovery procedure

1. **Check readiness.** `GET /health/ready` must return 200. If it returns 503,
   fix the database/migration problem first:
   - confirm `CHORE_TRACKER_DATABASE_PATH` points at the persistent database;
   - confirm the volume is mounted and writable;
   - run `alembic upgrade head` (the migration service or init container does
     this in container deployments);
   - then restart or let the process recover.
2. **Confirm the scheduler is enabled.** Check
   `CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED`; it must be `true` on the one process
   that owns the schedule.
3. **Read the logs.** Rollover logs include `reporting_week=`,
   `assignment_week=`, and `outcome=` values and do not include family member
   names. A failed outcome leaves earlier committed work intact.
4. **Restart the process.** Starting the API re-runs the startup catch-up:
   - host process: stop it and run `python -m chore_tracker` again;
   - Compose: `docker compose --env-file .env.docker restart backend`;
   - Kubernetes: `kubectl --namespace chore-tracker rollout restart
     deployment/chore-tracker-backend`.
5. **Wait for retry or startup catch-up.** While running, a failed attempt
   retries after five minutes. Startup catch-up runs immediately.
6. **Verify.** Use the admin report page and the read-only queries above to
   confirm:
   - the report row for `W - 1` exists and has entries/days;
   - the assignment rows for `W` exist for the expected children;
   - `weekly_rollover_state.last_completed_week_start` is at least `W`.
7. **Do not delete or rewrite history.** If the retry still fails, preserve the
   database, capture logs, and restore a backup only if the database is damaged.
   Deleting reports, assignments, or the checkpoint is not a supported repair.

### Recovery matrix

| Situation | Safe action |
| --- | --- |
| Report missing; process running | Wait for the five-minute retry, then restart if it still fails |
| Report missing; process restarted | Startup catch-up replays unprocessed Mondays |
| Report exists, current assignments missing | Checkpoint should not have advanced; restart to retry the assignment step |
| Readiness 503 | Fix the database/migrations first; the scheduler cannot safely run |
| Checkpoint at `W`, but assignments for `W` missing because the catalog was empty | Wait for the next Monday; configure the catalog before the next rollover. This is the catalog-timing limitation, not a failed retry |
| Database damaged | Restore the latest verified backup; see [Backup and restore](backup-restore.md) |
| Scheduler intentionally disabled | Re-enable it on exactly one process and restart; another process must not also run it |

## Upgrades and migrations

Alembic migrations are explicit, versioned, and forward-only. The application
never migrates automatically at startup, and readiness fails until the schema
is current.

### Before every upgrade

1. Take a verified backup. See [Backup and restore](backup-restore.md).
2. Note the current application version/commit and `alembic current` output.
3. Read the migration revisions being deployed.
4. Upgrade in a maintenance window. The backend must be single-instance, so
   there is no rolling backend upgrade.

### Host process

```bash
# Stop the API first if it is running.
alembic current
alembic upgrade head
alembic current
python -m chore_tracker
```

Then check `/health/ready` and open the admin report page.

### Docker Compose

The one-shot `migrate` service applies `alembic upgrade head` before the backend
starts. The backend waits for it to complete successfully.

```bash
docker compose --env-file .env.docker up --detach --build
docker compose --env-file .env.docker ps
curl --fail http://localhost:8080/health/ready
```

### Kubernetes

The chart runs migrations in an init container before the backend starts. Take a
backup first, update the image tags in your values file, then:

```bash
helm upgrade --install chore-tracker ./deploy/kubernetes/chore-tracker \
  --namespace chore-tracker \
  --values my-values.yaml \
  --wait --timeout 5m

kubectl --namespace chore-tracker rollout status deployment/chore-tracker-backend
```

If the init container or readiness probe fails, inspect the migration logs:

```bash
kubectl --namespace chore-tracker logs deployment/chore-tracker-backend -c migrate
```

Helm rollback rolls back Kubernetes objects, not the SQLite schema. If a newer
schema is incompatible with the older image, restore the pre-upgrade backup or
deploy an image that understands the newer schema. Practice this on a test
cluster before a homelab upgrade.

## Health and readiness

| Endpoint | Checks | Use |
| --- | --- | --- |
| `GET /health/live` | Process only; no SQLite access | Container liveness, process supervision |
| `GET /health/ready` | SQLite file exists, is accessible, and schema revision matches the current head | Traffic readiness, deploy gates, monitoring |
| `GET /health` | Alias for readiness | Backward-compatible checks |

Healthy responses are HTTP 200 `{"status":"ok"}`. Readiness returns HTTP 503
`{"status":"not_ready"}` when the database is unavailable or not migrated. The
response never includes paths or database errors.

The Docker image's own `HEALTHCHECK` uses liveness. Compose overrides it with
readiness so dependent services wait for migrations. Kubernetes uses liveness
and readiness probes against the matching endpoints. The frontend exposes
`/healthz` for its own static health and proxies `/health` and `/health/*` to
the API.

Recommended monitoring:

- alert when readiness has been failing for more than a few minutes;
- alert on container restart loops and disk pressure on the database volume;
- watch rollover logs for failed outcomes;
- verify backups are recent and restorable, not merely present.

## Backup, restore, and rollback

The SQLite database contains the entire application state:

- family and chore catalog;
- administrator records and passkey metadata (not private keys);
- the rotation anchor and weekly assignments;
- checklist snapshots and daily completion history;
- immutable weekly reports and day snapshots;
- the durable rollover checkpoint.

Back it up before every upgrade or risky operation. Full procedures, including
the tested verification script, are in
[Backup and restore](backup-restore.md).

## Known limitations

- **Unauthenticated children.** Child-facing endpoints have no authentication.
  Profile selection is a household convenience. Any client that can reach the
  app can act as any active child.
- **Single SQLite writer.** Run exactly one backend process. Do not run multiple
  Uvicorn workers, scale the backend above one replica, or point multiple
  instances at the same SQLite file. Kubernetes uses `Recreate` and a
  ReadWriteOnce volume for this reason.
- **No backend high availability.** An upgrade or pod replacement is a short
  outage. SQLite and the in-process rollover scheduler are not clustered.
- **No report email delivery.** SMTP settings are validated for deployment
  readiness, but the MVP does not send reports. Administrators read reports in
  the UI.
- **No manual rollover trigger.** Reports and assignments are generated by the
  scheduler. There is no admin button or CLI command to force a week. Configure
  the catalog before the first rollover.
- **At most two administrators and no passkey reset.** Enroll the second
  administrator as a recovery path. Lost invitations and lost passkeys require a
  backup restore or operator intervention.
- **Immutable history.** Assignments, their checklist snapshots, completions,
  and reports cannot be edited or deleted through the application. This is a
  deliberate auditability property; recovery is retry- and backup-based.
- **No email-based account recovery, no multi-family tenancy, no child
  identities.** These are out of scope for the MVP.
- **Themes are presentation only.** XP, levels, streaks, stickers, and
  standings are derived from completion facts and are not persisted game state.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Admin page asks for setup when an administrator exists | Inspect `administrators` and the enrollment state; setup is required only when there is no administrator or an unenrolled first administrator |
| Passkey prompt does not appear | Use HTTPS or `localhost`; check browser/device support and exact origin/RP ID |
| `Request origin is not allowed` | Browser origin must exactly match `CHORE_TRACKER_PASSKEY_ORIGIN` |
| Empty report history | The rollover has not completed yet, or the report step failed; check readiness and logs |
| Child sees "no assignment" | The week has not been generated. Check the checkpoint, active member/chore counts, and whether the catalog was configured after the checkpoint advanced |
| Readiness 503 after deploy | Migration service/init container failed, database path is wrong, volume is not mounted, or schema is not at head |
| Rollover keeps failing | Check readiness and logs; preserve the database and retry after the five-minute backoff. Restore only if the database is damaged |
| Database disk full | Free space on the volume, verify a recent backup, and restart after space is available |
| Report history is empty after restoring a backup | The backup predates the report; restore a later backup or accept the data loss point |

For setup and test commands, see [Development](development.md). For container
and cluster installation, see [Deployment](deployment.md).
