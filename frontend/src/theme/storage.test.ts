import { afterEach, describe, expect, it } from "vitest";
import {
  applyInitialDocumentTheme,
  clearAdministratorSession,
  clearCachedTheme,
  clearLastTheme,
  forgetRememberedChild,
  readCachedTheme,
  readLastTheme,
  readRememberedChildId,
  rememberAdministratorSession,
  rememberChildId,
  writeCachedTheme,
  writeLastTheme,
} from "./storage";

afterEach(() => {
  window.localStorage.clear();
  window.history.pushState({}, "", "/");
  delete document.documentElement.dataset.theme;
  delete document.body.dataset.theme;
});

describe("theme storage", () => {
  it("remembers the last child and reconciles a cached theme", () => {
    rememberChildId(7);
    writeCachedTheme("child", 7, "homestead");
    writeLastTheme("homestead");

    expect(readRememberedChildId()).toBe(7);
    expect(readCachedTheme("child", 7)).toBe("homestead");
    expect(readLastTheme()).toBe("homestead");

    clearCachedTheme("child", 7);
    forgetRememberedChild();
    clearLastTheme();

    expect(readCachedTheme("child", 7)).toBeNull();
    expect(readRememberedChildId()).toBeNull();
    expect(readLastTheme()).toBeNull();
  });

  it("applies a known remembered theme before React renders", () => {
    rememberChildId(3);
    writeCachedTheme("child", 3, "homestead");

    expect(applyInitialDocumentTheme()).toBe("homestead");
    expect(document.documentElement.dataset.theme).toBe("homestead");
    expect(document.body.dataset.theme).toBe("homestead");
  });

  it("applies a cached Quest child theme before the catalog request resolves", () => {
    rememberChildId(3);
    writeCachedTheme("child", 3, "quest");

    expect(applyInitialDocumentTheme()).toBe("quest");
    expect(document.documentElement.dataset.theme).toBe("quest");
    expect(document.body.dataset.theme).toBe("quest");
  });

  it("applies a cached Sticker Club v2 child theme before the catalog request resolves", () => {
    rememberChildId(4);
    writeCachedTheme("child", 4, "sticker-club-v2");

    expect(applyInitialDocumentTheme()).toBe("sticker-club-v2");
    expect(document.documentElement.dataset.theme).toBe("sticker-club-v2");
    expect(document.body.dataset.theme).toBe("sticker-club-v2");
  });

  it("applies a cached Quest admin theme only while an admin hint exists", () => {
    window.history.pushState({}, "", "/admin");
    rememberAdministratorSession(1, "quest");

    expect(applyInitialDocumentTheme()).toBe("quest");
    expect(document.documentElement.dataset.theme).toBe("quest");

    clearAdministratorSession();
    expect(applyInitialDocumentTheme()).toBe("homestead");
    expect(document.documentElement.dataset.theme).toBe("homestead");
  });

  it("ignores unknown cached ids and starts admin pages in Homestead", () => {
    rememberChildId(3);
    writeCachedTheme("child", 3, "future-theme");

    expect(applyInitialDocumentTheme()).toBe("homestead");
    expect(document.documentElement.dataset.theme).toBe("homestead");

    window.history.pushState({}, "", "/admin");
    writeCachedTheme("admin", 1, "quest");
    expect(applyInitialDocumentTheme()).toBe("homestead");
    expect(document.documentElement.dataset.theme).toBe("homestead");
  });
});