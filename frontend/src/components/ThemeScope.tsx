import type { ReactNode } from "react";

export function ThemeScope({
  themeId,
  children,
}: {
  themeId: string;
  children: ReactNode;
}) {
  return (
    <div className={`theme-scope theme-${themeId}`} data-theme={themeId}>
      {children}
    </div>
  );
}
