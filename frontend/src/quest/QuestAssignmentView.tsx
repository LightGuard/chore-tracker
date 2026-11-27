import type { CSSProperties } from "react";
import { Alert, Button, Checkbox, Loader } from "reshaped";
import type { ChecklistItem, CurrentAssignment, DerivedStats } from "../family/api";
import {
  questLeaderboard,
  questLevelProgress,
  xpForObjectives,
} from "./presentation";
import type { DerivedStatsStatus } from "../family/useDerivedStats";

const questDateFormatter = new Intl.DateTimeFormat("en", {
  weekday: "short",
  day: "2-digit",
  month: "short",
  timeZone: "UTC",
});

function formatQuestDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return questDateFormatter
    .format(new Date(Date.UTC(year, month - 1, day)))
    .toUpperCase()
    .replace(",", " ·");
}

type QuestAssignmentViewProps = {
  displayName: string;
  assignment: CurrentAssignment;
  weekNumber: number;
  stats: DerivedStats | null;
  statsStatus: DerivedStatsStatus;
  statsError: string;
  onRetryStats: () => void;
  savingItemId: number | null;
  saveError: string;
  onToggle: (item: ChecklistItem, checked: boolean) => void | Promise<void>;
};

export function QuestAssignmentView({
  displayName,
  assignment,
  weekNumber,
  stats,
  statsStatus,
  statsError,
  onRetryStats,
  savingItemId,
  saveError,
  onToggle,
}: QuestAssignmentViewProps) {
  const completedCount = assignment.checklist_items.filter(
    (item) => item.is_completed,
  ).length;
  const itemCount = assignment.checklist_items.length;
  const todayXp = xpForObjectives(itemCount, assignment.chore_weight);
  const hasOptionalItems = assignment.checklist_items.some(
    (item) => !item.is_required,
  );
  const nextIncompleteId = assignment.checklist_items.find(
    (item) => !item.is_completed,
  )?.id;
  const level = stats ? questLevelProgress(stats) : null;
  const leaderboard = stats ? questLeaderboard(stats) : null;
  const rankLabel =
    leaderboard?.rank != null
      ? `#${String(leaderboard.rank).padStart(2, "0")}`
      : "#--";
  const rankGapLabel =
    leaderboard?.rank == null
      ? stats
        ? "RANK UNAVAILABLE"
        : "STATS UNAVAILABLE"
      : leaderboard.rank === 1
        ? "YOU'RE #1"
        : `${leaderboard.gapToFirstXp} XP TO #1`;
  const nextLevelXp = level ? level.level * 500 : 0;
  const progressStyle = {
    "--quest-progress": `${Math.round((level?.progress ?? 0) * 100)}%`,
  } as CSSProperties;
  const weeklyDays = stats?.current_week.days ?? [];
  const streak = stats?.lifetime.current_streak ?? 0;

  return (
    <div className="quest-board">
      <section className="quest-player" aria-label="Quest progress">
        <div className="quest-avatar" style={progressStyle} aria-hidden="true">
          <span>{displayName.slice(0, 1).toUpperCase()}</span>
        </div>
        <div className="quest-player-copy">
          <div className="quest-name-row">
            <strong className="quest-player-name">{displayName}</strong>
            <span className="quest-level">
              {level ? `LVL ${String(level.level).padStart(2, "0")}` : "LVL --"}
            </span>
          </div>
          <p className="quest-xp">
            {level
              ? `${level.xp.toLocaleString()} / ${nextLevelXp.toLocaleString()} XP`
              : statsStatus === "error"
                ? "Progress unavailable"
                : "Progress is loading"}
          </p>
          <div
            className="quest-xp-track"
            role="progressbar"
            aria-label="Progress to next level"
            aria-valuemin={0}
            aria-valuemax={500}
            aria-valuenow={level?.xpIntoLevel ?? 0}
            aria-valuetext={
              level
                ? `${level.xpIntoLevel} of 500 XP to level ${level.level + 1}`
                : "Progress is unavailable"
            }
          >
            <i style={{ width: `${(level?.progress ?? 0) * 100}%` }} />
          </div>
        </div>
        <p className="quest-rank">
          <span>XP RANK</span>
          <strong aria-label={`XP rank ${leaderboard?.rank ?? "unknown"} of ${leaderboard?.playerCount ?? 0}`}>
            {rankLabel}
          </strong>
        </p>
      </section>

      {statsStatus === "loading" && !stats && (
        <div className="quest-stats-status" role="status">
          <Loader ariaLabel="Loading Quest progress" size="small" />
          <span>Syncing your run&hellip;</span>
        </div>
      )}

      {statsStatus === "error" && (
        <Alert
          color="warning"
          title="Quest progress unavailable"
          actionsSlot={
            <Button variant="outline" onClick={onRetryStats}>
              Try again
            </Button>
          }
        >
          {statsError || "Your checklist still works. Progress will retry."}
        </Alert>
      )}

      <section
        className="quest-card"
        aria-labelledby="assignment-heading"
      >
        <div className="quest-card-top">
          <span className="quest-tag">DAILY QUEST</span>
          <span className="quest-date">
            {formatQuestDate(assignment.today)}
          </span>
        </div>
        <h2 id="assignment-heading" className="quest-chore-name">
          {assignment.chore_name}
        </h2>
        {assignment.chore_description && (
          <p className="quest-description">{assignment.chore_description}</p>
        )}
        <div className="quest-meta">
          <span className="quest-xp-chip">
            {assignment.is_complete
              ? `+${todayXp} XP TODAY`
              : `UP TO +${todayXp} XP TODAY`}
          </span>
          <span>{level ? `${level.weeklyXp} XP THIS WEEK` : "WEEKLY XP --"}</span>
          <span>{itemCount} OBJECTIVES</span>
          <span>{completedCount} / {itemCount} CLEARED</span>
        </div>
        <div
          className="quest-progress-segments"
          aria-hidden="true"
        >
          {assignment.checklist_items.map((item) => (
            <i
              key={item.id}
              className={item.is_completed ? "on" : undefined}
            />
          ))}
        </div>
        <div className="quest-week-row">
          <span>
            WEEK {weekNumber} · {stats ? stats.current_week.complete_days : "–"} / 7
            DAYS CLEARED
          </span>
          <span className="quest-week-segments" aria-hidden="true">
            {Array.from({ length: 7 }, (_, index) => {
              const day = weeklyDays[index];
              return (
                <i
                  key={day?.date ?? index}
                  className={day?.state === "complete" ? "on" : undefined}
                />
              );
            })}
          </span>
        </div>
      </section>

      {assignment.is_complete && (
        <div className="quest-clear" role="status">
          <span>QUEST CLEAR</span>
          <strong>
            {hasOptionalItems ? "Every required objective is done today." : "Every objective is done today."}
            {stats ? ` ${streak}-day streak.` : ""}
          </strong>
        </div>
      )}

      {assignment.checklist_items.length === 0 ? (
        <Alert color="warning" title="No objectives yet">
          This chore does not have any checklist items.
        </Alert>
      ) : (
        <ol className="quest-objectives" aria-label="Today's checklist">
          {assignment.checklist_items.map((item, index) => {
            const state = item.is_completed
              ? "cleared"
              : item.id === nextIncompleteId
                ? "active"
                : "open";
            return (
              <li
                key={item.id}
                className={`quest-objective ${state}`}
              >
                <span className="quest-objective-index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <Checkbox
                  name={"checklist-item-" + item.id}
                  value={String(item.id)}
                  checked={item.is_completed}
                  disabled={savingItemId !== null}
                  onChange={({ checked }) => void onToggle(item, checked)}
                  className="quest-objective-checkbox"
                >
                  {item.label}
                  {!item.is_required && (
                    <span className="optional-item-tag">Optional</span>
                  )}
                </Checkbox>
                <span className="quest-objective-state" aria-hidden="true">
                  {state === "cleared"
                    ? "CLEARED"
                    : state === "active"
                      ? "ACTIVE"
                      : "OPEN"}
                </span>
                <span className="quest-objective-xp" aria-hidden="true">
                  +10 XP
                </span>
                <span className="quest-hex" aria-hidden="true">
                  {item.is_completed ? "✓" : ""}
                </span>
              </li>
            );
          })}
        </ol>
      )}

      {saveError && (
        <Alert color="critical" title="Couldn't save that objective">
          {saveError}
        </Alert>
      )}

      <div className="quest-streak">
        <span className="quest-flame" aria-hidden="true">▲</span>
        <strong>{stats ? `${streak}-DAY STREAK` : "STREAK --"}</strong>
        <span className="quest-streak-copy">
          {streak > 0
            ? "Clear every objective to keep it going."
            : "Clear every objective to start one."}
        </span>
      </div>

      <div className="quest-squad" aria-live="polite">
        <span className="quest-squad-label">ACHIEVEMENT RANK</span>
        <strong>
          {rankLabel} <span>OF {leaderboard?.playerCount ?? "–"}</span>
        </strong>
        <span className="quest-gap">{rankGapLabel}</span>
      </div>
    </div>
  );
}
