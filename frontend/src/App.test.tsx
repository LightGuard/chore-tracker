import { cleanup, fireEvent, render } from "@testing-library/react";
import { Button, Reshaped } from "reshaped";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { getApiBaseUrl } from "./config/api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/");
});

describe("application shell", () => {
  it("renders the application heading", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 })));

    const { getByRole } = render(<App />);

    expect(
      getByRole("heading", { level: 1, name: "Who’s doing chores?" }),
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