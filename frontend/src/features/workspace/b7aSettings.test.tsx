import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { AlertsAndFiles, SETTING_PERMISSIONS, SETTINGS_TABS } from "./sections/Settings";
import { moreCasePlace } from "./oneStory";
import { CaseExports } from "./sections/CasesList";
import { CaseFiles } from "./sections/FirstContact";

// B7a (0.10.97): Settings › Alerts and files (the urgent e-mail switch and the file storage; the server's
// PUT /oversight/settings/alerts-and-files checks the same permissions), and the routine sample complaint under
// "More cases to try", which opens its Resolve and close drawer.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (permissions: string[], isTrial = false) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: permissions },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial,
  }) as unknown as WorkspaceApi;

const render = (value: WorkspaceApi, node: React.ReactNode = <AlertsAndFiles />) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

describe("Settings › Alerts and files (B7-D12, D16)", () => {
  resources.data["/api/v1/oversight/settings"] = { urgent_email: false, attachment_quota_mb: 250 };

  it("is a Settings tab changed by the people the server lets change it", () => {
    expect(SETTINGS_TABS).toContain("Alerts and files");
    expect(SETTING_PERMISSIONS["Alerts and files"]).toEqual(["quality.review", "regulatory.approve"]);
  });

  it("offers the switch, off by default, and the storage to a quality reviewer outside a trial", () => {
    const html = render(api(["quality.review"]));
    expect(html).toContain("Send an e-mail when an urgent case arrives");
    expect(html).toContain("no names, no product, no words");
    expect(html).not.toMatch(/type="checkbox"[^>]*checked/);
    expect(html).toContain('value="250"');
    expect(html).toContain("Save file storage");
  });

  it("is read only for someone without the permission, and a trial keeps 100 MB", () => {
    const reader = render(api(["records.write"]));
    expect(reader).toMatch(/type="checkbox"[^>]*disabled/);
    expect(reader).not.toContain("Save file storage");
    const trial = render(api(["quality.review"], true));
    expect(trial).toContain("A free trial keeps 100 MB");
    expect(trial).not.toContain("Save file storage");
  });
});

describe("Cases export and files on a Case (spec 3.3, G15)", () => {
  it("offers both exports only to people with data.export, contacts masked", () => {
    expect(render(api(["case.log"]), <CaseExports view="all" q="" />)).toBe("");
    const html = render(api(["data.export"]), <CaseExports view="all" q="" />);
    expect(html).toContain("Export these cases (CSV)");
    expect(html).toContain("Export for QMS entry (CSV)");
    expect(html).toContain("Contacts are masked");
  });

  it("lists a Case's files and offers the upload to those who log cases", () => {
    resources.data["/api/v1/intake/e1/attachments"] = {
      items: [{ id: "f1", file_name: "alarm-log.pdf", size: 20480, created_at: "2026-11-10T09:00:00Z" }],
    };
    const html = render(api(["case.log"]), <CaseFiles caseId="e1" canAdd />);
    expect(html).toContain("alarm-log.pdf");
    expect(html).toContain("20 KB");
    expect(html).toContain('type="file"');
    expect(render(api(["quality.review"]), <CaseFiles caseId="e1" canAdd={false} />)).not.toContain('type="file"');
    resources.data["/api/v1/intake/e2/attachments"] = { items: [] };
    expect(render(api(["case.log"]), <CaseFiles caseId="e2" canAdd />)).toContain("No files on this case.");
  });
});

describe("More cases to try: the routine sample complaint (B7a)", () => {
  it("opens its Dispositions drawer; a Case still opens its check", () => {
    expect(moreCasePlace({ id: "c-1", ref: "SAMPLE-RT-01", label: "Routine", signed: false, complaint: true })).toEqual(
      { section: "Complaints", tab: "Dispositions?complaint=c-1" },
    );
    expect(moreCasePlace({ id: "e-1", ref: "SAMPLE-CALL-01", label: "Inquiry", signed: true })).toEqual({
      section: "Complaints",
      tab: "First contact?check=e-1",
    });
  });
});
