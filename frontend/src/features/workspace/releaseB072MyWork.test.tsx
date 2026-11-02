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
    work: {},
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
    expect(html).toContain("Due soon or overdue · 2");
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
