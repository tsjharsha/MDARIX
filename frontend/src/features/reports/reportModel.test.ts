import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../app/apiClient";
import { downloadError, fetchFile, filenameFrom } from "./download";
import { cellText, previewSections, recordPath, reportFallbackName, reportPath } from "./reportModel";

describe("report and case-record addresses", () => {
  it("asks for the format the person chose", () => {
    expect(reportPath("COMPLAINT_TREND", "PDF")).toBe("/api/v1/stage3/reports/COMPLAINT_TREND?output_format=PDF");
    expect(recordPath("abc-1", "csv")).toBe("/api/v1/stage3/investigations/abc-1/record?format=csv");
    expect(reportFallbackName("RISK_IMPACT", "CSV")).toBe("mdarix-risk-impact.csv");
  });
});

describe("report preview", () => {
  it("turns record lists into tables of their first rows with scalar columns only", () => {
    const rows = Array.from({ length: 12 }, (_, index) => ({ id: index, name: `C-${index}`, links: [1, 2] }));
    const [section] = previewSections({ complaints: rows, data_cut_off: "2026-10-01" }, 10);
    expect(section).toMatchObject({ kind: "table", label: "Complaints", columns: ["id", "name"], total: 12 });
    expect(section.kind === "table" && section.rows).toHaveLength(10);
  });

  it("shows mappings as facts, empty lists as empty, and never [object Object]", () => {
    const sections = previewSections({ counts: { open: 3, closed: { a: 1 } }, signals: [], note: "x" });
    expect(sections.map((item) => item.kind)).toEqual(["facts", "empty", "value"]);
    expect(sections[0].kind === "facts" && sections[0].facts).toEqual([
      ["Open", "3"],
      ["Closed", "1 fields"],
    ]);
    expect(cellText([{ a: 1 }, { b: 2 }])).toBe("2 items");
    expect(cellText(null)).toBe("—");
    expect(cellText(true)).toBe("Yes");
    expect(previewSections(null)).toEqual([]);
  });
});

describe("file downloads", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("takes the server's file name, never a folder", () => {
    expect(filenameFrom('attachment; filename="mdarix-risk-register-2026-10-06.csv"', "x.csv")).toBe(
      "mdarix-risk-register-2026-10-06.csv",
    );
    expect(filenameFrom("attachment; filename=../../etc/passwd", "x.csv")).toBe("passwd");
    expect(filenameFrom("attachment; filename*=UTF-8''case%20record.pdf", "x.pdf")).toBe("case record.pdf");
    expect(filenameFrom(null, "fallback.pdf")).toBe("fallback.pdf");
    expect(filenameFrom('attachment; filename=".hidden"', "fallback.pdf")).toBe("hidden");
  });

  it("reports a failed export with the server's message and the request id to quote", async () => {
    const response = new Response(
      JSON.stringify({ detail: { code: "PERMISSION_DENIED", message: "Your role does not allow this action" } }),
      { status: 403, headers: { "X-Request-ID": "req-123" } },
    );
    const error = await downloadError(response);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, code: "PERMISSION_DENIED", requestId: "req-123" });
    expect(error.message).toBe("Your role does not allow this action");
  });

  it("returns the file and its name on success, and an ApiError when the server refuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        new Response("a,b\n1,2\n", {
          status: 200,
          headers: { "Content-Disposition": 'attachment; filename="report.csv"' },
        }),
      ),
    );
    const file = await fetchFile("/api/v1/risk/export.csv", { fallbackName: "x.csv" });
    expect(file.filename).toBe("report.csv");
    expect(await file.blob.text()).toBe("a,b\n1,2\n");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/risk/export.csv",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: { request_id: "r-9" } }), { status: 500 })),
    );
    await expect(fetchFile("/x", { method: "POST", fallbackName: "x" })).rejects.toMatchObject({
      status: 500,
      requestId: "r-9",
    });
  });

  it("says the connection failed rather than showing a raw error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch")));
    await expect(fetchFile("/x", { fallbackName: "x" })).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
  });
});
