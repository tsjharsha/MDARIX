// UX1 (Persona Blueprint waves A and B): each persona's own first piece of work on Home, one onboarding story, the
// flagship bar on the step you are on, no background 403s, one log button, one overdue badge, honest counts.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { OVERSIGHT } from "./oversight";
import { HomeSection } from "./sections/Home";
import { ComplaintViews } from "./sections/ComplaintViews";
import { CaseFiles } from "./sections/FirstContact";
import { NewRecordsSection } from "./sections/Records";
import { overdueWhy, workColumns } from "./sections/ComplaintList";
import { flagshipBarParts } from "./sections/FlagshipBar";
import { VALIDATION_EVIDENCE_PATH } from "../validation/ValidationEvidence";
import {
  AI_PROPOSALS_PART,
  ONE_STORY_PATH,
  flagshipNextLabel,
  flagshipPlace,
  flagshipStepOn,
  type FlagshipRun,
} from "./oneStory";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown>, asked: [] as string[] }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    if (path) resources.asked.push(path);
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

beforeEach(() => {
  resources.data = {};
  resources.asked = [];
});

const api = (overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session: { user_id: "u1", business_permissions: [] },
    work: { products: [], investigations: [], setInvestigationId: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    ...overrides,
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

const LABELS = [
  "Signal: pressure alarms are rising",
  "Product reality",
  "What is known and what is not",
  "AI investigation",
  "Investigation Brief",
  "Human decision",
  "Action and impact",
];
const flagship = (done: number): FlagshipRun => ({
  run: "flagship",
  product: {
    id: "p1",
    ref: "SAMPLE-ORBIT-300",
    name: "OrbitCare 300",
    label: "OrbitCare 300",
    version: "Rev B",
    version_state: "KNOWN",
    unverified: 0,
  },
  investigation: { id: "inv1", ref: "SAMPLE-INV-001", question: "Why did pressure alarms rise after Rev B?" },
  change: null,
  capa: null,
  branch: null,
  ai_proposals: 1,
  mfa_verified: null,
  steps: LABELS.map((label, index) => ({ key: String(index), label, done: index < done, skipped: false })),
  current: done,
  finished: done === 7,
});
const tenStep = {
  run: "sample",
  complaint: { id: "c11", ref: "SAMPLE-RV-11" },
  steps: Array.from({ length: 10 }, (_, index) => ({ key: `s${index}`, label: `Ten ${index}`, done: false })),
  current: 0,
  finished: false,
  needs: [],
};
const home = (persona: string, extra: Partial<WorkspaceApi> = {}) =>
  render(<HomeSection heading={{ current: null }} />, api({ persona, ...extra }));
const primaries = (html: string) => html.match(/class="ac-primary"[^>]*>[^<]*/g) ?? [];

describe("Home: one onboarding story and each persona's own first piece of work", () => {
  it("leads the trial owner with the 7-step flagship, never the 10-step story", () => {
    resources.data[ONE_STORY_PATH] = { sample: tenStep, yours: null, flagship: flagship(2) };
    const html = home("admin");
    expect(html).toContain("Step 3 of 7: What is known and what is not");
    expect(html).toContain("See what is known and what is not");
    expect(html).not.toContain("of 10");
    expect(html).not.toContain("Continue the story");
  });

  it("gives the Service Desk a Log a call button that opens the log in place", () => {
    resources.data[ONE_STORY_PATH] = { sample: tenStep, yours: null, flagship: flagship(0) };
    const open = vi.fn();
    const html = home("servicedesk", { open });
    expect(html).toContain("Log a call");
    expect(html).not.toContain("Continue the story");
    expect(html).not.toContain("Step 1 of");
  });

  it("gives the Executive a place to look and no action, and no story", () => {
    resources.data[ONE_STORY_PATH] = { sample: tenStep, yours: null, flagship: flagship(0) };
    const html = home("executive");
    expect(html).toContain("See product exposure");
    expect(html).not.toContain("Continue the story");
    expect(html).not.toMatch(/Sign|Approve|Log a/);
  });

  it("puts the brief waiting for a signature on the Decision Maker's Home with its one-page summary", () => {
    resources.data["/api/v1/decisions/queue"] = {
      total: 1,
      items: [
        {
          investigation: {
            id: "inv1",
            business_id: "SAMPLE-INV-001",
            question: "Why did alarms rise?",
            product: { id: "p1", name: "OrbitCare 300" },
          },
          brief: { version: 1, quality_reviewer_name: "MDARIX sample reviewer" },
          awaiting_since: "2026-11-18T10:00:00Z",
        },
      ],
    };
    resources.data["/api/v1/investigations/inv1/decision"] = {
      brief: {
        created_by_name: "MDARIX sample author",
        submitted_by_name: "MDARIX sample author",
        quality_reviewer_name: "MDARIX sample reviewer",
        narrative: {
          proposed_conclusion: "Restore inspection of 32 sensors per lot.",
          recommended_actions: ["Open CAPA-02"],
        },
        supporting_evidence: [{}, {}],
        contradictions: [{}],
        unknowns: { open_count: 2 },
      },
    };
    const html = home("decision");
    expect(html).toContain("Review and sign");
    expect(html).toContain("1 decision waits for your signature");
    for (const text of [
      "Decision asked",
      "Restore inspection of 32 sensors per lot.",
      "MDARIX sample author; checked by MDARIX sample reviewer",
      "2 for · 1 against",
      "2 open unknowns",
      "Open CAPA-02",
    ])
      expect(html).toContain(text);
    expect(html).not.toContain("Continue the story");
  });

  it("says plainly that nothing waits rather than promising work that is not there", () => {
    resources.data["/api/v1/decisions/queue"] = { total: 0, items: [] };
    const html = home("decision");
    expect(html).toContain("Nothing waits for your signature now.");
    expect(html).not.toContain("Review and sign");
  });

  it("gives the Risk Reviewer the requested review in one click", () => {
    resources.data["/api/v1/case-reviews"] = {
      items: [
        {
          id: "r1",
          business_id: "CRV000001",
          status: "REQUESTED",
          status_label: "Requested",
          request_reason: "Does the risk file need updating?",
          investigation: { id: "inv1", business_id: "SAMPLE-INV-001" },
        },
      ],
    };
    const html = home("risk");
    expect(html).toContain("Start the risk review");
    expect(html).toContain("SAMPLE-INV-001 · CRV000001");
    expect(primaries(html)).toHaveLength(1);
  });
});

describe("the flagship bar names the step on screen, and step 4 works with AI off", () => {
  it("reads the screen's step, not the steps done plus one", () => {
    const run = flagship(2);
    expect(flagshipStepOn("Product 360", "Product 360?product=SAMPLE-ORBIT-300")).toBe(1);
    expect(flagshipBarParts(run, false, 1)).toContain("Step 2 of 7");
    expect(flagshipStepOn("Investigations", "Evidence?view=Overview&part=intelligence")).toBe(2);
    expect(flagshipStepOn("Investigations", `Evidence?part=${AI_PROPOSALS_PART}`)).toBe(3);
    expect(flagshipStepOn("Investigations", "Decisions & actions?part=brief")).toBe(4);
    expect(flagshipStepOn("Investigations", "Decisions & actions?part=decision")).toBe(5);
    // The cockpit's own steps (UX3).
    expect(flagshipStepOn("Investigations", "Evidence?part=glance")).toBe(2);
    expect(flagshipStepOn("Investigations", `Possible causes?part=${AI_PROPOSALS_PART}`)).toBe(3);
    expect(flagshipStepOn("Investigations", "Brief?part=brief")).toBe(4);
    expect(flagshipStepOn("Investigations", "Decision & action?part=decision")).toBe(5);
  });

  it("sends step 4 to the recorded proposals, labelled for AI off", () => {
    const run = flagship(3);
    expect(flagshipPlace(run, 3).tab).toBe(`Possible causes?part=${AI_PROPOSALS_PART}`);
    expect(flagshipNextLabel(run, false)).toBe("Review the recorded proposals");
    expect(flagshipNextLabel(run, true)).toBe("Next: AI investigation");
    expect(flagshipNextLabel(flagship(4), false)).toBe("Next: Investigation Brief");
  });
});

describe("no background 403: what a role may not read is never asked for", () => {
  it("asks for validation evidence only for the trial owner or an administrator", () => {
    render(<NewRecordsSection />, api({ session: { business_permissions: [], allowed_menu: ["home"] } } as never));
    expect(resources.asked).not.toContain(VALIDATION_EVIDENCE_PATH);
    resources.asked = [];
    render(<NewRecordsSection />, api({ session: { business_permissions: [], trial_owner: true } } as never));
    expect(resources.asked).toContain(VALIDATION_EVIDENCE_PATH);
  });

  it("never asks for a Case's files without the right to read them", () => {
    expect(render(<CaseFiles caseId="i1" canAdd={false} canRead={false} />)).toBe("");
    expect(resources.asked.some((path) => path.includes("/attachments"))).toBe(false);
  });
});

describe("Complaints: the Service Desk logs a case, with one log button", () => {
  it("shows Log a case to case.log alone", () => {
    const html = render(
      <ComplaintViews />,
      api({ persona: "servicedesk", session: { business_permissions: ["case.log"] } } as never),
    );
    expect(html).toContain("Log a case");
    expect(render(<ComplaintViews />, api({ persona: "executive" }))).not.toContain("Log a case");
  });

  it("shows one log button on the triage view", () => {
    const html = render(
      <ComplaintViews tab="To triage" />,
      api({ persona: "handler", session: { business_permissions: ["case.log", "complaint.triage"] } } as never),
    );
    expect(html.match(/Log a case/g)).toHaveLength(1);
    expect(html).not.toContain("Log a case or an urgent case");
  });

  it("shows one log button on the Service Desk's first view, To log (UX3: UX2 made it the first)", () => {
    const html = render(
      <ComplaintViews tab="Calls to check" />,
      api({ persona: "servicedesk", session: { business_permissions: ["case.log"] } } as never),
    );
    // One button (an empty list's sentence may still say "Log a case, or ...").
    expect(html.match(/Log a case<\/button>/g)).toHaveLength(1);
    // The urgent intake keeps its own button.
    expect(html).toContain("Urgent: death or serious injury");
  });
});

describe("one overdue badge that says why", () => {
  it("names the overdue target and keeps the running legal clock as a quiet line", () => {
    const reply = {
      key: "task:1",
      category: "COMMUNICATION",
      category_label: "Communications",
      title: "Reply due from Reporter of SAMPLE-RV-08",
      market: null,
      due_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
      state: "OVERDUE",
      hours_left: -48,
    };
    const legal = {
      key: "obligation:1",
      category: "OBLIGATION",
      category_label: "Authority report",
      title: "FDA 3500A",
      market: "US",
      due_at: new Date(Date.now() + 2 * 86_400_000 + 3_600_000).toISOString(),
      state: "RUNNING",
      hours_left: 49,
    };
    expect(overdueWhy(reply)).toMatch(/^Overdue: Reply due from Reporter \(2 days overdue\)$/);
    const [urgency] = workColumns({} as never, vi.fn());
    const html = render(<>{urgency.render({ work: { due: [legal, reply] } })}</>);
    expect(html.match(/ms-chip-deadline/g)).toHaveLength(1);
    expect(html).toContain("Overdue: Reply due from Reporter");
    expect(html).toContain("Legal clock: 2 days left");
  });
});

it("keeps the oversight path in use (Home still reads the next actions)", () => {
  home("quality");
  expect(resources.asked.some((path) => path.startsWith(OVERSIGHT))).toBe(true);
});
