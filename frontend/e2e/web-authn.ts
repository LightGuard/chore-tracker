import type { CDPSession, Page } from "@playwright/test";

export type WebAuthnCredential = {
  credentialId: string;
  isResidentCredential: boolean;
  rpId: string;
  privateKey: string;
  userHandle?: string;
  signCount: number;
};

type VirtualAuthenticator = {
  session: CDPSession;
  authenticatorId: string;
};

async function createVirtualAuthenticator(
  page: Page,
): Promise<VirtualAuthenticator> {
  const session = await page.context().newCDPSession(page);
  await session.send("WebAuthn.enable");
  const { authenticatorId } = await session.send(
    "WebAuthn.addVirtualAuthenticator",
    {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    },
  );
  return { session, authenticatorId };
}

export async function enableVirtualAuthenticator(
  page: Page,
): Promise<VirtualAuthenticator> {
  return createVirtualAuthenticator(page);
}

export async function addCredentialToNewAuthenticator(
  page: Page,
  credential: WebAuthnCredential,
): Promise<VirtualAuthenticator> {
  const authenticator = await createVirtualAuthenticator(page);
  await authenticator.session.send("WebAuthn.addCredential", {
    authenticatorId: authenticator.authenticatorId,
    credential,
  });
  return authenticator;
}

export async function credentialsFor(
  authenticator: VirtualAuthenticator,
): Promise<WebAuthnCredential[]> {
  const result = await authenticator.session.send("WebAuthn.getCredentials", {
    authenticatorId: authenticator.authenticatorId,
  });
  return result.credentials as WebAuthnCredential[];
}
