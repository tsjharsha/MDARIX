import { describe, expect, it } from "vitest";
import { storyStage, storySummary } from "./storyModel";

describe("investigation story stages", () => {
  it("shows complete, available and pending with their record counts", () => {
    expect(storyStage({ key: "decision", label: "Decision", status: "COMPLETE", count: 1 })).toEqual({
      label: "Complete",
      tone: "good",
      records: "1 record",
    });
    expect(storyStage({ key: "evidence", label: "Evidence", status: "AVAILABLE", count: 4 })).toEqual({
      label: "Records available",
      tone: "neutral",
      records: "4 records",
    });
    expect(storyStage({ key: "scenario", label: "Scenario", status: "PENDING", count: 0 })).toMatchObject({
      label: "Pending",
      records: "0 records",
    });
  });

  it("never turns an unknown state into one of the three", () => {
    expect(storyStage({ key: "x", label: "X", status: "REVIEW_REQUIRED" })).toMatchObject({
      label: "Review Required",
      tone: "neutral",
    });
  });

  it("summarizes the story", () => {
    const stages = [
      { key: "evidence", label: "Evidence", status: "AVAILABLE", count: 2 },
      { key: "decision", label: "Decision", status: "PENDING", count: 0 },
    ];
    expect(storySummary(stages)).toBe("1 of 2 stages have records; no signed decision yet.");
    expect(storySummary([{ key: "decision", label: "Decision", status: "COMPLETE", count: 1 }])).toBe(
      "1 of 1 stages have records; the decision is signed.",
    );
  });
});
