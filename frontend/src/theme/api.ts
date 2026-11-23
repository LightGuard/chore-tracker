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
