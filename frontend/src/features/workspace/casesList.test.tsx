import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { CaseHeaderView, CasesList } from "./sections/CasesList";
import { casesPath, type CaseHeader, type CasePage } from "./intake";

// 0.10.93 (B2 step 5): the Cases list pages and filters on the server (A5); each row and the Case check show the
// header (A3): owner, next action, due, why, missing information and escalation state.

const resources = vi.hoisted(() => ({ paths: [] as string[], data: null as unknown }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string) => {
    resources.paths.push(path);
    return { state: "ready", data: resources.data, reload: () => undefined };
  },
}));

const HEADER: CaseHeader = {
  owner: "Priya",
  next_action: "Answer and sign the Case check",
  due_at: "2026-11-10T18:30:00Z",
  overdue: true,
  reason: "A Case is checked the same working day",
  missing: [{ code: "IDENTIFIER_UNCONFIRMED:lot", label: "Lot: unconfirmed" }],
  escalation: { state: "NONE", label: "Not escalated", complaint_id: null },
};
const PAGE: CasePage = {
  items: [
    {
      id: "e1",
      reference: "SAMPLE-CASE-11",
      kind: "CONTACT",
      sample: true,
      received_at: "2026-11-09T09:00:00Z",
      words: "The pump alarmed twice",
      product_name: "OrbitCare 200",
      lot: "L-77",
      not_in_master: ["lot"],
      status: "OPEN",
      status_label: "To check",
      classification_label: null,
      suggestion_label: null,
      issue_category_label: "Malfunction",
      flagged: false,
      complaint_ref: null,
      header: HEADER,
    },
  ],
  total: 60,
  page: 1,
  size: 25,
  view: "to_check",
  views: [
    { code: "to_check", label: "To check" },
    { code: "mine", label: "My cases" },
  ],
  counts: { OPEN: 3, PENDING: 1, IN_REVIEW: 0, WAITING_INTERNAL: 0 },
  people: [{ id: "u1", name: "Priya" }],
};

const render = (node: React.ReactNode) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={{ session: { business_permissions: ["case.log"] } } as unknown as WorkspaceApi}>
      {node}
    </WorkspaceContext.Provider>,
  );

describe("the Cases list (A5) and the Case header (A3)", () => {
  it("asks the server for one page of one view and shows each row's next action", () => {
    resources.data = PAGE;
    const html = render(<CasesList onOpen={vi.fn()} />);
    expect(resources.paths[resources.paths.length - 1]).toContain(casesPath("to_check", "", 1));
    expect(html).toContain("SAMPLE-CASE-11");
    expect(html).toContain("Not in master data");
    expect(html).toContain("Answer and sign the Case check");
    expect(html).toContain("overdue since");
    expect(html).toContain("1 missing");
    expect(html).toContain("Open the case check");
    expect(html).toContain("Page 1 of 3 · 60 cases");
    expect(html).toContain("My cases");
  });

  it("shows owner, next action, why, missing information and escalation state on the Case", () => {
    const html = render(<CaseHeaderView header={HEADER} status="To check" />);
    for (const text of [
      "Priya",
      "Answer and sign the Case check",
      "same working day",
      "Lot: unconfirmed",
      "Not escalated",
    ])
      expect(html).toContain(text);
  });
});
