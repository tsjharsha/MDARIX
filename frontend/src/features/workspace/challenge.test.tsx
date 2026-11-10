import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ChallengeView } from "./sections/caseIntelligence/Challenge";
import { CaseIntelligencePanel } from "./sections/CaseIntelligence";
import {
  adoptBody,
  answerLine,
  answerProblem,
  blockingQuestions,
  challengePath,
  draftHeading,
  draftState,
  reasonProblem,
  recordSource,
  type ChallengeView as ChallengeData,
} from "./challenge";

// B5a step 7: the Challenge view (backend/app/case_challenge/router.py). Drafts say which rule drew them, list the
// records for and against and what is missing, and a person adopts (ticking facts) or dismisses each with a reason;
// material questions block "Submit for review" until answered or marked not applicable.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (permissions: string[], challenge = true) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: permissions, challenge },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
  }) as unknown as WorkspaceApi;

const render = (value: WorkspaceApi, node: React.ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const complaint = { type: "complaint", id: "c-1", ref: "SAMPLE-CMP-0003" };
const VIEW: ChallengeData = {
  notice: "Drafted by rule from your records. Drafts are explanations to test, not findings; you decide.",
  summary: { complaints: 14, no_version: 0, no_lot: 0, outside: 3, changes: 1 },
  drafts: [
    {
      rule: "H-1",
      rule_version: 1,
      key: "H-1:chg",
      title: "Component or supplier change",
      statement: "The change SAMPLE-CHG-014 may explain the complaints.",
      duplicate_of: "HYP-1",
      for: [{ text: "12 complaints after the change", records: [complaint] }],
      against: [{ text: "3 Rev A complaints without the part", records: [] }],
      missing: [{ text: "No incoming inspection evidence linked", records: [] }],
      action: null,
    },
    {
      rule: "H-2",
      rule_version: 1,
      key: "H-2:lots",
      title: "Lot or manufacturing",
      statement: "Lots 003 and 004 hold most complaints.",
      for: [],
      against: [],
      missing: [],
      action: { state: "DISMISSED", reason: "The lots share no component lot." },
    },
  ],
  questions: [
    { rule: "C-1", rule_version: 1, key: "C-1:x", text: "Does your explanation account for Rev A?", material: true },
    {
      rule: "C-7",
      rule_version: 1,
      key: "C-7:x",
      text: "Rev C also has complaints. Should the scope include it?",
      material: false,
      answer: { text: "Rev C is out of the market.", not_applicable: true },
    },
  ],
  blocking: ["C-1:x"],
  answers_editable: true,
};
resources.data[challengePath("inv-1")] = VIEW;

describe("Challenge view", () => {
  it("labels every draft with its rule and version and lists for, against and missing with record links", () => {
    const html = render(
      api(["investigation.work"]),
      <ChallengeView investigationId="inv-1" caseLabel="INV-1" readOnly={false} />,
    );
    expect(html).toContain("Drafted by rule H-1 (version 1)");
    expect(html).toContain("Records for");
    expect(html).toContain("Records against");
    expect(html).toContain("Missing");
    expect(html).toContain("SAMPLE-CMP-0003");
    expect(html).toContain("You may already have this: HYP-1");
    expect(html).toContain("Dismissed: The lots share no component lot.");
    expect(html).toContain("never ranked");
    expect(html).not.toMatch(/score|probability|confirmed|root cause/i);
  });

  it("lists the blocking material questions before Submit for review and offers answer or not applicable", () => {
    const html = render(
      api(["investigation.work"]),
      <ChallengeView investigationId="inv-1" caseLabel="INV-1" readOnly={false} />,
    );
    expect(html).toContain("Before Submit for review: 1 material question to answer");
    expect(html).toContain("Material · blocks Submit for review");
    expect(html).toContain("Not applicable: Rev C is out of the market.");
    expect(html).toContain("Adopt as a hypothesis");
    expect(html).toContain(">Answer<");
    expect(html).toContain(">Not applicable<");
  });

  it("offers no change to a reader or on a closed investigation", () => {
    for (const html of [
      render(api(["records.read"]), <ChallengeView investigationId="inv-1" caseLabel="INV-1" readOnly={false} />),
      render(api(["investigation.work"]), <ChallengeView investigationId="inv-1" caseLabel="INV-1" readOnly />),
    ]) {
      expect(html).toContain("Drafted by rule H-1 (version 1)");
      expect(html).not.toContain("Adopt as a hypothesis");
      expect(html).not.toContain(">Answer<");
    }
  });

  it("is a view of Intelligence only while the server has the challenge on", () => {
    const panel = (challenge: boolean) =>
      render(
        api(["investigation.work"], challenge),
        <CaseIntelligencePanel
          investigationId="inv-1"
          caseLabel="INV-1"
          view="Contradictions"
          onView={() => undefined}
        />,
      );
    expect(panel(true)).toContain(">Challenge<");
    expect(panel(false)).not.toContain(">Challenge<");
  });
});

describe("challenge rules on the screen", () => {
  it("builds the adopt request from the ticked facts", () => {
    expect(adoptBody("H-1:chg", ["for:0", "against:2"])).toEqual({
      key: "H-1:chg",
      facts: [
        { side: "for", index: 0 },
        { side: "against", index: 2 },
      ],
    });
  });

  it("asks for reasons and answers of at least 10 characters", () => {
    expect(reasonProblem("too short")).toMatch(/at least 10/);
    expect(reasonProblem("Long enough reason")).toBeNull();
    expect(answerProblem("short")).toMatch(/at least 10/);
    expect(answerProblem("An answer long enough")).toBeNull();
  });

  it("names states, headings, blocking questions and record targets", () => {
    expect(draftHeading({ rule: "H-2", rule_version: 1 })).toBe("Drafted by rule H-2 (version 1)");
    expect(draftState({ state: "ADOPTED", hypothesis: "HYP-3" })).toEqual({ label: "Adopted as HYP-3", tone: "good" });
    expect(draftState(null).label).toBe("Not acted on");
    expect(blockingQuestions(VIEW).map((item) => item.rule)).toEqual(["C-1"]);
    expect(answerLine(null)).toBe("Not answered");
    expect(recordSource(complaint, "inv-1")).toEqual({
      type: "Complaint",
      id: "c-1",
      ref: "SAMPLE-CMP-0003",
      case: "inv-1",
    });
  });
});
