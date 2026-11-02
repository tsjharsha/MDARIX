import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  ImportRunReport,
  fileTitle,
  identityText,
  imdrfText,
  originText,
  reasonsByColumn,
  runChecks,
  type ImportRun,
} from "./ImportReports";
import { importUrl, reportFocus } from "./ImportData";
import { imdrfLabels } from "./ComplaintList";

const run: ImportRun = {
  import_ref: "8f1c",
  entity: "complaints",
  file_name: "Sample complaints export.xlsx",
  imported_at: "2026-10-31T09:00:00+00:00",
  imported_by: "MDARIX sample author",
  mapping_version: "complaints-template:abc",
  masked_values: 0,
  sample: true,
  report: { rows_read: 40, rows_accepted: 38, rows_quarantined: 2, rows_changed: 0, rows_new: 38, balanced: true },
};

describe("an import's data-quality report", () => {
  it("says every row is accounted for, what was written and what was set aside", () => {
    const checks = runChecks(run);
    expect(checks.map((check) => [check.label, check.ok])).toEqual([
      ["Every row accounted for", true],
      ["Rows written", true],
      ["Rows that passed every check", false],
    ]);
    expect(checks[0].detail).toBe("40 rows read: 38 written and 2 set aside.");
    expect(checks[1].detail).toBe("38 new, 0 updated.");
    expect(checks[2].detail).toContain("2 rows set aside with their reasons");
  });

  it("counts as updated only the rows that changed a field (a re-upload of the same file)", () => {
    const again = { ...run.report, rows_new: 0, rows_changed: 1, rows_unchanged: 37 };
    expect(runChecks({ ...run, report: again })[1].detail).toBe("0 new, 1 updated, 37 unchanged.");
  });

  it("flags a run that does not balance and names replaced personal details", () => {
    const checks = runChecks({
      masked_values: 3,
      report: { ...run.report, rows_accepted: 37, balanced: false },
    });
    expect(checks[0].ok).toBe(false);
    expect(checks[0].detail).toContain("only 39 written or set aside");
    expect(checks[checks.length - 1].detail).toContain("3 values");
  });

  it("groups the reasons by column, most frequent first", () => {
    expect(
      reasonsByColumn([
        { problems: ["description: 'description' is required."] },
        { problems: ["description: This looks like it contains a phone number.", "event_date: not a date"] },
      ]),
    ).toEqual([
      ["description", 2],
      ["event_date", 1],
    ]);
  });

  it("shows the counts and the checks", () => {
    const html = renderToStaticMarkup(
      <ImportRunReport run={{ ...run, report: { ...run.report, rows_quarantined: 0, rows_accepted: 40 } }} />,
    );
    expect(html).toContain("Sample complaints export.xlsx");
    expect(html).toContain("Rows read");
    expect(html).toContain("No row was set aside.");
    expect(html).toContain("sample data");
  });

  it("names a file the import sent no name for by its data type", () => {
    expect(fileTitle({ file_name: null, entity: "complaints" })).toBe("Complaints file");
  });
});

describe("where a record came from and its reference data", () => {
  it("names the row, the file and who imported it", () => {
    const text = originText(
      {
        import_ref: "8f1c",
        line: 14,
        file_name: "Own complaints.csv",
        imported_at: "2026-10-31T09:00:00+00:00",
        imported_by: "Asha Rao",
        has_report: true,
      },
      "complaints",
    );
    expect(text).toMatch(/^Row 14 of Own complaints\.csv, imported .* by Asha Rao$/);
  });

  it("shows an IMDRF code with its term once loaded", () => {
    expect(imdrfText({ release: "2025", annex: "A", code: "A16", term: "Protective Measures Problem" })).toBe(
      "A16 Protective Measures Problem",
    );
    expect(imdrfText({ release: "2025", annex: "A", code: "A16", term: null })).toBe("A16");
  });

  it("labels problem codes by their IMDRF term first, the customer's code as its detail (0.10.70)", () => {
    const link = { release: "2025", annex: "A", code: "A16", term: "Protective Measures Problem" };
    expect(imdrfLabels(["PRESSURE_ALARM", "NFF"], { PRESSURE_ALARM: [link] })).toEqual({
      PRESSURE_ALARM: "Protective Measures Problem (IMDRF A16) · your code PRESSURE_ALARM",
    });
  });

  it("reads a product's UDI-DI and GMDN, or says what is missing", () => {
    expect(
      identityText({ udi_di: "04000000030010", gmdn_code: "13215", gmdn_term: "General-purpose infusion pump" }),
    ).toBe("UDI-DI 04000000030010 · GMDN 13215 General-purpose infusion pump");
    expect(identityText({ udi_di: null, gmdn_code: null, gmdn_term: null })).toBe("No UDI-DI · no GMDN term");
    const sample = { udi_di: "04000000030010", gmdn_code: null, gmdn_term: "General-purpose infusion pump" };
    expect(identityText(sample, true)).toBe("UDI-DI 04000000030010 · GMDN sample General-purpose infusion pump");
    expect(identityText(sample)).toBe("UDI-DI 04000000030010 · GMDN code not set General-purpose infusion pump");
  });
});

describe("links to a report", () => {
  it("sends the file's name with the import only", () => {
    expect(importUrl("/api/v1/trial/imports", "complaints", "import", "ISO", undefined, "My export.csv")).toBe(
      "/api/v1/trial/imports/complaints?file_name=My+export.csv",
    );
    expect(importUrl("/api/v1/trial/imports", "complaints", "check", "ISO", undefined, "My export.csv")).toBe(
      "/api/v1/trial/imports/complaints/check",
    );
  });

  it("reads the import a link names", () => {
    expect(reportFocus("report=8f1c")).toBe("8f1c");
    expect(reportFocus("Your data")).toBeNull();
  });
});
