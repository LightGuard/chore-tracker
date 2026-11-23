import { DEFAULT_THEME } from "./api";

const PREFIX = "chore-tracker.theme";
const LAST_CHILD_KEY = `${PREFIX}.last-child`;
const LAST_THEME_KEY = `${PREFIX}.last-theme`;
const LAST_ADMIN_KEY = `${PREFIX}.last-admin`;
const ADMIN_HINT_KEY = `${PREFIX}.admin-hint`;

type Scope = "child" | "admin";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function cacheKey(scope: Scope, id: number): string {
  return `${PREFIX}.${scope}.${id}`;
}

function read(key: string): string | null {
  try {
    return storage()?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    storage()?.setItem(key, value);
  } catch {
    // Storage can be unavailable in private modes; the server remains canonical.
  }
}

function remove(key: string): void {
  try {
    storage()?.removeItem(key);
  } catch {
    // Ignore unavailable storage.
  }
}

export function readRememberedChildId(): number | null {
  const raw = read(LAST_CHILD_KEY);
  if (!raw) return null;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function rememberChildId(id: number): void {
  write(LAST_CHILD_KEY, String(id));
}

export function forgetRememberedChild(): void {
  remove(LAST_CHILD_KEY);
}

export function readCachedTheme(scope: Scope, id: number): string | null {
  return read(cacheKey(scope, id));
}

export function writeCachedTheme(scope: Scope, id: number, themeId: string): void {
  write(cacheKey(scope, id), themeId);
}

export function clearCachedTheme(scope: Scope, id: number): void {
  remove(cacheKey(scope, id));
}

export function readCachedAdminBootstrapTheme(): string | null {
  if (read(ADMIN_HINT_KEY) !== "1") return null;
  const raw = read(LAST_ADMIN_KEY);
  if (!raw) return null;
  const id = Number(raw);
  if (!Number.isInteger(id) || id <= 0) return null;
  return readCachedTheme("admin", id);
}

export function rememberAdministratorSession(
  administratorId: number,
  themeId: string,
): void {
  write(LAST_ADMIN_KEY, String(administratorId));
  write(ADMIN_HINT_KEY, "1");
  writeCachedTheme("admin", administratorId, themeId);
  writeLastTheme(themeId);
}

export function clearAdministratorSession(): void {
  remove(ADMIN_HINT_KEY);
  clearLastTheme();
}

export function readLastTheme(): string | null {
  return read(LAST_THEME_KEY);
}

export function writeLastTheme(themeId: string): void {
  write(LAST_THEME_KEY, themeId);
}

export function clearLastTheme(): void {
  remove(LAST_THEME_KEY);
}

export function applyDocumentTheme(themeId: string): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = themeId;
  document.body.dataset.theme = themeId;
}

/**
 * Apply the last remembered child theme before React paints. Admin pages start
 * in Homestead until /auth/me confirms an administrator; a signed-out admin
 * must never inherit the previous administrator's theme.
 */
export function applyInitialDocumentTheme(): string {
  const isAdmin =
    typeof window !== "undefined" && window.location.pathname.startsWith("/admin");
  if (isAdmin) {
    const cached = readCachedAdminBootstrapTheme();
    const themeId = cached === DEFAULT_THEME.id ? cached : DEFAULT_THEME.id;
    applyDocumentTheme(themeId);
    return themeId;
  }
  const childId = readRememberedChildId();
  const cached = childId === null ? null : readCachedTheme("child", childId);
  // Unknown ids are ignored before the catalog is available.
  const themeId = cached === DEFAULT_THEME.id ? cached : DEFAULT_THEME.id;
  applyDocumentTheme(themeId);
  return themeId;
}