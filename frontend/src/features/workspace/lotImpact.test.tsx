import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import {
  countriesText,
  exclusionBody,
  exclusionProblem,
  factorKey,
  factorOf,
  groupLots,
  lotImpactPath,
  optionText,
  type FactorOption,
  type ImpactLot,
  type LotImpactView,
} from "./lotImpact";
import { runChecks, type ImportRun } from "./sections/ImportReports";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));

vi.mock("../customer-admin/shared", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../customer-admin/shared")>();
  return {
    ...actual,
    useResource: (path: string | null) => ({
      data: path ? (resources.data[path] ?? null) : null,
      error: null,
      state: "ready",
      loading: false,
      reload: vi.fn(),
    }),
  };
});

const { LotImpactPanel } = await import("./sections/LotImpact");
const { CaseHeader } = await import("./sections/CaseHeader");

const CASE = "case-1";
const BASE = `/api/v1/investigations/${CASE}/lot-impact`;

const lot = (over: Partial<ImpactLot>): ImpactLot => ({
  id: "l3",
  business_id: "LOT-0003",
  lot_identifier: "SAMPLE-ORBIT-300-LOT-003",
  product: "OrbitCare 300 Infusion Pump (Sample)",
  version: "Rev B",
  made_on: "2026-08-18",
  released: 150,
  complaints: 9,
  per_1000: 60,
  distribution_imported: true,
  shipped: 150,
  in_stock: 0,
  over_shipped: false,
  by_country: [
    { country: "US", units: 100 },
    { country: "IN", units: 50 },
  ],
  shipments: [
    {
      consignee: "Cedar Plains Medical Center (Sample)",
      consignee_type: "Hospital",
      consignee_reference: null,
      country: "US",
      units: 100,
      ship_date: "2026-08-23",
    },
  ],
  evidence: ["Genealogy: Pressure Sensor (Sample) (SAMPLE-ORBIT-300-C1) lot NS-SL-2417 (Sample)"],
  excluded: false,
  exclusion_reason: null,
  ...over,
});

const option: FactorOption = {
  kind: "COMPONENT_LOT",
  kind_label: "Component lot",
  id: "c1",
  lot: "NS-SL-2417 (Sample)",
  label: "Pressure Sensor (Sample) lot NS-SL-2417 (Sample)",
  lots: 5,
  case_lots: 2,
};

const lots = [
  lot({}),
  lot({
    id: "l8",
    lot_identifier: "SAMPLE-ORBIT-300-LOT-008",
    complaints: 0,
    per_1000: 0,
    released: 30,
    distribution_imported: false,
    shipped: null,
    in_stock: null,
    by_country: [],
    shipments: [],
  }),
];

const view = (over: Partial<LotImpactView> = {}): LotImpactView => ({
  investigation: { id: CASE, business_id: "INV-0001", closed: false },
  never_decides: "MDARIX lists the lots that share the factor you chose. It recommends no recall.",
  not_imported: "Distribution not imported",
  practice_label: "Practice record: made in a free trial.",
  reason_min: 10,
  options: [option],
  suggestion: { ...option, why: "2 of the case's 2 lots share it" },
  case_lots: 2,
  genealogy: true,
  saved: null,
  source: "suggested",
  list: {
    factor: { kind: "COMPONENT_LOT", id: "c1", lot: "NS-SL-2417 (Sample)", label: option.label },
    lots,
    totals: {
      lots: 2,
      with_complaints: 1,
      without_complaints: 1,
      excluded: 0,
      complaints: 9,
      released: 180,
      released_unknown: 0,
      shipped: 150,
      in_stock: 0,
      not_imported: 1,
      by_country: [
        { country: "US", units: 100 },
        { country: "IN", units: 50 },
      ],
    },
    fingerprint: "f".repeat(64),
    truncated: false,
  },
  signed: null,
  ...over,
});

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { user_id: "me", allowed_menu: ["home"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [] },
    isTrial: true,
  } as unknown as WorkspaceApi;
}

const render = (permissions: string[]) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={workspace(permissions)}>
      <LotImpactPanel investigationId={CASE} caseLabel="INV-0001" />
    </WorkspaceContext.Provider>,
  );

describe("the lot impact helpers", () => {
  it("previews another factor through the query and reads the picker's keys back", () => {
    expect(lotImpactPath(CASE)).toBe(BASE);
    expect(lotImpactPath(CASE, { kind: "COMPONENT_LOT", id: "c1", lot: "NS-SL-2417 (Sample)" })).toBe(
      `${BASE}?kind=COMPONENT_LOT&ref=c1&lot=NS-SL-2417+%28Sample%29`,
    );
    expect(factorOf(factorKey(option), [option])).toEqual({ kind: "COMPONENT_LOT", id: "c1", lot: option.lot });
    expect(factorOf("nothing", [option])).toBeNull();
    expect(optionText(option)).toBe("Pressure Sensor (Sample) lot NS-SL-2417 (Sample): 5 lots, 2 of this case's");
  });

  it("groups the lots, writes countries and asks a reason for each lot left out", () => {
    const groups = groupLots([...lots, lot({ id: "l5", excluded: true })]);
    expect(groups.withComplaints.map((item) => item.id)).toEqual(["l3"]);
    expect(groups.withoutComplaints.map((item) => item.id)).toEqual(["l8"]);
    expect(groups.excluded.map((item) => item.id)).toEqual(["l5"]);
    expect(countriesText(lots[0].by_country)).toBe("US 100 · IN 50");
    expect(countriesText([], "none")).toBe("none");
    expect(exclusionProblem({ l8: "short" }, lots, 10)).toBe(
      "Say in at least 10 characters why SAMPLE-ORBIT-300-LOT-008 is left out.",
    );
    expect(exclusionProblem({ l8: "Quarantined in our warehouse" }, lots, 10)).toBe("");
    expect(exclusionBody({ l8: " Quarantined in our warehouse " })).toEqual([
      { lot_id: "l8", reason: "Quarantined in our warehouse" },
    ]);
  });

  it("flags a lot that shipped more than it released in the data-quality report", () => {
    const run = {
      masked_values: 0,
      report: {
        rows_read: 3,
        rows_accepted: 2,
        rows_quarantined: 1,
        rows_changed: 0,
        rows_new: 2,
        balanced: true,
        flags: [{ lot_id: "L1", released: 150, shipped: 160, message: "Lot L1: 160 units shipped, 150 released." }],
      },
    } as Pick<ImportRun, "report" | "masked_values">;
    const check = runChecks(run).find((item) => item.label === "Units shipped within units released");
    expect(check?.ok).toBe(false);
    expect(check?.detail).toContain("1 lot shipped more units than released: Lot L1: 160 units shipped");
    expect(runChecks({ ...run, report: { ...run.report, flags: undefined } }).map((item) => item.label)).not.toContain(
      "Units shipped within units released",
    );
  });
});

describe("the case's Lot impact", () => {
  it("is one click from the case summary in a trial, and absent where it is not offered", () => {
    const header = (onLotImpact?: () => void) =>
      renderToStaticMarkup(
        <WorkspaceContext.Provider value={workspace(["investigation.work"])}>
          <CaseHeader
            investigationId={CASE}
            row={{ id: CASE }}
            onStep={vi.fn()}
            onChanged={vi.fn()}
            onLotImpact={onLotImpact}
          />
        </WorkspaceContext.Provider>,
      );
    expect(header(vi.fn())).toContain("Lot impact: which other lots share the suspect part");
    expect(header()).not.toContain("Lot impact");
  });

  it("shows the suggestion, the lots with and without complaints and 'distribution not imported'", () => {
    resources.data = { [BASE]: view() };
    const html = render(["investigation.work", "decision.sign", "data.export"]);
    // A section of the Scope step, with its own heading and anchor (no tab of its own).
    expect(html).toContain('id="lot-impact"');
    expect(html).toContain("Lot impact: what else is out there for INV-0001");
    expect(html).toContain("Suggested from the case&#x27;s lots");
    expect(html).toContain("It recommends no recall");
    expect(html).toContain("Lots with complaints · 1");
    expect(html).toContain("Lots without complaints yet · 1");
    expect(html).toContain("Distribution not imported");
    expect(html).toContain("60 per 1,000 units");
    expect(html).toContain("Keep this list with the case");
    // Nothing is kept yet: no signature and no export.
    expect(html).not.toContain("Sign the list");
    expect(html).not.toContain("PDF");
  });

  it("offers the signature on the kept list and says what changed since it was signed", () => {
    const kept = view({
      source: "saved",
      saved: { factor: { ...option }, scope_version: 3, saved_at: "2026-11-01T10:00:00Z", saved_by_name: "Asha" },
    });
    resources.data = { [BASE]: kept };
    expect(render(["investigation.work", "decision.sign", "data.export"])).toContain("Sign the list");
    expect(render(["investigation.work"])).toContain("A colleague who signs decisions signs the list");
    resources.data = {
      [BASE]: {
        ...kept,
        signed: {
          list: kept.list!,
          signature: {
            signer_name: "Asha",
            signer_role: "Leader",
            signed_at: "2026-11-01T10:05:00+00:00",
            meaning: "I confirm this list. MDARIX recommends no field action.",
            record_id: "r1",
            record_business_id: "SIG-0001",
            content_fingerprint: "f".repeat(64),
            scope_version: 4,
          },
          changed: true,
          changes: ["SAMPLE-ORBIT-300-LOT-008: distribution now imported (12 units shipped)"],
        },
      },
    };
    const html = render(["investigation.work", "decision.sign", "data.export"]);
    expect(html).toContain("Changed since signed");
    expect(html).toContain("distribution now imported (12 units shipped)");
    expect(html).toContain("Sign the list again");
    expect(html).toContain("PDF");
  });
});
