import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { FINDING_SIGNALS_TRIAGE, SignalTriageSummary } from "./sections/SignalInbox";
import { HomeTile } from "./sections/Readiness";
import { DETECTION_STATUS_PATH, FINDING_SIGNALS_NOW, WHILE_FINDING_SIGNALS } from "./signals";
import type { ReadinessCheck } from "./readiness";

// 0.10.41: right after an import, the dashboard's Signal triage and Readiness say that its signals are being found, as
// Getting started and the Signal inbox already did (0.10.40), and read them again once they are, after the same light
// status read (useResource's refreshWhile and statusPath, as background reads).

const reads = vi.hoisted(() => ({ pending: false, calls: [] as Array<{ path: string; options: unknown }> }));

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string, options: unknown) => {
    reads.calls.push({ path, options });
    const data = path.startsWith("/api/v1/triage/summary")
      ? { counts: { new: 2 }, by_priority: {}, detection_pending: reads.pending }
      : { items: [], total: 0, page: 1, page_size: 5, detection_pending: reads.pending };
    return { state: "ready", data, reload: () => undefined };
  },
}));

const panel = (pending: boolean) => {
  reads.pending = pending;
  reads.calls = [];
  return renderToStaticMarkup(<SignalTriageSummary onOpen={() => undefined} />);
};

const trends = (): ReadinessCheck =>
  ({
    code: "TRENDS_WITHOUT_ACTION",
    title: "Trends without action",
    value: 0,
    state: "CLEAR",
    detail: "No significant trend is waiting for a decision or a case",
    why: "Trends must reach CAPA and the risk file.",
    basis: [],
    opens: { section: "Signals", tab: null },
    items: [],
  }) as unknown as ReadinessCheck;

describe("Finding signals on the dashboard and on Readiness", () => {
  it("says so on the dashboard's Signal triage while they are found, and reads both its sources again after", () => {
    const html = panel(true);
    expect(html).toContain(FINDING_SIGNALS_TRIAGE);
    expect(FINDING_SIGNALS_TRIAGE).toBe(
      "Finding signals in the complaints you just imported… The counts update by themselves when they are ready.",
    );
    expect(html).toContain("Finding signals…");
    expect(html).not.toContain("No open signals");
    // The summary and the open signals both wait with the status read.
    expect(reads.calls.map((call) => call.options)).toEqual([WHILE_FINDING_SIGNALS, WHILE_FINDING_SIGNALS]);
    expect(WHILE_FINDING_SIGNALS.statusPath).toBe(DETECTION_STATUS_PATH);
    expect(WHILE_FINDING_SIGNALS.refreshWhile({ detection_pending: true })).toBe(true);
    expect(WHILE_FINDING_SIGNALS.refreshWhile({})).toBe(false);
    const done = panel(false);
    expect(done).not.toContain(FINDING_SIGNALS_NOW);
    expect(done).toContain("No open signals");
  });

  it("says so on Readiness's trend check instead of its number", () => {
    const finding = renderToStaticMarkup(<HomeTile check={trends()} onOpen={() => undefined} finding />);
    expect(finding).toContain(FINDING_SIGNALS_NOW);
    expect(finding).toContain("Finding signals");
    expect(finding).toContain("…");
    expect(finding).not.toContain("No significant trend is waiting");
    const done = renderToStaticMarkup(<HomeTile check={trends()} onOpen={() => undefined} />);
    expect(done).not.toContain(FINDING_SIGNALS_NOW);
    expect(done).toContain("No significant trend is waiting");
  });
});
