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
import { SHORT_STORY_PATH, resumeText, stepText, type ShortStory } from "./shortStory";
import { ResumeShortStory } from "./sections/ShortStory";
import { StoryBar } from "./sections/Entrance";
import { PracticeApproval } from "./sections/PracticeApproval";
import { DecisionRecord } from "./sections/Oversight";

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

  it("offers Discuss a pilot in Help instead of your own data on the classic navigation", () => {
    const classic = { navigation: "classic" };
    const normal = render(<HelpMenu onGettingStarted={() => undefined} defaultOpen />, api(classic));
    expect(normal).toContain("Getting started and import templates");
    expect(normal).not.toContain("Discuss a pilot");
    const sample = render(
      <HelpMenu onGettingStarted={() => undefined} defaultOpen />,
      api(classic, { sample_only: true }),
    );
    expect(sample).toContain("Discuss a pilot");
    expect(sample).toContain("This evaluation uses the sample only");
    expect(sample).not.toContain("import templates");
    // 0.10.87: the new navigation's Help offers neither; the top bar and the Next steps tab do.
    const fresh = render(<HelpMenu onGettingStarted={() => undefined} defaultOpen />, api({}, { sample_only: true }));
    expect(fresh).not.toContain("Discuss a pilot");
  });

  it("offers the upload on the Complaints header in a trial (0.10.79) and a pilot, never in a sample-only trial", () => {
    expect(render(<ComplaintViews />, api())).toContain("Import your data");
    expect(render(<ComplaintViews />, api({}, { sample_only: true }))).not.toContain("Import your data");
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

/** The server's short story at step ``current`` (backend/app/trial/short_story.py), trimmed to what the screens read. */
function shortStory(current: number): ShortStory {
  const labels = ["Read the call", "Decide the route", "Name the open question", "The intake decision summary"];
  return {
    available: true,
    complaint: { id: "c-rv11", ref: "SAMPLE-RV-11" },
    steps: labels.map((label, index) => ({
      key: (["read", "route", "question", "summary"] as const)[index],
      label,
      done: index < current,
    })),
    current,
    started: current > 0,
    finished: current === 4,
    call: {
      words: rv11().event.description!,
      phrases: [
        { text: "SpO2 read 4 to 6 points high", why: "A wrong reading: the device did not perform as intended." },
        { text: "sent for service", why: "The hospital asked for service: linked service work." },
      ],
      facts: [
        { label: "Harm", value: "None reported" },
        { label: "Malfunction", value: "Yes" },
      ],
    },
    route: {
      decision: "Complaint, with linked service work",
      source_quote: "its SpO2 read 4 to 6 points high on two patients",
      source_fact: "Malfunction recorded: yes.",
      owner_name: "Asha Quality",
      recorded_by: "Asha Quality",
      immediate_action: null,
    },
    question: {
      suggested: "Did any treatment decision rely on the high SpO2 readings?",
      why: "It decides the consequence.",
      asked:
        current > 2
          ? {
              id: "q-1",
              subject: "Did any treatment decision rely on the high SpO2 readings?",
              owner_name: "Asha Quality",
              due_on: "2026-11-04",
              status: "OPEN",
              logged_by: "Asha Quality",
            }
          : null,
      consequence: "Not known until the hospital answers",
    },
    service: rv11({ owner_id: "u1", owner_name: "Asha Quality" }).service!,
    markets: [
      {
        market: "US",
        label: "United States (FDA)",
        state: "Not assessed yet: still open",
        open: true,
        deadline: "Tue 1 Dec 2026, 23:59 EST",
        deadline_title: "United States (FDA): not assessed yet, provisional deadline",
        why: null,
      },
      {
        market: "IN",
        label: "India (CDSCO)",
        state: "Not assessed yet: still open",
        open: true,
        deadline: null,
        deadline_title: null,
        why: "Assessed because your procedure asks every market where this device is sold to be assessed.",
      },
    ],
    next: { action: "Assess the United States (FDA) market", who: "Asha Quality" },
    people: {
      prepared_by: ["Asha Quality"],
      may_approve: ["Asha Quality"],
      approved_by: [],
      practice: true,
      practice_note: "Practice approval: in a pilot a colleague approves this.",
    },
    practice_label: "Practice record: made in a free trial with sample or de-identified data.",
  };
}

const onPage = (current: number, tab = "Summary?ref=SAMPLE-RV-11") => {
  resources.data[eventPath("SAMPLE-RV-11")] = rv11();
  resources.data[SHORT_STORY_PATH] = shortStory(current);
  return render(<ComplaintPage tab={tab} />, api({ story: "short" }, { user_id: "u1" }));
};

describe("A4: the short story, from what was saved", () => {
  it("reads the call with the phrases that make it a possible complaint, and the facts beside them", () => {
    const html = onPage(0);
    expect(html).toContain("Step 1 of 4: read the call");
    expect(html).toContain("<mark>SpO2 read 4 to 6 points high</mark>");
    expect(html).toContain("<mark>sent for service</mark>");
    expect(html).toContain("None reported");
    expect(html).toContain(">Decide the route");
  });

  it("decides the route with both owners, then names the one open question", () => {
    const route = onPage(1);
    expect(route).toContain("Complaint, with linked service work");
    expect(route).toContain("<q>its SpO2 read 4 to 6 points high on two patients</q>");
    expect(route).toContain("Complaint owner (Quality)");
    expect(route).toContain("Service owner");
    expect(route).toContain("Confirm the route");
    const question = onPage(2);
    expect(question).toContain("Step 3 of 4: name the open question");
    expect(question).toContain("Reply due");
    expect(question).toContain("not known until the hospital answers");
    expect(question).toContain("Record the question");
  });

  it("ends in the intake decision summary, printable, with the full evaluation as its main button", () => {
    const html = onPage(4);
    for (const text of [
      "Intake decision summary · SAMPLE-RV-11",
      "Route chosen",
      "Complaint, with linked service work",
      "The fact it rests on",
      "Owner: Asha Quality; reply due",
      "In progress · SVC-24-1107 (sample service ticket) · owner Asha Quality",
      "Market assessments (United States, India)",
      "United States (FDA):</strong> still open; provisional deadline Tue 1 Dec 2026",
      "India (CDSCO):</strong> still open. Assessed because your procedure asks every market",
      "Who acts next",
      "Asha Quality: Assess the United States (FDA) market",
      "Prepared by",
      "May approve",
      "Not yet: the market assessments are still open",
      "Practice approval: in a pilot a colleague approves this.",
      "Continue the full evaluation",
      "Print or save as PDF",
    ])
      expect(html, text).toContain(text);
  });

  it("shows the story bar's step from the saved actions, and off the record the way back", () => {
    resources.data[SHORT_STORY_PATH] = shortStory(1);
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    const bar = (section: string, tab?: string) =>
      render(<StoryBar section={section} tab={tab} />, api({ story: "short" }));
    // The same screen, another step: the bar follows the record, not the place.
    expect(bar("Complaint", "Summary?ref=SAMPLE-RV-11")).toContain("Step 2 of 4: Decide the route");
    resources.data[SHORT_STORY_PATH] = shortStory(3);
    expect(bar("Complaint", "Summary?ref=SAMPLE-RV-11")).toContain("Step 4 of 4: The intake decision summary");
    const away = bar("Complaints", "Reporting");
    expect(away).toContain("Off the story&#x27;s path");
    expect(away).toContain("Resume SAMPLE-RV-11");
    expect(bar("Complaint", "Summary?ref=SAMPLE-RV-06")).toContain("Off the story&#x27;s path");
  });

  it("puts unfinished work first: Resume SAMPLE-RV-11 · step N of 4", () => {
    expect(resumeText(shortStory(0))).toBeNull();
    expect(resumeText(shortStory(2))).toBe("Resume SAMPLE-RV-11 · step 3 of 4");
    expect(resumeText(shortStory(4))).toBeNull();
    expect(stepText(shortStory(1))).toBe("Step 2 of 4: Decide the route");
    expect(stepText(shortStory(4))).toBe("Step 4 of 4: The intake decision summary · done");
    resources.data[SHORT_STORY_PATH] = shortStory(2);
    expect(render(<ResumeShortStory />, api())).toContain("Resume SAMPLE-RV-11 · step 3 of 4");
    expect(render(<ResumeShortStory />, api({ isTrial: false }))).not.toContain("Resume");
  });
});

const sources = import.meta.glob(["./sections/*.tsx"], { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;
const source = (name: string) => sources[`./sections/${name}.tsx`] ?? "";

describe("A6: separation of duties, shown honestly", () => {
  it("labels a solo trial owner's own approval at the button", () => {
    expect(renderToStaticMarkup(<PracticeApproval shown />)).toContain(
      "Practice approval: in a pilot a colleague approves this.",
    );
    expect(renderToStaticMarkup(<PracticeApproval shown={false} />)).toBe("");
    // Beside the approve button of a report snapshot and of a decision guide version (stage 3's practice exception).
    expect(source("Reports")).toMatch(
      /"Approve"\}\s*<\/button>\s*<PracticeApproval shown=\{standing\?\.same_person\} \/>/, // 0.10.83: plain words
    );
    expect(source("DecisionGuides")).toMatch(
      /Approve and publish"\}\s*<\/button>\s*<PracticeApproval shown=\{view\.approval\?\.same_person\} \/>/,
    );
  });

  it("names who prepared, who may approve and who approved on the decision record", () => {
    const view = {
      ...rv11(),
      record_people: {
        prepared_by: ["Asha Quality"],
        may_approve: ["Asha Quality"],
        approved_by: [],
        practice_note: "Practice approval: in a pilot a colleague approves this.",
      },
    } as EventView;
    const html = render(<DecisionRecord view={view} onChanged={() => undefined} />, api());
    expect(html).toContain("<dt>Prepared by</dt><dd>Asha Quality</dd>");
    expect(html).toContain("<dt>May approve</dt><dd>Asha Quality</dd>");
    expect(html).toContain("Nobody yet");
    expect(html).toContain("Practice approval: in a pilot a colleague approves this.");
  });
});

describe("F1 (0.10.72): Confirm the route never saves a harm judgement silently", () => {
  it("shows the reporter's statement, the unknown effect, the proposed severity to confirm, and what the click records", () => {
    const route = onPage(1);
    expect(route).toContain("<q>No harm was reported</q>");
    expect(route).toContain("Unknown: asked of the hospital in step 3.");
    expect(route).not.toContain("Negligible: no harm was reported");
    expect(route).toContain("Proposed: ");
    expect(route).toContain("I confirm the triage severity: ");
    expect(route).toContain("Confirm the route records");
    // Nothing is saved until the severity is confirmed or changed: the button waits (it was enabled before 0.10.72).
    expect(route).toMatch(/<button type="button" class="ac-primary" disabled=""[^>]*>Confirm the route/);
    expect(route).toContain("Confirm or change the triage severity first.");
  });
});

describe("Addendum 2 (0.10.72): the full evaluation counts its progress from the complaint's own checklist", () => {
  it("reads the step from the saved records on the complaint's page, and keeps Off the story's path", () => {
    resources.data[SHORT_STORY_PATH] = {
      ...shortStory(4),
      full_evaluation: {
        current: 2,
        steps: ["read", "triage", "markets", "report", "disposition", "decision", "ready"].map((key, index) => ({
          key,
          done: index < 2,
        })),
      },
    };
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    const bar = (section: string, tab?: string) =>
      render(<StoryBar section={section} tab={tab} />, api({ story: "reportable" }));
    // The complaint's Summary is open, but its triage is done: the step is the market assessment (0.10.71 read the
    // screen and said step 1).
    expect(bar("Complaint", "Summary?ref=SAMPLE-RV-11")).toContain("Step 3 of 7: Assess the US, then India");
    expect(bar("Complaint", "Summary?ref=SAMPLE-RV-06")).toContain("Off the story&#x27;s path");
  });
});
