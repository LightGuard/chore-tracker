import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Container, Reshaped } from "reshaped";
import { BrowserRouter, Route, Routes, useNavigate, useSearchParams } from "react-router-dom";
import { API_BASE_URL } from "./config/api";

type Administrator = { id: number; email: string };
type SetupStatus = { setup_required: boolean; enrollment_pending: boolean };
type Ceremony = { challenge_id: string; options: Record<string, unknown> };

function decodeBase64Url(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = window.atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return bytes.buffer;
}

function encodeBase64Url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function creationOptions(options: Record<string, unknown>): PublicKeyCredentialCreationOptions {
  const user = options.user as Record<string, unknown>;
  const exclude = options.excludeCredentials as Array<Record<string, unknown>> | undefined;
  return {
    ...options,
    challenge: decodeBase64Url(options.challenge as string),
    user: { ...user, id: decodeBase64Url(user.id as string) },
    excludeCredentials: exclude?.map((item) => ({
      ...item,
      id: decodeBase64Url(item.id as string),
    })),
  } as PublicKeyCredentialCreationOptions;
}

function requestOptions(options: Record<string, unknown>): PublicKeyCredentialRequestOptions {
  const allow = options.allowCredentials as Array<Record<string, unknown>> | undefined;
  return {
    ...options,
    challenge: decodeBase64Url(options.challenge as string),
    allowCredentials: allow?.map((item) => ({
      ...item,
      id: decodeBase64Url(item.id as string),
    })),
  } as PublicKeyCredentialRequestOptions;
}

function serializeCredential(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response;
  const serialized: Record<string, unknown> = {
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
  if (response instanceof AuthenticatorAttestationResponse) {
    serialized.response = {
      clientDataJSON: encodeBase64Url(response.clientDataJSON),
      attestationObject: encodeBase64Url(response.attestationObject),
      transports: response.getTransports?.() ?? [],
    };
  } else if (response instanceof AuthenticatorAssertionResponse) {
    serialized.response = {
      clientDataJSON: encodeBase64Url(response.clientDataJSON),
      authenticatorData: encodeBase64Url(response.authenticatorData),
      signature: encodeBase64Url(response.signature),
      userHandle: response.userHandle ? encodeBase64Url(response.userHandle) : null,
    };
  }
  return serialized;
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

async function registerPasskey(options: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (!navigator.credentials?.create) {
    throw new Error("This browser does not support passkey registration.");
  }
  const credential = await navigator.credentials.create({
    publicKey: creationOptions(options),
  });
  if (!(credential instanceof PublicKeyCredential)) {
    throw new Error("The authenticator did not return a passkey.");
  }
  return serializeCredential(credential);
}

async function authenticatePasskey(options: Record<string, unknown>): Promise<Record<string, unknown>> {
  if (!navigator.credentials?.get) {
    throw new Error("This browser does not support passkey authentication.");
  }
  const credential = await navigator.credentials.get({
    publicKey: requestOptions(options),
  });
  if (!(credential instanceof PublicKeyCredential)) {
    throw new Error("The authenticator did not return a credential.");
  }
  return serializeCredential(credential);
}

function AdminPage() {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [administrator, setAdministrator] = useState<Administrator | null>(null);
  const [email, setEmail] = useState("");
  const [invitationEmail, setInvitationEmail] = useState("");
  const [invitationUrl, setInvitationUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const enrollmentToken = searchParams.get("token");

  const refresh = useCallback(async () => {
    const setup = await apiRequest<SetupStatus>("/auth/setup");
    setStatus(setup);
    try {
      setAdministrator(await apiRequest<Administrator>("/auth/me"));
    } catch {
      setAdministrator(null);
    }
  }, []);

  useEffect(() => {
    void refresh().catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Unable to load administrator setup.");
    });
  }, [refresh]);

  async function handleInitialSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const started = await apiRequest<Ceremony>("/auth/setup/start", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      const credential = await registerPasskey(started.options);
      await apiRequest("/auth/setup/finish", {
        method: "POST",
        body: JSON.stringify({ challenge_id: started.challenge_id, credential }),
      });
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Administrator setup failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const started = await apiRequest<Ceremony>("/auth/login/options", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      const credential = await authenticatePasskey(started.options);
      await apiRequest("/auth/login/finish", {
        method: "POST",
        body: JSON.stringify({ challenge_id: started.challenge_id, credential }),
      });
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Passkey sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await apiRequest<{ enrollment_token: string }>("/auth/administrators", {
        method: "POST",
        body: JSON.stringify({ email: invitationEmail }),
      });
      setInvitationUrl(
        `${window.location.origin}/admin/enroll?token=${encodeURIComponent(result.enrollment_token)}`,
      );
      setInvitationEmail("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create administrator.");
    } finally {
      setBusy(false);
    }
  }

  async function handleEnrollment() {
    if (!enrollmentToken) return;
    setBusy(true);
    setError("");
    try {
      const started = await apiRequest<Ceremony>("/auth/enrollment/options", {
        method: "POST",
        body: JSON.stringify({ token: enrollmentToken }),
      });
      const credential = await registerPasskey(started.options);
      await apiRequest("/auth/enrollment/finish", {
        method: "POST",
        body: JSON.stringify({ challenge_id: started.challenge_id, credential }),
      });
      navigate("/admin", { replace: true });
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Passkey enrollment failed.");
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
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign out failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Container width="100%">
      <main className="app-shell admin-shell">
        <header>
          <h1>Chore Tracker administration</h1>
          <p>Administrator access uses passkeys.</p>
        </header>
        {error && <p role="alert" className="error-message">{error}</p>}
        {enrollmentToken ? (
          <section aria-labelledby="enrollment-heading">
            <h2 id="enrollment-heading">Register administrator passkey</h2>
            <p>This one-time invitation expires after 24 hours.</p>
            <button disabled={busy} onClick={() => void handleEnrollment()}>
              {busy ? "Registering…" : "Register passkey"}
            </button>
          </section>
        ) : administrator ? (
          <section aria-labelledby="admin-heading">
            <h2 id="admin-heading">Signed in as {administrator.email}</h2>
            <button disabled={busy} onClick={() => void handleLogout()}>Sign out</button>
            <h3>Second administrator</h3>
            <form onSubmit={(event) => void handleInvitation(event)}>
              <label htmlFor="invitation-email">Administrator email</label>
              <input
                id="invitation-email"
                type="email"
                required
                value={invitationEmail}
                onChange={(event) => setInvitationEmail(event.target.value)}
              />
              <button disabled={busy} type="submit">Create administrator invitation</button>
            </form>
            {invitationUrl && (
              <div className="invitation-result">
                <p>Send this one-time enrollment link to the second administrator:</p>
                <input aria-label="Enrollment link" readOnly value={invitationUrl} />
              </div>
            )}
          </section>
        ) : status?.setup_required ? (
          <section aria-labelledby="setup-heading">
            <h2 id="setup-heading">Initial administrator setup</h2>
            <p>Create the first administrator and register a passkey on this device.</p>
            <form onSubmit={(event) => void handleInitialSetup(event)}>
              <label htmlFor="admin-email">Administrator email</label>
              <input
                id="admin-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <button disabled={busy} type="submit">
                {busy ? "Setting up…" : "Create administrator and register passkey"}
              </button>
            </form>
          </section>
        ) : status ? (
          <section aria-labelledby="login-heading">
            <h2 id="login-heading">Administrator sign in</h2>
            <form onSubmit={(event) => void handleLogin(event)}>
              <label htmlFor="login-email">Administrator email</label>
              <input
                id="login-email"
                type="email"
                required
                autoComplete="username webauthn"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
              <button disabled={busy} type="submit">
                {busy ? "Signing in…" : "Sign in with passkey"}
              </button>
            </form>
          </section>
        ) : (
          <p>Loading administrator setup…</p>
        )}
      </main>
    </Container>
  );
}

function ApplicationShell() {
  return (
    <Container width="100%">
      <main className="app-shell">
        <header>
          <h1>Chore Tracker</h1>
          <p>Family chore tracker</p>
        </header>
      </main>
    </Container>
  );
}

function NotFound() {
  return (
    <Container width="100%">
      <main className="app-shell">
        <h1>Page not found</h1>
      </main>
    </Container>
  );
}

export function App() {
  return (
    <Reshaped theme="slate">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ApplicationShell />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/enroll" element={<AdminPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </Reshaped>
  );
}
