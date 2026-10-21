import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { SignalInbox, inboxEmpty } from "./sections/SignalInbox";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "./complaintList";
import { DEFAULT_SIGNAL_FILTERS, parseSignalsTab, signalListPath, signalsTab } from "./signals";

// 0.10.42: the Signal inbox's Data filter, as on the complaint list (0.10.41): All data, only your imported data, only
// the sample data, shown while the sample data is there. The server reads a signal's data from its complaints
// (GET /api/v1/triage/signals?source_system=..., backend/app/signals/service.py from_source).

const reads = vi.hoisted(() => ({ sources: [] as string[], paths: [] as string[] }));

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string) => {
    reads.paths.push(path);
    const data = {
      items: [],
      total: 3,
      page: 1,
      page_size: 50,
      counts_by_status: { NEW: 2, TRIAGE: 1 },
      sources: reads.sources,
      detection_pending: false,
    };
    return { state: "ready", data, reload: () => undefined };
  },
}));

vi.mock("./workspaceContext", () => ({
  useWorkspace: () => ({ work: { products: [] } }),
  useCan: () => false,
  sectionAllowed: () => true,
}));

const inbox = (sources: string[], source = "") => {
  reads.sources = sources;
  reads.paths = [];
  return renderToStaticMarkup(
    <SignalInbox initialFilters={{ ...DEFAULT_SIGNAL_FILTERS, source }} initialSignal={null} />,
  );
};

describe("the Signal inbox's Data filter", () => {
  it("is offered while the sample data is there, with the complaint list's words", () => {
    const html = inbox([IMPORTED_SOURCE, SAMPLE_SOURCE]);
    expect(html).toContain('aria-label="Data"');
    expect(html).toContain("All data");
    expect(html).toContain("Only your imported data");
    expect(html).toContain("Only the sample data");
    // Without the sample data every signal is the organization's own: no filter.
    expect(inbox([IMPORTED_SOURCE])).not.toContain('aria-label="Data"');
    expect(inbox([])).not.toContain('aria-label="Data"');
  });

  it("asks the server for the chosen data, so the list and the Open, New and All counts follow it", () => {
    const html = inbox([IMPORTED_SOURCE, SAMPLE_SOURCE], IMPORTED_SOURCE);
    expect(reads.paths.some((path) => path.includes(`source_system=${IMPORTED_SOURCE}`))).toBe(true);
    // The chips show the server's counts for the filtered list (here 2 new and 1 in triage: Open 3, All 3).
    expect(html).toMatch(/Open<span class="ac-tab-count">3<\/span>/);
    expect(html).toMatch(/All<span class="ac-tab-count">3<\/span>/);
    expect(signalListPath({ source: SAMPLE_SOURCE })).toContain(`source_system=${SAMPLE_SOURCE}`);
    expect(signalListPath({})).not.toContain("source_system");
  });

  it("keeps a chosen source in a link and says an empty filtered list matches nothing", () => {
    const tab = signalsTab({ filters: { source: IMPORTED_SOURCE } });
    expect(tab).toBe(`Signal inbox?source=${IMPORTED_SOURCE}`);
    expect(parseSignalsTab(tab).filters.source).toBe(IMPORTED_SOURCE);
    expect(parseSignalsTab("Signal inbox?source=<script>").filters.source).toBe("");
    expect(parseSignalsTab(undefined).filters.source).toBe("");
    expect(inboxEmpty({ ...DEFAULT_SIGNAL_FILTERS, source: SAMPLE_SOURCE }, false).title).toBe("No matching signals");
  });
});
