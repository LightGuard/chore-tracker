import type { DerivedStats } from "../family/api";

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

/**
 * Family-wide achievement rank from the shared `household.xp_rankings` value.
 *
 * The rank comes from each child's lifetime total XP, so it is independent of
 * the weekly standings order and the configured display order. Children tied on
 * total XP share a rank. The XP gap is measured against the highest lifetime
 * total so it stays on the same scale as the rank.
 */
export function questLeaderboard(stats: DerivedStats): QuestLeaderboard {
  const rankings = stats.household.xp_rankings;
  const selected = rankings.find(
    (ranking) => ranking.family_member_id === stats.family_member_id,
  );
  const leadingXp = rankings.reduce(
    (highest, ranking) => Math.max(highest, ranking.total_xp),
    0,
  );

  return {
    rank: selected?.rank ?? null,
    playerCount: stats.household.active_players,
    gapToFirstXp: selected ? Math.max(0, leadingXp - selected.total_xp) : 0,
  };
}
