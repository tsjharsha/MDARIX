// B8 run 6 (tr30, B9-D9 / B8-D9): patient and reporter details at Send for approval, and the Settings switch.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { isSimilarTable, type ReportDetail } from "./authorityReports";
import type { ReportabilitySettings } from "./reportability";
import { PersonalAtSend, personalBody } from "./sections/PersonalAtSend";
import { PersonalDataBody } from "./sections/ReportingWindows";
import { FieldRow } from "./sections/Reports";

const api = {
  session: { user_id: "u1", business_permissions: ["regulatory.review"] },
  work: { products: [] },
  open: vi.fn(),
  notify: vi.fn(),
  navigation: "new",
} as unknown as WorkspaceApi;
const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api}>{node}</WorkspaceContext.Provider>);

const report = (on: boolean) =>
  ({
    id: "r1",
    personal_data: on,
    sections: [
      {
        code: "3_3",
        title: "3.3 Patient",
        fields: [
          { id: "3_3A_E", number: "3.3a", label: "Codes", personal: null },
          { id: "3_3C", number: "3.3c", label: "Gender", personal: "PATIENT", options: ["Female", "Male"] },
          { id: "3_4B", number: "3.4b", label: "Facility", personal: "REPORTER" },
        ],
      },
    ],
  }) as unknown as ReportDetail;

const settings = (extra: Partial<ReportabilitySettings>) =>
  ({
    windows: [],
    lookback_days: 365,
    configured: false,
    templates: [],
    version: 1,
    ...extra,
  }) as ReportabilitySettings;

describe("B8: personal data at the report step", () => {
  it("shows the patient and reporter boxes only while the organization allows them", () => {
    expect(render(<PersonalAtSend detail={report(false)} values={{}} onChange={() => {}} />)).toBe("");
    const html = render(<PersonalAtSend detail={report(true)} values={{ "3_4B": "Ward" }} onChange={() => {}} />);
    expect(html).toContain("3.3c Gender");
    expect(html).toContain("3.4b Facility");
    expect(html).not.toContain("3.3a Codes");
    expect(html).toContain("never");
  });

  it("sends only the boxes typed, and no body when none is", () => {
    expect(personalBody({})).toBeUndefined();
    expect(personalBody({ "3_3C": " ", "3_4B": "Ward" })).toEqual({ personal: { "3_4B": "Ward" } });
  });

  it("lets only the Customer Admin switch it, with a reason", () => {
    const reader = render(<PersonalDataBody settings={settings({ report_personal_data: false })} onSaved={() => {}} />);
    expect(reader).toContain("Off:");
    expect(reader).not.toContain("Switch on");
    const admin = render(
      <PersonalDataBody
        settings={settings({ report_personal_data: true, can_set_personal_data: true })}
        onSaved={() => {}}
      />,
    );
    expect(admin).toContain("On:");
    expect(admin).toContain("Switch off");
    expect(admin).toContain("at least 10 characters");
  });
});

describe("B8: GB rows to confirm with your consultant", () => {
  it("shows the non-blocking warning beside an empty field", () => {
    const item = {
      id: "2_1B",
      number: "2.1b",
      label: "UDI production identifier",
      value: null,
      status: "MAY_BE_UNKNOWN",
      status_label: "May be unknown",
      source: null,
      personal: null,
      missing_class: "MAY_BE_UNKNOWN",
      note: null,
      by: null,
      at: null,
      warning:
        "Optional on MHRA's GB form; the EU help text asks for it in this report type. To confirm with your consultant.",
    };
    const html = render(<FieldRow detail={report(false)} item={item} onChanged={() => {}} canEdit />);
    expect(html).toContain("To confirm with your consultant.");
    expect(html).toContain('role="note"');
  });
});

describe("B8 review: the approval page's 4.3.3c", () => {
  it("draws the grid only for the table, never for text typed before it", () => {
    expect(isSimilarTable(JSON.stringify([{}, {}, {}, {}]))).toBe(true);
    expect(isSimilarTable("Three similar incidents in 2025")).toBe(false);
    expect(isSimilarTable(null)).toBe(false);
  });
});
