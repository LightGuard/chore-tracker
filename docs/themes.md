# Themes

Themes are visual and layout variants over the same application data. They add
no persisted game state: a theme changes how assignment, checklist, history,
report, and completion facts are presented. The only theme data stored by the
application is a nullable preference on each family member and administrator.

## Catalog

The API is the source of truth for available themes. `GET /themes` returns
entries in display order:

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

`homestead`, `quest`, and `sticker-club-v2` are available. Homestead remains the
default. The backend catalog lives in
`src/chore_tracker/application/services/themes.py`; preview images are frontend
assets under `frontend/public/theme-previews/`.

Unknown or unset saved values are treated as Homestead by the frontend. The API
deliberately returns the raw saved value so the server remains the durable
source of truth. Never reuse an id for a different visual direction; saved ids
are durable.

Migration `0008_theme_preferences` adds nullable `theme_id` columns to
`family_members` and `administrators`. It does not assign a theme to existing
rows. There is no theme table; the catalog is application-owned.

## Preference behavior

### Family flow

The family flow is child-first. Before a child is selected, the page renders in
Homestead and the header theme control is disabled. A child with a saved theme
sees their assignment immediately after selection. A child with no valid saved
theme sees the Homestead-styled picker before any assignment content; choosing a
theme saves it immediately and reveals the assignment. Choosing another child
from the dismissible Switch child step leaves the current child active until a
new child is selected.

Header and picker changes use `GET /themes` for names and preview images. Header
changes save immediately for the active child. A failed save keeps the previous
theme and surfaces an actionable retry; a failed first-time picker save stays on
the picker.

`PUT /family-members/{family_member_id}/theme` is idempotent and follows the
unauthenticated household trust model. An unknown child returns 404, an inactive
child 409, and an unavailable theme 422.

### Administrator flow

Signed-in administrator screens follow the administrator's saved theme. The
shared header, theme switcher, and preference API are the same ones used by the
family flow; changing the theme re-renders the signed-in layout immediately and
keeps the choice after reload. A selected child's theme is never consulted for
administrator screens.

`PUT /auth/me/theme` requires an authenticated administrator and the
same-origin check. Preferences are stored per administrator row. An unavailable
theme returns 422.

Pre-authentication initial setup, sign-in, and invitation acceptance remain on
the Homestead token styling regardless of an administrator's saved preference.
The signed-in layouts are desktop-first and reflow at tablet and phone widths
without page-level horizontal scrolling.

Family and administrator route contexts are separate. Child themes never theme
signed-in administrator screens, and administrator themes never theme family
screens. Signing out returns the administrator context to Homestead and disables
the theme control.

### Browser storage

Browser storage is limited to convenience and flash avoidance:

| Key | Purpose |
| --- | --- |
| `chore-tracker.theme.last-child` | Written only after a child has a saved theme; drives reload restoration |
| `chore-tracker.theme.child.<id>` | Cache of the last known theme for one child |
| `chore-tracker.theme.admin.<id>` | Cache of the last known theme for one administrator |
| `chore-tracker.theme.last-theme` | Small bootstrap mirror used before React paints |

Bundled child ids (`homestead`, `quest`, `sticker-club-v2`) can paint
immediately; other unknown ids are ignored. Server responses reconcile the
cache: a valid saved theme updates it, while an unset or unavailable theme
clears the per-identity entry and falls back to Homestead. Administrator
bootstrap remains Homestead until `/auth/me` confirms the administrator's saved
theme.

## Theme implementations

### Homestead

Homestead is the default warm paper ledger: a left index rail, serif headings,
ledger cards, and hand-note annotations. It is the fallback for unset or
unavailable preferences and the styling for pre-authentication administrator
screens.

### Quest

Quest is a dark co-op HUD for family-facing screens. It uses the shared header,
child selector, theme picker, assignment data, checklist writes, and completion
history; it adds presentation only. The selected child must have Quest saved for
the family screens to use it. Administrator screens keep the signed-in
administrator's theme and do not inherit a child's Quest selection.

Quest reads `GET /family-members/{family_member_id}/derived-stats` after a child
is selected and after each successful checklist change. The player HUD uses the
precomputed `lifetime.xp` and `current_week.xp` for XP and level, the
current-week days for the seven-day rail, the lifetime streak for the streak
strip, and the weighted weekly standings order for rank, player count, and XP
gap to first. A completed day shows the all-done "QUEST CLEAR" state; optional
checklist items contribute XP when checked but never block completion. The
shared payload also publishes `household.xp_rankings`, a family-wide
achievement rank derived from weighted total XP that is independent of the
weekly standings order and the child display order. Stats are never written by
the theme.

#### Quest XP mapping

Quest interprets the shared chore weight as XP per completed checklist item:

```text
XP = completed checklist items × chore weight × 10
```

The factor of 10 is Quest's base XP per item; the shared chore domain still
assigns no XP of its own. Quest reads the weight from the immutable assignment
snapshot (`chore_weight_snapshot`) rather than the live chore catalog, so
editing a chore's weight only affects future weeks. With the default weight of
1 this is the same 10 XP per completed item as before weights existed.

| Chore weight | XP per completed checklist item |
| --- | --- |
| 0 | 0 |
| 1 (default) | 10 |
| 2 | 20 |
| 5 | 50 |
| 10 | 100 |

Optional checklist items follow the same mapping. A weight-0 chore still
records completion, complete days, and streaks; it simply awards no XP. The
calculation lives in
`src/chore_tracker/application/services/quest_rewards.py`, and the derived-stats
endpoint exposes the resulting `xp` values so every Quest surface uses one
calculation. The Quest presentation constant `QUEST_XP_PER_ITEM_WEIGHT`
applies the
same factor to today's potential XP in the assignment HUD; keep the two in step
if the reward rate changes. The mapping is independent of the shared chore
domain, which continues to store only the neutral 0–10 weight.

The stats request is independent of the checklist. If it fails, the checklist
remains usable and the HUD shows an actionable retry; switching children clears
the previous child's stats before the new request resolves. Quest deliberately
has no seasons, currencies, shops, inventory, navigation, or other non-functional
controls.

### Sticker Club v2

Sticker Club v2 is the type-only Sticker Club concept: paper, ink, five sticker
colors, numbered jobs, and no person, chore, subtype, or animal pictograms. It
has no reward jar or collectible inventory. The theme uses the shared header,
child selector, theme picker, assignment/checklist writes, and completion
history.

The top bar always shows the current-week count as `N OF 7 STICKERS` with the
assistive label `N of 7 this week`. The only source is
`current_week.complete_days` from the generic derived-stat endpoint. A day is
worth one sticker when every required checklist item for that immutable
assignment day is complete; optional items never block the sticker. Incomplete
and `not_recorded` days earn none. Checking the
final item of today updates the seven-slot rail and count immediately from the
successful assignment mutation, then reconciles with the derived endpoint. The
count resets at the Monday boundary. `household.weekly_standings` is
intentionally ignored: this is a personal sticker sheet, not a leaderboard.

The seven-slot rail shows `DONE`, `PART`, or `—` in each slot so complete,
incomplete, and not-recorded days are distinguishable without color; today
receives an outline. The jobs live in a fixed-height scroll window with a
visible position rail. The all-done state uses the stamp language
`STICKER N OF 7`.

If the stats request fails, the assignment remains usable, the count shows a
placeholder rather than zero, and an actionable retry is offered. Switching
children clears the previous child's count before the new stats resolve. No
sticker count, inventory, reward, or collectible data is persisted; only the
existing theme preference is saved.

### Administrator layouts

Each theme has a distinct signed-in working layout:

- **Homestead:** paper ledger with a left index rail, serif headings, and
  ledger-style cards.
- **Quest:** dark command console with a lit navigation rail, clipped HUD
  surfaces, condensed headings, and lime/cyan status language.
- **Sticker Club v2:** type-only paper with a horizontal sticker-tag navigation
  strip, thick ink borders, hard shadows, and five-color content blocks.

The screens cover the signed-in shell and navigation, family member management,
chore and checklist management, report history, report detail/pagination, and
administrator invitation management. These are presentation changes only: no
administrator API, authorization, persistence, or workflow is changed. The
approved matrix and 18 reference screenshots are in
[design/admin](../design/admin/README.md).

## Fonts

All themes use bundled WOFF2 assets, not a font CDN:

| Theme / use | Font | Files |
| --- | --- | --- |
| Homestead headings | Source Serif 4 | `frontend/public/fonts/source-serif-4-*.woff2` |
| Homestead body | Nunito Sans | `frontend/public/fonts/nunito-sans-*.woff2` |
| Homestead handwritten notes | Caveat | `frontend/public/fonts/caveat-*.woff2` |
| Quest headings | Barlow Condensed | `frontend/public/fonts/barlow-condensed-*.woff2` |
| Quest body | Barlow | `frontend/public/fonts/barlow-*.woff2` |
| Sticker Club v2 display | Nunito | `frontend/public/fonts/nunito.woff2` |
| Sticker Club v2 body | Nunito Sans | `frontend/public/fonts/nunito-sans-*.woff2` |
| Small labels | JetBrains Mono | `frontend/public/fonts/jetbrains-mono-*.woff2` |

Font licenses are in `frontend/public/fonts/licenses/`; `fonts.css` declares the
self-hosted faces and is linked from `frontend/index.html`.

## Preview images

The committed phone assignment previews are:

- `frontend/public/theme-previews/homestead.png`
- `frontend/public/theme-previews/quest.png`
- `frontend/public/theme-previews/sticker-club-v2.png`

They are served from `/theme-previews/` and generated from the running frontend
against the deterministic preview fixtures in `frontend/e2e/backend_server.py`:

```bash
cd frontend
PREVIEW_BASE_URL=http://localhost:5174 npm run theme:preview
PREVIEW_THEME=quest PREVIEW_BASE_URL=http://localhost:5174 npm run theme:preview
PREVIEW_THEME=sticker-club-v2 PREVIEW_BASE_URL=http://localhost:5174 npm run theme:preview
```

The generation browser must be installed; set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` when using a pre-installed Chromium. Each
scripted fixture starts from a clean database and uses a deterministic
four-child assignment: Homestead uses three checklist items, Quest uses the
persisted completion history described above, and Sticker Club v2 uses two
complete days plus a partially complete today so its count and rail are
reproducible. The seven-child / six-checklist-item stress case remains a
separate test-only scenario.

Copy `frontend/.env.example` to `frontend/.env` to override the local frontend
defaults. Do not put secrets in `VITE_*` variables; those values are exposed to
browser code.

## Adding a theme

1. Add a stable lowercase id, display name, and frontend preview path to
   `THEME_CATALOG` in `src/chore_tracker/application/services/themes.py`.
2. Add the preview image under `frontend/public/theme-previews/`.
3. Add a scoped `theme-<id>` token block and layout rules in
   `frontend/src/styles.css`, keeping ReShaped components as the substrate.
4. Add the theme to backend API tests and frontend catalog fixtures, then cover
   its picker/dropdown rendering and responsive behavior.
5. If the theme derives presentation from completion facts, use
   `GET /family-members/{id}/derived-stats` rather than adding theme-specific
   persisted fields.
6. Never reuse an id for a different visual direction; saved ids are durable.

Theme tests must cover both family and administrator contexts. A child theme
must not leak into administrator screens, and an administrator theme must not
change the family flow.
