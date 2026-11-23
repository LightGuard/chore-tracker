import { useEffect, useRef, useState } from "react";
import { Alert, Button, Checkbox, Loader } from "reshaped";
import type { ChecklistItem, CurrentAssignment } from "../family/api";
import type { DerivedStatsStatus } from "../family/useDerivedStats";
import type { StickerWeek } from "./presentation";

const dateFormatter = new Intl.DateTimeFormat("en", {
  weekday: "long",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return dateFormatter.format(new Date(Date.UTC(year, month - 1, day)));
}

type StickerHeaderCountProps = {
  count: number | null;
  status: DerivedStatsStatus;
};

export function StickerHeaderCount({ count, status }: StickerHeaderCountProps) {
  const accessibleLabel =
    count === null
      ? status === "error"
        ? "Sticker count unavailable"
        : "Sticker count loading"
      : `${count} of 7 this week`;

  return (
    <span
      className="sticker-header-count"
      role="status"
      aria-label={accessibleLabel}
    >
      <b>{count ?? "—"}</b>
      <span>OF 7 STICKERS</span>
    </span>
  );
}

type StickerAssignmentViewProps = {
  displayName: string;
  assignment: CurrentAssignment;
  weekNumber: number;
  week: StickerWeek;
  statsStatus: DerivedStatsStatus;
  statsError: string;
  onRetryStats: () => void;
  savingItemId: number | null;
  saveError: string;
  onToggle: (item: ChecklistItem, checked: boolean) => void | Promise<void>;
};

export function StickerAssignmentView({
  displayName,
  assignment,
  weekNumber,
  week,
  statsStatus,
  statsError,
  onRetryStats,
  savingItemId,
  saveError,
  onToggle,
}: StickerAssignmentViewProps) {
  const completedCount = assignment.checklist_items.filter(
    (item) => item.is_completed,
  ).length;
  const itemCount = assignment.checklist_items.length;
  const nextIncompleteId = assignment.checklist_items.find(
    (item) => !item.is_completed,
  )?.id;
  const listRef = useRef<HTMLOListElement>(null);
  const [rail, setRail] = useState({
    visible: false,
    top: 0,
    height: 100,
    scrollTop: 0,
  });

  function updateRail() {
    const list = listRef.current;
    if (!list) return;
    const maxScroll = list.scrollHeight - list.clientHeight;
    const height =
      list.scrollHeight > 0
        ? Math.max(10, Math.min(100, (list.clientHeight / list.scrollHeight) * 100))
        : 100;
    setRail({
      visible: maxScroll > 1,
      top:
        maxScroll > 0
          ? (list.scrollTop / maxScroll) * (100 - height)
          : 0,
      height,
      scrollTop: list.scrollTop,
    });
  }

  useEffect(() => {
    updateRail();
    const list = listRef.current;
    if (!list || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(updateRail);
    observer.observe(list);
    return () => observer.disconnect();
  }, [assignment.checklist_items, savingItemId]);

  const scrollCopy = !rail.visible
    ? "All jobs in view"
    : rail.scrollTop < 4
      ? "Scroll · more jobs below"
      : "Scrolled · more jobs below";
  const stampCount = week.count === null ? "—" : String(week.count);

  return (
    <div className="sticker-board">
      <header className="sticker-intro">
        <div className="sticker-kicker">
          {formatDate(assignment.today)} · Week {weekNumber}
        </div>
        <h1>
          Hey, <em>{displayName}!</em> Fill your sticker.
        </h1>
        <p className="sticker-subline">
          <b>{itemCount} little jobs.</b> One chore, one sticker at a time.
        </p>
      </header>

      {statsStatus === "loading" && week.count === null ? (
        <div className="sticker-stats-loading" role="status">
          <Loader ariaLabel="Loading sticker count" size="small" />
          <span>Syncing this week&rsquo;s stickers&hellip;</span>
        </div>
      ) : null}

      {statsStatus === "error" && (
        <Alert
          color="warning"
          title="Sticker count unavailable"
          actionsSlot={
            <Button variant="outline" onClick={onRetryStats}>
              Try again
            </Button>
          }
        >
          {statsError ||
            "The jobs still work. Sticker progress will retry when you are ready."}
        </Alert>
      )}

      <div className="sticker-layout">
        <div className="sticker-main">
          <section
            className="sticker-chore"
            aria-labelledby="assignment-heading"
          >
            <div className="sticker-chore-top">
              <span className="sticker-tag">Today&rsquo;s chore</span>
              <span className="sticker-week-label">
                Week {weekNumber} · {completedCount} / {itemCount}
              </span>
            </div>
            <h2 id="assignment-heading">{assignment.chore_name}</h2>
            {assignment.chore_description && (
              <p className="sticker-description">{assignment.chore_description}</p>
            )}
            <div className="sticker-chore-progress">
              <span className="sticker-big-count">
                {completedCount}
                <span>/{itemCount}</span>
              </span>
              <span className="sticker-bars" aria-hidden="true">
                {assignment.checklist_items.map((item) => (
                  <i
                    key={item.id}
                    className={item.is_completed ? "on" : undefined}
                  />
                ))}
              </span>
              <span className="sticker-progress-label">
                {completedCount} done · {itemCount - completedCount} to go
              </span>
            </div>
          </section>

          {assignment.is_complete && (
            <div className="sticker-stamp" role="status">
              <span>STICKER {stampCount} OF 7</span>
              <strong>Sticker earned.</strong>
            </div>
          )}

          <div className="sticker-list-head">
            <h2>The jobs</h2>
            <span>Fixed window · scroll inside</span>
          </div>

          <div className="sticker-listwindow">
            {assignment.checklist_items.length === 0 ? (
              <Alert color="warning" title="No jobs yet">
                This chore does not have any checklist items.
              </Alert>
            ) : (
              <ol
                ref={listRef}
                className="sticker-jobs"
                aria-label="Today's checklist"
                onScroll={updateRail}
              >
                {assignment.checklist_items.map((item, index) => {
                  const isNext =
                    !item.is_completed && item.id === nextIncompleteId;
                  return (
                    <li
                      key={item.id}
                      className={`sticker-job ${
                        item.is_completed ? "done" : isNext ? "next" : "open"
                      }`}
                    >
                      <span className="sticker-job-number" aria-hidden="true">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <Checkbox
                        name={"checklist-item-" + item.id}
                        value={String(item.id)}
                        checked={item.is_completed}
                        disabled={savingItemId !== null}
                        onChange={({ checked }) =>
                          void onToggle(item, checked)
                        }
                        className="sticker-job-checkbox"
                      >
                        {item.label}
                      </Checkbox>
                      <span className="sticker-job-status" aria-hidden="true">
                        {item.is_completed ? "DONE" : isNext ? "NEXT" : "OPEN"}
                      </span>
                      <span className="sticker-job-box" aria-hidden="true">
                        {item.is_completed ? "✓" : ""}
                      </span>
                    </li>
                  );
                })}
              </ol>
            )}
            {rail.visible && (
              <span className="sticker-scroll-rail" aria-hidden="true">
                <i
                  style={{
                    top: `${rail.top}%`,
                    height: `${rail.height}%`,
                  }}
                />
              </span>
            )}
            <span className="sticker-list-fade" aria-hidden="true" />
          </div>

          <div className="sticker-scroll-cue">
            <span>{scrollCopy}</span>
            <b>
              {completedCount} / {itemCount} done
            </b>
          </div>

          {saveError && (
            <Alert color="critical" title="Couldn't save that job">
              {saveError}
            </Alert>
          )}

          <p className="sticker-hint">
            All <b>{itemCount} jobs</b> fill today&rsquo;s sticker.
          </p>
        </div>

        <aside className="sticker-aside">
          <section
            className="sticker-week"
            aria-labelledby="sticker-week-heading"
          >
            <div className="sticker-week-head">
              <h2 id="sticker-week-heading">This week</h2>
              <span>
                {week.count === null ? "—" : week.count} / 7 days
              </span>
            </div>
            <ol
              className="sticker-week-rail"
              aria-label="This week's stickers"
            >
              {week.days.map((day) => (
                <li
                  key={day.date}
                  className={`sticker-day ${day.state}${
                    day.isToday ? " today" : ""
                  }`}
                  aria-label={day.ariaLabel}
                >
                  <span className="sticker-day-letter" aria-hidden="true">
                    {day.dayLabel}
                  </span>
                  <span className="sticker-day-status" aria-hidden="true">
                    {day.statusLabel}
                  </span>
                </li>
              ))}
            </ol>
            <p className="sticker-week-note">
              One sticker for each complete day. A new week starts with a
              clean sheet.
            </p>
          </section>

          <div className="sticker-aside-poster" aria-hidden="true">
            <span>No pictograms · just the plan</span>
            <strong>
              Do the job.
              <br />
              Take the sticker.
            </strong>
            <i />
            <b />
          </div>
        </aside>
      </div>
    </div>
  );
}
