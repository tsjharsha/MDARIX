import { describe, expect, it } from "vitest";
import { STATEMENT_KIND, statementBadge, statementKind, statementOrigin, statementOriginLabel } from "./epistemic";

describe("statement kinds", () => {
  it("reads the four kinds and a hypothesis", () => {
    expect(statementKind("FACT", "HUMAN")).toBe("FACT");
    expect(statementKind("source assertion", "SYSTEM")).toBe("SOURCE_ASSERTION");
    expect(statementKind("DERIVED_OBSERVATION", "HUMAN")).toBe("DERIVED_OBSERVATION");
    expect(statementKind("AI_INTERPRETATION", "AI")).toBe("AI_INTERPRETATION");
    expect(statementKind("HYPOTHESIS", "HUMAN")).toBe("HYPOTHESIS");
  });

  it("never lets AI output read as a fact, whatever kind it claims", () => {
    expect(statementKind("FACT", "AI")).toBe("AI_INTERPRETATION");
    expect(statementKind("DERIVED_OBSERVATION", "LANGUAGE_MODEL")).toBe("AI_INTERPRETATION");
    expect(statementKind("HYPOTHESIS", "AI_ADOPTED")).toBe("AI_INTERPRETATION");
    expect(statementBadge({ kind: "FACT", origin: "AI", kindLabel: "Verified fact" }).kindLabel).toBe(
      "AI interpretation",
    );
  });

  it("reads an unknown or missing kind as a source assertion, never as a fact", () => {
    expect(statementKind(undefined, "HUMAN")).toBe("SOURCE_ASSERTION");
    expect(statementKind("SOMETHING_NEW", undefined)).toBe("SOURCE_ASSERTION");
  });

  it("styles only facts solid and AI distinctly", () => {
    expect(STATEMENT_KIND.FACT.style).toBe("fact");
    expect(STATEMENT_KIND.AI_INTERPRETATION.style).toBe("ai");
    const styles = Object.values(STATEMENT_KIND).map((kind) => kind.style);
    expect(new Set(styles).size).toBe(styles.length);
  });
});

describe("statement origins", () => {
  it("maps every spelling to a person, AI or MDARIX rules", () => {
    expect(statementOrigin("HUMAN")).toBe("PERSON");
    expect(statementOrigin("person")).toBe("PERSON");
    expect(statementOrigin("AI")).toBe("AI");
    expect(statementOrigin("AI_ADOPTED")).toBe("AI");
    expect(statementOrigin("SYSTEM")).toBe("SYSTEM");
    expect(statementOrigin("")).toBeNull();
  });

  it("labels the origin, saying when a person adopted AI output", () => {
    expect(statementOriginLabel("HUMAN")).toBe("Person");
    expect(statementOriginLabel("SYSTEM")).toBe("MDARIX rules");
    expect(statementOriginLabel("AI_ADOPTED")).toBe("AI, adopted by a person");
    expect(statementOriginLabel(null)).toBe("Origin not recorded");
  });

  it("describes the whole badge in one sentence for assistive technology", () => {
    const badge = statementBadge({ kind: "SOURCE_ASSERTION", origin: "HUMAN" });
    expect(badge.description).toMatch(/^Source assertion, made by Person\./);
    expect(statementBadge({ kind: "FACT", origin: "SYSTEM", originLabel: "Complaint system" }).originLabel).toBe(
      "Complaint system",
    );
  });
});
