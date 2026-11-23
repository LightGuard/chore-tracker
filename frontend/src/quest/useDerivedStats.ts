import { useCallback, useEffect, useRef, useState } from "react";
import { getDerivedStats, type DerivedStats } from "../family/api";

export type DerivedStatsStatus = "idle" | "loading" | "ready" | "error";

export type DerivedStatsState = {
  stats: DerivedStats | null;
  status: DerivedStatsStatus;
  error: string;
};

const STATS_ERROR =
  "We couldn't load Quest progress. Check your connection and try again.";

export function useDerivedStats(
  familyMemberId: number | null,
  enabled: boolean,
  refreshKey: number,
): DerivedStatsState & { reload: () => void } {
  const [stats, setStats] = useState<DerivedStats | null>(null);
  const [status, setStatus] = useState<DerivedStatsStatus>("idle");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const loadedFor = useRef<number | null>(null);

  useEffect(() => {
    if (!enabled || familyMemberId === null) {
      loadedFor.current = null;
      setStats(null);
      setStatus("idle");
      setError("");
      return;
    }

    const controller = new AbortController();
    if (loadedFor.current !== familyMemberId) {
      loadedFor.current = familyMemberId;
      setStats(null);
    }
    setStatus("loading");
    setError("");

    getDerivedStats(familyMemberId, controller.signal)
      .then((loaded) => {
        setStats(loaded);
        setStatus("ready");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof Error && reason.message
            ? reason.message
            : STATS_ERROR,
        );
        setStatus("error");
      });

    return () => controller.abort();
  }, [enabled, familyMemberId, refreshKey, reloadKey]);

  const reload = useCallback(() => setReloadKey((value) => value + 1), []);

  return { stats, status, error, reload };
}
