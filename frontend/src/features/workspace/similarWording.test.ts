import { describe, expect, it } from "vitest";
import { preselected } from "./sections/FirstContact";

// B6a P1: a likely duplicate found by similar wording alone is offered at escalation, never pre-selected.
describe("the escalation's pre-selected duplicate", () => {
  const rule = { id: "c1", ref: "C-1", reasons: ["same product", "same lot"], same_day: true };
  const words = { id: "c2", ref: "C-2", reasons: ["similar description (80 % words in common)"], wording_only: true };

  it("pre-selects the only match found by today's rule", () => {
    expect(preselected([rule])).toBe("c1");
  });

  it("never pre-selects a match found by the words alone", () => {
    expect(preselected([words])).toBe("");
    expect(preselected([words, rule])).toBe("c1");
  });
});
