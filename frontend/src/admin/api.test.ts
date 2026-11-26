import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE_URL } from "../config/api";
import { markReportEntryRewarded } from "./api";

const REWARD = {
  rewarded_at: "2026-11-26T15:30:00Z",
  rewarded_by: {
    administrator_id: 1,
    email: "admin@example.test",
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("markReportEntryRewarded", () => {
  it("PUTs to the entry reward endpoint and returns the persisted audit record", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify(REWARD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const reward = await markReportEntryRewarded("2026-11-16", 12);

    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE_URL}/reports/2026-11-16/entries/12/reward`,
      expect.objectContaining({ method: "PUT", credentials: "include" }),
    );
    expect(reward).toEqual(REWARD);
  });
});
