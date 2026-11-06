// 0.10.92 (development cycle 1, step 1): the bug and trust fixes the screens show, without a browser.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { CaseSections } from "./sections/CaseSections";
import { ThingsToGive } from "./sections/ReportBody";
import type { ReportDetail } from "./authorityReports";
import caseSections from "./sections/CaseSections.tsx?raw";
import caseBrief from "./sections/CaseDecisionBrief.tsx?raw";

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
  it("says what the eMDR needs and where to set it, instead of a one-line box that cannot give an e-mail", () => {
    const problem =
      "The eMDR file needs the contact office's e-mail (up to 50 characters): add it to your US responsible party in " +
      "Settings › Products";
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
            },
          ],
        },
      ],
    } as unknown as ReportDetail;
    const html = render(<ThingsToGive detail={detail} onChanged={() => undefined} canEdit />, api({}));
    expect(html).toContain("1 thing to give");
    expect(html).toContain(problem.replace(/'/g, "&#x27;"));
    expect(html).toContain("Set a responsible party in Settings › Products");
    expect(html).not.toContain("Save for your organization");
  });
});
