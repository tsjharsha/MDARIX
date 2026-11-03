import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { NEW_PLACES } from "../../app/linkTable";
import {
  COMPLAINT_LIST_VIEWS,
  INVESTIGATION_VIEWS,
  PERSONA_LIST_VIEWS,
  SERVER_VIEWS,
  inInvestigationView,
  listViewsFor,
} from "./listViews";
import { ComplaintViews, InvestigationList } from "./sections/ComplaintViews";
import { workColumns } from "./sections/ComplaintList";
import { ComplaintPage, sectionOf } from "./sections/ComplaintPage";
import { CaseHeader } from "./sections/CaseHeader";
import { LatestSigned, NewRecordsSection } from "./sections/Records";
import { StoryBar } from "./sections/Entrance";
import { GlobalSearch } from "./HybridShell";
import { eventPath, type EventView } from "./oversight";
import { SHORT_STORY_PATH, type ShortStory } from "./shortStory";
import { Table } from "../customer-admin/shared";
import { addressFor } from "./workspaceAddress";

// 0.10.74, Release C part C2: list views and record pages (the approved design's viewComplaints, viewRecord,
// viewInvestigations, viewRecords).

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (overrides: Partial<WorkspaceApi> = {}, session: Record<string, unknown> = {}) =>
  ({
    session: {
      user_id: "u1",
      allowed_menu: ["home", "products", "investigations"],
      business_permissions: ["records.write", "signal.triage", "data.export"],
      ...session,
    },
    work: { products: [{ id: "p1", name: "OrbitCare 300" }], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
    personaLabel: "Admin",
    ...overrides,
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode, value: WorkspaceApi = api()) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

/** The approved design's LIST_VIEWS (mdarix-hybrid-mockup.html). */
const MOCKUP_LIST_VIEWS = {
  admin: ["All open complaints", "Due this week", "Second look", "Reporting", "Waiting for the reporter"],
  quality: ["All open complaints", "Due this week", "Past target", "Second look"],
  regulatory: ["Reportability: decision needed", "Authority reports", "Legal clocks this week"],
  handler: ["To triage", "Calls to check", "Second look", "Waiting for the reporter"],
  decision: ["Waiting for my approval", "Signed this month"],
};

describe("list views: one choice, the persona's own first", () => {
  it("gives each persona the approved design's views, and every other view under More views", () => {
    expect(PERSONA_LIST_VIEWS).toEqual(MOCKUP_LIST_VIEWS);
    for (const [persona, views] of Object.entries(MOCKUP_LIST_VIEWS)) {
      const { mine, more } = listViewsFor(persona);
      expect(mine).toEqual(views);
      // Nothing is lost: the persona narrows the first choice, never what the person may open.
      expect([...mine, ...more].sort()).toEqual([...COMPLAINT_LIST_VIEWS].sort());
      expect(more.some((view) => views.includes(view))).toBe(false);
    }
    // A persona whose tabs hold no complaint list (it reaches Complaints by a link) gets Admin's.
    expect(listViewsFor("investigator").mine).toEqual(MOCKUP_LIST_VIEWS.admin);
    // Every view has its own address (the link table), and every server view a code the server knows.
    expect(NEW_PLACES.Complaints.tabs).toEqual([...COMPLAINT_LIST_VIEWS]);
    expect(Object.values(SERVER_VIEWS).map((view) => view.code)).toEqual([
      "open",
      "due-week",
      "legal-week",
      "reportability",
      "waiting-reporter",
      "my-approval",
      "signed-month",
    ]);
  });

  it("opens Complaints on the persona's first view, its views grouped for it, and asks the server for that view", () => {
    const decision = render(<ComplaintViews />, api({ persona: "decision", personaLabel: "Decision Maker" }));
    expect(decision).toContain('<optgroup label="For Decision Maker">');
    expect(decision).toContain('<optgroup label="More views">');
    expect(decision).toMatch(/<option value="Waiting for my approval" selected="">/);
    expect(decision).toContain("An authority report sent for approval that you did not prepare");
    const handler = render(<ComplaintViews />, api({ persona: "handler", personaLabel: "Complaint Handler" }));
    expect(handler).toMatch(/<option value="To triage" selected="">/);
    // A link to a view opens it, whatever the persona.
    const linked = render(<ComplaintViews tab="Legal clocks this week" />, api({ persona: "handler" }));
    expect(linked).toMatch(/<option value="Legal clocks this week" selected="">/);
    // No row of view pills before the list (the stage 7 chooser): one List view choice.
    expect(decision).not.toContain("uw-views-row");
  });

  it("shows six columns, one row action, and cards on a phone", () => {
    const row = {
      id: "c1",
      complaint_identifier: "SAMPLE-RV-06",
      description: "Pressure alarm silent during an occlusion",
      product_name: "OrbitCare 300",
      version: "Rev B",
      lot: "LOT-004",
      work: {
        owner_name: "Asha Quality",
        stage: "Market assessment",
        next: "Assess the United States (FDA) market",
        markets: ["US"],
        due: [
          {
            key: "k",
            title: "United States (FDA): 30-day report",
            market: "US",
            due_at: "2026-11-08T18:29:59Z",
            state: "DUE_SOON",
            hours_left: 100,
          },
        ],
      },
    };
    const html = renderToStaticMarkup(
      <Table
        caption="Due this week"
        rows={[row]}
        rowKey={(item) => String(item.id)}
        empty={{ title: "", detail: "" }}
        columns={workColumns({}, () => undefined, null)}
      />,
    );
    // The design system's card layout at phone width (admin-console.css .ac-table.ms-cards, ≤640 px).
    expect(html).toContain('class="ac-table ms-cards');
    const labels = [...html.matchAll(/data-label="([^"]*)"/g)].map((match) => match[1]);
    expect(labels).toEqual(["Urgency", "What happened", "Product, version, lot", "Markets", "Owner", "Stage", ""]);
    expect(html.match(/<button[^>]*class="ac-secondary"/g)?.length).toBe(1);
    expect(html).toContain(">Open<");
    expect(html).toContain("Asha Quality");
    expect(html).toContain("OrbitCare 300 · Rev B · Lot LOT-004");
  });

  it("lists every investigation in the Investigations tab, open ones first, with the same six-column shape", () => {
    const rows = [
      { id: "i1", workflow_state: "OPEN", owner_ref: "u1" },
      { id: "i2", workflow_state: "CLOSED", owner_ref: "u1" },
      { id: "i3", status: "open", owner_ref: "u2" },
    ];
    const ids = (view: (typeof INVESTIGATION_VIEWS)[number]) =>
      rows.filter((row) => inInvestigationView(row, view, "u1")).map((row) => row.id);
    expect(ids("Open investigations")).toEqual(["i1", "i3"]);
    expect(ids("Assigned to me")).toEqual(["i1"]);
    expect(ids("All investigations")).toEqual(["i1", "i2", "i3"]);
    resources.data["/api/v1/data-plane/investigations"] = {
      records: [
        {
          id: "i1",
          business_id: "INV000001",
          investigation_question: "Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?",
          product_id: "p1",
          workflow_state: "OPEN",
          owner_ref: "u1",
          owner_name: "Asha Quality",
          priority: "HIGH",
        },
      ],
    };
    const html = render(<InvestigationList />);
    expect(html).toMatch(/<option value="Open investigations" selected="">/);
    expect(html).toContain("INV000001");
    expect(html).toContain("OrbitCare 300");
    const labels = [...html.matchAll(/data-label="([^"]*)"/g)].map((match) => match[1]);
    expect(labels).toEqual(["Due", "Investigation", "Product", "Priority", "Owner", "Stage", ""]);
    // The list has its own address (no case), so a refresh or Back reopens the list, not the last investigation.
    expect(addressFor({ section: "Investigations", tab: "All investigations" })).toBe(
      "/app/investigations?step=All+investigations",
    );
  });
});

/** SAMPLE-RV-11's page as the server answers it, trimmed to what the page reads. */
function rv11(): EventView {
  const due = {
    key: "watch:c-rv11:US",
    category: "REPORTING",
    category_label: "Reporting deadlines",
    title: "United States (FDA): not assessed yet, provisional deadline",
    market: "US",
    due_at: "2026-12-02T04:59:59Z",
    due_label: "Tue 1 Dec 2026, 23:59 EST",
    state: "LATER",
    state_label: "Later",
    hours_left: 650,
    opens: { section: "Complaints", tab: "Reportability" },
  };
  return {
    event: {
      complaint_id: "c-rv11",
      ref: "SAMPLE-RV-11",
      business_id: "CMP000038",
      product: "PulseWatch 410 Patient Monitor (Sample)",
      version: "Rev A",
      lot: "SAMPLE-PULSE-410-LOT-002",
      market: "US",
      awareness_at: "2026-11-01T20:07:11Z",
      status_in_qms: "Open",
      owner_id: "u1",
      owner_name: "Asha Quality",
      owner_named: true,
      sample: true,
      description: "Biomedical engineering checked a monitor against a reference oximeter.",
      problem_code: "SPO2_READING_HIGH",
      harm: null,
    },
    summary: {
      nearest_deadline: { title: due.title, due_at: due.due_at, opens: due.opens },
      open_requests: 0,
      next_action: {
        label: "Assess the United States (FDA) market",
        detail: "",
        opens: { section: "Complaints", tab: "Reporting" },
      },
    },
    stages: [
      { code: "TRIAGE", label: "Triage", state: "DONE" },
      { code: "MARKETS", label: "Market assessment", state: "CURRENT" },
      { code: "INVESTIGATION", label: "Investigation", state: "NOT_NEEDED" },
      { code: "DECISION", label: "Decision", state: "OPEN" },
      { code: "READY", label: "Ready to close", state: "OPEN" },
      { code: "CLOSED", label: "Closed in the QMS", state: "LATER" },
    ],
    checklist: [
      {
        code: "MARKETS",
        label: "Market assessments",
        result: "BLOCKED",
        result_label: "Open",
        detail: "United States (FDA) is not assessed yet",
        action: "Assess the United States (FDA) market",
        opens: { section: "Complaints", tab: "Reporting" },
      },
    ],
    blocked: 1,
    state: "NOT_READY",
    state_label: "Not ready to close",
    changed_since_signed: false,
    ready: null,
    decision_record: { entries: [], sha256: "", version: 0, filed: null },
    you_are_owner: true,
    people: [{ id: "u1", name: "Asha Quality" }],
    reason_min: 20,
    never_closes: "MDARIX never closes the complaint.",
    practice_label: null,
    work: {
      owner_name: "Asha Quality",
      stage: "Market assessment",
      next: "Assess the United States (FDA) market",
      due: [due],
      markets: ["US"],
    },
    signers: {
      MARKETS: {
        people: [
          { id: "u1", name: "Asha Quality" },
          { id: "u2", name: "Rahul Colleague" },
        ],
        you: true,
        second_person: false,
      },
    },
    service: null,
    related: [
      { key: "communications", label: "Communications", count: 0, lines: ["None recorded"] },
      { key: "assessments", label: "Market assessments", count: 1, lines: ["United States (FDA): not assessed yet"] },
      { key: "service", label: "Service work", count: 0, lines: ["None linked"] },
      { key: "investigations", label: "Investigation", count: 0, lines: ["Not opened"], items: [] },
      { key: "reports", label: "Authority reports", count: 0, lines: ["None started"] },
      { key: "decisions", label: "Decision records", count: 0, lines: ["Nothing signed yet"] },
    ],
  } as unknown as EventView;
}

describe("the record page: highlights, path, Details · Related · Activity, and the rail", () => {
  it("shows the highlights, the path and the rail with the list's deadline, owner and next step", () => {
    const view = rv11();
    resources.data[eventPath("SAMPLE-RV-11")] = view;
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />);
    // Breadcrumbs back to the list.
    expect(html).toContain('aria-label="Where you are"');
    // Highlights: reference, product, version, lot, owner, markets, also known as.
    expect(html).toContain("Complaint · PulseWatch 410 Patient Monitor (Sample) · Rev A");
    expect(html).toContain("<h1");
    expect(html).toContain("SAMPLE-PULSE-410-LOT-002");
    expect(html).toContain("CMP000038");
    for (const field of ["Owner", "Markets", "Lot", "Also known as"]) expect(html).toContain(`<dt>${field}</dt>`);
    // The path: each stage as a chevron, the current one marked.
    expect(html).toMatch(/<li class="is-done"[^>]*>.*Triage/);
    expect(html).toMatch(/<li class="is-now" aria-current="step">.*Market assessment/);
    expect(html).toMatch(/<li class="is-skip"[^>]*>.*Investigation/);
    // Details · Related · Activity.
    expect(html).toMatch(/role="tab"[^>]*aria-selected="true"[^>]*>Details</);
    expect(html).toContain(">Related<");
    expect(html).toContain(">Activity<");
    // The rail: the next step is the list's and Oversight's next action, one main button.
    const rail = html.slice(html.indexOf('aria-label="What to do next"'));
    expect(rail).toContain("<b>Assess the United States (FDA) market</b>");
    expect(html.match(/class="ac-primary"/g)?.length).toBe(1);
    // Legal clocks: the work line's nearest deadline, as the list's urgency reads it.
    expect(rail).toContain("Due Tue 1 Dec 2026, 23:59 EST");
    expect(rail).toContain("Starter rules, for your consultant to confirm.");
    // Who signs the next step, and the owner the list shows.
    expect(rail).toContain("Each market&#x27;s conclusion");
    expect(rail).toContain("Rahul Colleague");
    expect(html).toContain("Asha Quality");
    expect(view.work?.owner_name).toBe("Asha Quality");
  });

  it("opens the former sections' addresses on the section that holds them now", () => {
    expect(sectionOf("Summary?ref=X")).toBe("Summary");
    expect(sectionOf("Decisions & actions?ref=X")).toBe("Summary");
    expect(sectionOf("Evidence?ref=X")).toBe("Related");
    expect(sectionOf("History?ref=X")).toBe("Activity");
    expect(sectionOf("Related?ref=X")).toBe("Related");
    expect(sectionOf(undefined)).toBe("Summary");
  });

  it("lists the linked records in Related and the record's own events in Activity", () => {
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    const related = render(<ComplaintPage tab="Related?ref=SAMPLE-RV-11" />);
    for (const label of ["Communications", "Market assessments", "Service work", "Investigation", "Authority reports"])
      expect(related).toContain(`<b>${label}</b>`);
    expect(related).toContain("United States (FDA): not assessed yet");
    expect(related).toContain("Open the log");
    expect(related).toContain("What was signed, and when");
    resources.data[`${eventPath("SAMPLE-RV-11")}/activity`] = {
      items: [
        { at: "2026-11-02T08:00:00Z", title: "Market conclusion signed", who: "Asha Quality", reason: null },
        {
          at: "2026-11-01T20:07:11Z",
          title: "Received; awareness: the legal clocks count from here",
          who: null,
          reason: null,
          from_record: true,
        },
      ],
      more: false,
    };
    const activity = render(<ComplaintPage tab="Activity?ref=SAMPLE-RV-11" />);
    expect(activity).toContain("<b>Market conclusion signed</b><small> · Asha Quality</small>");
    expect(activity).toContain("from the complaint record");
    expect(activity).toContain("The audit trail");
    const timeline = activity.slice(activity.indexOf('class="uw-timeline"'), activity.indexOf("The audit trail"));
    expect(timeline).not.toMatch(/\b[A-Z]+_[A-Z_]+\b/);
  });

  it("gives the investigation the same shape: highlights and its sections as the path", () => {
    const html = render(
      <CaseHeader
        investigationId="i1"
        row={{
          id: "i1",
          business_id: "INV000001",
          investigation_question: "Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?",
          product_id: "p1",
          workflow_state: "OPEN",
          owner_name: "Asha Quality",
          priority: "HIGH",
        }}
        onStep={() => undefined}
        onSection={() => undefined}
        onChanged={() => undefined}
      />,
    );
    expect(html).toContain("Investigation · OrbitCare 300");
    expect(html).toContain("INV000001");
    for (const field of ["Owner", "Complaints in scope", "Lots in scope", "Blocking the decision"])
      expect(html).toContain(`<dt>${field}</dt>`);
    expect(html).toContain("uw-highlights");
  });
});

describe("Records leads with the latest signed record, and the finished story says so", () => {
  it("leads Records with the person's latest signed record, for any organization", () => {
    resources.data["/api/v1/oversight/latest-signed"] = {
      record: {
        what: "United States (FDA) conclusion: reportable",
        signed_at: "2026-11-03T08:00:00Z",
        signed_by: "Asha Quality",
        meaning: "",
        complaint: { id: "c-rv11", ref: "SAMPLE-RV-11" },
        investigation: null,
      },
    };
    const pilot = render(<NewRecordsSection />, api({ isTrial: false }));
    expect(pilot).toContain("Your latest signed record");
    expect(pilot).toContain("United States (FDA) conclusion: reportable · SAMPLE-RV-11");
    expect(pilot).toContain("Download the decision record (PDF)");
    expect(pilot).toContain("Open SAMPLE-RV-11");
    expect(pilot).toContain("All records");
    const alone = render(
      <LatestSigned
        record={{
          what: "Reportability guide version",
          signed_at: null,
          signed_by: null,
          meaning: null,
          complaint: null,
          investigation: null,
        }}
      />,
    );
    expect(alone).toContain("Open the decision records");
    resources.data["/api/v1/oversight/latest-signed"] = { record: null };
    expect(render(<NewRecordsSection />, api({ isTrial: false }))).not.toContain("Your latest signed record");
  });

  it("says the short story is finished instead of off its path", () => {
    const finished: ShortStory = {
      available: true,
      complaint: { id: "c-rv11", ref: "SAMPLE-RV-11" },
      steps: (["read", "route", "question", "summary"] as const).map((key) => ({ key, label: key, done: true })),
      current: 4,
      started: true,
      finished: true,
    } as unknown as ShortStory;
    resources.data[SHORT_STORY_PATH] = finished;
    const bar = render(<StoryBar section="Records" />, api({ story: "short" }));
    expect(bar).toContain("Story finished");
    expect(bar).toContain("Back to the stories");
    expect(bar).not.toContain("Off the story");
    expect(bar).not.toContain("Resume SAMPLE-RV-11");
  });
});

// Read as a file: the test run does not load stylesheets (as app/pageScale.test.ts does).
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const sheetText = (): string =>
  fs.readFileSync(new URL("./workspace.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");

describe("the phone's search", () => {
  it("is an icon at 390 px that opens the same search as the top bar's", () => {
    const html = renderToStaticMarkup(<GlobalSearch open={() => undefined} />);
    expect(html).toContain('class="uw-search-toggle"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('placeholder="Search complaints, products, reports"');
    const sheet = sheetText();
    const phone = sheet.slice(sheet.lastIndexOf("@media (max-width: 640px)"));
    expect(phone).toContain(".uw-search-toggle {\n    display: grid;");
    expect(phone).toContain(".uw-top .uw-search.is-open {");
  });
});
