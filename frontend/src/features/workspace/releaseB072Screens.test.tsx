import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { taskListPath } from "./tasks";
import { ALERTS } from "./oversight";
import { SHORT_STORY_PATH } from "./shortStory";

// Release B (0.10.72), B4: My work leads with the single most urgent item; every other urgent obligation stays
// visible with its deadline; team numbers, completed work, queues and filters are revealed on request.
const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && (resources.data[path] ?? resources.data[path.split("?")[0]])) ?? null,
    reload: () => undefined,
  }),
}));
const { NewMyWorkSection } = await import("./sections/MyWork");

const api = (permissions: string[] = ["quality.review", "signal.triage"]) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: permissions },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
  }) as unknown as WorkspaceApi;
const render = () =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={api()}>
      <NewMyWorkSection />
    </WorkspaceContext.Provider>,
  );

const task = (id: string, title: string, due: string, overdue: boolean) => ({
  id,
  task_type: "COMMUNICATION_REPLY",
  title,
  status: "ASSIGNED",
  due_at: due,
  overdue,
  source: { label: "Communication" },
  assigned_user: { id: "u1", name: "Asha Quality" },
});
const LEAD = task("t1", "Reply due from Reporter of SAMPLE-RV-08", "2026-10-30T18:29:00Z", true);
const SOON = task("t2", "Approve snapshot 1 of the Form FDA 3500A", "2099-01-01T10:00:00Z", false);

function seed(resume: boolean) {
  resources.data = {
    [taskListPath("assigned", 1, 1)]: { items: [LEAD] },
    [taskListPath("overdue", 1, 20)]: { items: [LEAD] },
    [taskListPath("due_soon", 1, 20)]: { items: [SOON] },
    [ALERTS]: { items: [], unread: 0, escalations: 0, absences: [], people: [], never: "" },
    [SHORT_STORY_PATH]: resume
      ? {
          available: true,
          current: 2,
          started: true,
          finished: false,
          complaint: { id: "c1", ref: "SAMPLE-RV-11" },
          steps: [1, 2, 3, 4].map((n) => ({ key: `s${n}`, label: `Step ${n}`, done: n < 3, done_at: null })),
        }
      : { available: true, current: 0, started: false, finished: false, steps: [] },
  };
}

describe("B4: My work leads with one item, and keeps every urgent obligation in sight", () => {
  it("leads with the most urgent item: why, owner and deadline", () => {
    seed(false);
    const html = render();
    expect(html).toContain("Your next step");
    expect(html).toMatch(/class="ac-primary"[^>]*>Reply due from Reporter of SAMPLE-RV-08/);
    expect(html).toMatch(/class="uw-next-why">Communication · [^<]* · overdue · Owner: Asha Quality/);
  });

  it("lists every other urgent obligation with its deadline, never hidden", () => {
    seed(false);
    const html = render();
    // The lead is not listed again: the other urgent task, with its deadline.
    expect(html).toContain("Due soon or overdue · 1");
    expect(html).toContain("<strong>Approve snapshot 1 of the Form FDA 3500A</strong>");
    // Not inside a closed disclosure: the urgent list comes before "All my work".
    expect(html.indexOf("Due soon or overdue")).toBeLessThan(html.indexOf("All my work"));
  });

  it("reveals the team numbers, the queues, completed work and the filters on request", () => {
    seed(false);
    const html = render();
    expect(html).toContain("<summary>Team numbers</summary>");
    expect(html).toMatch(/<details class="uw-more uw-mw-all"><summary>All my work: tasks, approvals/);
  });

  it("makes the next step secondary while Resume SAMPLE-RV-11 shows (Addendum 2): one main button", () => {
    seed(true);
    const html = render();
    expect(html).toContain("Resume SAMPLE-RV-11 · step 3 of 4");
    expect(html).toMatch(/class="ac-secondary"[^>]*>Reply due from Reporter of SAMPLE-RV-08/);
  });
});

const { TrendCheck } = await import("./sections/TrendCheck");
const { risingSentence, comparisonLine, trendPath } = await import("./signalAi");

const ROW = {
  key: "orbit|revb|",
  product: { id: "p1", business_id: "PROD000001", name: "OrbitCare 300" },
  product_version: { id: "v1", business_id: "VER000002", version_identifier: "Rev B" },
  problem: null,
  name: "OrbitCare 300 Rev B",
  recent: 9,
  recent_days: 30,
  history: 6,
  history_days: 180,
  expected: 0.96,
  p_value: 0.0001,
  p_adjusted: 0.0002,
  ratio: 9.3,
  result: "SIGNIFICANT" as const,
  label: "Significant rise",
  sentence: "",
  recent_complaints: [],
  open_signals: [],
  basis: "UNITS" as const,
  baseline: "PREVIOUS_VERSION" as const,
  baseline_name: "OrbitCare 300 Rev A",
  lots: ["SAMPLE-ORBIT-300-LOT-003", "SAMPLE-ORBIT-300-LOT-004"],
};

describe("B5: Trends leads with one sentence per rising group", () => {
  it("says the rise, its lots and the comparison basis, and says plainly when units are missing", () => {
    expect(risingSentence(ROW)).toBe("OrbitCare 300 Rev B: 9 complaints against 1.0 expected (9.3×), lots 003 and 004");
    expect(comparisonLine(ROW)).toBe(
      "Compared with OrbitCare 300 Rev A: 6 in the 180 days before this version's release · per unit in the field",
    );
    expect(comparisonLine({ ...ROW, basis: "TIME", baseline: "OWN_HISTORY" })).toBe(
      "Compared with its own history: 6 in 180 days · Units not imported: compared by calendar days",
    );
  });

  it("shows the sentences first; statistics, every group, the grouping controls and the chart on request", () => {
    resources.data = {
      [trendPath("version", "")]: {
        grouping: "version",
        recent_days: 30,
        history_days: 180,
        min_complaints: 3,
        summary: {
          groups: 6,
          groups_tested: 2,
          complaints_counted: 44,
          significant: 1,
          elevated: 0,
          too_few: 4,
          short_history: 0,
        },
        items: [ROW, { ...ROW, key: "pulse", name: "PulseWatch 410 Rev A", result: "STEADY", lots: [] }],
        note: "",
        basis: { units: 2, time: 0, single_use: 0 },
      },
    };
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api()}>
        <TrendCheck onOpenSignal={() => undefined} />
      </WorkspaceContext.Provider>,
    );
    const lead = html.indexOf("OrbitCare 300 Rev B: 9 complaints against 1.0 expected (9.3×), lots 003 and 004");
    const revealed = html.indexOf("<summary>All groups, the method and the chart</summary>");
    expect(lead).toBeGreaterThan(-1);
    expect(revealed).toBeGreaterThan(lead);
    // The steady group, the tiles and the grouping controls are inside the disclosure.
    expect(html.indexOf("PulseWatch 410 Rev A")).toBeGreaterThan(revealed);
    expect(html.indexOf("Groups checked")).toBeGreaterThan(revealed);
    expect(html).toContain("Results allow for the 2 groups assessed.");
  });
});

const { NewRecordsSection } = await import("./sections/Records");

describe("B6: Records leads with the record of the work just finished", () => {
  const records = (done: boolean) => {
    resources.data = {
      [SHORT_STORY_PATH]: {
        available: true,
        current: done ? 4 : 2,
        finished: done,
        started: true,
        complaint: { id: "c1", ref: "SAMPLE-RV-11" },
        steps: [1, 2, 3, 4].map((n) => ({ key: `s${n}`, label: `Step ${n}`, done: done || n < 3, done_at: null })),
      },
    };
    return renderToStaticMarkup(
      <WorkspaceContext.Provider
        value={
          {
            ...api(["data.export"]),
            session: { allowed_menu: ["home"], business_permissions: ["data.export"] },
          } as never
        }
      >
        <NewRecordsSection />
      </WorkspaceContext.Provider>,
    );
  };
  it("leads with the intake decision summary and its Download; every other record behind All records", () => {
    const html = records(true);
    const lead = html.indexOf("Intake decision summary · SAMPLE-RV-11");
    expect(lead).toBeGreaterThan(-1);
    expect(html).toContain("Download the decision record (PDF)");
    expect(html.indexOf("<summary>All records: ")).toBeGreaterThan(lead);
    expect(html.indexOf("Inspection readiness")).toBeGreaterThan(html.indexOf("<summary>All records: "));
  });
  it("opens as before while nothing is finished", () => {
    const html = records(false);
    expect(html).not.toContain("The work you just finished");
    expect(html).not.toContain("<summary>All records: ");
  });
});
