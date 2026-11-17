import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AiCodeSuggestionList, AiCodeSuggestions, type AiCodeReply } from "./sections/ReportBody";
import { WorkspaceContext, canRunAi, type WorkspaceApi } from "./workspaceContext";
import { aiStatusBanner } from "./intelligence";

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
  it("keeps the button in a trial while AI cannot answer, disabled and with the reason (G-07)", () => {
    const api = (permissions: string[]) =>
      ({ session: { business_permissions: permissions }, isTrial: true }) as unknown as WorkspaceApi;
    const render = (permissions: string[]) =>
      renderToStaticMarkup(
        <WorkspaceContext.Provider value={api(permissions)}>
          <AiCodeSuggestions detail={{ ...(DETAIL as object), editable: true } as never} onChanged={vi.fn()} />
        </WorkspaceContext.Provider>,
      );
    const html = render(["ai.run"]);
    expect(html).toContain("Suggest IMDRF codes with AI");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>.*Suggest IMDRF codes with AI/);
    expect(html).toContain("Enter the codes by hand below.");
    // A role that may not run AI still never sees it.
    expect(render([])).toBe("");
  });

  it("never says AI is off for free trials: not switched on, or busy when the trial has AI (G-07)", () => {
    const none = aiStatusBanner({ enabled: false, reason_code: "PROVIDER_UNAVAILABLE", trial: true })!;
    expect(none.shortReason).toBe("AI is not switched on for this trial");
    const busy = aiStatusBanner({
      enabled: true,
      available: false,
      reason_code: "PROVIDER_UNAVAILABLE",
      trial: true,
      sample_data_only: true,
    })!;
    expect(busy.title).toBe("AI is busy");
    expect(JSON.stringify([none, busy])).not.toContain("off for free trials");
  });

  it("offers AI in a free trial only once the server says AI answers there", () => {
    expect(canRunAi(true, false, null)).toBe(true);
    expect(canRunAi(true, true, null)).toBe(false);
    expect(canRunAi(true, true, false)).toBe(false);
    expect(canRunAi(true, true, true)).toBe(true);
    expect(canRunAi(false, true, true)).toBe(false);
  });
});
