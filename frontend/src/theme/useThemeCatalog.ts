import { useEffect, useState } from "react";
import { DEFAULT_THEME, getThemes, type Theme } from "./api";

type ThemeCatalogState = {
  themes: Theme[];
  loading: boolean;
  error: string;
};

export function useThemeCatalog(): ThemeCatalogState {
  const [themes, setThemes] = useState<Theme[]>([DEFAULT_THEME]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getThemes(controller.signal)
      .then((loaded) => {
        if (loaded.length > 0) setThemes(loaded);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof Error
            ? reason.message
            : "We couldn't load the theme catalog.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  return { themes, loading, error };
}
