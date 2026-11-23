import { Alert, Button } from "reshaped";
import type { Theme } from "../theme/api";

type ThemePickerProps = {
  themes: Theme[];
  childName: string;
  selectedId: string;
  busy: boolean;
  error: string;
  onSelect: (themeId: string) => void | Promise<void>;
  onRetry?: () => void;
};

export function ThemePicker({
  themes,
  childName,
  selectedId,
  busy,
  error,
  onSelect,
  onRetry,
}: ThemePickerProps) {
  return (
    <section className="theme-picker-panel" aria-labelledby="theme-picker-heading">
      <div className="section-kicker">First time here</div>
      <h2 id="theme-picker-heading">Pick a look for {childName}</h2>
      <p className="section-lede">
        This saves right away and opens {childName}&rsquo;s chore. You can switch
        it from the header later.
      </p>
      {error && (
        <Alert
          color="critical"
          title="Theme was not saved"
          actionsSlot={
            onRetry ? (
              <Button
                variant="outline"
                disabled={busy}
                onClick={onRetry}
              >
                Try again
              </Button>
            ) : undefined
          }
        >
          {error}
        </Alert>
      )}
      <div className="theme-card-grid">
        {themes.map((theme) => (
          <button
            key={theme.id}
            type="button"
            className={`theme-card${theme.id === selectedId ? " selected" : ""}`}
            aria-pressed={theme.id === selectedId}
            disabled={busy}
            onClick={() => void onSelect(theme.id)}
          >
            <img src={theme.preview_image} alt="" />
            <span className="theme-card-copy">
              <strong>{theme.name}</strong>
              <span>{theme.id === selectedId ? "Current look" : "Choose this look"}</span>
            </span>
            {theme.id === selectedId && (
              <span className="theme-card-check" aria-hidden="true">
                ✓
              </span>
            )}
          </button>
        ))}
      </div>
      {busy && (
        <p className="theme-saving" role="status">
          Saving your theme&hellip;
        </p>
      )}
    </section>
  );
}