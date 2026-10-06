import { afterEach, describe, expect, it, vi } from "vitest";
import { SectionErrorBoundary, clientErrorReport, reportClientError } from "./ErrorBoundary";

describe("client error reports", () => {
  afterEach(() => vi.restoreAllMocks());

  it("carries the page, the error and where it happened, and never the query string", () => {
    const error = new Error("Cannot read properties of undefined");
    const report = clientErrorReport(error, "Investigations", { pathname: "/app/investigations" }, "req-1");
    expect(report).toMatchObject({
      path: "/app/investigations",
      message: "Cannot read properties of undefined",
      component: "Investigations",
      request_id: "req-1",
    });
    expect(report.stack).toContain("Cannot read properties of undefined");
    expect(Object.keys(report).sort()).toEqual(["component", "message", "path", "request_id", "stack"]);
  });

  it("keeps within the server's limits and drops a request id that is not one of ours", () => {
    const report = clientErrorReport("x".repeat(5000), undefined, { pathname: "/app" }, "r".repeat(65));
    expect(report.message.length).toBe(1000);
    expect(report.request_id).toBeUndefined();
    expect(report.component).toBeUndefined();
  });

  it("posts the report to /api/v1/client-errors and swallows a delivery failure", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", { setTimeout, clearTimeout, location: { pathname: "/app/signals", search: "?q=x" } });
    reportClientError(new Error("boom"), "Signals");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/client-errors", expect.objectContaining({ method: "POST" }));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body));
    expect(body).toMatchObject({ path: "/app/signals", message: "boom", component: "Signals" });
  });
});

describe("section error boundary", () => {
  it("clears a failure when the person opens another section", () => {
    expect(SectionErrorBoundary.getDerivedStateFromError()).toEqual({ failed: true });
    expect(
      SectionErrorBoundary.getDerivedStateFromProps(
        { name: "Signals", resetKey: 2, children: null },
        { failed: true, resetKey: 1 },
      ),
    ).toEqual({ failed: false, resetKey: 2 });
    expect(
      SectionErrorBoundary.getDerivedStateFromProps(
        { name: "Signals", resetKey: 1, children: null },
        { failed: true, resetKey: 1 },
      ),
    ).toBeNull();
  });
});
