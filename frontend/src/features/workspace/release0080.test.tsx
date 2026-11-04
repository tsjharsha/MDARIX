// 0.10.80 (owner request, 3 Nov 2026), trials on the new navigation: Getting started in the tab bar left of Home; the
// import leaves Getting started for its own page, Import your data (/app/import); the top bar hides "Sample data" once
// the sample is removed and, while the sample and imported data both exist, offers "Sample data · Your data", which the
// complaint lists, Trends › Trends to review and Automatic insights follow. Classic navigation and pilots unchanged.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, openImport, type WorkspaceApi } from "./workspaceContext";
import {
  AvatarMenu,
  DataChoice,
  PERSONA_TABS,
  TabBar,
  importOwnDataAction,
  readDataChoice,
  saveDataChoice,
  tabOfSection,
  trialDataBar,
  trialTabs,
  visibleTabs,
} from "./HybridShell";
import { GettingStartedSection } from "./sections/GettingStarted";
import { ImportYourDataSection, YOUR_COMPLAINTS_TAB, insightsPath } from "./sections/YourData";
import { ComplaintList } from "./sections/ComplaintList";
import { SignalInbox } from "./sections/SignalInbox";
import { DEFAULT_SIGNAL_FILTERS } from "./signals";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "./complaintList";
import { HelpMenu } from "../shared/HelpMenu";
import { routeFor } from "../../app/linkTable";
import { viewFromPath } from "../../app/router";
import { addressFor, locationFromAddress } from "./workspaceAddress";
import { VIEW_TO_SECTION } from "./UserWorkspace";
import { WORKSPACE_SECTIONS } from "./workspaceContext";

const reads = vi.hoisted(() => ({ data: {} as Record<string, unknown>, paths: [] as string[] }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    if (path) reads.paths.push(path);
    const data = (path && reads.data[path.split("?")[0]]) ?? null;
    return { state: data ? "ready" : "loading", data, reload: () => undefined };
  },
}));

const MENU = ["home", "products", "investigations"];
const OWNER = { allowed_menu: MENU, business_permissions: ["records.write", "signal.triage", "quality.review"] };
const REGULATORY = { allowed_menu: MENU, business_permissions: ["regulatory.review", "regulatory.approve"] };
const STATUS = "/api/v1/trial/status";
const status = (sample: number, own: number) => ({
  is_trial: true,
  is_owner: true,
  sample: { products: sample ? 3 : 0, complaints: sample },
  own_data: { products: own ? 1 : 0, lots: 0, complaints: own },
});

const api = (overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session: OWNER,
    work: { products: [], setInvestigationId: vi.fn(), refreshProducts: vi.fn() },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    ...overrides,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

beforeEach(() => {
  reads.data = {};
  reads.paths = [];
});

describe("1. Getting started in the tab bar", () => {
  it("is the first tab, left of Home, for every persona of a trial; never in a pilot's bar", () => {
    const allowed = ["Getting started", "My Work", "Complaints", "Trends"];
    for (const persona of [["home", "complaints"], ["home", "trends"], ["home"]]) {
      const tabs = visibleTabs(trialTabs(persona, true), allowed);
      expect(tabs[0]).toBe("start");
      expect(tabs[1]).toBe("home");
      expect(PERSONA_TABS[tabs[0]].label).toBe("Getting started");
    }
    expect(visibleTabs(trialTabs(["home", "complaints"], false), allowed)).toEqual(["home", "complaints"]);
    // A pilot's sections hold no Getting started (trial-only), even if the tab were asked for.
    expect(visibleTabs(["start", "home"], ["My Work"])).toEqual(["home"]);
    expect(tabOfSection("Getting started")).toBe("start");
    const bar = renderToStaticMarkup(<TabBar tabs={["start", "home"]} current="start" open={vi.fn()} />);
    expect(bar.indexOf("Getting started")).toBeLessThan(bar.indexOf("Home"));
    expect(bar).toContain('aria-current="page">Getting started');
  });
});

describe("2. Getting started without the import (new navigation)", () => {
  it("has no Your data tab and no upload; the classic navigation keeps both", () => {
    reads.data[STATUS] = status(37, 0);
    // The trial's tabs are on their own page, reached from Help (Short stories and your trial).
    const fresh = render(<GettingStartedSection focus="Your trial" />, api());
    expect(fresh).not.toContain(">Your data<");
    expect(fresh).not.toContain("Upload your export");
    expect(fresh).toContain(">About the sample data<");
    expect(fresh).toContain(">Your trial<");
    expect(reads.paths.some((path) => path.startsWith("/api/v1/trial/insights"))).toBe(false);
    const classic = render(<GettingStartedSection />, api({ navigation: "classic" }));
    expect(classic).toContain(">Your data<");
    expect(classic).toContain("Upload your export");
  });
});

describe("3. Import your data: its own page, /app/import", () => {
  it("has its own address, and every way in opens it", () => {
    expect(addressFor({ section: "Import your data" })).toBe("/app/import");
    expect(viewFromPath("/app/import")).toBe("import");
    expect(VIEW_TO_SECTION.import).toEqual(["Import your data"]);
    expect(locationFromAddress("/app/import", "?report=IMP-7", VIEW_TO_SECTION, WORKSPACE_SECTIONS)).toMatchObject({
      section: "Import your data",
    });
    // Old links to Getting started › Your data land on it, a data-quality report's link with its report.
    expect(routeFor("Getting started", "Your data", "mvp", "new")).toEqual({
      section: "Import your data",
      tab: undefined,
    });
    expect(routeFor("Getting started", "Your data?report=IMP-7", "mvp", "new")).toEqual({
      section: "Import your data",
      tab: "?report=IMP-7",
    });
    // The rest of Getting started stays where it was.
    expect(routeFor("Getting started", "Your trial", "mvp", "new")).toEqual({
      section: "Getting started",
      tab: "Your trial",
    });
    // On the classic navigation the address opens Getting started › Your data, as before.
    expect(routeFor("Import your data", undefined, "mvp", "classic")).toEqual({
      section: "Getting started",
      tab: "Your data",
    });
    // The top bar's button (and the avatar menu's), the Complaints header in a trial.
    const open = vi.fn();
    importOwnDataAction(true, OWNER as never, open)?.();
    expect(open).toHaveBeenLastCalledWith("Import your data");
    openImport(open, true);
    expect(open).toHaveBeenLastCalledWith("Import your data");
    openImport(open, false);
    expect(open).toHaveBeenLastCalledWith("Import data");
  });

  it("shows the upload, the data-quality reports and what the data shows", () => {
    reads.data[STATUS] = status(37, 0);
    const html = render(<ImportYourDataSection />, api());
    expect(html).toContain("Upload your export");
    expect(html).toContain("See the data-quality reports");
    expect(html).toContain("Automatic insights");
    // Before an import: no button to "your" complaints yet; the sample's removal is offered, folded, never forced.
    expect(html).not.toContain("See your complaints");
    expect(html).toContain("Optional: remove the sample data");
    expect(html).not.toMatch(/<details[^>]*open/);
  });

  it("once the organization's complaints are in, offers them, with Choose a file the one main button (0.10.82)", () => {
    reads.data[STATUS] = status(37, 4);
    reads.data["/api/v1/data/import/templates"] = {
      row_limit: 5000,
      file_limit_bytes: 1_000_000,
      creates_references: true,
      templates: [{ entity: "complaints", title: "Complaints", required: [], optional: [], download: "" }],
    };
    const chooseDataSource = vi.fn();
    const open = vi.fn();
    const html = render(<ImportYourDataSection />, api({ chooseDataSource, open }));
    expect(html.match(/class="ac-primary"/g)).toHaveLength(1);
    expect(html).toMatch(/<label class="ac-primary">.*Choose a file/);
    expect(html).toContain("See your complaints");
    expect(html).toContain("4 complaints of your own");
    expect(YOUR_COMPLAINTS_TAB).toBe(`All complaints?source_system=${IMPORTED_SOURCE}`);
  });
});

describe("4 and 5. The top bar's data", () => {
  it("reads the server's counts: the label, the choice, or nothing once the sample is removed", () => {
    expect(trialDataBar(status(37, 0))).toBe("sample");
    expect(trialDataBar(status(37, 4))).toBe("choice");
    expect(trialDataBar(status(0, 4))).toBe("none");
    expect(trialDataBar(status(0, 0))).toBe("none");
    expect(trialDataBar(null)).toBe("none");
  });

  it("offers Sample data · Your data, the sample by default, remembered per person", () => {
    const html = renderToStaticMarkup(<DataChoice source={SAMPLE_SOURCE} onChoose={vi.fn()} />);
    expect(html).toContain('aria-label="Data shown"');
    expect(html).toMatch(/aria-pressed="true"[^>]*>Sample data/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>Your data/);
    const store = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (k: string, v: string) => store.set(k, v),
      },
    });
    const asha = { user_id: "u1", current_tenant: { tenant_id: "t1" } } as never;
    const ravi = { user_id: "u2", current_tenant: { tenant_id: "t1" } } as never;
    expect(readDataChoice(asha)).toBe(SAMPLE_SOURCE);
    saveDataChoice(asha, IMPORTED_SOURCE);
    expect(readDataChoice(asha)).toBe(IMPORTED_SOURCE);
    expect(readDataChoice(ravi)).toBe(SAMPLE_SOURCE);
    vi.unstubAllGlobals();
  });

  it("is in the avatar menu at narrow widths, only while both exist", () => {
    const menu = (data?: { source: string; onChoose: () => void }) =>
      renderToStaticMarkup(
        <AvatarMenu session={null} current="Home" open={vi.fn()} showSettings data={data} defaultOpen />,
      );
    const both = menu({ source: IMPORTED_SOURCE, onChoose: vi.fn() });
    expect(both).toMatch(/aria-checked="true"[^>]*><span>Your data/);
    expect(both).toMatch(/aria-checked="false"[^>]*><span>Sample data/);
    expect(menu()).not.toContain("Data shown");
  });

  it("filters every complaint list and list view, Trends to review and Automatic insights", () => {
    const value = api({ dataSource: IMPORTED_SOURCE });
    render(<ComplaintList view={{ name: "All open complaints", code: "open" }} />, value);
    render(<ComplaintList work />, value);
    render(<SignalInbox initialFilters={DEFAULT_SIGNAL_FILTERS} initialSignal={null} />, value);
    const complaints = reads.paths.filter((path) => path.startsWith("/api/v1/complaints?"));
    expect(complaints).toHaveLength(2);
    for (const path of complaints) expect(path).toContain(`source_system=${IMPORTED_SOURCE}`);
    expect(reads.paths.find((path) => path.startsWith("/api/v1/triage/signals?"))).toContain(
      `source_system=${IMPORTED_SOURCE}`,
    );
    expect(insightsPath(SAMPLE_SOURCE)).toBe(`/api/v1/trial/insights?source=${SAMPLE_SOURCE}`);
    expect(insightsPath("")).toBe("/api/v1/trial/insights");
    // Without a choice (one source only, a pilot, the classic navigation) the lists read as before.
    reads.paths = [];
    render(<ComplaintList work />, api());
    expect(reads.paths.find((path) => path.startsWith("/api/v1/complaints?"))).not.toContain("source_system");
  });
});

describe("6. Sample-only trials and people without import rights", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("are told the page is not available, plainly", () => {
    reads.data[STATUS] = status(37, 0);
    const sampleOnly = render(<ImportYourDataSection />, api({ session: { ...OWNER, sample_only: true } as never }));
    expect(sampleOnly).toContain("This evaluation uses the sample only");
    expect(sampleOnly).not.toContain("Upload your export");
    const regulatory = render(<ImportYourDataSection />, api({ session: REGULATORY as never }));
    expect(regulatory).toContain("Import is not available to you");
    expect(regulatory).not.toContain("Upload your export");
    expect(importOwnDataAction(true, REGULATORY as never, vi.fn())).toBeUndefined();
  });

  it("see no Try your own data in Help on the new navigation", () => {
    const help = (session: object) =>
      render(<HelpMenu onGettingStarted={vi.fn()} defaultOpen />, api({ session: session as never }));
    expect(help(OWNER)).toContain("Try your own data");
    expect(help(REGULATORY)).not.toContain("Try your own data");
    expect(help({ ...OWNER, sample_only: true })).not.toContain("Try your own data");
    // The free trial user guide stays for everyone in a trial.
    expect(help(REGULATORY)).toContain("Free trial user guide");
  });
});
