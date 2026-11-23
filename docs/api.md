# API

The API is a FastAPI application. Interactive documentation is available from a
running instance at `/docs`, and the machine-readable schema is at
`/openapi.json`.

## Conventions

- Paths below are API paths. In development the frontend proxies `/api/*` to
  the API and strips the prefix, so a browser call to `/api/themes` reaches
  `/themes`. In Docker and Kubernetes, nginx performs the same proxy.
- Child-facing endpoints are intentionally unauthenticated. They use the
  household trust model: profile selection is not authentication.
- Administrator endpoints require the `chore_tracker_session` cookie. The
  session token is opaque, stored hashed in SQLite, `HttpOnly`,
  `SameSite=Strict`, and `Secure` when the configured passkey origin uses HTTPS.
- Administrator state-changing requests also require an `Origin` header that
  exactly matches `CHORE_TRACKER_PASSKEY_ORIGIN`. A mismatch returns HTTP 403
  with `{"detail":"Request origin is not allowed"}`.
- Errors use FastAPI's standard shape: `{"detail":"..."}`. Validation errors
  return HTTP 422 with FastAPI's structured detail list.
- Local calendar dates are ISO `YYYY-MM-DD` values interpreted in
  `CHORE_TRACKER_REPORT_TIMEZONE`. Do not send UTC timestamps for completion
  dates.
- ISO timestamps in responses are UTC and end in `Z`.
- Pagination parameters are validated: `limit` must be within the documented
  range and `offset` must be non-negative.

## Child-facing endpoints

These endpoints do not create assignments. The weekly rollover must have
generated the relevant week first.

### List active family members

```http
GET /family-members/active
```

Returns active profiles ordered by case-insensitive display name, then ID:

```json
[
  {
    "id": 1,
    "display_name": "Alex",
    "theme_id": null
  },
  {
    "id": 2,
    "display_name": "Sam",
    "theme_id": "quest"
  }
]
```

`theme_id` is the raw saved value or `null` when the child has never saved a
theme. The frontend interprets unknown or unavailable values as Homestead.

### Get the current assignment

```http
GET /family-members/{family_member_id}/current-assignment
```

Returns the selected active child's assignment for the current Monday-Sunday
week, including immutable chore snapshots and today's checklist state:

```json
{
  "id": 42,
  "family_member_id": 1,
  "week_start": "2026-11-23",
  "week_end": "2026-11-29",
  "chore_name": "Kitchen",
  "chore_description": "Reset the kitchen after dinner",
  "today": "2026-11-25",
  "checklist_items": [
    { "id": 101, "label": "Wipe counters", "position": 0, "is_completed": true },
    { "id": 102, "label": "Take out trash", "position": 1, "is_completed": false }
  ],
  "is_complete": false
}
```

`is_complete` is true only when every checklist item is complete for `today`.
The endpoint returns HTTP 404 when the profile does not exist or has no current
assignment, and HTTP 409 when the profile exists but is inactive.

### Get a child's derived statistics

```http
GET /family-members/{family_member_id}/derived-stats
```

Returns theme-neutral completion facts. The response is read-only, computed per
request, and not cached or persisted. Unknown profiles return HTTP 404;
inactive profiles return HTTP 409, matching current-assignment behavior.

```json
{
  "family_member_id": 1,
  "display_name": "Alex",
  "as_of": "2026-11-25",
  "timezone": "America/Denver",
  "lifetime": {
    "completed_checklist_items": 124,
    "complete_days": 31,
    "current_streak": 4
  },
  "current_week": {
    "week_start": "2026-11-23",
    "week_end": "2026-11-29",
    "completed_checklist_items": 22,
    "complete_days": 3,
    "days": [
      {
        "date": "2026-11-23",
        "completed_checklist_items": 3,
        "total_checklist_items": 3,
        "state": "complete"
      },
      {
        "date": "2026-11-24",
        "completed_checklist_items": 1,
        "total_checklist_items": 3,
        "state": "incomplete"
      },
      {
        "date": "2026-11-25",
        "completed_checklist_items": 0,
        "total_checklist_items": 3,
        "state": "not_recorded"
      }
    ]
  },
  "household": {
    "active_players": 7,
    "weekly_standings": [
      {
        "family_member_id": 2,
        "display_name": "Sam",
        "completed_checklist_items": 28,
        "complete_days": 4,
        "current_streak": 2
      }
    ]
  }
}
```

Field semantics:

- `lifetime.completed_checklist_items` counts persisted completion rows with
  `is_completed = true` across all assignments. It does not consult the current
  catalog.
- `lifetime.complete_days` counts assignment days where every immutable
  checklist snapshot item was complete.
- `lifetime.current_streak` counts consecutive complete days ending today, or
  ending yesterday when today is not complete. It is zero when neither day is
  complete.
- `current_week.days` always has seven entries. `state` is `complete`,
  `incomplete`, or `not_recorded`. A day with no persisted rows is
  `not_recorded` and is never complete.
- `household.weekly_standings` includes every active child, ordered by
  current-week completed items descending, current streak descending, then
  case-insensitive display name ascending. It has no rank field.
- Weekly values reset at the Monday boundary in the reporting timezone.

Themes map these facts in their presentation layer:

- **Quest** uses `XP = 10 × lifetime.completed_checklist_items` and
  `level = 1 + floor(XP / 500)`. Current-week XP is `10 ×
  current_week.completed_checklist_items`; rank, player count, and XP gap to
  first come from the order of `household.weekly_standings`.
- **Sticker Club v2** uses `current_week.complete_days` as its sticker count and
  `current_week.days` as its seven-slot week rail. It ignores weekly standings.

The themes never write derived data.

### Get checklist completion for a date

```http
GET /family-members/{family_member_id}/assignments/{assignment_id}/completion?completion_date=YYYY-MM-DD
```

Returns the assignment's checklist and completion state for one local calendar
date:

```json
{
  "assignment_id": 42,
  "completion_date": "2026-11-25",
  "checklist_items": [
    { "id": 101, "label": "Wipe counters", "position": 0, "is_completed": true },
    { "id": 102, "label": "Take out trash", "position": 1, "is_completed": false }
  ],
  "is_complete": false
}
```

Reads do not create completion rows. A date with no saved state returns every
item unchecked. The date must fall within the assignment's Monday-Sunday week,
otherwise the endpoint returns HTTP 422. Unknown family members, assignments, or
checklist items return HTTP 404; an inactive family member returns HTTP 409.

### Set checklist completion for a date

```http
PUT /family-members/{family_member_id}/assignments/{assignment_id}/checklist-items/{checklist_item_id}/completion
Content-Type: application/json

{ "completion_date": "2026-11-25", "is_completed": true }
```

The write is idempotent and returns the updated item plus the aggregate daily
state:

```json
{
  "assignment_id": 42,
  "completion_date": "2026-11-25",
  "checklist_item": {
    "id": 101,
    "label": "Wipe counters",
    "position": 0,
    "is_completed": true
  },
  "is_complete": false
}
```

Unchecking one item updates only that item's row for that date; records for
other items and other dates remain. Completion writes acquire a SQLite write
reservation before reading and updating, so concurrent requests serialize.
Status codes match the read endpoint.

### Get completion history

```http
GET /family-members/{family_member_id}/completion-history?limit=50&offset=0
```

Returns historical daily records for every persisted weekly assignment
belonging to the profile. Each assignment contributes one record per day in its
week, including days with no saved completion rows.

```json
{
  "items": [
    {
      "assignment_id": 42,
      "week_start": "2026-11-23",
      "week_end": "2026-11-29",
      "chore_name": "Kitchen",
      "chore_description": "Reset the kitchen after dinner",
      "completion_date": "2026-11-25",
      "completion_status": "incomplete"
    }
  ],
  "total": 14,
  "limit": 50,
  "offset": 0
}
```

- Records are ordered newest date first, with assignment ID as a deterministic
  tie-breaker.
- `limit` is 1-100 (default 50); `offset` is non-negative (default 0).
- `completion_status` is `complete` only when every snapshot item has a saved
  completed row; `incomplete` when at least one row exists but the full
  checklist is not complete; `not_yet_recorded` when no row exists.
- Historical records remain available after a profile or chore is deactivated.
  Catalog edits do not change assignment snapshots.
- An unknown profile returns HTTP 404. A known profile with no assignments
  returns HTTP 200 with an empty page.

## Theme endpoints

### List the theme catalog

```http
GET /themes
```

Public, ordered catalog:

```json
[
  {
    "id": "homestead",
    "name": "Homestead",
    "preview_image": "/theme-previews/homestead.png"
  },
  {
    "id": "quest",
    "name": "Quest",
    "preview_image": "/theme-previews/quest.png"
  },
  {
    "id": "sticker-club-v2",
    "name": "Sticker Club v2",
    "preview_image": "/theme-previews/sticker-club-v2.png"
  }
]
```

The API is the source of truth for available ids and preview paths. Preview
images are frontend assets. Homestead is the frontend fallback default.

### Set a child's theme

```http
PUT /family-members/{family_member_id}/theme
Content-Type: application/json

{ "theme_id": "quest" }
```

Idempotent. Returns `{"theme_id":"quest"}`. An unknown child returns HTTP 404,
an inactive child HTTP 409, and an unavailable theme HTTP 422. This endpoint
follows the unauthenticated household trust model.

### Set the signed-in administrator's theme

```http
PUT /auth/me/theme
Content-Type: application/json

{ "theme_id": "sticker-club-v2" }
```

Requires an authenticated administrator and the same-origin check. Idempotent;
returns the stored theme id. Preferences are stored per administrator row.
Unavailable themes return HTTP 422. See [Themes](themes.md) for the full
preference and caching behavior.

## Authentication endpoints

All `POST` authentication endpoints require the same-origin check.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/auth/setup` | none | Report `{"setup_required": bool, "enrollment_pending": bool}` |
| `POST` | `/auth/setup/start` | none | Claim the initial administrator and start passkey registration |
| `POST` | `/auth/setup/finish` | none | Verify the registration and create a session |
| `POST` | `/auth/login/options` | none | Start passkey authentication for an email |
| `POST` | `/auth/login/finish` | none | Verify authentication and create a session |
| `GET` | `/auth/me` | admin | Return the signed-in administrator, including `theme_id` |
| `PUT` | `/auth/me/theme` | admin + origin | Save the administrator theme |
| `POST` | `/auth/logout` | origin | Delete the session and clear the cookie |
| `POST` | `/auth/administrators` | admin + origin | Create a second-administrator enrollment invitation |
| `POST` | `/auth/enrollment/options` | origin | Start passkey enrollment from an invitation token |
| `POST` | `/auth/enrollment/finish` | origin | Verify enrollment and create a session |

Request shapes:

```json
{ "email": "admin@example.test" }
```

for setup, login, and administrator creation, and:

```json
{ "token": "one-time-enrollment-token" }
```

for enrollment options.

`setup/start`, `login/options`, and `enrollment/options` return a
`challenge_id` plus WebAuthn `options`. The browser passes the credential to the
matching `finish` endpoint:

```json
{ "challenge_id": "...", "credential": { } }
```

`POST /auth/administrators` returns `{"enrollment_token":"..."}`. The frontend
builds a one-time link at `/admin/enroll#token=...`. The link expires after 24
hours and the application allows at most two administrator records.

Passkey challenges expire after five minutes and are consumed once. The server
validates registration and authentication against the configured relying-party
ID and exact origin. Only credential IDs, public keys, signature counters, and
transport metadata are stored. See
[Administrator bootstrap and passkeys](operations.md#administrator-bootstrap-and-passkeys).

Common authentication errors:

| Status | Meaning |
| --- | --- |
| 401 | Authentication required, no enrolled administrator, or authentication failed |
| 403 | Origin does not match the configured passkey origin |
| 404 | Administrator email not found for sign-in |
| 409 | Setup already claimed/completed, duplicate email, credential duplicate, or administrator limit reached |
| 400 | Invalid, expired, reused, or unverifiable challenge/invitation |
| 422 | Invalid email or theme id |

## Administrator family-management endpoints

These require an administrator session; mutations also require the
same-origin check.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/family-members` | List all profiles, including inactive |
| `POST` | `/family-members` | Create a profile |
| `GET` | `/family-members/{family_member_id}` | Read one profile |
| `PATCH` | `/family-members/{family_member_id}` | Rename or activate/deactivate |

Create body:

```json
{ "display_name": "Alex", "is_active": true }
```

Update body accepts either field; at least one is required:

```json
{ "display_name": "Alexandra", "is_active": false }
```

Display names are trimmed and limited to 100 characters. Duplicate display
names are allowed. Inactive profiles keep their historical assignments and
completion records. There is no delete operation.

Status codes: unknown profile 404; blank, too long, empty update, or null field
422.

## Administrator chore-management endpoints

These require an administrator session; mutations also require the
same-origin check.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/chores` | List chores with ordered checklist items |
| `POST` | `/chores` | Create an inactive chore |
| `GET` | `/chores/{chore_id}` | Read one chore |
| `PATCH` | `/chores/{chore_id}` | Update name, description, or active state |
| `POST` | `/chores/{chore_id}/checklist-items` | Add a checklist item |
| `PATCH` | `/chores/{chore_id}/checklist-items/{item_id}` | Update label or active state |
| `DELETE` | `/chores/{chore_id}/checklist-items/{item_id}` | Delete a checklist item |
| `PUT` | `/chores/{chore_id}/checklist-order` | Reorder every checklist item |

Create body:

```json
{ "name": "Kitchen", "description": "Reset the kitchen after dinner" }
```

New chores are always created inactive. A chore cannot be activated until it has
at least one active checklist item, and an active chore must be deactivated
before its last active checklist item can be deactivated or removed.

Checklist item bodies:

```json
{ "label": "Wipe counters" }
```

```json
{ "label": "Wipe counters", "is_active": true }
```

Reorder body must contain every checklist item for the chore exactly once:

```json
{ "ordered_item_ids": [3, 1, 2] }
```

Catalog changes never update assignment snapshots or daily completion records.
Deleting a catalog item only clears the historical snapshot's
`source_checklist_item_id` reference through `ON DELETE SET NULL`; the snapshot
label and completion history remain. There is no chore delete operation;
deactivate instead.

Status codes: unknown chore or item 404; invalid/blank/too-long values, duplicate
or incomplete order 422; activation without an active item 422; removing the
last active item from an active chore 409.

## Weekly report endpoints

These require an administrator session and are read-only. Reports are created
only by the Monday rollover. Unauthenticated requests return HTTP 401.

### List report headers

```http
GET /reports
```

Returns finalized report headers newest week first:

```json
[
  {
    "id": 7,
    "week_start": "2026-11-16",
    "week_end": "2026-11-22",
    "generated_at": "2026-11-23T10:00:00Z",
    "summary": {
      "family_member_count": 2,
      "total_days": 14,
      "completed_days": 10,
      "incomplete_days": 4
    }
  }
]
```

### Get one report

```http
GET /reports/{week_start}?limit=25&offset=0
```

Returns one finalized report header plus a bounded page of entries:

```json
{
  "id": 7,
  "week_start": "2026-11-16",
  "week_end": "2026-11-22",
  "generated_at": "2026-11-23T10:00:00Z",
  "summary": {
    "family_member_count": 2,
    "total_days": 14,
    "completed_days": 10,
    "incomplete_days": 4
  },
  "entries": [
    {
      "id": 12,
      "family_member_name": "Alex",
      "chore_name": "Kitchen",
      "chore_description": "Reset the kitchen after dinner",
      "completed_days": 7,
      "incomplete_days": 0,
      "days": [
        { "date": "2026-11-16", "status": "complete" },
        { "date": "2026-11-17", "status": "complete" }
      ]
    }
  ],
  "total": 2,
  "limit": 25,
  "offset": 0
}
```

`limit` is 1-100 (default 25), and `offset` is non-negative. Each entry always
contains seven day rows. Values are read from the persisted report snapshot,
never recalculated from current household data. An unknown week returns HTTP
404. Invalid pagination returns HTTP 422.

The administrator UI uses five entries per page, but the API allows up to 100.

## Health endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health/live` | Process liveness; does not access SQLite |
| `GET` | `/health/ready` | SQLite accessibility and current Alembic revision |
| `GET` | `/health` | Alias for readiness |

Healthy responses are HTTP 200 `{"status":"ok"}`. Readiness returns HTTP 503
`{"status":"not_ready"}` when the database is unavailable or its schema is not
current. Readiness never exposes paths or database errors. Apply migrations
explicitly with `alembic upgrade head` before expecting readiness.
