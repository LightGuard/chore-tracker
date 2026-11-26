import type { DerivedStats, DerivedStatsStanding } from "../family/api";

export const QUEST_XP_PER_ITEM_WEIGHT = 10;
export const QUEST_XP_PER_LEVEL = 500;

export type QuestLevelProgress = {
  xp: number;
  level: number;
  xpIntoLevel: number;
  xpForNextLevel: number;
  progress: number;
  weeklyXp: number;
};

export type QuestLeaderboard = {
  rank: number | null;
  playerCount: number;
  gapToFirstXp: number;
  selected: DerivedStatsStanding | null;
};

export function xpForObjectives(itemCount: number, choreWeight: number): number {
  return (
    Math.max(0, itemCount) * Math.max(0, choreWeight) * QUEST_XP_PER_ITEM_WEIGHT
  );
}

export function levelForXp(xp: number): number {
  return 1 + Math.floor(Math.max(0, xp) / QUEST_XP_PER_LEVEL);
}

export function questLevelProgress(stats: DerivedStats): QuestLevelProgress {
  const xp = Math.max(0, stats.lifetime.xp);
  const xpIntoLevel = xp % QUEST_XP_PER_LEVEL;
  return {
    xp,
    level: levelForXp(xp),
    xpIntoLevel,
    xpForNextLevel: QUEST_XP_PER_LEVEL,
    progress: xpIntoLevel / QUEST_XP_PER_LEVEL,
    weeklyXp: Math.max(0, stats.current_week.xp),
  };
}

export function questLeaderboard(stats: DerivedStats): QuestLeaderboard {
  const standings = stats.household.weekly_standings;
  const selectedIndex = standings.findIndex(
    (standing) => standing.family_member_id === stats.family_member_id,
  );
  const selected = selectedIndex === -1 ? null : standings[selectedIndex];
  const leader = standings[0] ?? null;
  const gapToFirstXp =
    selected && leader ? Math.max(0, leader.xp - selected.xp) : 0;

  return {
    rank: selectedIndex === -1 ? null : selectedIndex + 1,
    playerCount: stats.household.active_players,
    gapToFirstXp,
    selected,
  };
}
