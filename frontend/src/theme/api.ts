import { apiRequest } from "../api/client";

export type Theme = {
  id: string;
  name: string;
  preview_image: string;
};

export type ThemeUpdateResult = {
  theme_id: string;
};

export const DEFAULT_THEME: Theme = {
  id: "homestead",
  name: "Homestead",
  preview_image: "/theme-previews/homestead.png",
};

/** Theme ids the frontend can safely paint before the catalog request resolves. */
export const BUNDLED_THEME_IDS = new Set(["homestead", "quest"]);

export function resolveBootstrapThemeId(
  themeId: string | null | undefined,
): string {
  return themeId && BUNDLED_THEME_IDS.has(themeId) ? themeId : DEFAULT_THEME.id;
}

export function getThemes(signal?: AbortSignal): Promise<Theme[]> {
  return apiRequest<Theme[]>("/themes", { signal });
}

export function updateFamilyMemberTheme(
  familyMemberId: number,
  themeId: string,
): Promise<ThemeUpdateResult> {
  return apiRequest<ThemeUpdateResult>(
    `/family-members/${familyMemberId}/theme`,
    {
      method: "PUT",
      body: JSON.stringify({ theme_id: themeId }),
    },
  );
}

export function updateAdministratorTheme(
  themeId: string,
): Promise<ThemeUpdateResult> {
  return apiRequest<ThemeUpdateResult>("/auth/me/theme", {
    method: "PUT",
    body: JSON.stringify({ theme_id: themeId }),
  });
}

export function resolveThemeId(
  themeId: string | null | undefined,
  themes: Theme[],
): string {
  if (themeId && themes.some((theme) => theme.id === themeId)) {
    return themeId;
  }
  return DEFAULT_THEME.id;
}

export function themeForId(themeId: string, themes: Theme[]): Theme {
  return themes.find((theme) => theme.id === themeId) ?? DEFAULT_THEME;
}
