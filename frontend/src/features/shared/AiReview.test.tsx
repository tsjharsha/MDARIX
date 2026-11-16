import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AI_UNREVIEWED_LABEL, AiReviewActions, aiReviewBody } from "./AiReview";

describe("reviewing an AI proposal", () => {
  it("accepts without a reason, and asks for a reason to edit or reject", () => {
    expect(aiReviewBody("ACCEPTED")).toEqual({ body: { decision: "ACCEPTED" } });
    expect(aiReviewBody("REJECTED", "no")).toHaveProperty("problem");
    expect(aiReviewBody("REJECTED", " States a cause as fact ")).toEqual({
      body: { decision: "REJECTED", reason: "States a cause as fact" },
    });
    expect(aiReviewBody("EDITED", "Tightened wording", "  ")).toEqual({ problem: "Write the corrected text." });
    expect(aiReviewBody("EDITED", "Tightened wording", "The person's text")).toEqual({
      body: { decision: "EDITED", reason: "Tightened wording", edited_text: "The person's text" },
    });
  });

  it("labels the output and offers Accept, Edit and Reject; read-only shows the label alone", () => {
    const html = renderToStaticMarkup(<AiReviewActions outputId="o-1" text="AI text" onReviewed={() => undefined} />);
    expect(html).toContain(AI_UNREVIEWED_LABEL);
    expect(html).toMatch(/Accept[\s\S]*Edit[\s\S]*Reject/);
    // Accept leads: the only primary button; Edit and Reject stay secondary.
    expect(html).toMatch(/class="ac-primary"[^>]*>(<svg[\s\S]*?<\/svg>)? Accept/);
    expect(html.match(/ac-primary/g)).toHaveLength(1);
    const readOnly = renderToStaticMarkup(
      <AiReviewActions outputId="o-1" text="AI text" disabled onReviewed={() => undefined} />,
    );
    expect(readOnly).toContain(AI_UNREVIEWED_LABEL);
    expect(readOnly).not.toContain("Accept");
  });

  it("shows who decided once the server says the output was reviewed, without the buttons", () => {
    for (const [state, words] of [
      ["ACCEPTED", "Accepted by a person"],
      ["EDITED", "Edited by a person"],
      ["REJECTED", "Rejected by a person"],
    ] as const) {
      const html = renderToStaticMarkup(<AiReviewActions outputId="o-1" state={state} />);
      expect(html).toContain(words);
      expect(html).not.toContain(AI_UNREVIEWED_LABEL);
      expect(html).not.toContain("Reject<");
    }
    const open = renderToStaticMarkup(<AiReviewActions outputId="o-1" state="NOT_REVIEWED" />);
    expect(open).toContain(AI_UNREVIEWED_LABEL);
  });
});
