import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { TraceBody, TraceLink, type ValueTrace } from "./sections/TraceValue";

// B6a G20 "Trace this value" (B6-39, B6-40): the panel's three parts, in order; the link only while the switch is on.
const TRACE: ValueTrace = {
  field: { id: "B3", number: "B3", label: "Date of event", value: "2026-10-02", status_label: "From the record" },
  origin: { type: "Complaint", ref: "SAMPLE-RV-06", label: "The complaint's event date", id: "c-1" },
  imports: [
    {
      import_ref: "r-1",
      line: 7,
      mapping_version: "complaints-template:abc123def456",
      file_name: "orbit-complaints.csv",
      imported_by: "Asha Rao",
      imported_at: "2026-10-03T09:00:00+00:00",
    },
  ],
  field_changes: [],
  record_events: [
    {
      action: "COMPLAINT_REPORTING_FACTS_SET",
      by: "Asha Rao",
      at: "2026-10-04T09:00:00+00:00",
      reason: "The call log shows the first contact",
      values: { before: { awareness_date: "2026-10-03" }, after: { awareness_date: "2026-10-02" } },
    },
  ],
  entered_on_report: [],
  snapshot: {
    version: 1,
    state: "APPROVED",
    requested_by: "Asha Rao",
    requested_at: "2026-10-05T09:00:00+00:00",
    approved_by: "Rahul Iyer",
    approved_at: "2026-10-05T10:00:00+00:00",
    sha256: "a".repeat(64),
    frozen_value: "2026-10-02",
  },
};

const withTrace = (trace: boolean | undefined, node: React.ReactNode) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={{ session: { b6: { trace } } } as unknown as WorkspaceApi}>
      {node}
    </WorkspaceContext.Provider>,
  );

describe("Trace this value", () => {
  it("shows the record and its import row, who changed it and why, then the snapshot it is frozen in", () => {
    const html = renderToStaticMarkup(<TraceBody data={TRACE} />);
    const order = ["1. Where it comes from", "2. Who entered or changed it", "3. Frozen in"].map((text) =>
      html.indexOf(text),
    );
    expect(order.every((at, index) => at >= 0 && (index === 0 || at > order[index - 1]))).toBe(true);
    expect(html).toContain("The complaint&#x27;s event date: SAMPLE-RV-06");
    expect(html).toContain("orbit-complaints.csv</strong>, row 7");
    expect(html).toContain("Why: The call log shows the first contact");
    expect(html).toContain("awareness date: 2026-10-03 → awareness date: 2026-10-02");
    expect(html).toContain("approved by Rahul Iyer");
    expect(html).toContain(`SHA-256 ${"a".repeat(64)}`);
    // Read only: nothing to press inside the panel.
    expect(html).not.toContain("<button");
  });

  it("says when a value was typed, never imported, and not frozen yet", () => {
    const html = renderToStaticMarkup(<TraceBody data={{ ...TRACE, origin: null, imports: [], snapshot: null }} />);
    expect(html).toContain("Entered on this report by a person.");
    expect(html).toContain("Not frozen yet: sending it for approval freezes it.");
  });

  it("shows the link only while the server has the switch on", () => {
    const link = <TraceLink reportId="r" fieldId="B3" title="B3 Date of event" />;
    expect(withTrace(true, link)).toContain('aria-label="Trace B3 Date of event"');
    expect(withTrace(false, link)).toBe("");
    expect(withTrace(undefined, link)).toBe("");
  });
});
