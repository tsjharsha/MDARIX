import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WORKSPACE_SECTIONS, WorkspaceContext, sectionAllowed, type WorkspaceApi } from "./workspaceContext";
import { WatchCard } from "./sections/ReportabilityWatch";
import { WindowsBody } from "./sections/ReportingWindows";
import { CapaCard, CheckBody, RecordsSection, RecurrenceView } from "./sections/Records";
import { addressFor, locationFromAddress } from "./workspaceAddress";
import { VIEW_TO_SECTION } from "./UserWorkspace";
import { viewFromPath } from "../../app/router";
import type { ReportabilitySettings, WatchItem } from "./reportability";
import type { CapaDetail, CapaItem } from "./effectiveness";
import { BASIS_DISCLAIMER, SIGNATURE_BASIS } from "../shared/standards";

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["home", "products", "investigations"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn(), setInvestigationId: vi.fn() },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode, permissions: string[] = []) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const watchItem = (overrides: Partial<WatchItem> = {}): WatchItem => ({
  id: "0b6f8f9e-1111-4222-8333-444455556666",
  business_id: "CMP000031",
  complaint_identifier: "SRC-31",
  product_id: "9d1c2b3a-1111-4222-8333-444455556666",
  product_name: "Infusion Pump",
  version: "B",
  status: "open",
  description: "Patient died after the pump stopped",
  country: "US",
  received_date: "2026-09-15",
  patient_involved: true,
  serious_injury: null,
  death: true,
  malfunction: true,
  aware_date: "2026-09-15",
  aware_source: "AWARENESS_DATE",
  days_since_aware: 28,
  triggers: ["DEATH", "MALFUNCTION"],
  clocks: [
    {
      window: "FDA MDR (30 calendar days)",
      days: 30,
      day_basis: "CALENDAR",
      due_date: "2026-10-15",
      state: "DUE_SOON",
      days_left: 2,
      triggers: ["DEATH", "MALFUNCTION"],
      basis: ["CFR803_50", "CFR803_53"],
    },
  ],
  binding: {
    window: "FDA MDR (30 calendar days)",
    days: 30,
    day_basis: "CALENDAR",
    due_date: "2026-10-15",
    state: "DUE_SOON",
    days_left: 2,
    triggers: ["DEATH", "MALFUNCTION"],
    basis: ["CFR803_50", "CFR803_53"],
  },
  follow_ups: [
    {
      code: "PATIENT_OUTCOME",
      label: "A patient was involved, but whether anyone was seriously injured is not recorded",
    },
  ],
  case: null,
  settled_by_case: false,
  in_review: false,
  state: "DUE_SOON",
  decision: null,
  ...overrides,
});

describe("a complaint on the reportability watch", () => {
  it("shows its clock, what it reports and the missing answers", () => {
    const markup = render(<WatchCard item={watchItem()} onDecide={vi.fn()} />, ["regulatory.review", "records.write"]);
    expect(markup).toContain("CMP000031");
    expect(markup).toContain("Due in 2 days");
    expect(markup).toContain("FDA MDR (30 calendar days)");
    expect(markup).not.toContain("(30 calendar days) (30 calendar days)");
    expect(markup).toContain("Death");
    expect(markup).toContain("Malfunction");
    expect(markup).toContain("whether anyone was seriously injured is not recorded");
    expect(markup).toContain("uw-cr-rail tone-warning");
    expect(markup).toContain("Record decision");
    expect(markup).toContain("Open investigation");
  });

  it("names the basis of its window beside the window's name", () => {
    const markup = render(<WatchCard item={watchItem()} onDecide={vi.fn()} />, []);
    expect(markup).toContain('aria-label="Basis of the window"');
    expect(markup).toContain('title="30-day reports by manufacturers">21 CFR 803.50<');
    expect(markup).toContain(">21 CFR 803.53<");
    const without = watchItem();
    const binding = without.binding ? { ...without.binding, basis: [] } : null;
    expect(render(<WatchCard item={{ ...without, binding }} onDecide={vi.fn()} />, [])).not.toContain("uw-basis");
  });

  it("offers no decision to a role without regulatory review or approval", () => {
    const markup = render(<WatchCard item={watchItem()} onDecide={vi.fn()} />, ["quality.review"]);
    expect(markup).not.toContain("Record decision");
  });

  it("shows a decision with its report, who and whether it came inside the window", () => {
    const decided = watchItem({
      state: "DECIDED",
      decision: {
        decision: "REPORTED",
        rationale: "Death: MDR filed within 30 days",
        report_reference: "MDR-3004-2026-00017",
        reported_on: "2026-10-01",
        window: "FDA MDR (30 calendar days)",
        due_on: "2026-10-15",
        on_time: true,
        decided_by: "Rita Regulatory",
        decided_at: "2026-10-01T10:00:00Z",
      },
    });
    const markup = render(<WatchCard item={decided} onDecide={vi.fn()} />, ["regulatory.approve"]);
    expect(markup).toContain("Reported · MDR-3004-2026-00017");
    expect(markup).toContain("Inside the window");
    expect(markup).toContain("Rita Regulatory");
    expect(markup).toContain("Change decision");
    expect(markup).not.toContain("Due in 2 days");
  });
});

describe("the reporting windows", () => {
  const settings: ReportabilitySettings = {
    windows: [
      {
        name: "FDA MDR (30 calendar days)",
        markets: ["US", "USA"],
        triggers: ["DEATH", "SERIOUS_INJURY", "MALFUNCTION"],
        days: 30,
        day_basis: "CALENDAR",
        note: "A 5-work-day report rests on a judgment",
        basis: ["CFR803_50", "CFR803_53"],
      },
    ],
    lookback_days: 365,
    configured: true,
    templates: [
      {
        name: "EU MDR: serious incident (15 days)",
        markets: ["DE"],
        triggers: ["DEATH", "SERIOUS_INJURY"],
        days: 15,
        day_basis: "CALENDAR",
        note: null,
        basis: ["MDR_87"],
      },
    ],
    version: 3,
    updated_by_name: "Rita Regulatory",
    updated_at: "2026-10-01T10:00:00Z",
  };

  it("lets a person with regulatory approval edit them, starting from templates", () => {
    const markup = render(<WindowsBody settings={settings} onSaved={vi.fn()} />, ["regulatory.approve"]);
    expect(markup).toContain("Save reporting windows");
    expect(markup).toContain("EU MDR: serious incident (15 days)");
    expect(markup).toContain("Templates are a starting point");
    expect(markup).toContain("Rita Regulatory");
    // Each window and template names its basis; the disclaimer is said once.
    expect(markup).toContain(">21 CFR 803.50<");
    expect(markup).toContain(">EU MDR Art. 87<");
    expect(markup.split(BASIS_DISCLAIMER).length).toBe(2);
  });

  it("shows them read-only to everyone else", () => {
    const markup = render(<WindowsBody settings={settings} onSaved={vi.fn()} />, ["regulatory.review"]);
    expect(markup).not.toContain("Save reporting windows");
    expect(markup).toContain("30 calendar days · starts on death, serious injury, malfunction · 2 markets");
    expect(markup).toContain(">21 CFR 803.53<");
    expect(markup).toContain(BASIS_DISCLAIMER);
    const handMade = { ...settings, windows: [{ ...settings.windows[0], basis: [] }] };
    expect(render(<WindowsBody settings={handMade} onSaved={vi.fn()} />, [])).not.toContain(BASIS_DISCLAIMER);
  });
});

const capaItem = (overrides: Partial<CapaItem> = {}): CapaItem => ({
  capa: {
    id: "c-1",
    business_id: "CAPA000012",
    capa_identifier: "CAPA-INV000147-1",
    title: "Replace the occlusion sensor",
    status: "Closed",
    action_type: "CORRECTIVE",
    source_system: "MDARIX",
    opened_on: "2026-08-01",
    due_on: "2026-09-01",
    closed: true,
    product_id: "p-1",
    product_name: "Infusion Pump",
    investigation: { id: "i-1", business_id: "INV000147" },
  },
  state: "NOT_PLANNED",
  planned_on: null,
  plan_source: null,
  days_left: null,
  closed_without_check: true,
  check: null,
  ...overrides,
});

describe("CAPA effectiveness", () => {
  it("flags a CAPA closed without a check", () => {
    const markup = render(<CapaCard item={capaItem()} onOpen={vi.fn()} />);
    expect(markup).toContain("CAPA000012");
    expect(markup).toContain("No check planned");
    expect(markup).toContain("Closed without an effectiveness check");
    expect(markup).toContain("case INV000147");
  });

  it("says when only the date came from the quality system", () => {
    const markup = render(
      <CapaCard
        item={capaItem({
          state: "DUE_SOON",
          planned_on: "2026-10-20",
          plan_source: "SOURCE_SYSTEM",
          days_left: 7,
          closed_without_check: false,
        })}
        onOpen={vi.fn()}
      />,
    );
    expect(markup).toContain("Due in 7 days");
    expect(markup).toContain("date from your quality system: confirm the plan");
  });

  it("draws the recurrence before and since, with its caveat", () => {
    const markup = render(
      <RecurrenceView
        recurrence={{
          available: true,
          product_id: "p-1",
          problem_codes: ["OCC"],
          measured_from: "2026-09-01",
          before: { complaints: 4, days: 42, per_30_days: 2.9 },
          since: { complaints: 1, days: 42, per_30_days: 0.7 },
          direction: "FEWER",
          too_early: false,
          note: "Observed from complaint records; not a statistical test. Judge against the criteria.",
        }}
      />,
    );
    expect(markup).toContain("Fewer complaints since");
    expect(markup).toContain("Problem codes OCC");
    expect(markup).toContain("not a statistical test");
    expect(markup).toContain("4 in 42 days");
    expect(
      render(
        <RecurrenceView recurrence={{ available: false, reason: "No product", product_id: null, problem_codes: [] }} />,
      ),
    ).toContain("No product");
  });

  const detail = (overrides: Partial<CapaDetail> = {}): CapaDetail => ({
    ...capaItem({ state: "DUE_SOON", planned_on: "2026-10-20", days_left: 7, closed_without_check: false }),
    check: {
      id: "k-1",
      round: 1,
      status: "PLANNED",
      criteria: "At most one OCC complaint in 90 days",
      planned_on: "2026-10-20",
      measured_from: "2026-09-01",
      plan_version: 1,
      planned_by: "Ivy Investigator",
      planned_at: "2026-09-01T10:00:00Z",
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
      product_id: "p-1",
      problem_codes: [],
    },
    suggestion: { criteria: "No new OCC complaints", planned_on: "2026-12-01", measured_from: "2026-09-01" },
    can_plan: true,
    can_sign: true,
    ...overrides,
  });

  it("lets a quality reviewer sign the result with password and authenticator code", () => {
    const markup = render(<CheckBody detail={detail()} onChanged={vi.fn()} />, ["quality.review"]);
    expect(markup).toContain("Sign the result of round 1");
    expect(markup).toContain("Effective: the criteria are met");
    expect(markup).toContain("Authenticator code");
    expect(markup).toContain("Change the plan");
  });

  it("says what a signed round records, and only once a round is signed", () => {
    const signed: CapaDetail["rounds"][number] = {
      id: "k-0",
      round: 1,
      status: "EFFECTIVE",
      criteria: "At most one OCC complaint in 90 days",
      planned_on: "2026-09-20",
      measured_from: "2026-08-01",
      plan_version: 1,
      planned_by: "Ivy Investigator",
      planned_at: "2026-08-01T10:00:00Z",
      result_summary: "No recurrence",
      evidence: {},
      signed_by: "Quinn Quality",
      signer_role: "QUALITY_REVIEWER",
      signed_at: "2026-09-21T10:00:00Z",
      content_fingerprint: "a".repeat(64),
    };
    const markup = render(<CheckBody detail={detail({ rounds: [signed] })} onChanged={vi.fn()} />, []);
    expect(markup).toContain(SIGNATURE_BASIS);
    expect(markup).toContain(BASIS_DISCLAIMER);
    expect(render(<CheckBody detail={detail()} onChanged={vi.fn()} />, [])).not.toContain(SIGNATURE_BASIS);
  });

  it("offers no signature to a role that may only plan", () => {
    const markup = render(<CheckBody detail={detail()} onChanged={vi.fn()} />, ["investigation.work"]);
    expect(markup).not.toContain("Sign the result");
    expect(markup).toContain("Change the plan");
    expect(render(<CheckBody detail={detail()} onChanged={vi.fn()} />, [])).not.toContain("Change the plan");
  });

  it("opens the plan form for a CAPA without a check", () => {
    const markup = render(
      <CheckBody detail={detail({ check: null, can_sign: false, state: "NOT_PLANNED" })} onChanged={vi.fn()} />,
      ["investigation.work"],
    );
    expect(markup).toContain("Plan the check");
    expect(markup).toContain("No new OCC complaints");
    expect(markup).toContain("reminder 14 days before the check day");
  });
});

describe("the Records section", () => {
  it("has its own address, menu entry and tab", () => {
    expect(viewFromPath("/app/records")).toBe("records");
    expect(VIEW_TO_SECTION.records).toEqual(["Records"]);
    expect(addressFor({ section: "Records", tab: "Effectiveness checks" })).toBe(
      "/app/records?tab=Effectiveness+checks",
    );
    expect(
      locationFromAddress("/app/records", "?tab=Effectiveness+checks", VIEW_TO_SECTION, WORKSPACE_SECTIONS),
    ).toEqual({
      section: "Records",
      tab: "Effectiveness checks",
    });
    expect(sectionAllowed("Records", ["home"])).toBe(true);
    expect(render(<RecordsSection />)).toContain("Effectiveness checks");
  });
});
