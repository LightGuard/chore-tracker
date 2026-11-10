export function getApiBaseUrl(
  configuredBaseUrl: string | undefined = import.meta.env.VITE_API_BASE_URL,
): string {
  const normalizedBaseUrl = configuredBaseUrl?.trim().replace(/\/+$/, "");

  return normalizedBaseUrl || "/api";
}

export const API_BASE_URL = getApiBaseUrl();