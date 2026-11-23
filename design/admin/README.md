# Administrator theme mockups

Concept-specific layouts for the six signed-in administrator screens in Homestead,
Quest, and Sticker Club v2. These are design mockups only: no administrator data, API,
authorization, or workflow changes are proposed.

## Approval status

**Approved by the product owner for implementation on [#75](https://github.com/LightGuard/chore-tracker/issues/75#issuecomment-7092208855).**

The approval covers all six signed-in administrator screens across Homestead, Quest,
and Sticker Club v2. Concept-specific implementation may proceed from this matrix.

## Review

Open the gallery from the repository root:

```bash
python3 -m http.server 4175 --bind 127.0.0.1
# then open http://127.0.0.1:4175/design/admin/index.html
```

The contact sheet is [overview.png](overview.png). Each screen page accepts
`?theme=homestead`, `?theme=quest`, or `?theme=sticker-club-v2`; the gallery links each
variant directly. The source pages are [shell.html](shell.html), [family.html](family.html),
[chores.html](chores.html), [reports.html](reports.html),
[report-detail.html](report-detail.html), and [invite.html](invite.html).

## Screen / theme matrix

| Screen | Homestead | Quest | Sticker Club v2 |
| --- | --- | --- | --- |
| Signed-in admin shell and navigation | [shot](shots/homestead-shell.png) | [shot](shots/quest-shell.png) | [shot](shots/sticker-club-v2-shell.png) |
| Family member management | [shot](shots/homestead-family.png) | [shot](shots/quest-family.png) | [shot](shots/sticker-club-v2-family.png) |
| Chore and checklist management | [shot](shots/homestead-chores.png) | [shot](shots/quest-chores.png) | [shot](shots/sticker-club-v2-chores.png) |
| Weekly report history | [shot](shots/homestead-reports.png) | [shot](shots/quest-reports.png) | [shot](shots/sticker-club-v2-reports.png) |
| Weekly report detail and pagination | [shot](shots/homestead-report-detail.png) | [shot](shots/quest-report-detail.png) | [shot](shots/sticker-club-v2-report-detail.png) |
| Administrator access | [shot](shots/homestead-invite.png) | [shot](shots/quest-invite.png) | [shot](shots/sticker-club-v2-invite.png) |

## Layout notes

- **Homestead** uses a warm paper ledger: index rail, serif headings and ledger cards,
  terracotta actions, and hand-note annotations. The existing admin content stays in a
  two-column workspace on wide screens.
- **Quest** uses a dark command console: HUD rail, condensed uppercase headings,
  clipped panels, lime/cyan status language, and mono labels.
- **Sticker Club v2** uses type-only paper: a horizontal sticker-tag navigation strip,
  thick ink borders, hard shadows, five-color content blocks, and no pictograms.
- The shell mockup reorganizes the existing signed-in session and navigation into a
  landing surface with links to the existing Family &amp; chores, Reports, and
  Administrator access sections. It does not introduce a new route, API, or data.
- Pre-authentication setup, sign-in, and invitation acceptance are intentionally not
  mocked here; they remain on the Homestead token styling from #72.
- All mockups are built from the existing admin controls and data labels. The
  administrator theme is the source of the active layout; a selected child's theme is
  not used on these screens.

## Verification

```bash
python3 -m http.server 4175 --bind 127.0.0.1
ADMIN_MOCKUP_BASE_URL=http://127.0.0.1:4175/design \
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/path/to/chromium \
node design/admin/render.mjs
```

[render.mjs](render.mjs) renders all 18 full-page screenshots and [overview.png](overview.png),
and checks every screen at 1440, 900, and 390 pixels for horizontal overflow. Fonts are
loaded from the bundled frontend assets; no third-party font requests are made.

## Implementation verification

The signed-in implementation is verified by the real-passkey Playwright flow in `frontend/e2e/admin-flow.spec.ts`. It switches each administrator theme through all six screens and attaches 18 screenshots named `<theme>-<screen>.png` to the Playwright run. The same flow checks phone (390 px) and tablet (768 px) widths for page-level horizontal overflow.

## Approval checklist

- [x] Product owner reviewed the 18 screenshots.
- [x] Layout direction approved for all three themes.
- [x] Approval recorded on issue #75.
- [x] Implementation may begin.
