import { describe, expect, it } from "vitest";
import { DETAILS_LIMIT, SUMMARY_LIMIT, problemMailto, problemReport } from "./ReportProblem";

describe("problem reports", () => {
  it("sends the person's words, the page without its query, and the last failed request's reference", () => {
    expect(problemReport("  Import fails ", " The check never ends. ", { pathname: "/app" }, "req-42")).toEqual({
      summary: "Import fails",
      details: "The check never ends.",
      path: "/app",
      request_id: "req-42",
    });
    expect(problemReport("a", "b", { pathname: "/app/signals" })).not.toHaveProperty("request_id");
  });

  it("keeps within the server's limits (200 and 5000 characters)", () => {
    const report = problemReport("s".repeat(300), "d".repeat(6000), { pathname: "/app" });
    expect(report.summary).toHaveLength(SUMMARY_LIMIT);
    expect(report.details).toHaveLength(DETAILS_LIMIT);
  });

  it("offers the same report by email when it cannot be sent", () => {
    const link = problemMailto(
      "support@example.com",
      { summary: "Import fails", details: "Nothing happens", path: "/app", request_id: "req-42" },
      new Date("2026-10-05T10:00:00Z"),
    );
    expect(link.startsWith("mailto:support@example.com?subject=")).toBe(true);
    const body = decodeURIComponent(link.split("&body=")[1]);
    expect(body).toContain("Nothing happens");
    expect(body).toContain("Page: /app");
    expect(body).toContain("Reference: req-42");
    expect(decodeURIComponent(link.split("subject=")[1].split("&")[0])).toBe("MDARIX problem: Import fails");
  });
});
