# Backup and restore

The SQLite database is the only durable application state. A backup restores
the family and chore catalog, administrator records and passkey metadata, the
rotation anchor, all weekly assignments and checklist snapshots, every daily
completion, every weekly report and day snapshot, every report reward record,
and the rollover checkpoint.

Private passkey keys are not in the database; they stay on the authenticator.
Restoring a database restores the credential records that were present when the
backup was taken, so a passkey enrolled later will no longer be known until a
backup containing it is restored.

The procedure in this guide is exercised by
[`scripts/verify-backup-restore.sh`](../scripts/verify-backup-restore.sh). Run
it after changing backup, migration, or restore behavior.

## Backup rules

- Back up before every upgrade, migration, restore, or risky operator action.
- Use SQLite's online backup API while the application is running, or stop the
  backend first and copy the file. Do not copy a live database file with `cp`;
  an active transaction or journal can make the copy inconsistent.
- Store backups outside the container, volume, and host that runs the app.
- Treat backups as sensitive household data even though passkey private keys are
  not present.
- Verify a backup by opening it read-only and running `PRAGMA integrity_check`
  and `PRAGMA foreign_key_check`. A file that exists is not automatically a
  usable backup.
- Keep at least one pre-upgrade backup and enough history to recover from a
  mistaken catalog change or a bad deploy. The application has no built-in
  retention or scheduling for backups.

## Host or local process

The default database path is `./data/chore-tracker.db`. The path can be
overridden with `CHORE_TRACKER_DATABASE_PATH`.

### Back up

With the API running, use the same SQLite backup API the verification script
uses:

```bash
python - <<'PY'
import sqlite3
from pathlib import Path

source_path = Path("data/chore-tracker.db")
backup_path = Path("chore-tracker-backup.db")

source = sqlite3.connect(source_path)
target = sqlite3.connect(backup_path)
try:
    source.backup(target)
finally:
    target.close()
    source.close()

with sqlite3.connect(backup_path) as check:
    assert check.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert check.execute("PRAGMA foreign_key_check").fetchall() == []
print(f"verified backup: {backup_path}")
PY
```

Copy the verified backup to durable storage. If the API is stopped, a plain
file copy of the database is also consistent, but the backup API is safe in both
cases and is the recommended procedure.

### Restore

1. Stop the API process so nothing writes to the database.
2. Preserve the current file instead of deleting it:

   ```bash
   mv data/chore-tracker.db data/chore-tracker.db.before-restore
   ```

3. Copy the verified backup into place and make sure the process user can read
   and write it:

   ```bash
   cp chore-tracker-backup.db data/chore-tracker.db
   ```

4. Confirm integrity and schema revision:

   ```bash
   python - <<'PY'
   import sqlite3

   with sqlite3.connect("data/chore-tracker.db") as connection:
       assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
       assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
   print("database integrity ok")
   PY

   alembic current
   ```

5. If the backup predates the current schema, apply migrations:

   ```bash
   alembic upgrade head
   ```

6. Start the API and check readiness:

   ```bash
   python -m chore_tracker
   curl --fail http://127.0.0.1:8000/health/ready
   ```

7. Sign in at `/admin`, open **Reports**, and verify a report from before the
   backup is present. Select a child and confirm their current assignment and
   history.

## Docker Compose

The database is stored at `/data/chore-tracker.db` on the named
`chore-tracker-data` volume. The `migrate` service and the backend share it.

### Back up

With the stack running:

```bash
docker compose --env-file .env.docker exec -T backend python - <<'PY'
import sqlite3

source = sqlite3.connect("/data/chore-tracker.db")
target = sqlite3.connect("/tmp/chore-tracker-backup.db")
try:
    source.backup(target)
finally:
    target.close()
    source.close()
PY

docker compose --env-file .env.docker cp \
  backend:/tmp/chore-tracker-backup.db ./chore-tracker-backup.db
```

Verify the downloaded file with the host procedure above, then move it to
durable storage. The temporary copy inside the container is not durable.

### Restore

1. Stop the backend so nothing writes to the volume:

   ```bash
   docker compose --env-file .env.docker stop backend
   ```

2. Copy the verified backup into the volume with a one-off container. The
   `--no-deps` flag avoids starting the migration service early, and the bind
   mount only needs read access to the host backup:

   ```bash
   docker compose --env-file .env.docker run --rm --no-deps \
     -v "$PWD:/backup:ro" \
     backend python -c "import shutil; shutil.copyfile('/backup/chore-tracker-backup.db', '/data/chore-tracker.db')"
   ```

3. Start the stack normally. The `migrate` service applies any newer migrations
   before the backend starts:

   ```bash
   docker compose --env-file .env.docker up --detach --wait
   curl --fail http://localhost:8080/health/ready
   ```

4. Sign in and verify reports and history as above.

If the restore fails or the wrong file was copied, stop the backend and repeat
with the preserved volume data. Keep the pre-restore volume contents when
practical; `docker compose down --volumes` deletes the volume and is never part
of a normal restore.

## Kubernetes

The chart persists the database on a ReadWriteOnce PVC at
`/data/chore-tracker.db` and runs migrations in an init container. The chart
README has the full installation and rollback context:
[Helm chart README](../deploy/kubernetes/chore-tracker/README.md).

### Back up online

Use SQLite's backup API inside the running backend pod, then copy the file out:

```bash
namespace=chore-tracker
pod="$(kubectl --namespace "${namespace}" get pod \
  -l app.kubernetes.io/component=backend \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl --namespace "${namespace}" exec -i "${pod}" -- python - <<'PY'
import sqlite3

source = sqlite3.connect("/data/chore-tracker.db")
target = sqlite3.connect("/tmp/chore-tracker-backup.db")
try:
    source.backup(target)
finally:
    target.close()
    source.close()
PY

kubectl --namespace "${namespace}" cp \
  "${pod}:/tmp/chore-tracker-backup.db" ./chore-tracker-backup.db
```

Verify the file on the host and store it outside the cluster. PVC snapshots are
also suitable when the StorageClass supports them; a cold copy after scaling the
backend to zero is acceptable for a small homelab, but the online backup avoids
downtime.

### Restore

Restoring while the backend is running is not supported. Use a temporary pod
that mounts the same PVC, replace the file, remove the helper, and scale the
backend back up.

1. Identify the claim. The chart's default claim is named after the release, for
   example `chore-tracker-data`; an existing claim keeps its own name:

   ```bash
   kubectl --namespace chore-tracker get pvc
   ```

2. Scale the backend to zero and wait for the pod to terminate:

   ```bash
   kubectl --namespace chore-tracker scale deployment/chore-tracker-backend --replicas=0
   kubectl --namespace chore-tracker wait --for=delete pod \
     -l app.kubernetes.io/component=backend --timeout=120s
   ```

3. Create a temporary restore pod with the same backend image and claim. Replace
   the image tag with the version you run, and the claim name if it differs:

   ```bash
   kubectl --namespace chore-tracker apply -f - <<'YAML'
   apiVersion: v1
   kind: Pod
   metadata:
     name: chore-tracker-restore
   spec:
     restartPolicy: Never
     securityContext:
       runAsNonRoot: true
       runAsUser: 10001
       runAsGroup: 10001
       fsGroup: 10001
     containers:
       - name: restore
         image: ghcr.io/lightguard/chore-tracker-backend:1.2.3
         command: ["sleep", "3600"]
         volumeMounts:
           - name: data
             mountPath: /data
     volumes:
       - name: data
         persistentVolumeClaim:
           claimName: chore-tracker-data
   YAML

   kubectl --namespace chore-tracker wait --for=condition=Ready \
     pod/chore-tracker-restore --timeout=120s
   ```

4. Copy the verified backup into the helper and replace the database file:

   ```bash
   kubectl --namespace chore-tracker cp \
     ./chore-tracker-backup.db chore-tracker-restore:/tmp/chore-tracker-backup.db

   kubectl --namespace chore-tracker exec chore-tracker-restore -- \
     sh -c 'cp /tmp/chore-tracker-backup.db /data/chore-tracker.db && chown 10001:10001 /data/chore-tracker.db'
   ```

5. Remove the helper and scale the backend back up:

   ```bash
   kubectl --namespace chore-tracker delete pod chore-tracker-restore
   kubectl --namespace chore-tracker scale deployment/chore-tracker-backend --replicas=1
   kubectl --namespace chore-tracker rollout status deployment/chore-tracker-backend
   ```

6. Check readiness and verify reports and history in the admin UI:

   ```bash
   kubectl --namespace chore-tracker exec deployment/chore-tracker-backend -- \
     python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/ready').read().decode())"
   ```

The new backend pod runs the migration init container again. If the backup
predates the current schema, the init container upgrades it before the API
starts.

## Verification script

Run the checked-in verification after changing backup, restore, or migration
behavior:

```bash
./scripts/verify-backup-restore.sh
```

The script:

1. creates a temporary database from the current migrations;
2. seeds two children, three chores, two weeks of assignments, daily
   completions, a finalized weekly report with a reward record, and a rollover
   checkpoint;
3. backs up with SQLite's online backup API and validates integrity;
4. renames the source database to simulate loss;
5. restores the backup;
6. compares a deterministic fingerprint of all history tables, including report
   reward records, between the backup and restored database;
7. asserts assignment, completion, report entry/day, reward, and checkpoint
   counts; and
8. reads the restored report and its reward through the application service.

Expected output:

```text
Applying migrations to a fresh sample database
Seeding a week of history, a finalized report, and rollover state
Backing up the database with SQLite's online backup API
Simulating loss of the source database and restoring the backup
Verifying the restored database
Backup and restore verification passed
  assignment rows: 4 (two weeks x two children)
  completion rows: 13
  weekly reports: 1 (2 entries, 14 day snapshots)
  report reward rows: 1
  report totals: 10/14 completed days
  rollover checkpoint: 2026-11-23
  data fingerprint: ...
```

The fingerprint line changes between runs because report generation timestamps
come from the clock. Within one run it is compared between the backup and the
restored database, so a mismatch means data was not retained. It is not a
secret and is not used for encryption.

## After a restore

1. Check readiness (`GET /health/ready`) before letting users back in.
2. Sign in as an administrator and confirm the expected reports are listed.
3. Open a report and spot-check the week, entries, daily statuses, and reward
   state. Reward records appear in the report detail view's **Reward** column.
4. Select a child and verify the current assignment and history.
5. Expect the scheduler to catch up any Mondays that were missed between the
   backup and the restore. This is safe and idempotent; the checkpoint prevents
   duplicate assignments and reports. See
   [Recovering a missed or failed rollover](operations.md#recovering-a-missed-or-failed-rollover).
6. If the restored database is older than the deployed schema, run
   `alembic upgrade head` before starting the application (the Compose and
   Kubernetes migration steps do this automatically).
7. Record the restore time and the backup used. A restore deliberately loses
   data created after the backup; communicate that data-loss point to the
   household.

## Upgrades and rollback

Take a backup before every image or schema upgrade. Migrations are forward-only;
`helm rollback` and image rollbacks do not downgrade SQLite. If an older image
cannot run against a newer schema, restore the pre-upgrade backup or deploy an
image that understands the current schema.

Practice the restore path on a test cluster or with the verification script
before relying on it during a real incident.
