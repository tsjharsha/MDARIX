import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, sectionAllowed, type WorkspaceApi } from "./workspaceContext";
import { HelpMenu } from "../shared/HelpMenu";
import { ComplaintViews } from "./sections/ComplaintViews";
import { SettingsSection } from "./sections/Settings";
import { DiscussPilot } from "./sections/GettingStarted";

// 0.10.71, Release A: the first five minutes.

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: null, reload: () => undefined }),
}));

const MENU = ["home", "products", "investigations"];
const api = (overrides: Partial<WorkspaceApi> = {}, session: Record<string, unknown> = {}) =>
  ({
    session: { allowed_menu: MENU, business_permissions: ["records.write", "signal.triage"], ...session },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    ...overrides,
  }) as unknown as WorkspaceApi;

const render = (node: React.ReactNode, value: WorkspaceApi) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

describe("A2: a sample-only trial cannot upload", () => {
  it("never offers Import data to a sample-only trial, whatever the role", () => {
    expect(sectionAllowed("Import data", MENU, ["records.write"])).toBe(true);
    expect(sectionAllowed("Import data", MENU, ["records.write"], true)).toBe(false);
    // Only the import: every other screen stays.
    expect(sectionAllowed("Complaints", MENU, ["records.write"], true)).toBe(true);
  });

  it("offers Discuss a pilot in Help instead of your own data", () => {
    const normal = render(<HelpMenu onGettingStarted={() => undefined} defaultOpen />, api());
    expect(normal).toContain("Try your own data");
    expect(normal).not.toContain("Discuss a pilot");
    const sample = render(<HelpMenu onGettingStarted={() => undefined} defaultOpen />, api({}, { sample_only: true }));
    expect(sample).toContain("Discuss a pilot");
    expect(sample).toContain("This evaluation uses the sample only");
    expect(sample).not.toContain("Try your own data");
    expect(sample).not.toContain("import templates");
    // Classic keeps its wording.
    expect(
      render(<HelpMenu onGettingStarted={() => undefined} defaultOpen />, api({ navigation: "classic" })),
    ).toContain("Getting started and import templates");
  });

  it("keeps the upload off the Complaints header in a trial, and on it in a pilot", () => {
    expect(render(<ComplaintViews />, api())).not.toContain("Import your data");
    expect(render(<ComplaintViews />, api({ isTrial: false }))).toContain("Import your data");
    expect(render(<ComplaintViews />, api({ isTrial: false }, { sample_only: true }))).not.toContain(
      "Import your data",
    );
  });

  it("has no import templates in Settings for a sample-only trial", () => {
    expect(render(<SettingsSection tab="Import templates" />, api())).toContain("Import templates");
    expect(render(<SettingsSection tab="Import templates" />, api({}, { sample_only: true }))).not.toContain(
      "Import templates",
    );
  });

  it("says so in Getting started, with the pilot conversation as the one action", () => {
    const html = renderToStaticMarkup(<DiscussPilot onOpen={() => undefined} />);
    expect(html).toContain("This evaluation uses the sample only");
    expect(html).toContain("Discuss a pilot");
    expect(html).not.toMatch(/upload|Check file/i);
  });
});

describe("A7: the visible release number", () => {
  it("shows the release in Help › About", async () => {
    const { releaseLine } = await import("../shared/HelpMenu");
    expect(releaseLine("0.10.71")).toBe("MDARIX release v0.10.71");
    expect(render(<HelpMenu defaultOpen />, api())).toContain("About");
    expect(render(<HelpMenu defaultOpen />, api())).toMatch(/MDARIX release (v\d+\.\d+\.\d+|not known)/);
  });
});
