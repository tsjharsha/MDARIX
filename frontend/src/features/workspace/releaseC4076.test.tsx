import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { REPORTS, owesWorksheet, worksheetMarkets } from "./authorityReports";
import { ReportsSection } from "./sections/ReportsTab";
import { DecisionTreesSection, TREE_NAMES, type Trees } from "./sections/DecisionTrees";
import { taskDestination } from "./tasks";
import { MARKET_SHORT } from "./marketAssessment";
import { STARTER_LABEL } from "../shared/standards";

// 0.10.76, Release C part C4: the EU MIR, GB MIR and Health Canada forms (starters, for your consultant to confirm) on
// the new navigation, Canada's tree, and a link to one report opening that report.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = () =>
  ({
    session: { user_id: "u1", allowed_menu: ["home"], business_permissions: ["regulatory.review"] },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    reportTab: vi.fn(),
    shownTab: "",
    navigation: "new",
    isTrial: true,
    persona: "admin",
    personaLabel: "Admin",
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api()}>{node}</WorkspaceContext.Provider>);

describe("the new forms are the new navigation's", () => {
  it("adds EU / NI, Great Britain and Canada to the worksheet markets on the new navigation only", () => {
    expect(worksheetMarkets("classic")).toEqual(["US", "IN"]);
    expect(worksheetMarkets("new")).toEqual(["US", "IN", "EU_NI", "GB", "CA"]);
    const eu = [{ market: "EU_NI", state: "REPORTABLE", suggested: "REPORTABLE" }];
    expect(owesWorksheet(eu)).toBe(false);
    expect(owesWorksheet(eu, "new")).toBe(true);
    expect(MARKET_SHORT.CA).toBe("Canada");
    expect(TREE_NAMES.CA).toBe("Canada");
  });

  it("marks the starter forms on the Reports tab", () => {
    resources.data[REPORTS] = {
      items: [],
      forms: [
        { market: "US", title: "Form FDA 3500A worksheet (eMDR)", version: "Form FDA 3500A (09/2025)", starter: false },
        {
          market: "EU_NI",
          title: "EU Manufacturer Incident Report (MIR) worksheet",
          version: "MIR form 7.3.1 (SB-11154, 06-05-2026)",
          starter: true,
        },
      ],
      never_submits: "",
      starter_mark: "Starter text.",
      practice_label: null,
    };
    const html = render(<ReportsSection />);
    expect(html).toContain("EU Manufacturer Incident Report (MIR)</span>");
    // G-17: no chip per form; the forms card says the starter mark once.
    expect(html.split(STARTER_LABEL).length - 1).toBe(1);
    expect(html).toContain("In MDARIX today");
    expect(html).not.toContain("record where and when you reported");
  });
});

describe("Canada's tree and a market outside the reporting windows", () => {
  it("shows the Canada button, the report its outcome creates, and that it is not in the windows", () => {
    const trees: Trees = {
      markets: [
        {
          market: "CA",
          label: "Canada (Health Canada)",
          title: "Canada mandatory problem reporting (Medical Devices Regulations s. 59-61.1)",
          version: 1,
          status: "STARTER",
          status_label: "Starter",
          version_label: "MDARIX starter · version 1",
          enabled: false,
          tests: { passed: 6, total: 6, current: true },
          questions: [
            { id: "CA1", text: "Is the device sold in Canada?", clause: "SOR/98-282 s. 59(1)(a)", extra: false },
          ],
          form: { title: "Health Canada mandatory medical device problem report worksheet", starter: true },
        },
      ],
      complaints: [],
      complaint: null,
      paths: {},
      never_decides: "",
      starter_mark: "",
    };
    resources.data["/api/v1/decision-trees"] = trees;
    const html = render(<DecisionTreesSection />);
    // 0.10.83 (D2): the tab opens on answering; with no complaint on the watch it says so. Its editor (releaseD2083)
    // names the form and the windows.
    expect(html).toContain("No complaint waits for a decision");
  });
});

describe("a link to one report", () => {
  it("opens the report an approval task is about", () => {
    const task = {
      task_type: "APPROVAL",
      investigation: null,
      source: { type: "ReportSnapshot", id: "s1", business_id: null, label: "" },
      details: { complaint_id: "c1", obligation_id: "r1" },
    };
    expect(taskDestination(task as never)).toEqual({ section: "Complaints", tab: "Reports?report=r1" });
    // A task from before 0.10.76 (no report named) still opens the complaint's reports.
    expect(taskDestination({ ...task, details: { complaint_id: "c1" } } as never).tab).toBe("Reports?complaint=c1");
  });
});
