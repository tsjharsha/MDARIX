// 0.10.88 (DEV-10): what the browser journeys found, as rendered from the server's answers.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ReportPage } from "./sections/ReportsTab";
import { eventPath } from "./oversight";
import { REPORTS } from "./authorityReports";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    // A refusal as the server sends it: its message, code and the reference for support.
    return value instanceof Error
      ? { state: "error", data: null, error: value.message, code: value.name, requestId: "req-1", reload: () => {} }
      : { state: "ready", data: value, reload: () => undefined };
  },
}));

const api = () =>
  ({
    session: { user_id: "u1", business_permissions: ["records.write", "signal.triage", "regulatory.review"] },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api()}>{node}</WorkspaceContext.Provider>);

const refused = (message: string, code: string) => Object.assign(new Error(message), { name: code });

describe("a record that is not there (removed, or a mistyped link) offers the way back, not a Retry", () => {
  it("on a complaint's page", () => {
    resources.data[eventPath("SAMPLE-RV-99")] = refused("No such complaint", "COMPLAINT_NOT_FOUND");
    resources.data["/api/v1/triage"] = { items: [] };
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-99" />);
    expect(html).toContain("This complaint could not be opened");
    expect(html).toContain("Open the complaint list");
    expect(html).not.toContain(">Retry<");
  });

  it("on a report's page", () => {
    resources.data[`${REPORTS}/r-gone`] = refused("No such report in your organization", "REPORT_NOT_FOUND");
    const html = render(<ReportPage id="r-gone" onBack={() => undefined} />);
    expect(html).toContain("This report could not be opened");
    expect(html).toContain("All reports");
    expect(html).not.toContain(">Retry<");
  });
});
