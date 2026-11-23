import type { Theme } from "../theme/api";
import { ThemeDropdown } from "./ThemeDropdown";

type AppHeaderProps = {
  themes: Theme[];
  themeId: string;
  themeDisabled: boolean;
  themeDisabledReason?: string;
  themeBusy?: boolean;
  onThemeChange: (themeId: string) => void | Promise<void>;
  currentChild?: string;
  onSwitchChild?: () => void;
  currentAdministrator?: string;
  context?: "family" | "admin";
};

export function AppHeader({
  themes,
  themeId,
  themeDisabled,
  themeDisabledReason,
  themeBusy,
  onThemeChange,
  currentChild,
  onSwitchChild,
  currentAdministrator,
  context = "family",
}: AppHeaderProps) {
  const isQuest = themeId === "quest";

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <a
          className="app-brand"
          href="/"
          aria-label={isQuest ? "Quest home" : "Chore Tracker home"}
        >
          <span className="app-brand-mark" aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3.2 9.2 10 3.3l6.8 5.9v7.1a.8.8 0 0 1-.8.8H4a.8.8 0 0 1-.8-.8V9.2Z" />
              <path d="M7.6 17.1v-5h4.8v5" />
            </svg>
          </span>
          <span className="app-brand-copy">
            <strong>
              {isQuest ? (
                <>
                  QUE<span className="quest-wordmark-accent">ST</span>
                </>
              ) : (
                "Chore Tracker"
              )}
            </strong>
            <span>{isQuest ? "family command" : "our house, one page"}</span>
          </span>
        </a>

        <div className="app-header-identity">
          {currentChild ? (
            <>
              <span className="identity-label">
                {isQuest ? "Playing as" : "Doing chores"}
              </span>
              <strong>{currentChild}</strong>
              {onSwitchChild && (
                <button type="button" className="text-button" onClick={onSwitchChild}>
                  Switch child
                </button>
              )}
            </>
          ) : currentAdministrator ? (
            <>
              <span className="identity-label">Administrator</span>
              <strong>{currentAdministrator}</strong>
            </>
          ) : (
            <span className="identity-label">
              {context === "admin"
                ? "No administrator signed in"
                : "No child selected"}
            </span>
          )}
        </div>

        <div className="app-header-theme">
          <ThemeDropdown
            themes={themes}
            themeId={themeId}
            disabled={themeDisabled}
            disabledReason={themeDisabledReason}
            busy={themeBusy}
            onChange={onThemeChange}
          />
        </div>
      </div>
    </header>
  );
}