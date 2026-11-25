import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssignmentGenerator } from "./AssignmentGenerator";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const generatedResult = {
  week_start: "2026-11-16",
  week_end: "2026-11-22",
  status: "generated" as const,
  assignment_count: 2,
  assignments: [
    {
      id: 1,
      family_member_id: 1,
      family_member_name: "Alex",
      chore_id: 2,
      chore_name: "Kitchen",
      week_start: "2026-11-16",
      week_end: "2026-11-22",
    },
    {
      id: 2,
      family_member_id: 2,
      family_member_name: "Zoe",
      chore_id: 1,
      chore_name: "Bathroom",
      week_start: "2026-11-16",
      week_end: "2026-11-22",
    },
  ],
};

function installFetch(handler: (url: string, init?: RequestInit) => Response) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    return handler(String(input), init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderGenerator(onSessionExpired = vi.fn()) {
  render(
    <Reshaped theme="slate">
      <AssignmentGenerator onSessionExpired={onSessionExpired} />
    </Reshaped>,
  );
  return onSessionExpired;
}

function chooseWeek(value: string) {
  fireEvent.change(screen.getByLabelText("Target week"), {
    target: { value },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("weekly assignment generation panel", () => {
  it("submits the selected week and shows the generated assignments", async () => {
    const fetchMock = installFetch(() => jsonResponse(generatedResult, 201));
    renderGenerator();

    chooseWeek("2026-11-18");
    fireEvent.click(screen.getByRole("button", { name: "Generate assignments" }));

    expect(await screen.findByText("Assignments generated")).toBeInTheDocument();
    expect(
      screen.getByText("Generated 2 assignments for Nov 16 – 22, 2026."),
    ).toBeInTheDocument();
    expect(screen.getByText("Assignments for Nov 16 – 22, 2026")).toBeInTheDocument();
    expect(screen.getByText("Alex")).toBeInTheDocument();
    expect(screen.getByText("Kitchen")).toBeInTheDocument();
    expect(screen.getByLabelText("Target week")).toHaveValue("2026-11-16");

    const [url, request] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/assignments");
    expect(request?.method).toBe("POST");
    expect(request?.body).toBe(JSON.stringify({ week: "2026-11-18" }));
  });

  it("reports that an existing week was not changed", async () => {
    installFetch(() =>
      jsonResponse(
        {
          ...generatedResult,
          status: "already_exists",
        },
        200,
      ),
    );
    renderGenerator();

    fireEvent.click(screen.getByRole("button", { name: "Generate assignments" }));

    expect(
      await screen.findByText("Assignments already exist"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Nothing changed; 2 assignments already existed for Nov 16 – 22, 2026.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the actionable API diagnostic when generation is rejected", async () => {
    installFetch(() =>
      jsonResponse(
        {
          detail:
            "Cannot generate weekly assignments for 2026-11-30 before the rotation anchor exists.",
        },
        409,
      ),
    );
    renderGenerator();

    chooseWeek("2026-11-30");
    fireEvent.click(screen.getByRole("button", { name: "Generate assignments" }));

    expect(
      await screen.findByText("Assignment generation failed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Cannot generate weekly assignments for 2026-11-30 before the rotation anchor exists.",
      ),
    ).toBeInTheDocument();
  });

  it("expires the administrator session when the API returns 401", async () => {
    const onSessionExpired = renderGenerator();
    installFetch(() => jsonResponse({ detail: "Authentication required" }, 401));

    fireEvent.click(screen.getByRole("button", { name: "Generate assignments" }));

    await waitFor(() => expect(onSessionExpired).toHaveBeenCalledTimes(1));
    expect(
      screen.queryByText("Assignment generation failed"),
    ).not.toBeInTheDocument();
  });

  it("explains when a generated week has no active family members", async () => {
    installFetch(() =>
      jsonResponse(
        {
          week_start: "2026-11-16",
          week_end: "2026-11-22",
          status: "generated",
          assignment_count: 0,
          assignments: [],
        },
        201,
      ),
    );
    renderGenerator();

    fireEvent.click(screen.getByRole("button", { name: "Generate assignments" }));

    expect(
      await screen.findByText(
        "No active family members were included in this week. The week was still recorded as generated.",
      ),
    ).toBeInTheDocument();
  });
});
