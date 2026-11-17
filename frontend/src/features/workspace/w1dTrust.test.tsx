// W1d, trust closure: the six views on Getting started (D07), the synthetic follow-up and the inconclusive result on
// the effectiveness check (D04), step 7's planned -> follow-up -> signed line, and the sample evidence register (D08).
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FOLLOW_UP_LINE, FlagshipView, OneStory, SIX_VIEWS } from "./sections/OneStory";
import { FlagshipBar } from "./sections/FlagshipBar";
import { CheckBody } from "./sections/Records";
import {
  REGISTER_LINK,
  SAMPLE_REGISTER_PATH,
  SampleRegisterPage,
  type SampleRegisterData,
} from "./sections/SampleRegister";
import { ONE_STORY_PATH, didItWorkLine, effectivenessStages, type FlagshipRun } from "./oneStory";
import { signBody, signProblem, type CapaDetail, type SyntheticFollowUp } from "./effectiveness";
import { workedTone } from "./decisionSummary";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { SAMPLE_SOURCE } from "./complaintList";

const reads = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const data = (path && reads.data[path.split("?")[0]]) ?? null;
    return { state: data ? "ready" : "loading", data, reload: () => undefined };
  },
  send: async () => ({}),
}));
vi.mock("./useAiStatus", () => ({ useAiReady: () => null, useAiBanner: () => null }));

const api = (permissions: string[] = []) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: permissions },
    work: { products: [], setInvestigationId: vi.fn(), refreshProducts: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    startStory: vi.fn(),
    navigation: "new",
    isTrial: true,
    dataSource: SAMPLE_SOURCE,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, permissions: string[] = []) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api(permissions)}>{node}</WorkspaceContext.Provider>);
const primaries = (html: string) => html.match(/class="ac-primary[^"]*"/g) ?? [];

type Capa = NonNullable<FlagshipRun["capa"]>;
const run = (current = 0, capa: Partial<Capa> = {}): FlagshipRun => ({
  run: "flagship",
  product: {
    id: "p-orbit",
    ref: "SAMPLE-ORBIT-300",
    name: "OrbitCare 300 Infusion Pump (Sample)",
    label: "OrbitCare 300",
    version: "Rev B",
    version_state: "KNOWN",
    unverified: 0,
  },
  investigation: { id: "inv-1", ref: "SAMPLE-INV-001", question: "Why did pressure-alarm complaints rise?" },
  change: null,
  capa: {
    id: "capa-2",
    ref: "SAMPLE-CAPA-02",
    title: "Restore incoming inspection",
    check_planned: false,
    check_status: null,
    follow_up: false,
    ...capa,
  },
  branch: null,
  ai_proposals: 1,
  mfa_verified: null,
  steps: Array.from({ length: 7 }, (_, index) => ({
    key: `k${index}`,
    label: `Step ${index + 1}`,
    done: index < current,
    skipped: false,
  })),
  current,
  finished: current >= 7,
});

beforeEach(() => {
  reads.data = {};
});

describe("D07: Getting started names the six views under its one main button", () => {
  it("shows the quiet strip and the register link, and still one main button", () => {
    reads.data[ONE_STORY_PATH] = { sample: null, yours: null, flagship: run() };
    const html = render(<OneStory />);
    expect(primaries(html)).toHaveLength(1);
    expect(html).toContain("Start the sample investigation");
    expect(html).toMatch(/Start the sample investigation.*uw-gs-views/s);
    for (const view of SIX_VIEWS) expect(html).toContain(`<li>${view}</li>`);
    expect(SIX_VIEWS).toHaveLength(6);
    expect(html).toContain(REGISTER_LINK);
  });

  it("the strip shows before the first step only", () => {
    expect(render(<FlagshipView story={{ sample: null, yours: null }} run={run(2)} />)).not.toContain("uw-gs-views");
  });

  it("the flagship bar links to the register", () => {
    reads.data[ONE_STORY_PATH] = { sample: null, yours: null, flagship: run(3) };
    expect(render(<FlagshipBar section="Product 360" />)).toContain(REGISTER_LINK);
  });
});

describe("D04: step 7 reads planned -> synthetic follow-up -> signed", () => {
  it("is too early until a person signs, then shows the signed result", () => {
    expect(didItWorkLine(run().capa)).toMatch(/^Did it work\? Too early/);
    expect(didItWorkLine(run(7, { check_planned: true, follow_up: true }).capa)).toMatch(/Too early/);
    expect(didItWorkLine(run(7, { check_planned: true, check_status: "INCONCLUSIVE" }).capa)).toBe(
      "Did it work? Signed: inconclusive",
    );
    const stages = effectivenessStages(run(7, { check_planned: true, follow_up: true }).capa);
    expect(stages.map((stage) => stage.done)).toEqual([true, true, false]);
    expect(stages[1].label).toBe("Synthetic follow-up (sample) to review");
    const signed = effectivenessStages(
      run(7, { check_planned: true, follow_up: true, check_status: "EFFECTIVE" }).capa,
    );
    expect(signed.map((stage) => stage.done)).toEqual([true, true, true]);
    expect(signed[2].label).toBe("Signed by a person: effective");
  });

  it("the step 7 card shows the stages once the check is planned", () => {
    const planned = run(6, { check_planned: true, follow_up: true });
    const html = render(<FlagshipView story={{ sample: null, yours: null }} run={planned} />);
    expect(html).toContain("Did it work? Too early");
    expect(html).toContain('aria-label="Effectiveness check"');
    expect(html).toContain("Synthetic follow-up (sample) to review");
    expect(render(<FlagshipView story={{ sample: null, yours: null }} run={run(6)} />)).not.toContain(
      'aria-label="Effectiveness check"',
    );
  });

  it("the finished story points to the follow-up until it is signed, never saying it worked", () => {
    const waiting = render(
      <FlagshipView story={{ sample: null, yours: null }} run={run(7, { check_planned: true, follow_up: true })} />,
    );
    expect(waiting).toContain(FOLLOW_UP_LINE);
    expect(primaries(waiting)).toHaveLength(1);
    expect(waiting).not.toMatch(/it worked/i);
    const signed = run(7, { check_planned: true, follow_up: true, check_status: "NOT_EFFECTIVE" });
    expect(render(<FlagshipView story={{ sample: null, yours: null }} run={signed} />)).not.toContain(FOLLOW_UP_LINE);
  });
});

const followUp: SyntheticFollowUp = {
  label: "Synthetic follow-up (sample)",
  synthetic: true,
  notice: "Synthetic follow-up (sample): simulated lots built after the fix. It is not real history.",
  action: "Incoming inspection restored to 32 units per lot (SAMPLE-CAPA-02)",
  evidence_ref: "SAMPLE-EV-006",
  follow_up_days: 90,
  before: {
    source: "Your sample records: lots 003 and 004",
    lots: ["SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004"],
    units: 300,
    months: [
      { month: 1, days: 30, complaints: 5 },
      { month: 2, days: 30, complaints: 6 },
      { month: 3, days: 16, complaints: 3 },
    ],
    complaints: 14,
    unit_months: 715,
    per_1000_unit_months: 19.6,
  },
  after: {
    source: "Synthetic follow-up (sample)",
    lots: [
      {
        lot: "FU-LOT-101",
        built_day_after_fix: 10,
        units: 150,
        sensors_inspected: 32,
        sensors_out_of_range: 0,
        complaints: 1,
      },
    ],
    months: [
      { month: 1, days: 30, complaints: 0 },
      { month: 2, days: 30, complaints: 0 },
      { month: 3, days: 30, complaints: 1 },
    ],
    complaints: 1,
    unit_months: 750,
    per_1000_unit_months: 1.3,
  },
  limits: ["Synthetic: the follow-up lots are simulated for the sample."],
};
const detail = (extra: Partial<CapaDetail> = {}): CapaDetail => ({
  capa: {
    id: "capa-2",
    business_id: "CAPA000002",
    capa_identifier: "SAMPLE-CAPA-02",
    title: "Restore incoming inspection",
    status: "Open",
    action_type: null,
    source_system: "MDARIX_SAMPLE",
    opened_on: "2026-11-17",
    due_on: "2027-01-01",
    closed: false,
    product_id: "p-orbit",
    product_name: "OrbitCare 300",
    investigation: null,
  },
  state: "SCHEDULED",
  planned_on: "2027-01-31",
  plan_source: "MDARIX",
  days_left: 75,
  closed_without_check: false,
  check: {
    id: "k-1",
    round: 1,
    status: "PLANNED",
    criteria: "No pressure-alarm complaint from lots made after the fix.",
    planned_on: "2027-01-31",
    measured_from: "2026-11-17",
    plan_version: 1,
    planned_by: "Meera Nair",
    planned_at: "2026-11-17T10:00:00Z",
    result_summary: null,
    evidence: {},
    signed_by: null,
    signer_role: null,
    signed_at: null,
    content_fingerprint: null,
  },
  excluded: false,
  rounds: [],
  recurrence: {
    available: false,
    reason: "The measurement has not started yet",
    product_id: "p-orbit",
    problem_codes: [],
  },
  suggestion: { criteria: "x", planned_on: "2027-01-31", measured_from: "2026-11-17" },
  can_plan: true,
  can_sign: true,
  synthetic_follow_up: followUp,
  ...extra,
});

describe("D04: the effectiveness check shows the labelled follow-up and the person signs", () => {
  it("labels the follow-up synthetic and offers effective, not effective and inconclusive", () => {
    const html = render(<CheckBody detail={detail()} onChanged={vi.fn()} />, ["quality.review"]);
    expect(html).toContain("Synthetic follow-up (sample)");
    expect(html).toContain("Synthetic, not real history");
    expect(html).toContain("It is not real history.");
    expect(html).toContain("FU-LOT-101");
    expect(html).toContain("1 complaint in 750 unit-months (1.3 per 1,000)");
    expect(html).toContain("14 complaints in 715 unit-months (19.6 per 1,000)");
    expect(html).toContain("Inconclusive: the evidence does not settle it yet");
    expect(html).toContain("Authenticator code");
    expect(html).toContain("labelled as such");
  });

  it("has no follow-up where the server sends none", () => {
    const html = render(<CheckBody detail={detail({ synthetic_follow_up: null })} onChanged={vi.fn()} />, [
      "quality.review",
    ]);
    expect(html).not.toContain("Synthetic follow-up (sample)");
  });

  it("sends the person's chosen result, password and code; nothing is chosen for them", () => {
    const form = {
      result: "INCONCLUSIVE" as const,
      summary: "One complaint on a short follow-up",
      password: "pw",
      code: "123456",
    };
    expect(signProblem({ ...form, result: "" })).toBe("Choose the result: effective, not effective or inconclusive");
    expect(signBody(form, 1)).toEqual({
      result: "INCONCLUSIVE",
      summary: "One complaint on a short follow-up",
      plan_version: 1,
      password: "pw",
      mfa_code: "123456",
    });
    expect(workedTone("INCONCLUSIVE")).toBe("warning");
  });
});

const register: SampleRegisterData = {
  title: "Sample evidence register",
  product: {
    id: "p-orbit",
    ref: "SAMPLE-ORBIT-300",
    name: "OrbitCare 300 Infusion Pump (Sample)",
    versions: [
      { version: "Rev A", released: "2025-11-22", description: "Rev A" },
      { version: "Rev B", released: "2026-09-03", description: "Rev B" },
    ],
  },
  change: { ref: "SAMPLE-CHG-014", description: "Inspection reduced from 32 to 13 units per lot.", on: "2026-08-29" },
  component: {
    ref: "SAMPLE-ORBIT-300-C1",
    suppliers: [{ revision: "Rev B", supplier: "NovaSense Components", from: null }],
  },
  lots: [
    {
      ref: "SAMPLE-ORBIT-300-LOT-003",
      version: "Rev B",
      built: "2026-09-03",
      units: 150,
      complaints: 9,
      pressure_alarm: 9,
      in_case: true,
    },
  ],
  complaints: {
    on_product: 22,
    pressure_alarm: 18,
    in_case: 14,
    trend: [
      {
        version: "Rev B",
        recent: 9,
        recent_days: 30,
        expected: 0.97,
        ratio: 9.3,
        label: "Significant rise",
        monthly: { before: 1.0, after: 9.0 },
      },
    ],
    trend_source: "The trend check (Trends and Home read the same computation)",
  },
  inspection: [{ when: "Rev B, NovaSense Components", units_per_lot: 13, source: "SAMPLE-CHG-014" }],
  case: { id: "inv-1", ref: "SAMPLE-INV-001", question: "Why?" },
  evidence: {
    records: [
      {
        ref: "SAMPLE-EV-001",
        title: "Supplier change record",
        recorded: "2026-11-03",
        source: "MDARIX sample dataset",
        content: null,
      },
    ],
    for: [{ evidence: "SAMPLE-EV-001", hypothesis: "NovaSense sensors", why: "The change record." }],
    against: [{ evidence: "SAMPLE-EV-002", hypothesis: "Ward settings", why: "Lots 001-002 show none." }],
    missing: [{ what: "Bench test of returned pumps", needed: "A reference gauge", status: "open" }],
  },
  follow_up: {
    label: "Synthetic follow-up (sample)",
    notice: "Synthetic follow-up (sample): not real history.",
    record: {
      ref: "SAMPLE-EV-006",
      title: "Synthetic follow-up (sample): lots built after SAMPLE-CAPA-02",
      recorded: "2026-11-17",
    },
    capa: { id: "capa-2", ref: "SAMPLE-CAPA-02", title: "Restore" },
    check: null,
    after: { complaints: 1, unit_months: 750, per_1000_unit_months: 1.3 },
  },
  limits: ["Every record here is sample data made for the free trial: OrbitCare 300 is not a real device."],
};

describe("D08: the sample evidence register", () => {
  it("shows the trend check's monthly rates, the records' counts, the evidence and the labelled follow-up", () => {
    reads.data[SAMPLE_REGISTER_PATH] = register;
    const html = render(<SampleRegisterPage />);
    expect(html).toContain("Sample evidence register");
    expect(html).toContain("1.0 → 9.0");
    expect(html).toContain("9.3×");
    expect(html).toContain("SAMPLE-ORBIT-300-LOT-003");
    expect(html).toContain("22 complaints on the product, 18 of them pressure alarms; 14 are in the investigation.");
    expect(html).toContain("SAMPLE-CHG-014");
    expect(html).toContain("Bench test of returned pumps");
    expect(html).toContain("Lots 001-002 show none.");
    expect(html).toContain("Synthetic follow-up (sample)");
    expect(html).toContain("once it is planned");
    expect(html).toContain("OrbitCare 300 is not a real device");
    expect(primaries(html)).toHaveLength(0);
  });
});
