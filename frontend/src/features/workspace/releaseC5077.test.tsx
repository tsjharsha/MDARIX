import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { fieldTone, isMissing, type ReportDetail, type WorksheetField } from "./authorityReports";
import { FieldRow, codeMeta } from "./sections/Reports";
import { pickPath, CodePicker } from "./sections/CodePicker";
import { euIdentityText, registrationText } from "./sections/ImportReports";
import { lotsText, risingSentence } from "./signalAi";
import { SETTINGS_TABS, SETTING_PERMISSIONS } from "./sections/Settings";

// 0.10.77, Release C part C5: codes. A mapped code is a suggestion the regulatory manager confirms or changes in the
// code picker; Settings › Products holds the identity fields; the trend sentence counts each lot.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (permissions = ["regulatory.review"]) =>
  ({
    session: { user_id: "u1", allowed_menu: ["home"], business_permissions: permissions },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    reportTab: vi.fn(),
    shownTab: "",
    navigation: "new",
    isTrial: true,
    persona: "regulatory",
    personaLabel: "Regulatory Leader",
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, permissions?: string[]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api(permissions)}>{node}</WorkspaceContext.Provider>);

const SUGGESTED: WorksheetField = {
  id: "H6_PROBLEM",
  number: "H6",
  label: "Medical device problem code",
  value: null,
  status: "SUGGESTED",
  status_label: "Suggested from your approved mapping",
  source: { type: "ImdrfMapping", ref: "SPO2_READING_HIGH -> IMDRF Annex A, release 2026", label: "x", id: null },
  personal: null,
  missing_class: "MUST_HAVE",
  editable: true,
  note: null,
  by: null,
  at: null,
  code_annex: "A",
  suggestion: "A090807 High Readings (FDA 2459)",
  suggested: null,
};
const detail = { id: "r1", codes_confirmed: true } as unknown as ReportDetail;

describe("a suggested code waits for the regulatory manager", () => {
  it("shows the suggestion with Confirm and Change, and counts it as missing", () => {
    const html = render(<FieldRow detail={detail} item={SUGGESTED} onChanged={() => undefined} canEdit />);
    expect(html).toContain("Suggested: </span>A090807 High Readings (FDA 2459)");
    expect(html).toContain("it is not filed until you do");
    expect(html).toContain(">Confirm</button>");
    expect(html).toContain(">Change</button>");
    expect(html).not.toContain("Enter a value");
    expect(isMissing(SUGGESTED)).toBe(true);
    expect(isMissing({ ...SUGGESTED, missing_class: "FOLLOW_UP" })).toBe(false);
    expect(fieldTone("SUGGESTED")).toBe("warning");
    expect(fieldTone("CHANGED")).toBe("good");
  });

  it("says who confirmed or changed it, and what was suggested", () => {
    const at = "2026-11-03T10:00:00Z";
    expect(codeMeta({ status: "CONFIRMED", by: "Rahul Colleague", at, suggested: "x" })).toMatch(
      /^Confirmed by Rahul Colleague /,
    );
    expect(codeMeta({ status: "CHANGED", by: "Asha", at, suggested: "A090807 High Readings" })).toMatch(
      /^Changed by Asha .*; suggested A090807 High Readings$/,
    );
    // Someone who may not work on reports reads it: no buttons.
    const html = render(<FieldRow detail={detail} item={SUGGESTED} onChanged={() => undefined} canEdit={false} />);
    expect(html).not.toContain(">Confirm</button>");
    // The classic navigation keeps its field row (no suggestion there).
    const classic = { ...detail, codes_confirmed: false } as ReportDetail;
    const row = { ...SUGGESTED, status: "FROM_RECORD", value: "A0908 x", suggestion: null };
    expect(render(<FieldRow detail={classic} item={row} onChanged={() => undefined} canEdit />)).toContain(
      "Confirm against the source",
    );
  });

  it("the picker searches by word, browses the annex and shows each definition and FDA code", () => {
    expect(pickPath("A", "high readings", "A09")).toBe(
      "/api/v1/regulatory-reference/imdrf/codes?pick=1&annex=A&q=high+readings",
    );
    expect(pickPath("A", "", "A0908")).toBe("/api/v1/regulatory-reference/imdrf/codes?pick=1&annex=A&parent=A0908");
    resources.data[pickPath("A", "", null)] = {
      release: "2026",
      fda_version: "26.08e",
      codes: [
        {
          code: "A09",
          term: "Output Problem",
          definition: "A heading.",
          status: null,
          selectable: true,
          children: 14,
          fda: { code: "1234", term: "Output Problem" },
        },
        {
          code: "E01",
          term: "Nervous System",
          definition: null,
          status: "Not selectable",
          selectable: false,
          children: 3,
          fda: null,
        },
      ],
    };
    const html = render(<CodePicker annex="A" label="H6" onChoose={() => undefined} onCancel={() => undefined} />);
    expect(html).toContain("Annex A · Medical device problem");
    expect(html).toContain("IMDRF release 2026 · FDA codes 26.08e");
    expect(html).toContain("Search by word");
    expect(html).toContain("A heading.");
    expect(html).toContain("FDA 1234");
    expect(html).toContain("14 under it");
    expect(html).toContain("Heading: choose a code under it");
  });
});

describe("product identity and the trend's lots", () => {
  it("Settings has Products, changed by people who may change records", () => {
    expect(SETTINGS_TABS).toContain("Products");
    expect(SETTING_PERMISSIONS.Products).toEqual(["records.write"]);
  });

  it("reads each registration and the EU identity in plain words", () => {
    expect(
      registrationText({
        id: "1",
        market: "US",
        registration_type: "510K",
        registration_number: "K000001",
        product_code: "DQA",
        product_code_name: "Oximeter",
        body_name: null,
        body_number: null,
        risk_class: "II",
      }),
    ).toBe("US · 510(k) K000001 · FDA product code DQA (Oximeter) · Class II");
    expect(euIdentityText({ basic_udi_di: "B-1", emdn_code: "Z12", emdn_term: "Instruments" })).toBe(
      "Basic UDI-DI B-1 · EMDN Z12 Instruments",
    );
    expect(euIdentityText({ basic_udi_di: null, emdn_code: null })).toBe("");
  });

  it("counts each lot in the trend sentence (addendum: 003 (4), 004 (4), 005 (1))", () => {
    const lots = ["SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004", "SAMPLE-ORBIT-300-LOT-005"];
    const counts = { [lots[0]]: 4, [lots[1]]: 4, [lots[2]]: 1 };
    expect(lotsText(lots, counts)).toBe("003 (4), 004 (4), 005 (1)");
    expect(lotsText(lots)).toBe("003, 004 and 005");
    expect(
      risingSentence({ name: "OrbitCare 300 Rev B", recent: 9, expected: 1, ratio: 9.3, lots, lot_counts: counts }),
    ).toBe("OrbitCare 300 Rev B: 9 complaints against 1.0 expected (9.3×), lots 003 (4), 004 (4), 005 (1)");
  });
});
