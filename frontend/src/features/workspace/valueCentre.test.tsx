import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ValueCentre, summaryText, type ValueCentreData } from "./sections/ValueCentre";

// B6a P2 Value Centre v0 (B6-43, B6-44): the numbers as read, the baseline named, the QMS history apart, no person.
const resources = vi.hoisted(() => ({ data: null as unknown }));
vi.mock("../customer-admin/shared", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../customer-admin/shared")>();
  return {
    ...actual,
    useResource: (path: string | null) => ({ data: path ? resources.data : null, state: "ready", reload: vi.fn() }),
  };
});

const DATA: ValueCentreData = {
  go_live: "2026-09-01T00:00:00+00:00",
  baseline: { from: "2026-09-01T00:00:00+00:00", to: "2026-10-01T00:00:00+00:00", fixed: true },
  metrics: [
    {
      code: "TIME_TO_TRIAGE",
      label: "Time to triage",
      unit: "hours",
      definition: "From the record reaching MDARIX to its triage completed",
      baseline: { count: 2, median: 8, p90: 10 },
      months: [{ month: "2026-11", count: 1, median: 30, p90: 30 }],
      imported: { count: 5, median: 48, p90: 70 },
    },
    {
      code: "REPORT_COMPLETENESS",
      label: "Completeness of report fields",
      unit: "percent",
      definition: "Mandatory fields with a value in the approved report",
      baseline: { count: 0, median: null, p90: null },
      months: [],
      imported: null,
    },
  ],
};

const render = (on: boolean, permissions: string[] = ["data.export"]) => {
  resources.data = DATA;
  const api = { session: { b6: { value_centre: on }, business_permissions: permissions } } as unknown as WorkspaceApi;
  return renderToStaticMarkup(
    <WorkspaceContext.Provider value={api}>
      <ValueCentre />
    </WorkspaceContext.Provider>,
  );
};

describe("Value Centre", () => {
  it("says each number with its 90th percentile and count, or that it is not measured yet", () => {
    expect(summaryText({ count: 2, median: 8, p90: 10 }, "hours")).toBe("8 h (90 % within 10 h, 2 records)");
    expect(summaryText({ count: 1, median: 100, p90: 100 }, "percent")).toBe("100% (90 % at or below 100%, 1 record)");
    expect(summaryText({ count: 0, median: null, p90: null }, "days")).toBe("Not measured yet");
    expect(summaryText(undefined, "days")).toBe("Not measured yet");
  });

  it("shows the baseline, the latest month and the QMS history apart, and no person", () => {
    const html = render(true);
    expect(html).toContain("Your baseline: the first 30 days after go-live");
    expect(html).toContain("From your QMS export, before MDARIX");
    expect(html).toContain("8 h (90 % within 10 h, 2 records)");
    expect(html).toContain("2026-11: 30 h");
    expect(html).toContain("48 h (90 % within 70 h, 5 records)");
    expect(html).toContain("no one&#x27;s working time is tracked");
    // No QMS history for a measure: a dash (UTF-8, never a stray byte).
    expect(html).toMatch(/>—</);
    expect(html).not.toMatch(/(entered|approved|signed|triaged|completed) by/i);
  });

  it("is hidden while the server has the switch off", () => {
    expect(render(false)).toBe("");
  });
});
