import { describe, expect, it } from "vitest";
import {
  answerOriginText,
  conversationSummary,
  hasStructuredContent,
  structuredAnswer,
  structuredOf,
} from "./structuredModel";

const UUID = "3f2b8c1e-4d5a-4b6c-8d7e-9f0a1b2c3d4e";

const payload = {
  summary: "Occlusion alarms rose after release B.",
  known_facts: [
    {
      statement: "42 complaints mention occlusion.",
      epistemic_type: "DERIVED_OBSERVATION",
      origin: "SYSTEM",
      sources: ["CMP000012", { business_id: "EVD000003" }],
    },
    "A plain string fact",
    { statement: "" },
  ],
  supporting_evidence: [{ statement: "Seal hardness dropped.", sources: [{ business_id: "EVD000004" }, UUID] }],
  contradicting_evidence: [{ statement: "Lot KS-5521 passed incoming inspection.", sources: [] }],
  unknowns: [{ statement: "Supplier test method", business_id: "UNK000031", status: "open" }],
  missing_evidence: [
    { statement: "Hardness test of lot KS-5521", request_business_id: "EVR000004" },
    { statement: "Field data" },
  ],
  limitations: ["Only 30 days of data."],
  next_steps: ["Request the supplier's test report."],
  sources: [{ business_id: "EVD000003", title: "Complaint trend", kind: "EVIDENCE", relevance: 1.4 }, { id: UUID }],
  ai_used: false,
  ai_note: "AI was not used.",
};

describe("the structured Ask answer", () => {
  it("normalizes every section and drops empty or malformed items", () => {
    const answer = structuredAnswer(payload)!;
    expect(answer.summary).toBe("Occlusion alarms rose after release B.");
    expect(answer.knownFacts).toHaveLength(2);
    expect(answer.knownFacts[0]).toEqual({
      statement: "42 complaints mention occlusion.",
      kind: "DERIVED_OBSERVATION",
      origin: "SYSTEM",
      sources: ["CMP000012", "EVD000003"],
    });
    expect(answer.knownFacts[1]).toMatchObject({ statement: "A plain string fact", kind: null, origin: null });
    expect(answer.supporting[0].sources).toEqual(["EVD000004"]);
    expect(answer.unknowns[0]).toEqual({ statement: "Supplier test method", businessId: "UNK000031", status: "open" });
    expect(answer.missing.map((item) => item.requestBusinessId)).toEqual(["EVR000004", null]);
    expect(answer.sources).toEqual([
      { businessId: "EVD000003", title: "Complaint trend", kind: "EVIDENCE", relevance: 1 },
    ]);
    expect(answer.aiUsed).toBe(false);
    expect(answer.aiNote).toBe("AI was not used.");
  });

  it("never shows a UUID as a source", () => {
    const answer = structuredAnswer(payload)!;
    expect(JSON.stringify(answer)).not.toContain(UUID);
  });

  it("falls back to the existing rendering when there is nothing structured", () => {
    expect(structuredAnswer(null)).toBeNull();
    expect(structuredAnswer("text")).toBeNull();
    expect(hasStructuredContent(structuredAnswer({ ai_used: true }))).toBe(false);
    expect(hasStructuredContent(structuredAnswer(payload))).toBe(true);
  });

  it("finds the structured answer at the top of the response or inside it", () => {
    expect(structuredOf({ structured: payload })?.summary).toBe(payload.summary);
    expect(structuredOf({ response: { structured: payload } })?.summary).toBe(payload.summary);
    expect(structuredOf({ response: {} })).toBeNull();
  });

  it("says when the answer was built from records without AI", () => {
    expect(answerOriginText(structuredAnswer({ ai_used: false }))).toBe("Answer built from your records (AI not used)");
    expect(answerOriginText(structuredAnswer({ ai_used: true }))).toMatch(/^AI interpretation/);
    expect(answerOriginText(structuredAnswer({}))).toBeNull();
  });

  it("gives My Work the conversation's summary when there is one", () => {
    expect(conversationSummary({ structured: payload })).toBe(payload.summary);
    expect(conversationSummary({ prompt: "What changed?" })).toBeNull();
  });
});
