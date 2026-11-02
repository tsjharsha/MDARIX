import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { DecisionBoard } from "./sections/CaseSections";
import { ScopeView } from "./sections/CaseScope";
import { forAndAgainst } from "./decisionBrief";

/**
 * Release B (0.10.72), "Show less, by default": each changed screen's default render shows what it must and leaves
 * out what is revealed on request. B1's market assessment is in marketAssessment.test.tsx.
 */
const sources = import.meta.glob(["./sections/*.tsx", "./*.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;
const source = (name: string) => sources[`./sections/${name}.tsx`] ?? sources[`./${name}.tsx`] ?? "";

function workspace(navigation: "new" | "classic" = "new"): WorkspaceApi {
  return {
    session: { allowed_menu: ["home"], business_permissions: ["investigation.work"] },
    navigation,
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], investigations: [], requestOpenInvestigation: vi.fn(), setInvestigationId: vi.fn() },
  } as unknown as WorkspaceApi;
}
const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace()}>{node}</WorkspaceContext.Provider>);

// The sample brief of SAMPLE-INV-001 as composed before 0.10.72: two pieces listed twice under supporting, one also
// under contradicting (its link to the alternative hypothesis).
const OLD_SAMPLE_BRIEF = {
  leading_hypothesis: { business_id: "HYP000001", statement: "The NovaSense pressure sensors read high. (Sample)" },
  supporting_evidence: [
    { source: "CASE", evidence_business_id: "EVD000002", title: "Incoming inspection results, lots 003-004 (Sample)" },
    { source: "CASE", evidence_business_id: "EVD000001", title: "Supplier change record SAMPLE-CHG-014 (Sample)" },
    {
      source: "HYPOTHESIS",
      evidence_business_id: "EVD000001",
      hypothesis_business_id: "HYP000001",
      title: "Supplier change record SAMPLE-CHG-014 (Sample)",
      rationale: "The sensor supplier changed for Rev B.",
    },
    {
      source: "HYPOTHESIS",
      evidence_business_id: "EVD000002",
      hypothesis_business_id: "HYP000001",
      title: "Incoming inspection results, lots 003-004 (Sample)",
      rationale: "Sampled sensors in lots 003 and 004 read 4-6% high.",
    },
  ],
  contradicting_evidence: [
    {
      source: "HYPOTHESIS",
      evidence_business_id: "EVD000002",
      hypothesis_business_id: "HYP000002",
      title: "Incoming inspection results, lots 003-004 (Sample)",
      rationale: "Lots 001-002 on the same wards show no high readings.",
    },
  ],
};

const READINESS = {
  workflow_state: "BRIEF_IN_REVIEW",
  steps: [{ key: "gaps", label: "Unknowns", status: "IN_PROGRESS", detail: "2 open unknowns" }],
  checks: [
    {
      key: "unknowns",
      label: "Unknowns are answered",
      result: "PENDING",
      rationale: "2 open unknowns still to answer",
    },
    { key: "risk_review", label: "Risk review", result: "NOT_REQUIRED", rationale: "Not required by policy" },
    { key: "brief_ready", label: "Investigation brief", result: "PENDING", rationale: "Waits for its quality review" },
    { key: "decision", label: "Decision", result: "PENDING", rationale: "No version is approved for decision yet" },
  ],
};

describe("B2: the investigation leads with what the decision rests on", () => {
  it("lists each piece of evidence once, for or against the leading explanation (addendum: the root cause)", () => {
    const { supporting, contradicting } = forAndAgainst(OLD_SAMPLE_BRIEF);
    expect(supporting.map((line) => line.evidence)).toEqual(["EVD000002", "EVD000001"]);
    expect(contradicting).toEqual([]);
  });

  it("shows the explanation, the evidence for and against, and what blocks the decision with its owner", () => {
    const html = render(
      <DecisionBoard row={{ owner_name: "Asha Quality" }} readiness={READINESS} content={OLD_SAMPLE_BRIEF} />,
    );
    expect(html).toContain("Leading explanation:</strong> The NovaSense pressure sensors read high. (Sample)");
    expect(html).toContain("For it (2)");
    expect(html).toContain("Against it (0)");
    expect(html).toContain(
      "<strong>Unknowns are answered</strong>: 2 open unknowns still to answer · Owner: Asha Quality",
    );
    expect(html).toContain(
      "<strong>Investigation brief</strong>: Waits for its quality review · Owner: A quality reviewer",
    );
    // Not required is not a blocker; the decision itself is what is blocked.
    expect(html).not.toContain("Risk review");
    expect(html).not.toContain("No version is approved");
  });

  it("keeps one set of section controls, the selectors behind Change investigation, empty parts in one line", () => {
    expect(source("CaseSections")).not.toContain("<Tabs");
    expect(source("CaseSections")).toContain("Not started yet: ");
    expect(source("UserWorkspace")).toContain('"Change investigation"');
    // The decision panel's empty history, follow-ups and impact assessments say nothing on the new navigation.
    expect(source("CaseDecision")).toContain('(navigation !== "new" || history.length > 0)');
  });

  it("shows the scope by the customer's references, with no None lines and a long list folded", () => {
    const html = render(
      <ScopeView
        scope={
          {
            version: 1,
            question: "Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?",
            product_versions: [],
            included_complaints: Array.from({ length: 14 }, (_, index) => ({
              id: `c${index}`,
              business_id: `CMP0000${10 + index}`,
              complaint_identifier: `SAMPLE-ORBIT-300-CMP-${String(index + 1).padStart(3, "0")}`,
            })),
            excluded_complaints: [],
            lots: [{ id: "l1", business_id: "LOT000003", lot_identifier: "SAMPLE-ORBIT-300-LOT-003" }],
            markets: [],
            failure_modes: [],
          } as never
        }
      />,
    );
    expect(html).toContain("14 complaints");
    expect(html).toContain("SAMPLE-ORBIT-300-CMP-001");
    expect(html).toContain("SAMPLE-ORBIT-300-LOT-003");
    expect(html).not.toContain("CMP000010");
    expect(html).not.toContain(">None<");
    expect(html).not.toContain("Markets");
  });
});

describe("B3: the complaint page shows one action per row and does the triage itself", () => {
  const page = () => source("ComplaintPage");
  it("puts Send to behind the row's More menu, one action per row", () => {
    // Send to renders inside the row's More menu, and only when a colleague may sign the step.
    expect(page()).toMatch(/function SendTo[\s\S]*?if \(!canSend \|\| !others\.length\) return null;[\s\S]*?<details className="uw-row-more">/);
  });
  it("shows the triage panel on the page instead of a button to the triage list", () => {
    expect(page()).toContain("<InlineTriage complaintId={event.complaint_id}");
    expect(page()).toContain("{triageHere ? (");
    // Saved on the page, it stays on the page.
    expect(source("Triage")).toContain('item.kind === "COMPLAINT" && !inline');
  });
  it("reveals the coding, the record's data and the stage list on request", () => {
    expect(page()).toContain("<summary>Coding and record details</summary>");
    expect(page()).toContain("<summary>Stage by stage</summary>");
  });
  it("leads with the intake decision summary once step 4 is reached (Addendum 2)", () => {
    expect(page()).toContain("<summary>The full complaint record</summary>");
    expect(page()).toContain("(shortStory.data?.current ?? 0) >= 3");
  });
});

describe("F2: step 3 is the consequence question the screen recorded", () => {
  it("keeps the recorded request with the story, and reads the consequence as the server states it", () => {
    expect(source("ShortStory")).toContain('{ step: "question", request_id: asked.id }');
    // The summary keeps the answer as written (an answer is never lower-cased).
    expect(source("ShortStory")).toContain("Consequence: {story.question.consequence}\n");
  });
});
