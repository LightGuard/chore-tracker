import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("application shell", () => {
  it("renders the application heading and a ReShaped component", () => {
    const { getByRole } = render(<App />);

    expect(
      getByRole("heading", { level: 1, name: "Chore Tracker" }),
    ).toBeInTheDocument();
    expect(
      getByRole("button", { name: "ReShaped is ready" }),
    ).toBeInTheDocument();
  });
});