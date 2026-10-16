import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintsSection } from "./sections/Complaints";
import { ComplaintFilterBar } from "./sections/ComplaintList";
import {
  EMPTY_COMPLAINT_FILTERS,
  complaintListPath,
  complaintListTab,
  hasComplaintFilters,
  insightComplaintFilters,
  parseComplaintListTab,
  sourceText,
  versionChoices,
  versionValue,
} from "./complaintList";

function workspace(): WorkspaceApi {
  return {
    session: { allowed_menu: ["products", "investigations"], business_permissions: [] },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [{ id: "p-1", name: "OrbitCare 300" }], requestOpenInvestigation: vi.fn() },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace()}>{node}</WorkspaceContext.Provider>);

describe("the complaint list's filters", () => {
  it("asks the server for each filter set, paged", () => {
    expect(complaintListPath(EMPTY_COMPLAINT_FILTERS, 1)).toBe("/api/v1/complaints?page=1&page_size=50");
    const path = complaintListPath(
      {
        ...EMPTY_COMPLAINT_FILTERS,
        productId: "p-1",
        version: "PVR000002",
        lot: " LOT-003 ",
        problemCode: "NFF",
        country: "US",
        source: "MDARIX_SAMPLE",
      },
      2,
      { sort: "received", order: "asc" },
    );
    const params = new URL(path, "https://x.test").searchParams;
    expect(Object.fromEntries(params)).toEqual({
      page: "2",
      page_size: "50",
      sort: "received",
      order: "asc",
      product_id: "p-1",
      version: "PVR000002",
      lot: "LOT-003",
      problem_code: "NFF",
      country: "US",
      source_system: "MDARIX_SAMPLE",
    });
  });

  it("carries filters in a tab name and reads them back", () => {
    expect(complaintListTab()).toBe("Complaint list");
    const tab = complaintListTab({ version: "PVR000002", country: "United States" });
    expect(tab).toBe("Complaint list?version=PVR000002&country=United+States");
    expect(parseComplaintListTab(tab)).toEqual({
      isList: true,
      filters: { ...EMPTY_COMPLAINT_FILTERS, version: "PVR000002", country: "United States" },
    });
    expect(parseComplaintListTab("Backlog").isList).toBe(false);
    expect(parseComplaintListTab(undefined)).toEqual({ isList: false, filters: EMPTY_COMPLAINT_FILTERS });
    expect(hasComplaintFilters(EMPTY_COMPLAINT_FILTERS)).toBe(false);
    expect(hasComplaintFilters({ ...EMPTY_COMPLAINT_FILTERS, lot: "L-1" })).toBe(true);
  });

  it("takes Automatic insights' filters and source", () => {
    const filters = insightComplaintFilters(
      { version: "PVR000002", lot: "SAMPLE-ORBIT-300-LOT-003", code: "NFF", country: "US" },
      "MDARIX_SAMPLE",
    );
    expect(parseComplaintListTab(complaintListTab(filters)).filters).toEqual({
      ...EMPTY_COMPLAINT_FILTERS,
      version: "PVR000002",
      lot: "SAMPLE-ORBIT-300-LOT-003",
      problemCode: "NFF",
      country: "US",
      source: "MDARIX_SAMPLE",
    });
    // No filter on the panel: every complaint of its data.
    expect(complaintListTab(insightComplaintFilters({}, "TRIAL_UPLOAD"))).toBe(
      "Complaint list?source_system=TRIAL_UPLOAD",
    );
    expect(sourceText("MDARIX_SAMPLE")).toBe("Only the sample data");
    expect(sourceText("TRIAL_UPLOAD")).toBe("Only your imported data");
  });

  it("offers the chosen product's versions only", () => {
    const versions = [
      { id: "v-1", business_id: "PVR000001", product_id: "p-1", label: "OrbitCare 300 Rev A" },
      { id: "v-2", business_id: null, product_id: "p-2", label: "PulseWatch 410 Rev A" },
    ];
    expect(versionChoices(versions, "")).toHaveLength(2);
    expect(versionChoices(versions, "p-1").map(versionValue)).toEqual(["PVR000001"]);
    expect(versionValue(versions[1])).toBe("v-2");
  });
});

describe("Complaints › Complaint list", () => {
  it("is a tab of Complaints that a link opens", () => {
    const markup = render(<ComplaintsSection tab="Complaint list?version=PVR000002&country=US" />);
    expect(markup).toMatch(/aria-selected="true"[^>]*>Complaint list</);
    expect(markup).toContain("Loading Complaints in your organization");
  });

  it("shows the filters chosen, with what the complaints record to choose from", () => {
    const data = {
      problem_codes: ["NFF", "OCCLUSION"],
      countries: ["Germany", "US"],
      statuses: ["open"],
      versions: [
        { id: "v-1", business_id: "PVR000001", product_id: "p-1", label: "OrbitCare 300 Rev A" },
        { id: "v-2", business_id: "PVR000002", product_id: "p-1", label: "OrbitCare 300 Rev B" },
        { id: "v-3", business_id: "PVR000003", product_id: "p-2", label: "PulseWatch 410 Rev A" },
      ],
    };
    const filters = {
      ...parseComplaintListTab("Complaint list?version=PVR000002&lot=LOT-003&problem_code=NFF&country=US").filters,
      productId: "p-1",
      source: "MDARIX_SAMPLE",
    };
    const markup = render(
      <ComplaintFilterBar
        filters={filters}
        data={data}
        products={[{ id: "p-1", name: "OrbitCare 300" }]}
        onChange={vi.fn()}
      />,
    );
    expect(markup).toMatch(/<option value="PVR000002" selected="">OrbitCare 300 Rev B<\/option>/);
    expect(markup).not.toContain("PulseWatch 410 Rev A"); // another product's version
    expect(markup).toMatch(/<option value="NFF" selected="">NFF<\/option>/);
    expect(markup).toMatch(/<option value="US" selected="">US<\/option>/);
    expect(markup).toContain('value="LOT-003"');
    expect(markup).toContain("Only the sample data");
    expect(markup).toContain("Clear filters");
    // A value from a link that the list does not offer stays chosen; no filter, no Clear filters.
    const unknown = render(
      <ComplaintFilterBar
        filters={{ ...EMPTY_COMPLAINT_FILTERS, country: "Narnia" }}
        data={data}
        products={[]}
        onChange={vi.fn()}
      />,
    );
    expect(unknown).toMatch(/<option value="Narnia" selected="">Narnia<\/option>/);
    expect(
      render(<ComplaintFilterBar filters={EMPTY_COMPLAINT_FILTERS} data={data} products={[]} onChange={vi.fn()} />),
    ).not.toContain("Clear filters");
  });
});
