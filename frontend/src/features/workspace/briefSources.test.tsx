import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { BriefChallengeSections } from "./sections/caseIntelligence/Challenge";
import { briefChallenge, originLabel } from "./challenge";

// B5a step 7: the Decision Brief shows the Challenge (drafts with what was done, questions with answers) and the
// Sources (every record cited, collapsed with "N records, M rules") composed with it (case_challenge/brief.py). A brief
// composed before B5 has neither and shows neither.

const api = { session: { challenge: true }, work: {}, open: vi.fn(), notify: vi.fn() } as unknown as WorkspaceApi;
const render = (content: Record<string, unknown>) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={api}>
      <BriefChallengeSections content={content} caseId="inv-1" />
    </WorkspaceContext.Provider>,
  );

const CONTENT = {
  challenge: {
    notice: "Drafted by rule from your records.",
    drafts: [
      {
        rule: "H-1",
        rule_version: 1,
        key: "H-1:chg",
        title: "Component or supplier change",
        statement: "The change SAMPLE-CHG-014 may explain the complaints.",
        for: [],
        against: [],
        missing: [],
        action: { state: "ADOPTED", hypothesis: "HYP-4" },
      },
    ],
    questions: [
      {
        rule: "C-5",
        rule_version: 1,
        key: "C-5:u",
        text: "The bench test is still open.",
        material: true,
        answer: { text: "Accepted as a limitation: the bench rig is booked." },
      },
    ],
    blocking: [],
  },
  sources: {
    as_of: "2026-11-10T09:00:00Z",
    count: 3,
    summary: "3 records, 2 rules",
    groups: {
      complaints: {
        count: 2,
        items: [
          { id: "c-1", ref: "SAMPLE-CMP-0001", origin: "SAMPLE" },
          { id: "c-2", ref: "SAMPLE-CMP-0002", origin: "SAMPLE" },
        ],
      },
      hypotheses: { count: 1, items: [{ id: "h-1", ref: "HYP-4", origin: "MDARIX" }] },
    },
    rules: [
      { rule: "C-5", version: 1, name: "Open question on the leading hypothesis" },
      { rule: "H-1", version: 1, name: "Component or supplier change" },
    ],
  },
};

describe("The brief's Challenge and Sources sections", () => {
  it("shows each draft with its rule and what was done, and each question with its answer", () => {
    const html = render(CONTENT);
    expect(html).toContain("Drafted by rule H-1 (version 1)");
    expect(html).toContain("Adopted as HYP-4");
    expect(html).toContain("Question from rule C-5 (version 1), material");
    expect(html).toContain("Answer: Accepted as a limitation");
  });

  it("lists every source collapsed with its count, grouped, with origin and the rules", () => {
    const html = render(CONTENT);
    expect(html).toMatch(/<details>\s*<summary>/);
    expect(html).toContain("3 records, 2 rules");
    expect(html).toContain("Complaints");
    expect(html).toContain("SAMPLE-CMP-0002");
    expect(html).toContain("Sample");
    expect(html).toContain("C-5 v1 Open question on the leading hypothesis; H-1 v1 Component or supplier change");
    expect(briefChallenge(CONTENT)?.groups.map((group) => group.kind)).toEqual(["complaint", "hypothesis"]);
  });

  it("adds nothing to a brief composed before B5", () => {
    expect(render({ investigation: {} })).toBe("");
    expect(briefChallenge({})).toBeNull();
    expect(originLabel(undefined)).toBe("Created in MDARIX");
  });
});
