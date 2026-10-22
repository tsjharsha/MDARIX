import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintList } from "./sections/ComplaintList";
import { listTitle } from "./sections/common";

// 0.10.43: the complaint list's heading was "Complaints in your organization · 4993": the count after a sentence read
// as a stray separator, it was not written with a thousands separator, and it counts the complaints the filters
// choose, not the organization's. It is now named like the other lists, the list's name and its count.

const reads = vi.hoisted(() => ({ total: 4993 as number | undefined }));

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({
    state: "ready",
    data: { items: [], total: reads.total, page: 1, pages: 1, sources: [], versions: [] },
    reload: () => undefined,
  }),
}));

const render = () =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { allowed_menu: [], business_permissions: [] },
          open: vi.fn(),
          work: { products: [] },
        } as unknown as WorkspaceApi
      }
    >
      <ComplaintList eyebrow="Complaints" />
    </WorkspaceContext.Provider>,
  );

describe("list headings", () => {
  it("name the list, then its count with a thousands separator", () => {
    expect(listTitle("Signal inbox", 2)).toBe("Signal inbox · 2");
    expect(listTitle("Complaint list", 4993)).toBe("Complaint list · 4,993");
    expect(listTitle("Complaint list", 0)).toBe("Complaint list · 0");
    // Until the list is read, the name alone: never a separator with nothing after it.
    expect(listTitle("Complaint list", undefined)).toBe("Complaint list");
    expect(listTitle("Complaint list", null)).toBe("Complaint list");
  });

  it("shows the complaint list as the Signal inbox is shown", () => {
    const html = render();
    expect(html).toContain("<h2>Complaint list · 4,993</h2>");
    expect(html).not.toContain("in your organization");
    reads.total = undefined;
    expect(render()).toContain("<h2>Complaint list</h2>");
  });
});
