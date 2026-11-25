import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { Button } from "reshaped";

type AdminLayoutProps = {
  themeId: string;
  administratorEmail: string;
  busy: boolean;
  reportsView: boolean;
  onLogout: () => Promise<void>;
  children: ReactNode;
};

export function AdminLayout({
  themeId,
  administratorEmail,
  busy,
  reportsView,
  onLogout,
  children,
}: AdminLayoutProps) {
  const location = useLocation();
  const accessActive = location.hash === "#administrator-access";
  const assignmentsActive = location.hash === "#weekly-assignments";

  return (
    <main className="admin-workspace-shell">
      <div
        className="admin-workspace"
        data-admin-theme={themeId}
        data-admin-section={reportsView ? "reports" : "family"}
      >
        <aside className="admin-side-nav" aria-label="Administration">
          <div className="admin-nav-kicker">Administration</div>
          <nav className="admin-nav-links" aria-label="Administration sections">
            <NavLink
              end
              to="/admin"
              className={({ isActive }) =>
                `admin-nav-link${
                  isActive && !accessActive && !assignmentsActive
                    ? " active"
                    : ""
                }`
              }
            >
              <span>Family &amp; chores</span>
              <small aria-hidden="true">
                Profiles, catalog, checklist order
              </small>
            </NavLink>
            <NavLink
              to="/admin/reports"
              className={({ isActive }) =>
                `admin-nav-link${isActive ? " active" : ""}`
              }
            >
              <span>Reports</span>
              <small aria-hidden="true">Immutable weekly snapshots</small>
            </NavLink>
            <Link
              to="/admin#weekly-assignments"
              className={`admin-nav-link${assignmentsActive ? " active" : ""}`}
              aria-current={assignmentsActive ? "location" : undefined}
            >
              <span>Weekly assignments</span>
              <small aria-hidden="true">Generate a week manually</small>
            </Link>
            <Link
              to="/admin#administrator-access"
              className={`admin-nav-link${accessActive ? " active" : ""}`}
              aria-current={accessActive ? "location" : undefined}
            >
              <span>Administrator access</span>
              <small aria-hidden="true">Second administrator invitation</small>
            </Link>
          </nav>

          <section
            className="admin-session"
            aria-labelledby="admin-session-heading"
          >
            <span className="admin-session-kicker">Passkey session</span>
            <h2 id="admin-session-heading">
              Signed in as {administratorEmail}
            </h2>
            <p>Administrator session active</p>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void onLogout()}
            >
              Sign out
            </Button>
          </section>
        </aside>

        <div className="admin-content">{children}</div>
      </div>
    </main>
  );
}
