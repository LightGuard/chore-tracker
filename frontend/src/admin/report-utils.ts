const monthFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  timeZone: "UTC",
});

const generatedFormatter = new Intl.DateTimeFormat("en", {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

const weekdayFormatter = new Intl.DateTimeFormat("en", {
  weekday: "short",
  timeZone: "UTC",
});

export function fromLocalDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function formatWeekRange(start: string, end: string): string {
  const startDate = fromLocalDate(start);
  const endDate = fromLocalDate(end);
  const startMonth = monthFormatter.format(startDate);
  const endMonth = monthFormatter.format(endDate);
  const startLabel = `${startMonth} ${startDate.getUTCDate()}`;
  const endLabel =
    startMonth === endMonth
      ? `${endDate.getUTCDate()}`
      : `${endMonth} ${endDate.getUTCDate()}`;
  return `${startLabel} – ${endLabel}, ${endDate.getUTCFullYear()}`;
}

export function formatReportWeekday(value: string): string {
  return weekdayFormatter.format(fromLocalDate(value));
}

export function formatGeneratedAt(value: string): string {
  return generatedFormatter.format(new Date(value));
}

export function reportCompletionPercent(completed: number, total: number): number {
  return total > 0 ? Math.round((completed / total) * 100) : 0;
}
