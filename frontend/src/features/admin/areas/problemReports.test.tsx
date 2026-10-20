import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ProblemReports, replyLink, type ProblemReport } from "./ProblemReports";
import { Operations } from "./Operations";
import { OPERATIONS_SECTIONS, sectionGuide } from "./sections";

const { report } = vi.hoisted(() => ({
  report: (overrides: Partial<ProblemReport> = {}): ProblemReport => ({
    id: "r1",
    business_id: "SUPT000003",
    tenant_name: "Orbit Medical Devices",
    tenant_business_id: "TEN000004",
    reporter: "asha.rao@orbit.example",
    reporter_business_id: "USR000008",
    summary: "Export stalls",
    details: "The complaint export never finishes.",
    path: "/app/complaints",
    request_id: "req-abc12345",
    status: "OPEN",
    created_at: "2026-10-20T09:30:00+00:00",
    closed_at: null,
    resolution: null,
    ...overrides,
  }),
}));

// The list answers at once, as GET /api/v1/platform-admin/support/problems would.
vi.mock("../../customer-admin/shared", async (original) => {
  const actual = await original<typeof import("../../customer-admin/shared")>();
  const listing = {
    items: [
      report(),
      report({ id: "r2", business_id: "SUPT000002", status: "CLOSED", resolution: "Fixed in 0.10.37", reporter: null }),
    ],
    counts: { OPEN: 1, CLOSED: 1 },
  };
  return { ...actual, useResource: () => ({ state: "ready", data: listing, reload: () => {} }) };
});

describe("Platform Admin, Operations, Problem reports (FUN-07)", () => {
  it("is a section of Operations with its own one-line purpose", () => {
    expect(OPERATIONS_SECTIONS).toContain("Problem reports");
    expect(sectionGuide("Operations", "Problem reports")).toContain("answer the reporter by email");
    expect(renderToStaticMarkup(<Operations section="Problem reports" />)).toContain("SUPT000003");
  });

  it("lists every report with its organization, reporter, words and status", () => {
    const html = renderToStaticMarkup(<ProblemReports />);
    for (const text of [
      "SUPT000003",
      "Orbit Medical Devices",
      "asha.rao@orbit.example",
      "Export stalls",
      "The complaint export never finishes.",
      "Page: /app/complaints",
      "Reference: req-abc12345",
      "Done: Fixed in 0.10.37",
      "Close",
    ])
      expect(html).toContain(text);
    // The closed report has no Close action, and no reply without an address.
    expect(html.match(/Reply by email/g)).toHaveLength(1);
  });

  it("replies to the reporter, naming the report in the subject", () => {
    const link = replyLink(report())!;
    expect(link.startsWith("mailto:asha.rao@orbit.example?subject=")).toBe(true);
    expect(decodeURIComponent(link)).toContain("Re: SUPT000003: Export stalls");
    expect(replyLink(report({ reporter: null }))).toBeNull();
    expect(replyLink(report({ reporter: "a@b.example?cc=x@y.example" }))).toBeNull();
    expect(replyLink(report({ reporter: "a@b.example, c@d.example" }))).toBeNull();
  });
});
