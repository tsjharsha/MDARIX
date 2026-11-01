import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { DispositionCard, DispositionPanel, SignedDisposition } from "./sections/Dispositions";
import {
  covers,
  formOf,
  handsOnText,
  signBody,
  signProblem,
  treeStates,
  type BoardItem,
  type DispositionForm,
  type DispositionScreen,
  type DispositionVersion,
} from "./disposition";

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["home"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn(), setInvestigationId: vi.fn() },
  } as unknown as WorkspaceApi;
}
const render = (node: ReactNode, permissions: string[] = ["quality.review"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const screen = (overrides: Partial<DispositionScreen> = {}): DispositionScreen => ({
  complaint: {
    id: "c-1",
    ref: "CMP000041",
    complaint_identifier: "SAMPLE-RT-01",
    product_name: "VentraLink 250",
    version: "Rev B",
    lot: "LOT-005",
    description: "Low-flow alarm after a filter change.",
    source: "Distributor",
    problem_code: null,
    country: "Germany",
    received_date: "2026-10-29",
    awareness_date: "2026-10-29",
  },
  opened_at: "2026-10-31T10:00:00+00:00",
  triggers: [],
  trigger_codes: [],
  trigger_rules: [{ code: "SAFETY", label: "Safety issue", definition: "A death is recorded." }],
  candidates: [],
  routine: {
    offered: true,
    blocked: [],
    basis: "Not on the reportability watch: no death, serious injury or malfunction recorded; patient outcome known",
    markets: [
      { market: "US", label: "United States (FDA)" },
      { market: "EU_NI", label: "EU and Northern Ireland (EU MDR)" },
    ],
    target_seconds: 600,
  },
  reportability: { on_watch: false, settled: true, markets: [] },
  corrections: { USER_INSTRUCTED: "User instructed", OTHER: "Other (describe it)" },
  attributions: [
    { code: "USE_RELATED", label: "Use-related", definition: "How the device was set up." },
    { code: "UNDETERMINED", label: "Undetermined", definition: "Say why." },
  ],
  no_investigation_clause: "ISO 13485:2016 clause 8.2.2",
  classification: {
    id: "k-1",
    version: 1,
    use_environment: "UNKNOWN",
    use_environment_text: null,
    user_type: "HEALTHCARE_PROFESSIONAL",
    user_type_text: null,
    source_values: { use_environment: "Step-down unit", user_type: "Healthcare professional" },
    state: "PROPOSED",
    coding_criteria_version: "coding-starter-1",
    confirmed_by: null,
    confirmed_at: null,
  },
  use_environments: { HOSPITAL_WARD: "Hospital ward", OTHER: "Other", UNKNOWN: "Unknown" },
  user_types: { HEALTHCARE_PROFESSIONAL: "Healthcare professional", UNKNOWN: "Unknown" },
  coding_criteria: { version: "coding-starter-1", rules: ["A step-down unit is coded hospital ward."] },
  disposition_rules: { version: "disposition-starter-1", rules: ["Answer in order."] },
  current: null,
  history: [],
  version: 0,
  training: [
    {
      code: "DISPOSITION_RULES",
      title: "Complaint disposition rules (starter)",
      version: "disposition-starter-1",
      statement: "I have read the complaint disposition rules, MDARIX starter, version 1",
      state: "MISSING",
      held_version: null,
      trained_at: null,
      method: null,
    },
  ],
  training_required: true,
  trained_colleagues: [],
  starter_mark: "Starter text — awaiting regulatory confirmation: check it against your own procedure.",
  practice_label:
    "Practice record: made in a free trial with sample or de-identified data. Not your regulatory record.",
  ...overrides,
});

const filled = (base: DispositionScreen): DispositionForm => ({
  ...formOf(base),
  record: {
    troubleshooting: "Alarm check and filter inspection",
    correction_type: "USER_INSTRUCTED",
    correction: "User instructed to re-seat the filter",
    result: "Alarm cleared",
    service_ticket: "DIST-REF-2231",
    no_investigation_rationale: "User-correctable seating fault, cleared at service level.",
  },
  attribution: "USE_RELATED",
  password: "secret",
});

const signed: DispositionVersion = {
  id: "d-1",
  version: 1,
  branch: "SERVICE_LEVEL",
  branch_label: "Resolved at service level",
  triggers: [],
  answers: {},
  service_record: {
    troubleshooting: "Alarm check",
    correction_type: "USER_INSTRUCTED",
    correction: "User instructed to re-seat the filter",
    result: "Alarm cleared",
    service_ticket: "DIST-REF-2231",
    no_investigation_rationale: "User-correctable seating fault.",
    clause: "ISO 13485:2016 clause 8.2.2",
  },
  attribution: "USE_RELATED",
  attribution_label: "Use-related",
  attribution_reason: null,
  investigation_id: null,
  investigation_ref: null,
  routine_path: true,
  hands_on_seconds: 305,
  change_reason: null,
  content_fingerprint: "f".repeat(64),
  signed_by: "Priya Sharma",
  signed_at: "2026-10-31T10:05:05+00:00",
  superseded: false,
  sample: false,
};

describe("the disposition rules on screen", () => {
  it("pre-selects service level on the routine path and escalation when a trigger is met", () => {
    expect(formOf(screen()).branch).toBe("SERVICE_LEVEL");
    expect(formOf(screen()).useEnvironment).toBe("UNKNOWN"); // proposed as is: never guessed
    const triggered = screen({ trigger_codes: ["NEW_FAILURE_MODE"] });
    expect(formOf(triggered).branch).toBe("ESCALATED_BY_TRIGGER");
    expect(treeStates(triggered, "ESCALATED_BY_TRIGGER")).toEqual({
      TRIGGER: "taken",
      KNOWN_ISSUE: "refused",
      SERVICE_LEVEL: "refused",
      CHOICE: "refused",
    });
    // A known issue (an open case matches) opens on that case; a trigger still wins over it.
    const case1 = { id: "case-1", ref: "INV1", identifier: "SAMPLE-INV-001", question: "Why?", match: [] };
    const known = screen({ candidates: [case1] });
    expect(formOf(known)).toMatchObject({ branch: "KNOWN_ISSUE", caseId: "case-1" });
    expect(treeStates(known, "KNOWN_ISSUE")).toEqual({
      TRIGGER: "no",
      KNOWN_ISSUE: "taken",
      SERVICE_LEVEL: "open",
      CHOICE: "open",
    });
    expect(formOf(screen({ candidates: [case1], trigger_codes: ["INJURY"] }))).toMatchObject({
      branch: "ESCALATED_BY_TRIGGER",
      caseId: "",
    });
    expect(treeStates(screen(), "SERVICE_LEVEL")).toEqual({
      TRIGGER: "no",
      KNOWN_ISSUE: "no",
      SERVICE_LEVEL: "taken",
      CHOICE: "open",
    });
  });

  it("asks for the service record, the attribution, the training and the password before signing", () => {
    const base = screen();
    expect(signProblem(base, formOf(base), true)).toMatch(/troubleshooting/);
    const ready = filled(base);
    expect(signProblem(base, ready, false)).toMatch(/practice training/);
    expect(signProblem(base, ready, true)).toBeNull();
    // When the server needs the authenticator code, the form asks for it before sending (no refusal after signing).
    const coded = { ...base, code_required: true };
    expect(signProblem(coded, ready, true)).toBe("Enter the 6-digit code from your authenticator app.");
    expect(signProblem(coded, { ...ready, code: "12345" }, true)).toMatch(/6-digit code/);
    expect(signProblem(coded, { ...ready, code: " 123456 " }, true)).toBeNull();
    expect(signProblem(base, { ...ready, attribution: "" }, true)).toMatch(/attribution/);
    expect(signProblem(base, { ...ready, attribution: "UNDETERMINED" }, true)).toMatch(/Undetermined/);
    expect(signProblem(base, { ...ready, useEnvironment: "OTHER" }, true)).toMatch(/other/);
    const known = screen({
      candidates: [{ id: "case-1", ref: "INV1", identifier: "SAMPLE-INV-001", question: "Why?", match: [] }],
    });
    expect(signProblem(known, { ...filled(known), branch: "SERVICE_LEVEL", caseId: "" }, true)).toMatch(
      /not that known issue/,
    );
    expect(signProblem(known, { ...filled(known), branch: "KNOWN_ISSUE", caseId: "case-1" }, true)).toMatch(/reason/);
  });

  it("sends what the person saw and lists what the one signature covers", () => {
    const base = screen();
    const body = signBody(base, filled(base));
    expect(body.routine).toBe(true);
    expect(body.seen_triggers).toEqual([]);
    expect(body.opened_at).toBe(base.opened_at);
    expect(body.classification).toEqual({
      use_environment: "UNKNOWN",
      use_environment_text: null,
      user_type: "HEALTHCARE_PROFESSIONAL",
      user_type_text: null,
    });
    expect(signBody(base, { ...filled(base), branch: "ESCALATED_BY_CHOICE" }).service_record).toBeNull();
    expect(covers(base, "SERVICE_LEVEL")).toEqual([
      "The disposition: resolved at service level",
      "The classification, confirmed",
      "United States (FDA): not reportable (routine basis)",
      "EU and Northern Ireland (EU MDR): not reportable (routine basis)",
    ]);
    expect(covers(base, "ESCALATED_BY_CHOICE")).toHaveLength(2);
    expect(handsOnText(305)).toBe("5 min 5 s");
  });
});

describe("the disposition screens", () => {
  it("shows the routine path's basis, the four questions, the source value and the training", () => {
    const html = render(<DispositionPanel screen={screen()} onSigned={vi.fn()} onTrained={vi.fn()} />);
    expect(html).toContain("Routine path: one screen, one signature");
    expect(html).toContain("United States (FDA)</strong>: not reportable");
    for (const text of [
      "Is an escalation trigger met?",
      "Is it a known issue?",
      "Was it resolved at service level?",
      "Otherwise: escalate by choice",
    ])
      expect(html).toContain(text);
    expect(html).toContain("Source value: “Step-down unit” (not on the list)");
    expect(html).toContain("Show the coding criteria");
    expect(html).toContain("I have read the complaint disposition rules, MDARIX starter, version 1");
    expect(html).toContain("Practice record");
  });

  it("refuses the other branches when a trigger is met, and says the market assessment is still due", () => {
    const html = render(
      <DispositionPanel
        screen={screen({
          trigger_codes: ["NEW_FAILURE_MODE"],
          triggers: [
            {
              code: "NEW_FAILURE_MODE",
              label: "New failure mode",
              field: "problem_code",
              value: "BATTERY_SHUTDOWN",
              record: "CMP000045",
              fact: "Problem code BATTERY_SHUTDOWN not recorded before on VentraLink 250",
            },
          ],
          routine: { ...screen().routine, offered: false, blocked: ["On the reportability watch"] },
          reportability: { on_watch: true, settled: false, markets: [] },
          training_required: false,
        })}
        onSigned={vi.fn()}
        onTrained={vi.fn()}
      />,
    );
    expect(html).toContain("Standard path");
    expect(html).toContain("BATTERY_SHUTDOWN not recorded before");
    expect(html).toContain("Refused: a trigger is met");
    expect(html).toContain("its market assessment is still due under Complaints › Reportability");
    expect(html).not.toContain("I have read the");
  });

  it("shows a signed disposition as signed, with a new version only on request", () => {
    const html = render(
      <DispositionPanel screen={screen({ current: signed, version: 1 })} onSigned={vi.fn()} onTrained={vi.fn()} />,
    );
    expect(html).toContain("Sign a new version");
    expect(html).not.toContain("Is an escalation trigger met?");
  });

  it("shows a signed version with its record, attribution and hands-on time, and a card per complaint", () => {
    const html = render(<SignedDisposition version={signed} />);
    expect(html).toContain("Resolved at service level");
    expect(html).toContain("ISO 13485:2016 clause 8.2.2");
    expect(html).toContain("Use-related");
    expect(html).toContain("5 min 5 s (routine path; target under 10 minutes)");
    const item = {
      ...screen().complaint,
      on_watch: false,
      routine_offered: true,
      triggers: [],
      known_issue: [],
    } as BoardItem;
    const routine = render(<DispositionCard item={item} onOpen={vi.fn()} />);
    expect(routine).toContain("Close on the routine path");
    expect(routine).toContain("Routine path");
    // A known issue (an open case with the same product and problem code, or the same lot) links to that case.
    const known = render(<DispositionCard item={{ ...item, known_issue: ["CASE-1"] }} onOpen={vi.fn()} />);
    expect(known).toContain("Link to the open case");
    expect(known).toContain("Known issue");
    expect(known).not.toContain("Close on the routine path");
    expect(known).not.toContain("Routine path");
    // A trigger decides first, even with a matching open case.
    const triggered = render(
      <DispositionCard
        item={{ ...item, routine_offered: false, triggers: ["NEW_FAILURE_MODE"], known_issue: ["CASE-1"] }}
        onOpen={vi.fn()}
      />,
    );
    expect(triggered).toContain("Decide the disposition");
    expect(triggered).not.toContain("Link to the open case");
    expect(render(<DispositionCard item={{ ...item, disposition: signed }} onOpen={vi.fn()} />)).toContain(
      "Open the disposition",
    );
  });
});
