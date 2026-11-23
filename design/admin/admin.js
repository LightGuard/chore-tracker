const THEMES = {
  homestead: {
    name: "Homestead",
    word: "Chore Tracker",
    sub: "House ledger",
    mark: "H",
  },
  quest: {
    name: "Quest",
    word: "QUEST",
    sub: "Admin command",
    mark: "Q",
  },
  "sticker-club-v2": {
    name: "Sticker Club v2",
    word: "STICKER <em>CLUB</em>",
    sub: "Admin sheet",
    mark: null,
  },
};

const requested = new URLSearchParams(window.location.search).get("theme");
const themeKey = requested && THEMES[requested] ? requested : "homestead";
const theme = THEMES[themeKey];
document.documentElement.dataset.theme = themeKey;
document.body.classList.add("admin-page", "theme-" + themeKey);
document.title = theme.name + " · " + (document.body.dataset.screen || "Admin") + " · Admin mockup";

const header = document.createElement("header");
header.className = "admin-topbar";
header.innerHTML =
  '<a class="brand" href="index.html" aria-label="' +
  theme.name +
  ' administration">' +
  (theme.mark ? '<span class="brand-mark" aria-hidden="true">' + theme.mark + "</span>" : "") +
  '<span class="brand-copy"><strong class="brand-word">' +
  theme.word +
  '</strong><span class="brand-sub">' +
  theme.sub +
  '</span></span></a><div class="topbar-tools"><span class="topbar-context">Signed in as <strong>jordan@example.com</strong></span><button type="button" class="theme-control">Theme <strong>' +
  theme.name +
  '</strong><span aria-hidden="true">▾</span></button></div>';
document.body.prepend(header);

const main = document.querySelector("main.admin-main");
const workspace = document.createElement("div");
workspace.className = "admin-workspace";
const aside = document.createElement("aside");
aside.className = "admin-side";
aside.innerHTML =
  '<div class="nav-kicker">Administration</div><nav aria-label="Administration sections">' +
  '<a class="nav-link" data-nav="family" href="family.html"><span>Family &amp; chores</span><small>Profiles, catalog, checklist order</small></a>' +
  '<a class="nav-link" data-nav="reports" href="reports.html"><span>Reports</span><small>Immutable weekly snapshots</small></a>' +
  '<a class="nav-link" data-nav="invite" href="invite.html"><span>Administrator access</span><small>Second administrator invitation</small></a>' +
  '</nav><div class="side-session"><span class="side-kicker">Passkey session</span><strong>jordan@example.com</strong><span>Administrator session active</span><button type="button">Sign out</button></div>';
const active = document.body.dataset.active;
if (active) {
  const link = aside.querySelector('[data-nav="' + active + '"]');
  if (link) {
    link.classList.add("active");
    link.setAttribute("aria-current", "page");
  }
}
document.body.insertBefore(workspace, main);
workspace.append(aside, main);

const footer = document.createElement("footer");
footer.className = "mockup-foot";
footer.innerHTML =
  "<span>Mockup · " +
  theme.name +
  " · " +
  (document.body.dataset.screen || "Admin") +
  "</span><span>No new data, API, authorization, or workflow.</span>";
document.body.append(footer);

for (const link of document.querySelectorAll(".admin-main a[href$='.html'], .admin-side a[href$='.html']")) {
  const href = link.getAttribute("href");
  if (href && !href.includes("?") && !href.startsWith("index.html")) {
    link.setAttribute("href", href + "?theme=" + themeKey);
  }
}
