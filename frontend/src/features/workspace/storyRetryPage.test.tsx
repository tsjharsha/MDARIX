import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { GettingStartedSection } from "./sections/GettingStarted";
import { DETECTION_STATUS_PATH } from "./signals";
import { TRIAL_STORY_PATH } from "./trialStory";

// 0.10.43: Getting started reads its story with retry (storyRetry.test.ts), so a reload that fails during or after an
// import is read again; and while the import's signals are found it asks the small status read meanwhile.

const reads = vi.hoisted(() => ({ calls: [] as Array<{ path: string | null; options: any }> }));

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null, options: unknown = {}) => {
    reads.calls.push({ path, options });
    return { state: "loading", data: null, reload: () => undefined };
  },
}));

describe("Getting started's story", () => {
  it("is read with retry, and again once the import's signals are found", () => {
    const api = {
      session: { allowed_menu: [], business_permissions: [] },
      open: vi.fn(),
      notify: vi.fn(),
      work: { products: [], setInvestigationId: vi.fn() },
    } as unknown as WorkspaceApi;
    renderToStaticMarkup(
      <WorkspaceContext.Provider value={api}>
        <GettingStartedSection />
      </WorkspaceContext.Provider>,
    );
    const story = reads.calls.find((call) => call.path === TRIAL_STORY_PATH);
    expect(story?.options.retry).toBe(true);
    expect(story?.options.statusPath).toBe(DETECTION_STATUS_PATH);
    expect(story?.options.refreshWhile({ signals_pending: true })).toBe(true);
    expect(story?.options.refreshWhile({ signals_pending: false })).toBe(false);
  });
});
