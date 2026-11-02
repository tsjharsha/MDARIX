import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, sectionAllowed, type WorkspaceApi } from "./workspaceContext";
import { HelpMenu } from "../shared/HelpMenu";
import { ComplaintViews } from "./sections/ComplaintViews";
import { SettingsSection } from "./sections/Settings";
import { DiscussPilot } from "./sections/GettingStarted";
import { ComplaintPage } from "./sections/ComplaintPage";
import { serviceText } from "./sections/ServiceWork";
import { eventPath, type EventView } from "./oversight";

// 0.10.71, Release A of the Simplicity and WoW plan.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
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

/** SAMPLE-RV-11's page as the server answers it, trimmed to what the page reads. */
export function rv11(service: Partial<NonNullable<EventView["service"]>> | null = {}): EventView {
  return {
    event: {
      complaint_id: "c-rv11",
      ref: "SAMPLE-RV-11",
      business_id: "CMP000038",
      product: "PulseWatch 410",
      market: "US",
      awareness_at: "2026-11-01T09:00:00Z",
      status_in_qms: "Open",
      owner_id: "u1",
      owner_name: "Asha Quality",
      owner_named: false,
      sample: true,
      description:
        "Biomedical engineering checked a monitor against a reference oximeter: its SpO2 read 4 to 6 points high on two patients. No harm was reported. The monitor is out of use and sent for service.",
      harm: "PATIENT_INVOLVED",
    },
    summary: {
      nearest_deadline: null,
      open_requests: 0,
      next_action: {
        label: "Assess the United States (FDA) market",
        detail: "",
        opens: { section: "Complaints", tab: "Reporting" },
      },
    },
    stages: [],
    checklist: [],
    blocked: 1,
    state: "OPEN",
    state_label: "Open",
    changed_since_signed: false,
    ready: null,
    decision_record: { entries: [], sha256: "", version: 0, filed: null },
    you_are_owner: true,
    people: [{ id: "u1", name: "Asha Quality" }],
    reason_min: 10,
    never_closes: "",
    practice_label: null,
    work: { owner_name: "Asha Quality", stage: "Assessment", next: null, due: [], markets: ["US"] },
    service:
      service === null
        ? null
        : {
            reference: "SVC-24-1107 (sample service ticket)",
            owner_id: null,
            owner_name: null,
            status: "IN_PROGRESS",
            status_label: "In progress",
            status_at: "2026-11-01T09:00:00Z",
            header: null,
            ...service,
          },
  } as unknown as EventView;
}

describe("A5: the linked service work", () => {
  it("says the service is complete and the quality assessment still open, with its owner and next step", () => {
    resources.data[eventPath("SAMPLE-RV-11")] = rv11({
      status: "COMPLETE",
      status_label: "Complete",
      owner_id: "u1",
      owner_name: "Asha Quality",
      header: "Service complete · Quality assessment open",
    });
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />, api());
    expect(html).toContain("Service complete · Quality assessment open</strong> · Quality owner: Asha Quality");
    expect(html).toContain("Next: Assess the United States (FDA) market");
    expect(html).toContain("Complete since");
  });

  it("names the service work while it runs, and nothing when none is linked", () => {
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />, api());
    expect(html).not.toContain("Service complete");
    expect(html).toContain("In progress since");
    expect(html).toContain("SVC-24-1107 (sample service ticket) · owner not named yet");
    expect(serviceText(rv11(null))).toBe("No service work linked.");
  });
});
