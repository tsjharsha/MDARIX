import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AiCodeSuggestionList, type AiCodeReply } from "./sections/ReportBody";
import { canRunAi } from "./workspaceContext";

const DETAIL = {
  sections: [
    {
      fields: [{ id: "H6_PROBLEM", number: "H6", label: "Device problem code", code_annex: "A" }],
    },
  ],
} as never;

const REPLY: AiCodeReply = {
  suggestions: [
    {
      annex: "A",
      code: "A0501",
      term: "Occlusion alarm",
      confidence: 0.82,
      quote: "the occlusion alarm sounded",
      field_ids: ["H6_PROBLEM"],
    },
  ],
  ai: { status: "COMPLETED", ai_execution_id: "e-1" },
};

describe("AI code suggestions (AI-R part D)", () => {
  it("shows each proposal as an AI suggestion with its confidence, quote and the field it would go in", () => {
    const html = renderToStaticMarkup(
      <AiCodeSuggestionList detail={DETAIL} reply={REPLY} entered={[]} busy={false} onEnter={vi.fn()} />,
    );
    expect(html).toContain("AI suggestion");
    expect(html).toContain("A0501");
    expect(html).toContain("82% confidence");
    expect(html).toContain("the occlusion alarm sounded");
    expect(html).toContain("Enter in H6 Device problem code");
    const done = renderToStaticMarkup(
      <AiCodeSuggestionList detail={DETAIL} reply={REPLY} entered={["A:A0501"]} busy={false} onEnter={vi.fn()} />,
    );
    expect(done).toContain("Entered in H6 Device problem code");
    expect(done).not.toContain("Enter in H6");
  });

  it("says why when nothing is proposed", () => {
    const html = renderToStaticMarkup(
      <AiCodeSuggestionList
        detail={DETAIL}
        reply={{ suggestions: [], ai: { status: "REFUSED", message: "AI available on paid plans." } }}
        entered={[]}
        busy={false}
        onEnter={vi.fn()}
      />,
    );
    expect(html).toContain("AI available on paid plans.");
  });
});

describe("offering AI actions", () => {
  it("offers AI in a free trial only once the server says AI answers there", () => {
    expect(canRunAi(true, false, null)).toBe(true);
    expect(canRunAi(true, true, null)).toBe(false);
    expect(canRunAi(true, true, false)).toBe(false);
    expect(canRunAi(true, true, true)).toBe(true);
    expect(canRunAi(false, true, true)).toBe(false);
  });
});
