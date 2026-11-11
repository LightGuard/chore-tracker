import { fireEvent, render, screen } from "@testing-library/react";
import { Button, Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { getApiBaseUrl } from "./config/api";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("application shell", () => {
  it("renders the application heading", () => {
    const { getByRole } = render(<App />);

    expect(
      getByRole("heading", { level: 1, name: "Chore Tracker" }),
    ).toBeInTheDocument();
  });
});

describe("administrator setup screen", () => {
  it("offers initial setup when no administrator exists", async () => {
    window.history.pushState({}, "", "/admin");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith("/auth/setup")) {
        return new Response(JSON.stringify({
          setup_required: true,
          enrollment_pending: false,
        }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "Authentication required" }), {
        status: 401,
      });
    }));

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Initial administrator setup" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Administrator email")).toBeInTheDocument();
  });

  it("shows second-administrator provisioning to an authenticated administrator", async () => {
    window.history.pushState({}, "", "/admin");
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith("/auth/setup")) {
        return new Response(JSON.stringify({
          setup_required: false,
          enrollment_pending: false,
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        id: 1,
        email: "first@example.test",
      }), { status: 200 });
    }));

    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Signed in as first@example.test",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create administrator invitation" }),
    ).toBeInTheDocument();
  });
});

describe("ReShaped integration", () => {
  it("renders an interactive component within the theme provider", () => {
    const onClick = vi.fn();
    const { getByRole } = render(
      <Reshaped theme="slate">
        <Button onClick={onClick}>Test button</Button>
      </Reshaped>,
    );

    fireEvent.click(getByRole("button", { name: "Test button" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("API configuration", () => {
  it("uses a same-origin API path by default", () => {
    expect(getApiBaseUrl(undefined)).toBe("/api");
  });

  it("uses the configured API base URL without a trailing slash", () => {
    expect(getApiBaseUrl("https://api.example.test/")).toBe(
      "https://api.example.test",
    );
  });

  it("falls back to the same-origin path for an empty value", () => {
    expect(getApiBaseUrl("   ")).toBe("/api");
  });
});
