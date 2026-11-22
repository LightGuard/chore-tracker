function decodeBase64Url(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = window.atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  return bytes.buffer;
}

function encodeBase64Url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return window
    .btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function creationOptions(
  options: Record<string, unknown>,
): PublicKeyCredentialCreationOptions {
  const user = options.user as Record<string, unknown>;
  const exclude = options.excludeCredentials as
    | Array<Record<string, unknown>>
    | undefined;
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

function requestOptions(
  options: Record<string, unknown>,
): PublicKeyCredentialRequestOptions {
  const allow = options.allowCredentials as
    | Array<Record<string, unknown>>
    | undefined;
  return {
    ...options,
    challenge: decodeBase64Url(options.challenge as string),
    allowCredentials: allow?.map((item) => ({
      ...item,
      id: decodeBase64Url(item.id as string),
    })),
  } as PublicKeyCredentialRequestOptions;
}

function serializeCredential(
  credential: PublicKeyCredential,
): Record<string, unknown> {
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
      userHandle: response.userHandle
        ? encodeBase64Url(response.userHandle)
        : null,
    };
  }

  return serialized;
}

export async function registerPasskey(
  options: Record<string, unknown>,
): Promise<Record<string, unknown>> {
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

export async function authenticatePasskey(
  options: Record<string, unknown>,
): Promise<Record<string, unknown>> {
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
