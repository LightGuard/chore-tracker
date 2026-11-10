import { fireEvent, render } from "@testing-library/react";
import { Button, Reshaped } from "reshaped";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("application shell", () => {
  it("renders the application heading", () => {
    const { getByRole } = render(<App />);

    expect(
      getByRole("heading", { level: 1, name: "Chore Tracker" }),
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