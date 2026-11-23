# Chore Tracker — UI directions

Phone-first design concepts for the existing React 19 + Reshaped app. **No application code was changed**; everything in this folder is standalone design material used to render the images.

Six passes: five broad directions, two focused options after feedback, a fantasy one-off, a more playful Wayfinder pass, a console-home/achievements experiment, and two seven-kid stress-test iterations.

## Interactive archive

The overview is now both a static board and a clickable gallery.

- **Live archive:** http://127.0.0.1:4173/ &mdash; served locally from this folder.
- Click a direction card to open its board.
- Inside the board, hover or focus the phone or desktop areas to reveal clickable hotspots; click one for the full-size screen.
- The screen thumbnails under the board open a lightbox; the board itself opens full-size.
- Filters: initial five, focused iteration, round 3, iterations, and "adds a layer."
- Deep links work: `#wayfinder`, `#homescreen`, etc. Arrow keys navigate; Escape closes.

Restart the server any time with:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory design
```

The archive is [index.html](index.html). The updated static overview is [boards/00-overview.png](boards/00-overview.png). It now carries eleven directions, including the two stress-test iterations.

## The directions

| # | Concept | One-liner | Best for |
|---|---------|-----------|----------|
| 01 | **Homestead** | Warm paper ledger, serif type, stamped all-done moment. | A cozy, low-key household. Easiest to land from the current UI. |
| 02 | **Sticker Club** | Collectible sticker chart with animal avatars, stars, and a reward jar. | Younger kids and reward-driven households. |
| 03 | **Still** | Calm focus mode: one chore, one progress ring, very little noise. | Kids who find loud dashboards stressful; parents who want a quiet report. |
| 04 | **Quest** | Dark co-op game HUD: XP, hex objectives, streaks, family leaderboard. | Older kids and teens. |
| 05 | **Ledger** | Editorial broadsheet: oversized Bodoni numerals, strict rules, archive. | A design-forward household; strongest admin report. |
| 06 | **Matchday** | A household sports club: team sheet, fixture card, form guide, full-time flag. | Mixed-age homes that want playful, teen-safe energy without a reward economy. |
| 07 | **Checkpoint** | Sticker Club × Quest: blue/acid zine energy, three checkpoints, a week log. | Mixed-age homes that want maximum personality without changing what the app tracks. |
| 08 | **Wayfinder** | Storybook guild board: shield party, icon trail, illustrated quest cards, moss-sprite guide. | Adventure/tabletop-loving families; playful for kids, atmospheric for teens. |
| 09 | **Homescreen** | Console-style family home: chore tiles, profiles, achievement shelf, dock. | A family that wants a game-console feel and explicit achievements. |
| 10 | **Sticker Club v2** | Type-only Sticker Club at 7 kids / 6 jobs; no person or chore pictograms. | A younger, reward-driven house with long lists. |
| 11 | **Quest Light** | Quest in daylight, stress-tested with 7 players and 6 objectives. | Older kids and teens who want game energy without the dark HUD. |

## Iteration 2 — what was intentionally left out

The feedback was clear: the playfulness of Sticker Club and Quest was working, but household/family goals were post-MVP. Matchday and Checkpoint were built to that constraint.

**They do not add:** XP, levels, currencies, reward jars, collectible sticker inventories, household goals, leaderboards, streaks, or any new persisted fields.

**They reuse:** profiles, the weekly chore and checklist, per-item daily completion, existing day completion/history, and the immutable weekly report. The only numbers on screen are today's checklist counts and the week that already exists.

## Wayfinder, round 2

The first Wayfinder pass was an illuminated parchment ledger. The feedback was that it felt too close to the other directions and not playful enough. This pass keeps the fantasy but changes the visual language: a colorful guild noticeboard, shield medallions, illustrated chore covers, icon tiles for sponge/broom/trash, stickered objective stamps, a moss-sprite guide, and a shared guild board instead of another report table.

It still adds no systems: party = profiles, quest = weekly chore, objectives = checklist, trail = daily completion. No XP, items, coins, inventory, goals, or leaderboards.

## Homescreen — achievements caveat

Homescreen is the intentional exception to the "existing data only" rule. It adds:

- a console-style home built around chore tiles and profiles;
- an achievement shelf and a dedicated achievements screen.

The achievements are derived from data the app already records &mdash; complete days, completed checklists, all four finishing on the same day, consecutive days. Suggested rules:

- **First Clear** &mdash; complete every item in one day.
- **Full House** &mdash; all four family members finish on the same day.
- **On a Roll** &mdash; three complete days in a row.
- **Perfect Week** &mdash; seven complete days in one week.
- **Weekend Warrior** &mdash; complete both weekend days.

There is **no XP, currency, shop, or inventory**. If implemented, achievements need a stable rule engine and persisted unlock state; treat that as post-MVP, not a reskin.

## Stress-test iterations

These two are deliberately harder than the current household data: **seven children** and **six checklist items** on one chore. The seven profiles are a layout fixture, not existing app data. Both use a fixed-height list window so the long labels wrap and the extra rows scroll instead of shrinking.

### Sticker Club v2 — no person or chore pictograms

A type-only answer to Sticker Club. Every person is a die-cut name tag with an initial and a name; every job is a numbered line; every status is a word or a check. There are no animal avatars, no chore illustrations, and no subtype icon tiles. The visual play comes from oversized rounded type, five-color sticker blocks, offset shadows, and the rotated "YOU" tag.

- Seven 46px name tags fit one row at 390px.
- Six jobs sit in a 190px window; the fourth row clips by design and the rail shows position.
- The scrolled state keeps the same header and CTA while surfacing jobs 03–06.
- The desktop shows all seven kids, all six jobs, and the family sheet at once.

Old Sticker Club remains concept 02 for comparison; v2 is concept 10.

### Quest Light — daylight HUD

The dark Quest HUD in a light token set: cream, black rules, lime, cyan, and a little ember. The layout is unchanged: a seven-player squad rail, a daily quest card, six objectives, and a fixed scroll window. XP, streaks, and rank are the original Quest game layer, still post-MVP.

- Seven two-letter player cards fit the full 354px width.
- Six objectives in a 190px phone window; 3.5 rows visible.
- The scrolled state surfaces objectives 03–06 without moving the squad or quest card.
- The desktop widens the same window to 268px and shows 5.5 rows.

Old Quest remains concept 04 for comparison; Quest Light is concept 11.

## Images

- **All eleven — phone overview:** [boards/00-overview.png](boards/00-overview.png)
- **Archive detail previews:** [Sticker Club v2](shots/12-archive-sticker-v2.png) · [Quest Light](shots/12-archive-quest-light.png)
- **Concept boards (phone + second phone + desktop + notes):**
  - [01 Homestead](boards/01-homestead-board.png)
  - [02 Sticker Club](boards/02-sticker-club-board.png)
  - [03 Still](boards/03-still-board.png)
  - [04 Quest](boards/04-quest-board.png)
  - [05 Ledger](boards/05-ledger-board.png)
  - [06 Matchday](boards/06-matchday-board.png)
  - [07 Checkpoint](boards/07-checkpoint-board.png)
  - [08 Wayfinder](boards/08-wayfinder-board.png)
  - [09 Homescreen](boards/09-homescreen-board.png)
  - [10 Sticker Club v2](boards/10-sticker-club-v2-board.png)
  - [11 Quest Light](boards/11-quest-light-board.png)
- **Iteration 2 individual screens:**
  - Matchday: [phone](shots/06-matchday-phone.png) · [full time](shots/06-matchday-phone-fulltime.png) · [desktop](shots/06-matchday-desktop.png)
  - Checkpoint: [phone](shots/07-checkpoint-phone.png) · [week log](shots/07-checkpoint-phone-week.png) · [desktop](shots/07-checkpoint-desktop.png)
- **Wayfinder, round 2:** [phone](shots/08-wayfinder-phone.png) · [quest complete](shots/08-wayfinder-phone-complete.png) · [desktop](shots/08-wayfinder-desktop.png)
- **Homescreen:** [phone home](shots/09-homescreen-phone.png) · [achievements](shots/09-homescreen-phone-achievements.png) · [desktop](shots/09-homescreen-desktop.png)
- **Sticker Club v2:** [top](shots/10-sticker-club-v2-phone.png) · [scrolled](shots/10-sticker-club-v2-phone-scroll.png) · [sticker earned](shots/10-sticker-club-v2-phone-done.png) · [desktop](shots/10-sticker-club-v2-desktop.png)
- **Quest Light:** [top](shots/11-quest-light-phone.png) · [scrolled](shots/11-quest-light-phone-scroll.png) · [quest clear](shots/11-quest-light-phone-done.png) · [desktop](shots/11-quest-light-desktop.png)
- **Current UI baseline:** [shots/00-current-phone.png](shots/00-current-phone.png) and [shots/00-current-desktop.png](shots/00-current-desktop.png), captured with mocked API responses for comparison.

Resolution: phone shots are 1170 × 2532 (390 × 844 @3×), desktop shots are 2880 × 1800 (1440 × 900 @2×), boards are 2700 × 1755.

## What changes in the app

The original nine are re-skins of the existing screens and data model; the two stress-test iterations push the same patterns to seven children and six-item lists:

- Floating-family screen: profile switch → weekly chore → per-item daily check-off.
- All-done states.
- Admin weekly report and history/archive.
- Desktop is a secondary, shared-screen view.

Homescreen additionally introduces a console home and an achievement layer; that is the one concept with a new feature surface. Sticker Club v2 keeps the existing reward caveat; Quest Light keeps the existing game-layer caveat.

Most of the visual change is CSS: Reshaped CSS variables, typography, borders, radii, shadows, and a handful of layout classes. Structural changes to flag:

1. **Profile picker:** every concept replaces the child `<Select>` with a visible name/avatar row, tag strip, card grid, or game tiles. The state and API calls stay the same.
2. **Themes:** Quest and Homescreen need scoped `--rs-*` token overrides (or custom theme objects). Quest Light is a light token set; Sticker Club v2 is light and type-only.

No new runtime dependencies are required for any direction. Fonts used in the mockups are macOS system fonts (Iowan Old Style, Bodoni 72, Avenir Next, Avenir Next Condensed, Arial Rounded MT Bold, Copperplate); if the app ships cross-platform, either bundle equivalents or lean on the declared fallbacks. No game assets or logos are used in Wayfinder or Homescreen.

## Admin theme mockups

Per-screen signed-in administrator layouts for Homestead, Quest, and Sticker Club v2 live in [admin/](admin/README.md), with all 18 screen/theme shots and an approval contact sheet. They are design work for #75 and were approved by the product owner before implementation.

## Source mockups

The `concepts/` folder contains standalone HTML/CSS (including `wayfinder/`, `homescreen/`, `sticker-club/v2/`, and `quest/light/`) used only to render the images — it does not import the app and is not wired into `frontend/src`. The archive is `index.html` at the root of this folder. The render helpers are `render.mjs` (screens), `render-boards.mjs` (boards), and the static server is plain Python `http.server`.