import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { EXAMPLE_QUESTIONS, RuleAnswers } from "./AskMdarixPage";

describe("Ask MDARIX without AI", () => {
  it("shows the fixed-rule answers to the counting part of the question", () => {
    const markup = renderToStaticMarkup(
      <RuleAnswers
        answers={[
          {
            key: "lots",
            question: "What do lots SAMPLE-ORBIT-300-LOT-003 and SAMPLE-ORBIT-300-LOT-004 have in common?",
            answer: {
              summary: "Lots 003 and 004 are both Rev B lots; together they have 14 of 22 complaints.",
              table: {
                columns: ["Lot", "Version", "Complaints"],
                rows: [
                  ["SAMPLE-ORBIT-300-LOT-003", "Rev B", 9],
                  ["SAMPLE-ORBIT-300-LOT-004", "Rev B", 5],
                ],
              },
              facts: ["Both lots are Rev B."],
            },
          },
        ]}
      />,
    );
    expect(markup).toContain("Counted from your complaint records");
    expect(markup).toContain("together they have 14 of 22 complaints");
    expect(markup).toContain("<td>SAMPLE-ORBIT-300-LOT-003</td>");
    expect(markup).toContain("Fixed rules, no AI");
  });

  it("offers questions that work without AI", () => {
    expect(EXAMPLE_QUESTIONS.length).toBeGreaterThanOrEqual(4);
    expect(EXAMPLE_QUESTIONS.some((text) => /lots/i.test(text))).toBe(true);
  });
});

describe("A records-only answer", () => {
  it("says once why AI was not used", async () => {
    const { AskAnswer } = await import("./AskMdarixPage");
    const note = "AI is off for free trials, so this answer comes from your records only.";
    const markup = renderToStaticMarkup(
      <AskAnswer
        result={{
          response: { limitations: [note], grounding: { investigation_scoped: true } },
          structured: { summary: "From the case records: 2 records.", ai_used: false, ai_note: note },
        }}
      />,
    );
    expect(markup.split(note).length - 1).toBe(1);
    expect(markup).not.toContain("AI suggestions are advisory");
    expect(markup).not.toContain("AI proposal, not reviewed");
  });

  it("puts Accept, Edit and Reject on a model's answer", async () => {
    const { AskAnswer } = await import("./AskMdarixPage");
    const markup = renderToStaticMarkup(
      <AskAnswer result={{ response: { ai_call_id: "c-1", provider_output: { answer: "From the sample." } } }} />,
    );
    expect(markup).toContain("AI proposal, not reviewed");
    expect(markup).toMatch(/Accept[\s\S]*Edit[\s\S]*Reject/);
  });
});
