import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ResolveClosePanel } from "./sections/ResolveClose";
import type { DispositionScreen } from "./disposition";
import {
  isNewCode,
  needsTree,
  reportabilityLine,
  resolveBody,
  resolveCovers,
  resolveFormOf,
  resolveProblem,
  type ResolveForm,
  type ResolveScreen,
} from "./resolveClose";

const render = (node: ReactNode) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { allowed_menu: ["home"], business_permissions: ["quality.review"] },
          open: vi.fn(),
          notify: vi.fn(),
          work: { products: [], requestOpenInvestigation: vi.fn(), setInvestigationId: vi.fn() },
        } as unknown as WorkspaceApi
      }
    >
      {node}
    </WorkspaceContext.Provider>,
  );

const disposition = (overrides: Partial<DispositionScreen> = {}) =>
  ({
    complaint: {
      id: "c-1",
      ref: "CMP000041",
      complaint_identifier: "CASE-0007",
      product_name: "VentraLink 250",
      version: "Rev B",
      lot: "LOT-005",
      description: "Low-flow alarm after a filter change.",
      source: "Case",
      problem_code: null,
      country: "Germany",
      received_date: "2026-11-09",
      awareness_date: "2026-11-09",
    },
    opened_at: "2026-11-10T10:00:00+00:00",
    triggers: [],
    trigger_codes: [],
    candidates: [],
    routine: {
      offered: true,
      blocked: [],
      basis: "Not on the reportability watch",
      markets: [{ market: "US", label: "United States (FDA)" }],
      target_seconds: 600,
    },
    reportability: { on_watch: false, settled: true, markets: [] },
    corrections: {
      USER_INSTRUCTED: "User instructed",
      PART_REPLACED: "Part replaced",
      NO_FAULT_FOUND: "No fault found",
      OTHER: "Other (describe it)",
    },
    attributions: [
      { code: "USE_RELATED", label: "Use-related", definition: "" },
      { code: "UNDETERMINED", label: "Undetermined", definition: "" },
    ],
    no_investigation_clause: "ISO 13485:2016 clause 8.2.2",
    classification: {
      use_environment: "HOSPITAL_WARD",
      use_environment_text: null,
      user_type: "HEALTHCARE_PROFESSIONAL",
      user_type_text: null,
      source_values: {},
    },
    use_environments: { HOSPITAL_WARD: "Hospital ward", OTHER: "Other" },
    user_types: { HEALTHCARE_PROFESSIONAL: "Healthcare professional" },
    current: null,
    history: [],
    version: 0,
    training: [],
    training_required: false,
    trained_colleagues: [],
    ...overrides,
  }) as unknown as DispositionScreen;

const screen = (overrides: Partial<ResolveScreen> = {}, inner: Partial<DispositionScreen> = {}): ResolveScreen => ({
  disposition: disposition(inner),
  mode: "COMPLETE",
  button: "Resolve and close",
  offer: { full: true, blocking: [], routine: true },
  closed: false,
  closed_at: null,
  prefill: {
    troubleshooting: "Filter re-seated over the phone with the therapist.",
    correction_type: "USER_INSTRUCTED",
    service_ticket: "",
    problem_code: "",
  },
  problem_code_read_only: false,
  problem_codes: ["LOW_FLOW_ALARM", "FILTER_SEATING"],
  product_codes: ["LOW_FLOW_ALARM"],
  similar_last_12_months: 2,
  owner: { id: null, name: null, is_me: false },
  reporters_with_contact: 1,
  no_contact_reason: null,
  reasons: { USE_RELATED_INSTRUCTED: "Single event, use-related, resolved by instruction", OTHER: "Other" },
  device_returned: { NOT_NEEDED: "Not needed" },
  told_how: { PHONE: "Phone", NOT_POSSIBLE: "Not possible" },
  ticket_corrections: ["PART_REPLACED", "SETTING_CORRECTED"],
  ...overrides,
});

const filled = (base: ResolveScreen): ResolveForm => ({
  ...resolveFormOf(base),
  problemCode: "LOW_FLOW_ALARM",
  correction: "User instructed to re-seat the filter.",
  result: "Alarm cleared",
  reason: "USE_RELATED_INSTRUCTED",
  attribution: "USE_RELATED",
  toldHow: "PHONE",
  password: "secret",
});

describe("Resolve and close: the rules (B7, spec 1.2)", () => {
  it("opens pre-filled from the Case, and an anonymous reporter is 'not possible' with the Case's reason", () => {
    const form = resolveFormOf(screen());
    expect(form.troubleshooting).toMatch(/re-seated/);
    expect(form.correctionType).toBe("USER_INSTRUCTED");
    expect(form.toldHow).toBe("");
    const anonymous = resolveFormOf(screen({ reporters_with_contact: 0, no_contact_reason: "Caller gave no name" }));
    expect(anonymous.toldHow).toBe("NOT_POSSIBLE");
    expect(anonymous.toldReason).toBe("Anonymous: Caller gave no name");
  });

  it("never skips the problem code or customer told; a ticket only for service work", () => {
    const base = screen();
    expect(resolveProblem(base, filled(base), true)).toBeNull();
    expect(resolveProblem(base, { ...filled(base), problemCode: " " }, true)).toMatch(/problem code/);
    expect(resolveProblem(base, { ...filled(base), toldHow: "" }, true)).toMatch(/customer was told/);
    expect(resolveProblem(base, { ...filled(base), toldHow: "NOT_POSSIBLE", toldReason: "" }, true)).toMatch(
      /could not be told/,
    );
    expect(resolveProblem(base, { ...filled(base), correctionType: "PART_REPLACED" }, true)).toMatch(/ticket/);
    expect(resolveProblem(base, { ...filled(base), reason: "OTHER", rationale: "short" }, true)).toMatch(/20/);
    expect(resolveProblem(base, { ...filled(base), correctionType: "NO_FAULT_FOUND" }, true)).toMatch(/undetermined/);
    // Connect: the QMS letter's ID is enough.
    const connect = screen({ mode: "CONNECT" });
    expect(resolveProblem(connect, { ...filled(connect), toldHow: "", qmsLetterId: "QMS-LTR-1" }, true)).toBeNull();
  });

  it("asks for the known-behaviour reference when the code is new on the product, and sends the trigger as seen", () => {
    const base = screen();
    expect(isNewCode(base, "low_flow_alarm")).toBe(false);
    expect(isNewCode(base, "FILTER_SEATING")).toBe(true);
    expect(isNewCode(screen({ product_codes: null }), "FILTER_SEATING")).toBe(false);
    const fresh = { ...filled(base), problemCode: "FILTER_SEATING" };
    expect(resolveProblem(base, fresh, true)).toMatch(/new on this product/);
    const body = resolveBody(base, { ...fresh, knownBehaviour: "IFU-VL-3 section 7" }, true);
    expect(body.seen_triggers).toEqual(["NEW_FAILURE_MODE"]);
    expect(body.known_behaviour_ref).toBe("IFU-VL-3 section 7");
    expect(resolveBody(base, filled(base), true).seen_triggers).toEqual([]);
  });

  it("asks to take over the owner, sends the reason codes and closes only when offered in full", () => {
    const owned = screen({ owner: { id: "u-2", name: "Asha Rao", is_me: false } });
    expect(resolveProblem(owned, filled(owned), true)).toMatch(/Take over as owner from Asha Rao/);
    const body = resolveBody(owned, { ...filled(owned), takeOver: true }, false);
    expect(body.take_over).toBe(true);
    expect(body.close).toBe(false);
    expect(body.service_record.no_investigation_reason).toBe("USE_RELATED_INSTRUCTED");
    expect(body.service_record.no_investigation_rationale).toBe("");
    expect(body.customer_told.how).toBe("PHONE");
  });

  it("uses the tree for other triggers or a matching investigation, the one screen otherwise", () => {
    expect(needsTree(screen())).toBe(false);
    expect(needsTree(screen({}, { trigger_codes: ["NEW_FAILURE_MODE"] }))).toBe(false);
    expect(needsTree(screen({}, { trigger_codes: ["INJURY"] }))).toBe(true);
    expect(
      needsTree(screen({}, { candidates: [{ id: "i", ref: "INV1", identifier: "", question: "", match: [] }] })),
    ).toBe(true);
    expect(needsTree(screen({ closed: true }, { current: {} as never }))).toBe(false);
  });

  it("states the reportability line and what the one signature covers, by mode", () => {
    expect(reportabilityLine(screen())).toBe("Not reportable for United States (FDA), on the routine basis.");
    expect(resolveCovers(screen(), true)).toContain("Ready to close, and the complaint closed in MDARIX");
    expect(resolveCovers(screen({ mode: "CONNECT" }), true)).toContain(
      "Ready to close in your QMS (your QMS closes it)",
    );
  });
});

describe("Resolve and close: the screen", () => {
  it("shows the sections in order, pre-filled, with the mode's button and the way to the tree", () => {
    const html = render(<ResolveClosePanel screen={screen()} onDone={vi.fn()} onTree={vi.fn()} onTrained={vi.fn()} />);
    const order = ["What happened", "Problem", "Troubleshooting and resolution", "Why no investigation", "Cause"];
    let at = 0;
    for (const heading of [...order, "Customer told", "Reportability", "One signature covers"]) {
      const found = html.indexOf(heading, at);
      expect(found, heading).toBeGreaterThan(-1);
      at = found;
    }
    expect(html).toContain("Filter re-seated over the phone");
    expect(html).toContain("Similar complaints on this product and problem code in the last 12 months: 2");
    expect(html).toContain("Resolve and close");
    expect(html).toContain("Use the full decision tree");
    expect(html).not.toMatch(/gradient/);
    const connect = render(
      <ResolveClosePanel
        screen={screen({ mode: "CONNECT", button: "Resolve and mark ready to close in your QMS" })}
        onDone={vi.fn()}
        onTree={vi.fn()}
        onTrained={vi.fn()}
      />,
    );
    expect(connect).toContain("Resolve and mark ready to close in your QMS");
  });

  it("offers Resolve only, with what blocks closing, when something else is open", () => {
    const html = render(
      <ResolveClosePanel
        screen={screen({ offer: { full: false, blocking: ["No task on the event is open"], routine: true } })}
        onDone={vi.fn()}
        onTree={vi.fn()}
        onTrained={vi.fn()}
      />,
    );
    expect(html).toContain("closing waits for No task on the event is open");
    expect(html).toMatch(/>Resolve</);
  });

  it("shows a closed complaint with Reopen and its reason", () => {
    const html = render(
      <ResolveClosePanel
        screen={screen({ closed: true, closed_at: "2026-11-10T09:00:00+00:00" })}
        onDone={vi.fn()}
        onTree={vi.fn()}
        onTrained={vi.fn()}
      />,
    );
    expect(html).toContain("Closed in MDARIX");
    expect(html).toContain("Why it reopens (at least 20 characters)");
    expect(html).toContain("Reopen");
  });
});
