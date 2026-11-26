import type {
  CurrentAssignment,
  DerivedStats,
  DerivedStatsDayState,
} from "../family/api";

export type StickerDayState = DerivedStatsDayState | "unknown";

export type StickerDay = {
  date: string;
  dayLabel: string;
  state: StickerDayState;
  statusLabel: string;
  isToday: boolean;
  /** Stickers this day mints for this week's chore, or null when unknown. */
  earned: number | null;
  ariaLabel: string;
};

export type StickerWeek = {
  /** Total stickers earned this week, or null while the inputs are unknown. */
  count: number | null;
  /** Complete days in the current week, or null while stats are unknown. */
  completeDays: number | null;
  /** Stickers a complete day mints for this week's chore, or null when unknown. */
  perDay: number | null;
  days: StickerDay[];
};

const WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];
const WEEKDAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
const WEEK_DAY_COUNT = 7;

const STATE_COPY: Record<StickerDayState, { visible: string; spoken: string }> = {
  complete: { visible: "DONE", spoken: "complete" },
  incomplete: { visible: "PART", spoken: "incomplete" },
  not_recorded: { visible: "—", spoken: "not recorded" },
  unknown: { visible: "?", spoken: "unavailable" },
};

/** Sticker Club's own ceiling for a chore weight. */
export const STICKER_WEIGHT_MAX = 10;

/**
 * Sticker Club's mapping from the shared chore weight to the stickers a
 * complete day mints: one sticker per weight point, between 0 and 10. A weight
 * of 0 mints nothing and 1 keeps the original one-sticker-per-day behaviour.
 *
 * The chore domain stores the weight without interpreting it; this policy is
 * Sticker Club's own and is documented in `docs/themes.md`.
 */
export function stickersForWeight(weight: number): number {
  if (!Number.isFinite(weight)) return 0;
  return Math.min(STICKER_WEIGHT_MAX, Math.max(0, Math.trunc(weight)));
}

export function formatStickerCount(count: number): string {
  return `${count} sticker${count === 1 ? "" : "s"}`;
}

function addDays(value: string, days: number): string {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + days));
  return date.toISOString().slice(0, 10);
}

function dayFromState(
  date: string,
  index: number,
  state: StickerDayState,
  isToday: boolean,
  perDay: number | null,
): StickerDay {
  const copy = STATE_COPY[state];
  const earned =
    state === "complete" ? perDay : state === "unknown" ? null : 0;
  const earnedCopy =
    earned === null || earned === 0 ? "" : `, ${formatStickerCount(earned)}`;
  return {
    date,
    dayLabel: WEEKDAY_LABELS[index],
    state,
    statusLabel: copy.visible,
    isToday,
    earned,
    ariaLabel: `${WEEKDAY_NAMES[index]}, ${copy.spoken}${earnedCopy}${
      isToday ? ", today" : ""
    }`,
  };
}

/**
 * The week's sticker sheet. Each complete day mints `chore_weight` stickers
 * from the immutable assignment snapshot, so the weekly total ranges from 0 to
 * 70 and the same weight is used for every day the view can award.
 */
export function stickerWeek(
  stats: DerivedStats | null,
  assignment?: CurrentAssignment,
): StickerWeek {
  const weekStart = stats?.current_week.week_start ?? assignment?.week_start;
  const perDay = assignment
    ? stickersForWeight(assignment.chore_weight)
    : null;
  if (!weekStart) {
    return { count: null, completeDays: null, perDay, days: [] };
  }

  const statsDays = stats?.current_week.days ?? [];
  const days = Array.from({ length: WEEK_DAY_COUNT }, (_, index) => {
    const source = statsDays[index];
    const date = source?.date ?? addDays(weekStart, index);
    const isToday = date === assignment?.today;
    let state: StickerDayState = source?.state ?? "unknown";

    if (stats && assignment && isToday) {
      const completed = assignment.checklist_items.filter(
        (item) => item.is_completed,
      ).length;
      if (assignment.is_complete) {
        state = "complete";
      } else if (completed > 0 || state !== "not_recorded") {
        state = "incomplete";
      } else {
        state = "not_recorded";
      }
    }

    return dayFromState(date, index, state, isToday, perDay);
  });

  const completeDays = stats
    ? days.filter((day) => day.state === "complete").length
    : null;
  const count =
    completeDays !== null && perDay !== null ? completeDays * perDay : null;
  return { count, completeDays, perDay, days };
}
