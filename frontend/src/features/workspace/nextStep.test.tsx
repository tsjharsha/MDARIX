import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";

// Quality plan stage 7, "done when": a new user finds where to start within 10 seconds. The first screen after
// sign-in (My work on the new navigation) names the next action in its main button.
const answers: Record<string, unknown> = {};
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    data: path ? (Object.entries(answers).find(([key]) => path.startsWith(key))?.[1] ?? null) : null,
    state: "ready",
    error: null,
    reload: () => undefined,
  }),
}));

const { NextStep } = await import("./sections/MyWork");

const api = {
  session: { business_permissions: ["signal.triage", "records.write"], allowed_menu: ["home", "products"] },
  work: {},
  open: () => undefined,
  notify: () => undefined,
  navigation: "new",
} as unknown as WorkspaceApi;

const mainButton = () => {
  const html = renderToStaticMarkup(
    <WorkspaceContext.Provider value={api}>
      <NextStep />
    </WorkspaceContext.Provider>,
  );
  return /class="ac-primary"[^>]*>([^<]*)/.exec(html)?.[1]?.trim();
};

describe("the first screen names the next action in its main button", () => {
  it("is the soonest task assigned to me", () => {
    answers["/api/v1/tasks"] = {
      items: [
        {
          id: "t1",
          title: "Reportability decision for SAMPLE-RV-06: due Sun 8 Nov",
          task_type: "REPORTABILITY_DECISION",
        },
      ],
    };
    answers["/api/v1/oversight/alerts"] = { items: [] };
    expect(mainButton()).toBe("Reportability decision for SAMPLE-RV-06: due Sun 8 Nov");
  });

  it("is my most urgent reminder when no task is mine", () => {
    answers["/api/v1/tasks"] = { items: [] };
    answers["/api/v1/oversight/alerts"] = {
      items: [
        { title: "Reply due from Reporter of SAMPLE-RV-08", opens: { section: "Complaints", tab: "Communications" } },
      ],
    };
    expect(mainButton()).toBe("Reply due from Reporter of SAMPLE-RV-08");
  });

  it("is the complaints to triage when nothing waits for me", () => {
    answers["/api/v1/tasks"] = { items: [] };
    answers["/api/v1/oversight/alerts"] = { items: [] };
    expect(mainButton()).toBe("Triage the new complaints");
  });
});
