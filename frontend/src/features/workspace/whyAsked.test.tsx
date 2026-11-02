import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { basisOf } from "../shared/standards";
import { WhyAsked } from "../shared/Basis";
import { CASE_STEPS } from "./caseWorkflow";
import { DECIDE_AND_SIGN, DecideAndSign } from "./sections/common";
import {
  CASE_STEP_WHY,
  COMPLAINT_STEP_WHY,
  DISPOSITION_WHY,
  FIRST_CONTACT_WHY,
  TRIAGE_WHY,
  type Why,
} from "./whyAsked";

// Quality plan stage 8 (8.2, 8.3): every question and step says why it is asked, with its clause; every signature
// shows first what is signed and what it rests on, and the "you decide" line once.

const sources = import.meta.glob(["./sections/*.tsx"], { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;
const source = (name: string) => sources[`./sections/${name}.tsx`] ?? "";

describe("Why am I asked? (8.2)", () => {
  const tables: Array<[string, Readonly<Record<string | number, Why>>, Array<string | number>]> = [
    // closure.py's checklist codes, and ready to close.
    [
      "complaint steps",
      COMPLAINT_STEP_WHY,
      ["TRIAGE", "FIRST_CONTACT", "MARKETS", "OBLIGATIONS", "DECISION", "REQUESTS", "TASKS", "CAPA", "READY"],
    ],
    ["investigation steps", CASE_STEP_WHY, CASE_STEPS.map((step) => step.key)],
    ["first-contact questions", FIRST_CONTACT_WHY, ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9"]],
    ["triage fields", TRIAGE_WHY, ["severity", "owners", "action", "awareness"]],
    ["disposition questions", DISPOSITION_WHY, [1, 2, 3, 4]],
  ];
  it.each(tables)("gives every one of the %s a reason and a clause from the catalog", (_, table, keys) => {
    for (const key of keys) {
      const why = table[key];
      expect(why?.why, String(key)).toMatch(/^[A-Z].{20,}\.$/);
      expect(why.basis.length, String(key)).toBeGreaterThan(0);
      expect(
        basisOf(why.basis).map((item) => item.id),
        String(key),
      ).toEqual([...why.basis]);
    }
  });

  it("reads as one line with its clause", () => {
    const html = renderToStaticMarkup(<WhyAsked why={COMPLAINT_STEP_WHY.MARKETS} clause="21 CFR 803.3" />);
    expect(html).toContain("Why am I asked?");
    expect(html).toContain("21 CFR 803.50");
    expect(html).toContain("21 CFR 803.3");
  });

  it("is shown on each screen that asks", () => {
    expect(source("ComplaintPage")).toContain("<WhyAsked why={COMPLAINT_STEP_WHY[item.code]}");
    expect(source("CaseHeader")).toContain("<WhyAsked why={CASE_STEP_WHY[next.key]}");
    expect(source("FirstContact")).toContain("<WhyAsked why={FIRST_CONTACT_WHY[question.id]}");
    expect(source("Dispositions")).toContain("<WhyAsked why={DISPOSITION_WHY[number]}");
    expect(source("Triage")).toContain("<WhyAsked why={TRIAGE_WHY.awareness}");
    // A market's question gives its guide's own note and its locked clause.
    expect(source("MarketAssessment")).toMatch(/<WhyAsked\s+why=\{\{ why: question\.note \|\| MARKET_QUESTION_WHY/);
  });
});

describe("the summary before signing (8.3)", () => {
  it("says what is signed, then what it rests on, then the line once", () => {
    const html = renderToStaticMarkup(
      <DecideAndSign signs="United States (FDA): reportable." restsOn={["Your answers to 8 questions.", null]} />,
    );
    expect(html.indexOf("You sign")).toBeLessThan(html.indexOf("It rests on"));
    expect(html.indexOf("It rests on")).toBeLessThan(html.indexOf("You decide and sign"));
    expect(html.split(DECIDE_AND_SIGN.split(".")[0]).length - 1).toBe(1);
  });

  it("names the facts at the flagship's signatures: the market, the report, the decision and ready to close", () => {
    expect(source("MarketAssessment")).toMatch(/signs=\{`\$\{item\.label\}/);
    expect(source("Reports")).toContain("fingerprint ${shortPrint(snapshot.content_fingerprint)}");
    expect(source("CaseDecision")).toContain("fingerprint ${shortPrint(context.briefContentHash)}");
    expect(source("Oversight")).toContain("fingerprint ${shortPrint(view.decision_record.sha256)}");
    expect(source("FirstContact")).toContain("The first-contact check of ${item.reference}");
  });
});
