import { useEffect, useId, useRef, useState } from "react";
import type { Theme } from "../theme/api";

type ThemeDropdownProps = {
  themes: Theme[];
  themeId: string;
  disabled: boolean;
  disabledReason?: string;
  busy?: boolean;
  onChange: (themeId: string) => void | Promise<void>;
};

export function ThemeDropdown({
  themes,
  themeId,
  disabled,
  disabledReason,
  busy = false,
  onChange,
}: ThemeDropdownProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const current = themes.find((theme) => theme.id === themeId) ?? themes[0];

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="theme-dropdown" ref={wrapRef}>
      <button
        ref={triggerRef}
        type="button"
        className="theme-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label="Theme"
        disabled={disabled || busy}
        title={disabled ? disabledReason : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        {current && (
          <img
            className="theme-trigger-thumb"
            src={current.preview_image}
            alt=""
            width="54"
            height="64"
          />
        )}
        <span className="theme-trigger-copy">
          <span className="theme-trigger-label">Theme</span>
          <strong>{current?.name ?? "Homestead"}</strong>
        </span>
        <span className="theme-trigger-caret" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div
          className="theme-menu"
          id={menuId}
          role="listbox"
          aria-label="Available themes"
        >
          {themes.map((theme) => (
            <button
              key={theme.id}
              type="button"
              role="option"
              aria-selected={theme.id === themeId}
              className={`theme-option${theme.id === themeId ? " selected" : ""}`}
              disabled={busy}
              onClick={() => {
                setOpen(false);
                void onChange(theme.id);
              }}
            >
              <img src={theme.preview_image} alt="" width="46" height="55" />
              <span>
                <strong>{theme.name}</strong>
                <small>{theme.id === themeId ? "Current theme" : "Use this theme"}</small>
              </span>
              {theme.id === themeId && (
                <span className="theme-option-check" aria-hidden="true">
                  ✓
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
