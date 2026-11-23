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
import {
  NavLink,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { ApiError, apiRequest } from "../api/client";
import { AppHeader } from "../components/AppHeader";
import { ThemeScope } from "../components/ThemeScope";
import { DEFAULT_THEME, resolveThemeId, updateAdministratorTheme } from "../theme/api";
import {
  applyDocumentTheme,
  clearCachedTheme,
  clearLastTheme,
  writeCachedTheme,
  writeLastTheme,
} from "../theme/storage";
import { useThemeCatalog } from "../theme/useThemeCatalog";
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
  const [administrator, setAdministrator] = useState<Administrator | null>(null);
  const [email, setEmail] = useState("");
  const [invitationEmail, setInvitationEmail] = useState("");
  const [invitationUrl, setInvitationUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sessionMessage, setSessionMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [themeBusy, setThemeBusy] = useState(false);
  const [themeError, setThemeError] = useState("");
  const [failedThemeId, setFailedThemeId] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const { weekStart } = useParams<{ weekStart?: string }>();
  const reportsView = location.pathname.startsWith("/admin/reports");
  const enrollmentToken = new URLSearchParams(
    window.location.hash.slice(1),
  ).get("token");

  const themeId = administrator
    ? resolveThemeId(administrator.theme_id, catalog.themes)
    : DEFAULT_THEME.id;

  useLayoutEffect(() => {
    applyDocumentTheme(themeId);
    if (!administrator) return;
    writeLastTheme(themeId);
    if (
      administrator.theme_id &&
      catalog.themes.some((theme) => theme.id === administrator.theme_id)
    ) {
      writeCachedTheme("admin", administrator.id, administrator.theme_id);
    } else {
      clearCachedTheme("admin", administrator.id);
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
    }
  }, []);

  useEffect(() => {
    refresh()
      .catch((reason: unknown) => {
        setError(
          messageFor(reason, "Unable to load administrator setup."),
        );
      })
      .finally(() => setLoading(false));
  }, [refresh]);

  const handleSessionExpired = useCallback(() => {
    setAdministrator(null);
    clearLastTheme();
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
      clearLastTheme();
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
        <main className="app-shell admin-shell">
        <View gap={1} paddingBlock={3}>
          <Text as="h1" variant="headline-1">
            {reportsView ? "Weekly reports" : "Chore Tracker administration"}
          </Text>
          <Text color="neutral-faded">
            {reportsView
              ? "Browse immutable Monday–Sunday completion snapshots generated for the household."
              : "Administrator access uses passkeys. Child profiles remain separate and are not signed-in accounts."}
          </Text>
        </View>

        <View gap={4} paddingTop={4}>
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

          {loading ? (
            <View
              align="center"
              gap={2}
              padding={6}
              attributes={{ role: "status" }}
            >
              <Loader ariaLabel="Loading administrator setup" />
              <Text color="neutral-faded">Loading administrator setup…</Text>
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
                  This one-time invitation expires after 24 hours. Register a
                  passkey on this device to finish enrollment.
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
          ) : administrator ? (
            <SignedInContent
              administrator={administrator}
              busy={busy}
              invitationEmail={invitationEmail}
              invitationUrl={invitationUrl}
              reportsView={reportsView}
              reportWeek={weekStart}
              onInvitationEmailChange={setInvitationEmail}
              onInvitation={handleInvitation}
              onLogout={handleLogout}
              onSessionExpired={handleSessionExpired}
            />
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
                    this device. This unauthenticated setup path is available
                    only before the first passkey is registered.
                  </Text>
                  <FormControl id="admin-email">
                    <FormControl.Label>Administrator email</FormControl.Label>
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
                    Use the passkey registered for your administrator account.
                  </Text>
                  <FormControl id="login-email">
                    <FormControl.Label>Administrator email</FormControl.Label>
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
  onLogout: () => Promise<void>;
  onSessionExpired: () => void;
};

function AdminNavigation({ reportsView }: { reportsView: boolean }) {
  return (
    <nav className="admin-nav" aria-label="Administration sections">
      <NavLink
        end
        to="/admin"
        className={({ isActive }) =>
          `admin-nav-link${isActive ? " active" : ""}`
        }
      >
        Family &amp; chores
      </NavLink>
      <NavLink
        to="/admin/reports"
        className={({ isActive }) =>
          `admin-nav-link${isActive ? " active" : ""}`
        }
        aria-current={reportsView ? "page" : undefined}
      >
        Reports
      </NavLink>
    </nav>
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
  onLogout,
  onSessionExpired,
}: SignedInProps) {
  return (
    <View gap={4}>
      <Card padding={4} borderRadius="medium">
        <View
          direction="row"
          align="center"
          justify="space-between"
          gap={3}
          wrap
        >
          <View gap={1}>
            <Text as="h2" variant="headline-3">
              Signed in as {administrator.email}
            </Text>
            <Text variant="caption-1" color="neutral-faded">
              Administrator session active
            </Text>
          </View>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void onLogout()}
          >
            Sign out
          </Button>
        </View>
      </Card>

      <AdminNavigation reportsView={reportsView} />

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
          <FamilyMemberManager onSessionExpired={onSessionExpired} />
          <ChoreManager onSessionExpired={onSessionExpired} />

          <Card
            as="section"
            padding={5}
            borderRadius="large"
            attributes={{ "aria-labelledby": "second-administrator-heading" }}
          >
            <View gap={3}>
              <View gap={1}>
                <Text
                  as="h2"
                  variant="headline-2"
                  attributes={{ id: "second-administrator-heading" }}
                >
                  Second administrator
                </Text>
                <Text color="neutral-faded">
                  The household supports at most two administrators. Create a
                  one-time enrollment link that expires after 24 hours.
                </Text>
              </View>
              <form onSubmit={(event) => void onInvitation(event)}>
                <View gap={2}>
                  <FormControl id="invitation-email">
                    <FormControl.Label>Administrator email</FormControl.Label>
                    <TextField
                      name="email"
                      value={invitationEmail}
                      onChange={({ value }) => onInvitationEmailChange(value)}
                      inputAttributes={{
                        type: "email",
                        required: true,
                      }}
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
                <View gap={2}>
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
            </View>
          </Card>
        </>
      )}
    </View>
  );
}