import { describe, expect, it } from "vitest";
import {
  claimWeightLabelFor,
  DEFAULT_CLAIM_WEIGHT_LABEL,
} from "./claimsPresentation";

describe("claim weight labels", () => {
  it("uses neutral weight wording for Homestead", () => {
    expect(claimWeightLabelFor("homestead")(2)).toBe("Weight 2");
    expect(claimWeightLabelFor("homestead")(0)).toBe("Weight 0");
  });

  it("uses Quest's own weight-to-XP mapping for Quest", () => {
    expect(claimWeightLabelFor("quest")(1)).toBe("Worth 10 XP");
    expect(claimWeightLabelFor("quest")(2)).toBe("Worth 20 XP");
    expect(claimWeightLabelFor("quest")(0)).toBe("Worth 0 XP");
  });

  it("falls back to neutral wording for unknown or retired theme ids", () => {
    expect(claimWeightLabelFor("sticker-club-v2")(3)).toBe("Weight 3");
    expect(claimWeightLabelFor("retired-theme")(3)).toBe("Weight 3");
    expect(claimWeightLabelFor("")(5)).toBe("Weight 5");
  });

  it("exposes the neutral default label on its own", () => {
    expect(DEFAULT_CLAIM_WEIGHT_LABEL(7)).toBe("Weight 7");
  });
});
