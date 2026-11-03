import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { ReviewControls } from "@/components/review-controls";
import type { EventTypeRead } from "@/lib/schemas/cameras";

const CATALOG: EventTypeRead[] = [
  { key: "smoking", name: "Smoking", severity: "warning", alert: true },
  { key: "sleeping", name: "Sleeping", severity: "critical", alert: true },
];

describe("ReviewControls", () => {
  it("submits a correct review in one click", async () => {
    const onSubmit = vi.fn();
    render(
      <ReviewControls
        events={["smoking"]}
        review={null}
        eventTypes={CATALOG}
        onSubmit={onSubmit}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Correct" }));
    expect(onSubmit).toHaveBeenCalledWith({
      review: "correct",
      wrong_events: [],
      missed_events: [],
      note: null,
    });
  });

  it("asks for wrong and missed events when incorrect", async () => {
    const onSubmit = vi.fn();
    render(
      <ReviewControls
        events={["smoking"]}
        review={null}
        eventTypes={CATALOG}
        onSubmit={onSubmit}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Incorrect" }));
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Wrong: Smoking" }),
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Missed: Sleeping" }),
    );
    await userEvent.type(screen.getByRole("textbox"), "just steam");
    await userEvent.click(screen.getByRole("button", { name: "Save review" }));
    expect(onSubmit).toHaveBeenCalledWith({
      review: "incorrect",
      wrong_events: ["smoking"],
      missed_events: ["sleeping"],
      note: "just steam",
    });
  });
});
