import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "../workspaceContext";
import {
  CSV_BOM,
  FileQuestions,
  HowItWasRead,
  IMPORT_PATH,
  ImportPanel,
  dateFormatChoices,
  importUrl,
  issueText,
  type ImportSetup,
} from "./ImportData";
import { asideCounts, fixColumns, previewValue, runChecks, type ImportRun } from "./ImportReports";

// Stage 4 (0.10.65), "Your Excel just works": one upload screen and one path, the file's own choices, and set-aside
// rows fixed or dismissed on screen.

const setup: ImportSetup = {
  row_limit: 5000,
  file_limit_bytes: 2 * 1024 * 1024,
  creates_references: true,
  usual: { date_order: "DMY", number_format: "GROUP" },
  templates: [
    { entity: "products", title: "Products and versions", required: [], optional: [], download: "" },
    { entity: "complaints", title: "Complaints", required: [], optional: [], download: "" },
  ],
};

function renderPanel() {
  const api = {
    session: { business_permissions: ["records.write"] },
    isTrial: true,
    work: {},
  } as unknown as WorkspaceApi;
  return renderToStaticMarkup(
    <WorkspaceContext.Provider value={api}>
      <ImportPanel setup={setup} onImported={vi.fn()} />
    </WorkspaceContext.Provider>,
  );
}

describe("the one upload screen", () => {
  it("posts every upload to the one path, with the file's choices", () => {
    expect(IMPORT_PATH).toBe("/api/v1/data/import");
    expect(
      importUrl(IMPORT_PATH, "complaints", "check", "AUTO", undefined, "register.xlsx", {
        sheet: "Complaint Register",
        numberFormat: "DECIMAL_COMMA",
        dateColumn: "Logged On",
      }),
    ).toBe(
      "/api/v1/data/import/complaints/check?date_format=AUTO&number_format=DECIMAL_COMMA&sheet=Complaint+Register&date_column=Logged+On",
    );
    // The default number format and no sheet or column add nothing.
    expect(importUrl(IMPORT_PATH, "lots", "check", "DMY", undefined, undefined, { numberFormat: "GROUP" })).toBe(
      "/api/v1/data/import/lots/check?date_format=DMY",
    );
  });

  it("starts with dates found from the file, the organization's usual order named, and its number format", () => {
    expect(dateFormatChoices("DMY")[0]).toEqual(["AUTO", "From the file, else DD/MM/YYYY"]);
    expect(dateFormatChoices("MDY")[0][1]).toContain("MM/DD/YYYY");
    const html = renderPanel();
    expect(html).toContain('<option value="AUTO" selected="">From the file, else DD/MM/YYYY');
    expect(html).toContain('<option value="GROUP" selected="">1,250.00 or 1,25,000</option>');
    expect(html).toContain("Up to 5,000 rows and 2 MB per file.");
    // A trial opens on its complaints export.
    expect(html).toMatch(/aria-pressed="true" class="selected"[^>]*>2\. Complaints/);
  });

  it("names each problem by its row and the file's own column name", () => {
    expect(issueText({ row: 5, column: "death", header: "Death (Y/N)", message: "'Maybe' is not a yes or no" })).toBe(
      "Row 5 · Death (Y/N): 'Maybe' is not a yes or no",
    );
    expect(issueText({ row: null, column: null, message: "The file is empty." })).toBe("File: The file is empty.");
  });

  it("lists the columns not used, a second column of a field with the one used", () => {
    const html = renderToStaticMarkup(
      <HowItWasRead
        report={{
          ignored_columns: ["Sr. No.", "Complaint Received Date"],
          duplicate_columns: [
            { header: "Complaint Received Date", column: "received_date", kept: "Date of Complaint" },
          ],
          notes: ["Read the sheet 'Complaint Register' of the Excel workbook."],
        }}
      />,
    );
    expect(html).toContain(
      "Not used (not stored):</b> Sr. No., Complaint Received Date (the same as Date of Complaint)",
    );
  });

  it("asks which sheet to read and, without a date column, which column holds the date", () => {
    const html = renderToStaticMarkup(
      <FileQuestions
        report={{
          sheet: "Complaint Register",
          sheets: ["Complaint Register", "Batch Register"],
          needs_date_column: true,
          date_column_choices: ["Logged On"],
        }}
        busy={false}
        sheet={null}
        onSheet={vi.fn()}
        dateColumn={null}
        onDateColumn={vi.fn()}
      />,
    );
    expect(html).toContain("Sheet to read");
    expect(html).toContain('<option value="Complaint Register" selected="">');
    expect(html).toContain("Which column holds the date each complaint was received?");
    expect(html).toContain('<option value="Logged On">Logged On</option>');
    expect(html).toContain('<option value="none">None: date each complaint the day it is imported</option>');
    expect(
      renderToStaticMarkup(
        <FileQuestions
          report={{ sheets: ["Only"] }}
          busy={false}
          sheet={null}
          onSheet={vi.fn()}
          dateColumn={null}
          onDateColumn={vi.fn()}
        />,
      ),
    ).toBe("");
  });

  it("shows every date of the preview in one format", () => {
    expect(previewValue("2026-08-14")).toMatch(/14/);
    expect(previewValue("2026-08-14")).not.toContain("2026-08-14");
    expect(previewValue("PX-20")).toBe("PX-20");
    expect(previewValue("")).toBe("—");
  });

  it("downloads the rows to fix with a byte-order mark, so Excel keeps accented letters", () => {
    expect(CSV_BOM).toBe("﻿");
  });
});

describe("set-aside rows fixed on screen", () => {
  it("offers the fields the reasons name, or every field when they name none", () => {
    const row = {
      row: { complaint_id: "FIX-1", received_date: "2062-04-03", description: "Display froze" },
      problems: ["received_date: '03/04/2062' reads as 3 Apr 2062, a day still to come."],
    };
    expect(fixColumns(row)).toEqual(["received_date"]);
    expect(fixColumns({ ...row, problems: ["This row has more values than the header has columns."] })).toEqual([
      "complaint_id",
      "received_date",
      "description",
    ]);
  });

  it("counts what is still open, processed again and dismissed", () => {
    expect(asideCounts({ open: 2, reprocessed: 0, dismissed: 0 })).toBe("");
    expect(asideCounts({ open: 0, reprocessed: 2, dismissed: 1 })).toBe(
      "0 still open · 2 processed again · 1 dismissed",
    );
  });

  it("reads the data-quality report's columns not used", () => {
    const run: Pick<ImportRun, "report" | "masked_values"> = {
      masked_values: 0,
      report: {
        rows_read: 4,
        rows_accepted: 4,
        rows_quarantined: 0,
        rows_changed: 0,
        rows_new: 3,
        rows_unchanged: 1,
        balanced: true,
        columns_not_used: ["Sr. No."],
      },
    };
    const checks = runChecks(run);
    expect(checks.find((check) => check.label === "Columns not used")?.detail).toBe("Sr. No.: not stored.");
    expect(checks[1].detail).toBe("3 new, 0 updated, 1 unchanged.");
    const none = runChecks({ ...run, report: { ...run.report, columns_not_used: [] } });
    expect(none.find((check) => check.label === "Columns not used")?.detail).toBe("Every column of the file was used.");
    // Older runs recorded no columns: no line.
    const older = runChecks({ ...run, report: { ...run.report, columns_not_used: undefined } });
    expect(older.some((check) => check.label === "Columns not used")).toBe(false);
  });
});
