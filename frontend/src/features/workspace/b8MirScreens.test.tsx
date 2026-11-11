// B8 step 11: the EU MIR screens without a browser: the chain card, the types a position allows, the 4.3.3c table,
// and the MIR XML beside the PDF only after approval.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { fieldOptions, similarRows, type ReportDetail, type WorksheetField } from "./authorityReports";
import { FollowUps } from "./sections/FollowUps";
import { MirFiles, MirNeeds } from "./sections/MirFiles";
import { SimilarTableRow } from "./sections/SimilarTable";

const api = {
  session: { user_id: "u1", business_permissions: ["regulatory.review", "data.export"] },
  work: { products: [] },
  open: vi.fn(),
  notify: vi.fn(),
  navigation: "new",
} as unknown as WorkspaceApi;
const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api}>{node}</WorkspaceContext.Provider>);

const LATER = ["Follow up", "Final (Reportable incident)", "Final (Non-reportable incident)"];
const ALL = ["Initial", "Follow up", "Combined initial and final", ...LATER.slice(1)];
const eu = (extra: Partial<ReportDetail>): ReportDetail =>
  ({
    id: "r1",
    kind: "INITIAL",
    state: "ACCEPTED",
    state_label: "Accepted",
    stage: "SUBMITTED",
    form: { code: "EU_MIR" },
    parent_id: null,
    request: null,
    india_chain: null,
    canada_chain: null,
    mir: null,
    ...extra,
  }) as unknown as ReportDetail;
const table = [0, 1, 2, 3].map((n) => ({
  start: `${2026 - n}-01-01`,
  end: `${2026 - n}-12-31`,
  country_incidents: 1,
  country_devices: 400,
  eea_incidents: 2,
  eea_devices: 2500,
  world_incidents: 3,
  world_devices: 9000 + n,
}));

describe("B8: the EU MIR screens", () => {
  it("shows the chain in order with each state", () => {
    const html = render(
      <FollowUps
        detail={eu({
          mir_chain: {
            type: "Initial",
            types: ["Initial", "Combined initial and final"],
            items: [
              { id: "f1", type: "Follow up", state: "ACCEPTED", due_on: "2026-12-01" },
              { id: "f2", type: "Final (Reportable incident)", state: "DRAFT", due_on: "2027-01-15" },
            ],
            ended: false,
            can_create: false,
          },
        })}
        canWrite
        onChanged={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    const order = ["Initial report", "Follow up report", "Final (Reportable incident) report"].map((text) =>
      html.indexOf(text),
    );
    expect(order.every((at, index) => at >= 0 && (index === 0 || at > order[index - 1]))).toBe(true);
    expect(html).toContain("Accepted");
    expect(html).toContain("accepted");
    expect(html).toContain("draft");
    expect(html).toContain("The final (reportable incident) report is open");
  });

  it("offers only the types this position allows", () => {
    const typeField = { id: "1_2E", options: ALL };
    expect(fieldOptions(eu({ mir_chain: { type: "Follow up", types: LATER } }), typeField)).toEqual(LATER);
    const first = fieldOptions(
      eu({ mir_chain: { type: "Initial", types: ["Initial", "Combined initial and final"] } }),
      typeField,
    );
    expect(first).toEqual(["Initial", "Combined initial and final"]);
    expect(fieldOptions(eu({ mir_chain: null }), typeField)).toEqual(ALL); // switch off: the form's list, as before
    expect(
      fieldOptions(eu({ mir_chain: { type: "Initial", types: [] } }), { id: "3_2C", options: ["Unknown"] }),
    ).toEqual(["Unknown"]);
    // The chain card creates only later types: never a second Initial or a Combined.
    const html = render(
      <FollowUps
        detail={eu({ mir_chain: { type: "Initial", types: ["Initial"], items: [], ended: false, can_create: true } })}
        canWrite
        onChanged={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    for (const type of LATER) expect(html).toContain(type);
    expect(html).not.toContain("Combined initial and final");
    expect(html).not.toContain("Next report on");
  });

  it("offers a later report as a Final (Non-reportable incident) after a not-reportable re-sign", () => {
    const html = render(
      <FollowUps
        detail={eu({
          kind: "RESPONSE",
          state: "DRAFT",
          parent_id: "r0",
          mir_chain: {
            type: "Follow up",
            types: LATER,
            due_on: "2026-12-01",
            due_note: "Your date (1.2f): no fixed legal period",
            offer_final_non: { type: "Final (Non-reportable incident)", "4_2B": "Alarm worked as designed." },
          },
        })}
        canWrite
        onChanged={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(html).toContain("Start the Final (Non-reportable incident)");
    expect(html).toContain("Your date (1.2f): no fixed legal period");
    expect(html).toContain("This report is not cancelled");
  });

  it("no XML before approval: what the file still needs is listed", () => {
    const draft = { stage: "CREATED", mir: { snapshot: null, sha256: null, missing: ["1.2f (1_2F)"], errors: [] } };
    expect(render(<MirFiles detail={draft as unknown as ReportDetail} onXml={vi.fn()} />)).toBe("");
    expect(render(<MirNeeds detail={draft as unknown as ReportDetail} />)).toContain("1.2f (1_2F)");
    const before = { stage: "APPROVED", mir: { snapshot: null, sha256: null, missing: [], errors: [] } };
    expect(render(<MirFiles detail={before as unknown as ReportDetail} onXml={vi.fn()} />)).toBe(""); // approved before B8
  });

  it("both files ready after approval", () => {
    const approved = { stage: "APPROVED", mir: { snapshot: "s1", sha256: "ab".repeat(32), missing: [], errors: [] } };
    const html = render(<MirFiles detail={approved as unknown as ReportDetail} onXml={vi.fn()} />);
    expect(html).toContain("Download XML (MIR 7.3.1)");
    expect(html).toContain("Import the XML into the official MIR PDF if your authority asks for it");
    expect(html).toContain("MDARIX never submits");
    expect(render(<MirNeeds detail={approved as unknown as ReportDetail} />)).toBe("");
  });

  it("GB report shows MORE as its only route", () => {
    const mir = { snapshot: "s1", sha256: "ab".repeat(32), missing: [], errors: [] };
    const more = [{ code: "MHRA_MORE", label: "MHRA's MORE portal" }];
    const gb = { stage: "APPROVED", form: { code: "GB_MIR" }, routes: more, mir };
    const html = render(<MirFiles detail={gb as unknown as ReportDetail} onXml={vi.fn()} />);
    expect(html).toContain("Download XML (GB MIR 7.2.1)");
    expect(html).toContain("upload the XML in MHRA&#x27;s MORE, the only route MHRA takes");
    expect(html).toContain("The PDF is your record copy");
    expect(html).not.toContain("national competent authority");
    const draft = { ...gb, stage: "CREATED", mir: { ...mir, snapshot: null, missing: ["4.2f (4_2F)"] } };
    expect(render(<MirNeeds detail={draft as unknown as ReportDetail} />)).toContain("MHRA&#x27;s GB schema");
  });

  it("a Northern Ireland incident uploads the EU file in MORE, version to confirm", () => {
    const mir = { snapshot: "s1", sha256: "ab".repeat(32), missing: [], errors: [] };
    const ni = { stage: "APPROVED", form: { code: "EU_MIR" }, routes: [{ code: "MHRA_MORE_EU" }], mir };
    const html = render(<MirFiles detail={ni as unknown as ReportDetail} onXml={vi.fn()} />);
    expect(html).toContain("Download XML (MIR 7.3.1)");
    expect(html).toContain("to confirm with MHRA before your first upload");
  });

  it("enters 4.3.3c as a table of periods and regions, every number a person's", () => {
    const item = {
      id: "4_3_3C",
      number: "4.3.3c",
      label: "Number of similar serious incidents",
      value: JSON.stringify(table),
      status: "ENTERED",
      status_label: "Entered",
      kind: "TABLE",
      editable: true,
    } as unknown as WorksheetField;
    const html = render(<SimilarTableRow detail={eu({})} item={item} onChanged={vi.fn()} canEdit />);
    for (const period of ["N", "N-1", "N-2", "N-3"]) expect(html).toContain(`<th scope="row">${period}</th>`);
    expect(html).toContain("Devices on the market: EEA + CH + TR");
    expect(html).toContain("9003");
    expect(html).toContain("Change the table");
    expect(html).toContain("MDARIX holds no distribution data");
    const empty = render(
      <SimilarTableRow detail={eu({})} item={{ ...item, value: null }} onChanged={vi.fn()} canEdit />,
    );
    expect(empty).toContain("Enter the table");
    expect(similarRows("not a table")).toHaveLength(4);
  });
});
