import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("application shell", () => {
  it("renders the application heading and a ReShaped component", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Chore Tracker" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "ReShaped is ready" }),
    ).toBeInTheDocument();
  });
});