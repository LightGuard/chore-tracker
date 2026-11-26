import { xpForObjectives } from "../quest/presentation";

/**
 * A theme-provided label for one claimable chore's reward weight.
 *
 * The extra-chores area is shared by every family theme, but the shared chore
 * weight does not mean the same thing in each theme's vocabulary (neutral
 * weight on Homestead, XP on Quest). A theme therefore supplies its own wording
 * instead of the component hardcoding one.
 */
export type ClaimWeightLabel = (weight: number) => string;

/** Neutral wording used by Homestead and any unknown or retired theme id. */
export const DEFAULT_CLAIM_WEIGHT_LABEL: ClaimWeightLabel = (weight) =>
  `Weight ${weight}`;

const THEME_CLAIM_WEIGHT_LABELS: Record<string, ClaimWeightLabel> = {
  // Quest reads the shared weight as XP. A finished extra chore counts as one
  // weighted objective, which is exactly the derived XP the API awards for a
  // done claim, so this reuses Quest's own mapping rather than restating it.
  quest: (weight) => `Worth ${xpForObjectives(1, weight)} XP`,
};

/**
 * Resolve the weight label for a family theme.
 *
 * Add an entry per theme that should not use the neutral wording. Unknown or
 * retired theme ids fall back to the default, matching the Homestead fallback
 * rule for theme selection.
 */
export function claimWeightLabelFor(themeId: string): ClaimWeightLabel {
  return THEME_CLAIM_WEIGHT_LABELS[themeId] ?? DEFAULT_CLAIM_WEIGHT_LABEL;
}
