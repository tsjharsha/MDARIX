// The SAMPLE-RV-11 complaint page as the server answers it, for the record-page tests (0.10.74 C2, 0.10.82 D1).
import type { EventView } from "../features/workspace/oversight";

export function rv11(): EventView {
  const due = {
    key: "watch:c-rv11:US",
    category: "REPORTING",
    category_label: "Reporting deadlines",
    title: "United States (FDA): not assessed yet, provisional deadline",
    market: "US",
    due_at: "2026-12-02T04:59:59Z",
    due_label: "Tue 1 Dec 2026, 23:59 EST",
    state: "LATER",
    state_label: "Later",
    hours_left: 650,
    opens: { section: "Complaints", tab: "Reportability" },
  };
  return {
    event: {
      complaint_id: "c-rv11",
      ref: "SAMPLE-RV-11",
      business_id: "CMP000038",
      product: "PulseWatch 410 Patient Monitor (Sample)",
      version: "Rev A",
      lot: "SAMPLE-PULSE-410-LOT-002",
      market: "US",
      awareness_at: "2026-11-01T20:07:11Z",
      status_in_qms: "Open",
      owner_id: "u1",
      owner_name: "Asha Quality",
      owner_named: true,
      sample: true,
      description: "Biomedical engineering checked a monitor against a reference oximeter.",
      problem_code: "SPO2_READING_HIGH",
      harm: null,
    },
    summary: {
      nearest_deadline: { title: due.title, due_at: due.due_at, opens: due.opens },
      open_requests: 0,
      next_action: {
        label: "Assess the United States (FDA) market",
        detail: "",
        opens: { section: "Complaints", tab: "Reporting" },
      },
    },
    stages: [
      { code: "TRIAGE", label: "Triage", state: "DONE" },
      { code: "MARKETS", label: "Market assessment", state: "CURRENT" },
      { code: "INVESTIGATION", label: "Investigation", state: "NOT_NEEDED" },
      { code: "DECISION", label: "Decision", state: "OPEN" },
      { code: "READY", label: "Ready to close", state: "OPEN" },
      { code: "CLOSED", label: "Closed in the QMS", state: "LATER" },
    ],
    checklist: [
      {
        code: "MARKETS",
        label: "Market assessments",
        result: "BLOCKED",
        result_label: "Open",
        detail: "United States (FDA) is not assessed yet",
        action: "Assess the United States (FDA) market",
        opens: { section: "Complaints", tab: "Reporting" },
      },
    ],
    blocked: 1,
    state: "NOT_READY",
    state_label: "Not ready to close",
    changed_since_signed: false,
    ready: null,
    decision_record: { entries: [], sha256: "", version: 0, filed: null },
    you_are_owner: true,
    people: [{ id: "u1", name: "Asha Quality" }],
    reason_min: 20,
    never_closes: "MDARIX never closes the complaint.",
    practice_label: null,
    work: {
      owner_name: "Asha Quality",
      stage: "Market assessment",
      next: "Assess the United States (FDA) market",
      due: [due],
      markets: ["US"],
    },
    signers: {
      MARKETS: {
        people: [
          { id: "u1", name: "Asha Quality" },
          { id: "u2", name: "Rahul Colleague" },
        ],
        you: true,
        second_person: false,
      },
    },
    service: null,
    related: [
      { key: "communications", label: "Communications", count: 0, lines: ["None recorded"] },
      { key: "assessments", label: "Market assessments", count: 1, lines: ["United States (FDA): not assessed yet"] },
      { key: "service", label: "Service work", count: 0, lines: ["None linked"] },
      { key: "investigations", label: "Investigation", count: 0, lines: ["Not opened"], items: [] },
      { key: "reports", label: "Authority reports", count: 0, lines: ["None started"] },
      { key: "decisions", label: "Decision records", count: 0, lines: ["Nothing signed yet"] },
    ],
  } as unknown as EventView;
}
