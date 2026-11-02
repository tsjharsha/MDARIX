import { createContext } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { SignalInbox } from "./sections/SignalInbox";
import { DEFAULT_SIGNAL_FILTERS } from "./signals";
import { trendCountText, trendHeadline } from "./signalAi";

// 0.10.44: the Signal inbox's Complaints column showed "2290" beside a title saying "2,290 complaints": its counts are
// grouped the en-US way, as the list headings and the import result are (DEV-025), whatever the browser's language.

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({
    state: "ready",
    data: {
      items: [
        {
          id: "7b7f3c55-4d0e-4c8e-9b55-0d4f7f1d2a10",
          business_id: "SIG000001",
          title: "2,290 complaints: unspecified problem on Aster Pump Rev C in 30 days",
          status: "NEW",
          problem_key: "UNSPECIFIED",
          complaint_count: 2290,
          recent_complaints_7d: 1204,
          suggested_priority: "HIGH",
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
      counts_by_status: { NEW: 1203, TRIAGE: 1 },
      sources: [],
      detection_pending: false,
    },
    reload: () => undefined,
  }),
}));

vi.mock("./workspaceContext", () => ({
  useWorkspace: () => ({ work: { products: [] } }),
  useCan: () => false,
  sectionAllowed: () => true,
  // The shown signal is part of the screen's address in the workspace; here none is shown.
  useTabParam: () => [null, () => undefined],
  WorkspaceContext: createContext(null),
}));

describe("the Signal inbox's counts", () => {
  it("group thousands in the Complaints column and the status chips", () => {
    const html = renderToStaticMarkup(<SignalInbox initialFilters={DEFAULT_SIGNAL_FILTERS} initialSignal={null} />);
    expect(html).toContain("<strong>2,290</strong>");
    expect(html).toContain("1,204 in last 7 days");
    expect(html).toMatch(/New<span class="ac-tab-count">1,203<\/span>/);
    expect(html).not.toContain(">2290<");
  });

  it("group thousands in the trend check's counts", () => {
    expect(trendCountText({ recent: 2290, expected: 1204.46, ratio: 1.9, result: "SIGNIFICANT" })).toBe(
      "2,290 against 1,204.5 expected (1.9× expected)",
    );
    expect(trendCountText({ recent: 2290, expected: 0, ratio: null, result: "SHORT_HISTORY" })).toBe(
      "2,290 in 30 days",
    );
    const board = { summary: { significant: 0, elevated: 0, groups: 12, complaints_counted: 4993 } };
    expect(trendHeadline(board as Parameters<typeof trendHeadline>[0]).detail).toContain("4,993 complaints counted");
  });
});
