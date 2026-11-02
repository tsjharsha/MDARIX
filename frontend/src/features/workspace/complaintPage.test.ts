import { describe, expect, it } from "vitest";
import { deadlineChips, headline, nextStep } from "./sections/ComplaintPage";

const due = (key: string, category: string, market: string | null, due_at: string) =>
  ({
    key,
    category,
    market,
    due_at,
    category_label: category,
    title: key,
    state: "LATER",
    state_label: "",
    hours_left: 1,
    opens: null,
  }) as never;

describe("the complaint page's header (stage 7)", () => {
  it("shows one chip per market's legal deadline, then one per kind of own target", () => {
    const chips = deadlineChips([
      due("reply", "REPLY", "US", "2026-10-30T18:29:59Z"),
      due("fda", "REPORTING", "US", "2026-11-29T18:29:59Z"),
      due("fda-report", "OBLIGATION", "US", "2026-12-01T18:29:59Z"),
      due("india", "REPORTING", "IN", "2026-12-02T18:29:59Z"),
      due("reply-2", "REPLY", "US", "2026-12-03T18:29:59Z"),
    ]);
    expect(chips.map((item: { key: string }) => item.key)).toEqual(["reply", "fda", "india"]);
  });

  it("says what happened in one line", () => {
    expect(headline("  The pump  free-flowed. ")).toBe("The pump free-flowed.");
    expect(headline(null)).toBe("No description recorded");
    expect(headline("x".repeat(200)).length).toBe(140);
  });

  it("names one next action: the checklist's, else signing ready to close", () => {
    const opens = { section: "Complaints", tab: "Reportability" };
    expect(
      nextStep({
        summary: { next_action: { label: "Assess the US market", detail: "", opens } },
        state: "NOT_READY",
        blocked: 1,
      } as never),
    ).toEqual({ label: "Assess the US market", opens });
    expect(nextStep({ summary: { next_action: null }, state: "READY_TO_SIGN", blocked: 0 } as never)?.label).toBe(
      "Sign ready to close",
    );
    expect(nextStep({ summary: { next_action: null }, state: "FILED", blocked: 0 } as never)).toBeNull();
  });
});
