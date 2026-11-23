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
  ariaLabel: string;
};

export type StickerWeek = {
  count: number | null;
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

const STATE_COPY: Record<StickerDayState, { visible: string; spoken: string }> = {
  complete: { visible: "DONE", spoken: "complete" },
  incomplete: { visible: "PART", spoken: "incomplete" },
  not_recorded: { visible: "—", spoken: "not recorded" },
  unknown: { visible: "?", spoken: "unavailable" },
};

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
): StickerDay {
  const copy = STATE_COPY[state];
  return {
    date,
    dayLabel: WEEKDAY_LABELS[index],
    state,
    statusLabel: copy.visible,
    isToday,
    ariaLabel: `${WEEKDAY_NAMES[index]}, ${copy.spoken}${isToday ? ", today" : ""}`,
  };
}

export function stickerWeek(
  stats: DerivedStats | null,
  assignment?: CurrentAssignment,
): StickerWeek {
  const weekStart = stats?.current_week.week_start ?? assignment?.week_start;
  if (!weekStart) return { count: null, days: [] };

  const statsDays = stats?.current_week.days ?? [];
  const days = Array.from({ length: 7 }, (_, index) => {
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

    return dayFromState(date, index, state, isToday);
  });

  const count = stats
    ? days.filter((day) => day.state === "complete").length
    : null;
  return { count, days };
}
