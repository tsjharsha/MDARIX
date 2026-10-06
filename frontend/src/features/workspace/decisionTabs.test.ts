import { describe, expect, it } from "vitest";
import { DECISION_TAB, decisionTab, parseDecisionTab, tabName } from "./decisionTabs";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";

describe("the Decision tab", () => {
  it("opens on a follow-up, an impact assessment or a case when a valid reference is given", () => {
    expect(decisionTab()).toBe(DECISION_TAB);
    expect(decisionTab({ followUp: UUID })).toBe(`Decision?follow_up=${UUID}`);
    expect(decisionTab({ assessment: "IMP000001" })).toBe("Decision?assessment=IMP000001");
    expect(decisionTab({ caseId: UUID })).toBe(`Decision?case=${UUID}`);
    expect(decisionTab({ followUp: "not a ref!" })).toBe("Decision");
  });

  it("reads back what a tab name asks to open, and ignores anything else", () => {
    expect(parseDecisionTab(`Decision?follow_up=${UUID}`)).toEqual({ followUp: UUID, assessment: null, caseId: null });
    expect(parseDecisionTab("Decision?assessment=IMP000001")).toEqual({
      followUp: null,
      assessment: "IMP000001",
      caseId: null,
    });
    expect(parseDecisionTab(`Decision?case=${UUID}`).caseId).toBe(UUID);
    expect(parseDecisionTab("Decision")).toEqual({ followUp: null, assessment: null, caseId: null });
    expect(parseDecisionTab(`Reviews?follow_up=${UUID}`).followUp).toBeNull();
    expect(parseDecisionTab("Decision?follow_up=%3Cscript%3E").followUp).toBeNull();
    expect(parseDecisionTab(null).assessment).toBeNull();
  });

  it("keeps the tab part of a tab name", () => {
    expect(tabName(`Decision?follow_up=${UUID}`)).toBe("Decision");
    expect(tabName("Approvals")).toBe("Approvals");
    expect(tabName(undefined)).toBe("");
  });
});
