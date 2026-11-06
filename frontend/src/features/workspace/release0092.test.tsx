// 0.10.92 (development cycle 1, step 1): the bug and trust fixes the screens show, without a browser.
import fs from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { CaseSections } from "./sections/CaseSections";
import { ThingsToGive } from "./sections/ReportBody";
import type { ReportDetail } from "./authorityReports";
import caseSections from "./sections/CaseSections.tsx?raw";
import caseBrief from "./sections/CaseDecisionBrief.tsx?raw";
import { workColumns } from "./sections/ComplaintList";
import { TrendHeroes } from "./sections/TrendCheck";
import type { TrendBoard, TrendItem } from "./signalAi";
import { SAMPLE_SOURCE } from "./complaintList";
import { WhoSigns } from "./sections/ComplaintPage";
import { NeedsProduct } from "./sections/common";
import userGuide from "../help/userGuide.ts?raw";
import caseAuditSource from "./caseAudit.ts?raw";

const heroCss: string = fs.readFileSync(new URL("./heroPages.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "loading", data: null, reload: () => undefined }),
}));

const api = (work: Partial<WorkspaceApi["work"]>) =>
  ({
    session: { user_id: "u1", business_permissions: ["records.write"] },
    work: { products: [], investigations: [], investigationId: "", ...work },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

describe("1.3 (A3): accepting a brief shows the decision form at once", () => {
  it("tells the case page when the brief's status changes, and the decision form and header read it again", () => {
    // The brief panel calls onChanged after every review action and after a submit, besides its own reload.
    expect(caseBrief).toMatch(/onDone=\{\(\) => \{\s*brief\.reload\(\);\s*onChanged\?\.\(\);/);
    expect(caseBrief.match(/brief\.reload\(\);\s*onChanged\?\.\(\);/g)).toHaveLength(2);
    // The case page remounts the decision form and the header on it, and reads the case's status again.
    expect(caseSections).toContain("setBriefRound((round) => round + 1);");
    expect(caseSections).toMatch(/<CaseDecisionPanel\s+key=\{`\$\{id\}:\$\{briefRound\}`\}/);
    expect(caseSections).toMatch(/<CaseHeader\s+key=\{`\$\{id\}:\$\{briefRound\}`\}/);
    expect(caseSections).toMatch(/readiness\.reload\(\);\s*brief\.reload\(\);\s*onChanged\(\);/);
  });
});

describe("1.4 (A4): a direct link to an investigation opens it", () => {
  it("says the investigation is opening while its link resolves, never 'No investigation open'", () => {
    const html = render(
      <CaseSections onChanged={() => undefined} />,
      api({ caseLink: { id: "INV000001", state: "resolving" } }),
    );
    expect(html).toContain("Opening the investigation…");
    expect(html).toContain("Finding INV000001 and its product.");
    expect(html).not.toContain("No investigation open");
  });

  it("still says no investigation is open when none was asked for", () => {
    expect(render(<CaseSections onChanged={() => undefined} />, api({}))).toContain("No investigation open");
  });
});

describe("1.5 (A5): the eMDR's contact office is asked for before approval", () => {
  it("says what the eMDR needs, asks for the e-mail beside it, and links where the party is set", () => {
    const problem =
      "The eMDR file needs the contact office's e-mail (up to 50 characters): add it here, or to your US " +
      "responsible party in Settings › Products";
    const detail = {
      id: "r1",
      editable: true,
      complaint: { product_name: "PulseWatch 410" },
      form: { clauses: [] },
      mandatory: { total: 24, filled: 23, missing: ["G1"] },
      sections: [
        {
          code: "G",
          title: "G",
          fields: [
            {
              id: "G1",
              number: "G1",
              label: "Contact office",
              value: "Medisynth Devices; contact: Jane Doe",
              status: "FROM_RECORD",
              scope: "ORGANIZATION",
              once: true,
              once_key: "G1",
              problem,
              ask: "CONTACT_EMAIL",
            },
          ],
        },
      ],
    } as unknown as ReportDetail;
    const html = render(<ThingsToGive detail={detail} onChanged={() => undefined} canEdit />, api({}));
    expect(html).toContain("1 thing to give");
    expect(html).toContain(problem.replace(/'/g, "&#x27;"));
    expect(html).toContain("Set a responsible party in Settings › Products");
    expect(html).toContain('type="email"');
    expect(html).toContain('aria-label="G1 Contact office: e-mail"');
    expect(html).toContain("Save the e-mail for your organization");
    // The one-line box that cannot carry an e-mail is not offered for it.
    expect(html).not.toContain("Save for your organization");
  });
});

describe("1.7: the Complaints list's headings and the change behind a trend", () => {
  it("gives the country, owner and stage columns their headings, placed over their cells (A8)", () => {
    // The hero list stacks the last four columns in its third; their headings were display: none.
    expect(heroCss).not.toMatch(/thead th:nth-child\(n \+ 4\)\s*\{\s*display: none/);
    expect(heroCss).toMatch(
      /:is\(th:nth-child\(4\), td\[data-label="Incident country"\]\)\s*\{\s*grid-column: 3;\s*grid-row: 2;/,
    );
    expect(heroCss).toMatch(/:is\(th:nth-child\(5\), td\[data-label="Owner"\]\)\s*\{\s*grid-column: 4;\s*grid-row: 2;/);
    expect(heroCss).toMatch(
      /:is\(th:nth-child\(6\), td\[data-label="Stage"\]\)\s*\{\s*grid-column: 3 \/ span 2;\s*grid-row: 3;/,
    );
    // The six columns, in the order the positions above assume.
    expect(workColumns({}, () => undefined).map((column) => column.label)).toEqual([
      "Legal clock",
      "What happened",
      "Product, version, lot",
      "Incident country",
      "Owner",
      "Stage",
    ]);
  });

  it("names the supplier change recorded on the rising version, beside its lots (A10)", () => {
    const rising = {
      key: "g1",
      name: "OrbitCare 300 Infusion Pump (Sample) Rev B",
      result: "SIGNIFICANT",
      recent: 9,
      recent_days: 30,
      expected: 1,
      ratio: 9.3,
      history: 6,
      history_days: 180,
      baseline: "PREVIOUS_VERSION",
      p_value: 0.0001,
      lots: ["SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004"],
      lot_counts: { "SAMPLE-ORBIT-300-LOT-003": 5, "SAMPLE-ORBIT-300-LOT-004": 4 },
      open_signals: [],
      product: { id: "p1", business_id: null, identifier: "SAMPLE-ORBIT-300", name: "OrbitCare 300 (Sample)" },
      product_version: { id: "v1", business_id: null, version_identifier: "Rev B" },
      changes: [
        {
          id: "c1",
          identifier: "SAMPLE-CHG-014",
          change_type: "Supplier change",
          title: "OrbitCare 300 Rev B: pressure sensor sourced from NovaSense Components.",
          event_at: "2026-08-18T10:00:00Z",
        },
      ],
    } as unknown as TrendItem;
    const board = { items: [rising], recent_days: 30, history_days: 180, min_complaints: 3, summary: {} };
    const html = renderToStaticMarkup(
      <TrendHeroes board={board as unknown as TrendBoard} action={() => null} source={SAMPLE_SOURCE} />,
    );
    expect(html).toContain("Recorded change on this version:");
    expect(html).toContain(
      "SAMPLE-CHG-014 (supplier change): OrbitCare 300 Rev B: pressure sensor sourced from NovaSense",
    );
    expect(html.indexOf("SAMPLE-CHG-014")).toBeGreaterThan(html.indexOf("Lot 003"));
  });
});

describe("1.8 (A12): a trial has no administrator to ask", () => {
  const signers = { signers: { READY: { people: [], you: false, second_person: true } } } as never;

  it("tells a trial to invite a colleague, and a pilot that an administrator gives the role", () => {
    const trial = render(<WhoSigns view={signers} code="READY" />, api({}));
    expect(trial).toContain("nobody in your organization yet: invite a colleague in Team");
    expect(trial).not.toContain("administrator");
    const pilot = render(<WhoSigns view={signers} code="READY" />, { ...api({}), isTrial: false } as WorkspaceApi);
    expect(pilot).toContain("an administrator gives a colleague the role");
  });

  it("sends a trial with no products to its own import, never to an administrator", () => {
    const html = render(
      <NeedsProduct>{() => null}</NeedsProduct>,
      api({ state: "empty", view: null } as Partial<WorkspaceApi["work"]>),
    );
    expect(html).toContain("Import your data");
    expect(html).not.toContain("administrator");
  });

  it("says in the user guide who resets a lost authenticator in a trial", () => {
    expect(userGuide).toContain("In a free trial, the person who invited you resets it in Team");
    expect(caseAuditSource).toContain("or in a free trial to support@mdarix.in");
  });
});
