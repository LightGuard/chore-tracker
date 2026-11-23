import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useState,
  type FormEvent,
} from "react";
import {
  Alert,
  Button,
  Card,
  Container,
  FormControl,
  Loader,
  Text,
  TextField,
  View,
} from "reshaped";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ApiError, apiRequest } from "../api/client";
import { AppHeader } from "../components/AppHeader";
import { ThemeScope } from "../components/ThemeScope";
import {
  DEFAULT_THEME,
  resolveThemeId,
  updateAdministratorTheme,
} from "../theme/api";
import {
  applyDocumentTheme,
  clearAdministratorSession,
  clearCachedTheme,
  readCachedAdminBootstrapTheme,
  rememberAdministratorSession,
  writeLastTheme,
} from "../theme/storage";
import { useThemeCatalog } from "../theme/useThemeCatalog";
import { AdminLayout } from "./AdminLayout";
import { ChoreManager } from "./ChoreManager";
import { FamilyMemberManager } from "./FamilyMemberManager";
import { ReportDetail } from "./ReportDetail";
import { ReportHistory } from "./ReportHistory";
import { authenticatePasskey, registerPasskey } from "./passkeys";

type Administrator = { id: number; email: string; theme_id?: string | null };
type SetupStatus = { setup_required: boolean; enrollment_pending: boolean };
type Ceremony = { challenge_id: string; options: Record<string, unknown> };

function messageFor(reason: unknown, fallback: string): string {
  return reason instanceof ApiError ? reason.message : fallback;
}

function isUnauthorized(reason: unknown): boolean {
  return reason instanceof ApiError && reason.status === 401;
}

export function AdminPage() {
  const catalog = useThemeCatalog();
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [administrator, setAdministrator] = useState<Administrator | null>(
    null,
  );
  const [email, setEmail] = useState("");
  const [invitationEmail, setInvitationEmail] = useState("");
  const [invitationUrl, setInvitationUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sessionMessage, setSessionMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [themeBusy, setThemeBusy] = useState(false);
  const [themeError, setThemeError] = useState("");
  const [bootstrapTheme, setBootstrapTheme] = useState(
    () => readCachedAdminBootstrapTheme() ?? DEFAULT_THEME.id,
  );
  const [failedThemeId, setFailedThemeId] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const { weekStart } = useParams<{ weekStart?: string }>();
  const reportsView = location.pathname.startsWith("/admin/reports");
  const enrollmentToken = new URLSearchParams(
    window.location.hash.slice(1),
  ).get("token");

  const signedIn = Boolean(administrator) && !enrollmentToken;
  const authThemeId = loading ? bootstrapTheme : DEFAULT_THEME.id;
  const themeId =
    administrator && !enrollmentToken
      ? resolveThemeId(administrator.theme_id, catalog.themes)
      : authThemeId;

  useEffect(() => {
    if (loading || !location.hash) return;
    const target = document.getElementById(location.hash.slice(1));
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ block: "start" });
    }
  }, [administrator, loading, location.hash, reportsView]);

  useLayoutEffect(() => {
    applyDocumentTheme(themeId);
    if (!administrator) return;
    if (
      administrator.theme_id &&
      catalog.themes.some((theme) => theme.id === administrator.theme_id)
    ) {
      rememberAdministratorSession(administrator.id, administrator.theme_id);
    } else {
      clearCachedTheme("admin", administrator.id);
      writeLastTheme(themeId);
    }
  }, [administrator, catalog.themes, themeId]);

  const refresh = useCallback(async () => {
    const setup = await apiRequest<SetupStatus>("/auth/setup");
    setStatus(setup);
    try {
      setAdministrator(await apiRequest<Administrator>("/auth/me"));
    } catch (reason) {
      if (!isUnauthorized(reason)) throw reason;
      setAdministrator(null);
      clearAdministratorSession();
      setBootstrapTheme(DEFAULT_THEME.id);
    }
  }, []);

  useEffect(() => {
    refresh()
      .catch((reason: unknown) => {
        setError(messageFor(reason, "Unable to load administrator setup."));
      })
      .finally(() => setLoading(false));
  }, [refresh]);

  const handleSessionExpired = useCallback(() => {
    setAdministrator(null);
    clearAdministratorSession();
    setBootstrapTheme(DEFAULT_THEME.id);
    setStatus((current) =>
      current
        ? { ...current, setup_required: false, enrollment_pending: false }
        : current,
    );
    setSessionMessage("Your session expired. Sign in again.");
    setInvitationUrl("");
  }, []);

  async function handleInitialSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSessionMessage("");
    try {
      const started = await apiRequest<Ceremony>("/auth/setup/start", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      const credential = await registerPasskey(started.options);
      await apiRequest("/auth/setup/finish", {
        method: "POST",
        body: JSON.stringify({
          challenge_id: started.challenge_id,
          credential,
        }),
      });
      await refresh();
    } catch (reason) {
      setError(messageFor(reason, "Administrator setup failed."));
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSessionMessage("");
    try {
      const started = await apiRequest<Ceremony>("/auth/login/options", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      const credential = await authenticatePasskey(started.options);
      await apiRequest("/auth/login/finish", {
        method: "POST",
        body: JSON.stringify({
          challenge_id: started.challenge_id,
          credential,
        }),
      });
      await refresh();
    } catch (reason) {
      setError(messageFor(reason, "Passkey sign-in failed."));
    } finally {
      setBusy(false);
    }
  }

  async function handleInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await apiRequest<{ enrollment_token: string }>(
        "/auth/administrators",
        {
          method: "POST",
          body: JSON.stringify({ email: invitationEmail }),
        },
      );
      setInvitationUrl(
        `${window.location.origin}/admin/enroll#token=${encodeURIComponent(
          result.enrollment_token,
        )}`,
      );
      setInvitationEmail("");
    } catch (reason) {
      if (isUnauthorized(reason)) {
        handleSessionExpired();
      } else {
        setError(messageFor(reason, "Unable to create administrator."));
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleEnrollment() {
    if (!enrollmentToken) return;
    setBusy(true);
    setError("");
    setSessionMessage("");
    try {
      const started = await apiRequest<Ceremony>("/auth/enrollment/options", {
        method: "POST",
        body: JSON.stringify({ token: enrollmentToken }),
      });
      const credential = await registerPasskey(started.options);
      await apiRequest("/auth/enrollment/finish", {
        method: "POST",
        body: JSON.stringify({
          challenge_id: started.challenge_id,
          credential,
        }),
      });
      navigate("/admin", { replace: true });
      await refresh();
    } catch (reason) {
      setError(messageFor(reason, "Passkey enrollment failed."));
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setBusy(true);
    setError("");
    try {
      await apiRequest("/auth/logout", { method: "POST" });
      setAdministrator(null);
      clearAdministratorSession();
      setBootstrapTheme(DEFAULT_THEME.id);
      setInvitationUrl("");
      setSessionMessage("You have signed out.");
    } catch (reason) {
      setError(messageFor(reason, "Sign out failed."));
    } finally {
      setBusy(false);
    }
  }

  async function handleThemeChange(nextThemeId: string) {
    if (!administrator || themeBusy) return;
    setThemeBusy(true);
    setThemeError("");
    setFailedThemeId(nextThemeId);
    try {
      const result = await updateAdministratorTheme(nextThemeId);
      setAdministrator({ ...administrator, theme_id: result.theme_id });
      setThemeError("");
      setFailedThemeId("");
    } catch (reason) {
      setThemeError(
        messageFor(reason, "We couldn't save that theme. Try again."),
      );
    } finally {
      setThemeBusy(false);
    }
  }

  const notices = (
    <>
      {catalog.error && (
        <Alert color="warning" title="Theme catalog unavailable">
          {catalog.error} Homestead is being used for now.
        </Alert>
      )}

      {themeError && (
        <Alert
          color="critical"
          title="Theme was not saved"
          actionsSlot={
            failedThemeId ? (
              <Button
                variant="outline"
                disabled={themeBusy}
                onClick={() => void handleThemeChange(failedThemeId)}
              >
                Try again
              </Button>
            ) : undefined
          }
        >
          {themeError}
        </Alert>
      )}

      {error && (
        <Alert color="critical" title="Administrator request failed">
          {error}
        </Alert>
      )}
    </>
  );

  return (
    <ThemeScope themeId={themeId}>
      <AppHeader
        themes={catalog.themes}
        themeId={themeId}
        themeDisabled={!administrator || themeBusy}
        themeDisabledReason="Sign in as an administrator to change the theme."
        themeBusy={themeBusy}
        onThemeChange={handleThemeChange}
        currentAdministrator={administrator?.email}
        context="admin"
      />
      <Container width="100%">
        {signedIn && administrator ? (
          <AdminLayout
            themeId={themeId}
            administratorEmail={administrator.email}
            busy={busy}
            reportsView={reportsView}
            onLogout={handleLogout}
          >
            <header className="admin-page-head">
              <div className="admin-page-kicker">
                {reportsView ? "Weekly archive" : "Signed-in administration"}
              </div>
              <h1>
                {reportsView
                  ? "Weekly reports"
                  : "One house, one control room."}
              </h1>
              <p>
                {reportsView
                  ? "Browse immutable Monday–Sunday completion snapshots generated for the household."
                  : "Manage the household roster, chore catalog, weekly reports, and administrator access without changing the underlying workflow."}
              </p>
            </header>

            {notices}

            <SignedInContent
              administrator={administrator}
              busy={busy}
              invitationEmail={invitationEmail}
              invitationUrl={invitationUrl}
              reportsView={reportsView}
              reportWeek={weekStart}
              onInvitationEmailChange={setInvitationEmail}
              onInvitation={handleInvitation}
              onSessionExpired={handleSessionExpired}
            />
          </AdminLayout>
        ) : (
          <main className="app-shell admin-shell admin-auth-shell">
            <View gap={1} paddingBlock={3}>
              <Text as="h1" variant="headline-1">
                {reportsView
                  ? "Weekly reports"
                  : "Chore Tracker administration"}
              </Text>
              <Text color="neutral-faded">
                {reportsView
                  ? "Browse immutable Monday–Sunday completion snapshots generated for the household."
                  : "Administrator access uses passkeys. Child profiles remain separate and are not signed-in accounts."}
              </Text>
            </View>

            <View gap={4} paddingTop={4}>
              {notices}

              {loading ? (
                <View
                  align="center"
                  gap={2}
                  padding={6}
                  attributes={{ role: "status" }}
                >
                  <Loader ariaLabel="Loading administrator setup" />
                  <Text color="neutral-faded">
                    Loading administrator setup…
                  </Text>
                </View>
              ) : enrollmentToken ? (
                <Card
                  as="section"
                  padding={5}
                  borderRadius="large"
                  attributes={{ "aria-labelledby": "enrollment-heading" }}
                >
                  <View gap={3}>
                    <Text
                      as="h2"
                      variant="headline-2"
                      attributes={{ id: "enrollment-heading" }}
                    >
                      Register administrator passkey
                    </Text>
                    <Text>
                      This one-time invitation expires after 24 hours. Register
                      a passkey on this device to finish enrollment.
                    </Text>
                    <View direction="row">
                      <Button
                        disabled={busy}
                        loading={busy}
                        onClick={() => void handleEnrollment()}
                      >
                        Register passkey
                      </Button>
                    </View>
                  </View>
                </Card>
              ) : status?.setup_required ? (
                <Card
                  as="section"
                  padding={5}
                  borderRadius="large"
                  attributes={{ "aria-labelledby": "setup-heading" }}
                >
                  <form onSubmit={(event) => void handleInitialSetup(event)}>
                    <View gap={3}>
                      <Text
                        as="h2"
                        variant="headline-2"
                        attributes={{ id: "setup-heading" }}
                      >
                        Initial administrator setup
                      </Text>
                      <Text color="neutral-faded">
                        Create the first administrator and register a passkey on
                        this device. This unauthenticated setup path is
                        available only before the first passkey is registered.
                      </Text>
                      <FormControl id="admin-email">
                        <FormControl.Label>
                          Administrator email
                        </FormControl.Label>
                        <TextField
                          name="email"
                          value={email}
                          onChange={({ value }) => setEmail(value)}
                          inputAttributes={{
                            type: "email",
                            autoComplete: "email",
                            required: true,
                          }}
                        />
                      </FormControl>
                      <View direction="row">
                        <Button
                          type="submit"
                          disabled={busy}
                          loading={busy}
                          loadingAriaLabel="Creating administrator"
                        >
                          Create administrator and register passkey
                        </Button>
                      </View>
                    </View>
                  </form>
                </Card>
              ) : status ? (
                <Card
                  as="section"
                  padding={5}
                  borderRadius="large"
                  attributes={{ "aria-labelledby": "login-heading" }}
                >
                  <form onSubmit={(event) => void handleLogin(event)}>
                    <View gap={3}>
                      {sessionMessage && (
                        <Alert color="warning" title="Session ended">
                          {sessionMessage}
                        </Alert>
                      )}
                      <Text
                        as="h2"
                        variant="headline-2"
                        attributes={{ id: "login-heading" }}
                      >
                        Administrator sign in
                      </Text>
                      <Text color="neutral-faded">
                        Use the passkey registered for your administrator
                        account.
                      </Text>
                      <FormControl id="login-email">
                        <FormControl.Label>
                          Administrator email
                        </FormControl.Label>
                        <TextField
                          name="email"
                          value={email}
                          onChange={({ value }) => setEmail(value)}
                          inputAttributes={{
                            type: "email",
                            autoComplete: "username webauthn",
                            required: true,
                          }}
                        />
                      </FormControl>
                      <View direction="row">
                        <Button
                          type="submit"
                          disabled={busy}
                          loading={busy}
                          loadingAriaLabel="Signing in"
                        >
                          Sign in with passkey
                        </Button>
                      </View>
                    </View>
                  </form>
                </Card>
              ) : null}
            </View>
          </main>
        )}
      </Container>
    </ThemeScope>
  );
}

type SignedInProps = {
  administrator: Administrator;
  busy: boolean;
  invitationEmail: string;
  invitationUrl: string;
  reportsView: boolean;
  reportWeek?: string;
  onInvitationEmailChange: (value: string) => void;
  onInvitation: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onSessionExpired: () => void;
};

function AdminOverview() {
  return (
    <section
      className="admin-overview"
      aria-labelledby="admin-overview-heading"
    >
      <div className="admin-overview-heading">
        <div>
          <span className="admin-overview-kicker">Administration</span>
          <h2 id="admin-overview-heading">Choose a workspace</h2>
        </div>
        <p>
          Existing household tools, organized for the signed-in administrator.
        </p>
      </div>
      <div className="admin-overview-grid">
        <a className="admin-overview-card" href="#family-members">
          <span className="admin-overview-tag">Family</span>
          <strong>Family &amp; chores</strong>
          <span>Profiles, chore catalog, checklist order.</span>
          <i aria-hidden="true">→</i>
        </a>
        <Link className="admin-overview-card" to="/admin/reports">
          <span className="admin-overview-tag">Archive</span>
          <strong>Weekly reports</strong>
          <span>Immutable Monday–Sunday snapshots.</span>
          <i aria-hidden="true">→</i>
        </Link>
        <a className="admin-overview-card" href="#administrator-access">
          <span className="admin-overview-tag">Access</span>
          <strong>Administrator access</strong>
          <span>Invite the second administrator.</span>
          <i aria-hidden="true">→</i>
        </a>
      </div>
    </section>
  );
}

function SignedInContent({
  administrator,
  busy,
  invitationEmail,
  invitationUrl,
  reportsView,
  reportWeek,
  onInvitationEmailChange,
  onInvitation,
  onSessionExpired,
}: SignedInProps) {
  return (
    <div className="admin-screen-content">
      {reportsView ? (
        reportWeek ? (
          <ReportDetail
            key={reportWeek}
            weekStart={reportWeek}
            onSessionExpired={onSessionExpired}
          />
        ) : (
          <ReportHistory onSessionExpired={onSessionExpired} />
        )
      ) : (
        <>
          <AdminOverview />
          <FamilyMemberManager onSessionExpired={onSessionExpired} />
          <ChoreManager onSessionExpired={onSessionExpired} />
          <AdministratorAccessPanel
            administratorEmail={administrator.email}
            busy={busy}
            invitationEmail={invitationEmail}
            invitationUrl={invitationUrl}
            onInvitationEmailChange={onInvitationEmailChange}
            onInvitation={onInvitation}
          />
        </>
      )}
    </div>
  );
}

type AdministratorAccessProps = {
  administratorEmail: string;
  busy: boolean;
  invitationEmail: string;
  invitationUrl: string;
  onInvitationEmailChange: (value: string) => void;
  onInvitation: (event: FormEvent<HTMLFormElement>) => Promise<void>;
};

function AdministratorAccessPanel({
  administratorEmail,
  busy,
  invitationEmail,
  invitationUrl,
  onInvitationEmailChange,
  onInvitation,
}: AdministratorAccessProps) {
  return (
    <Card
      as="section"
      padding={5}
      borderRadius="large"
      className="admin-panel admin-invite-panel"
      attributes={{
        "aria-labelledby": "second-administrator-heading",
        id: "administrator-access",
      }}
    >
      <View gap={4}>
        <View gap={1}>
          <Text
            as="h2"
            variant="headline-2"
            attributes={{ id: "second-administrator-heading" }}
          >
            Administrator access
          </Text>
          <Text color="neutral-faded">
            The household supports at most two administrators. Create a one-time
            enrollment link that expires after 24 hours.
          </Text>
        </View>

        <div className="admin-split admin-invite-grid">
          <div className="admin-form-panel">
            <Text as="h3" variant="headline-3">
              Invite a second administrator
            </Text>
            <form onSubmit={(event) => void onInvitation(event)}>
              <View gap={2} paddingTop={2}>
                <FormControl id="invitation-email">
                  <FormControl.Label>Administrator email</FormControl.Label>
                  <TextField
                    name="email"
                    value={invitationEmail}
                    onChange={({ value }) => onInvitationEmailChange(value)}
                    inputAttributes={{ type: "email", required: true }}
                  />
                </FormControl>
                <View direction="row">
                  <Button type="submit" disabled={busy}>
                    Create administrator invitation
                  </Button>
                </View>
              </View>
            </form>
            {invitationUrl && (
              <View gap={2} paddingTop={3}>
                <Alert color="positive" title="Enrollment link created">
                  Send this one-time link to the second administrator. It can be
                  used once.
                </Alert>
                <FormControl id="enrollment-link">
                  <FormControl.Label>Enrollment link</FormControl.Label>
                  <TextField
                    name="enrollment_link"
                    value={invitationUrl}
                    onChange={() => undefined}
                    inputAttributes={{ readOnly: true }}
                  />
                </FormControl>
              </View>
            )}
          </div>

          <aside className="admin-context-panel admin-access-context">
            <span className="admin-context-kicker">Access model</span>
            <h3>Passkey sessions</h3>
            <p>
              Administrator access uses a passkey registered for this account.
              Child profiles remain separate and are not signed-in accounts.
            </p>
            <dl className="admin-context-list">
              <div>
                <dt>Signed in</dt>
                <dd>{administratorEmail}</dd>
              </div>
              <div>
                <dt>Session</dt>
                <dd>Active</dd>
              </div>
              <div>
                <dt>Administrators</dt>
                <dd>2 maximum</dd>
              </div>
            </dl>
          </aside>
        </div>
      </View>
    </Card>
  );
}
