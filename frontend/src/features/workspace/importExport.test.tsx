import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../app/apiClient";
import { HowItWasRead, alsoCreatesText, checkFailureText, importedText, readyText } from "./sections/ImportData";

describe("uploading a quality system's export as it comes", () => {
  it("says what a complaints file adds besides its complaints", () => {
    expect(alsoCreatesText({ products: 1, lots: 2 })).toBe("1 product and 2 lots");
    expect(alsoCreatesText({ products: 2, versions: 1, lots: 1 })).toBe("2 products, 1 version and 1 lot");
    expect(alsoCreatesText({})).toBe("");
    expect(alsoCreatesText(undefined)).toBe("");
  });

  it("counts the complaints imported apart from the products and lots they name", () => {
    expect(importedText("Complaints", { created: 9, updated: 0, also_created: { products: 2, lots: 3 } })).toBe(
      "Imported complaints: 4 new, 0 updated, and 2 products and 3 lots they name.",
    );
    expect(
      importedText("Complaints", {
        created: 3,
        updated: 1,
        also_created: { lots: 1 },
        rejected_rows: 2,
        masked_values: 1,
      }),
    ).toBe(
      "Imported complaints: 2 new, 1 updated, and 1 lot they name; 2 rows set aside to fix; personal data replaced in 1 value.",
    );
    expect(importedText("Products and versions", { created: 2, updated: 0, rejected_rows: 1 })).toBe(
      "Imported products and versions: 2 new, 0 updated; 1 row set aside to fix.",
    );
    expect(importedText("Lots and batches", {})).toBe("Imported lots and batches: 0 new, 0 updated.");
  });

  it("says plainly that a file without data rows cannot be checked (DEV-018)", () => {
    const empty = new ApiError("The file has a header but no data rows.", 422, "IMPORT_FILE_EMPTY", "abc123");
    expect(checkFailureText(empty)).toBe("The file has a header but no data rows.");
    // Anything else keeps its reference for support.
    expect(checkFailureText(new ApiError("Server error", 500, "INTERNAL", "abc123"))).toBe(
      "Server error (reference abc123)",
    );
  });

  it("groups every count in the result the en-US way, whatever the browser's language (DEV-025)", () => {
    expect(importedText("Complaints", { created: 0, updated: 4993 })).toBe(
      "Imported complaints: 0 new, 4,993 updated.",
    );
    expect(
      importedText("Complaints", {
        created: 13_251,
        updated: 1200,
        also_created: { products: 1000, versions: 1, lots: 1250 },
        rejected_rows: 2500,
        masked_values: 1001,
      }),
    ).toBe(
      "Imported complaints: 11,000 new, 1,200 updated, and 1,000 products, 1 version and 1,250 lots they name; 2,500 rows set aside to fix; personal data replaced in 1,001 values.",
    );
    expect(alsoCreatesText({ lots: 4993 })).toBe("4,993 lots");
    expect(readyText({ rows: 4993, new_records: 4993, new_rows: 4993, row_limit: 5000 })).toBe(
      "4,993 rows ready to import (4,993 new rows of your 5,000).",
    );
  });

  it("says a free trial's rows as its allowance counts them: one row in the file is one row", () => {
    const report = { rows: 6, rows_to_import: 6, new_records: 12, new_rows: 6, also_creates: { products: 1, lots: 4 } };
    expect(readyText({ ...report, row_limit: 5000 })).toBe(
      "6 rows ready to import (6 new rows of your 5,000); the complaints also add 1 product and 4 lots they name, which do not count as rows.",
    );
    expect(readyText({ ...report, row_limit: 5000, also_creates: {}, masked_values: 1 })).toBe(
      "6 rows ready to import (6 new rows of your 5,000); personal data will be replaced in 1 value.",
    );
    // A workspace without an allowance still counts the new records.
    expect(readyText({ ...report, row_limit: null })).toBe(
      "6 rows ready to import (12 new records), including 1 product and 4 lots the complaints name.",
    );
  });

  it("shows how the columns were read and which were left out, unstored", () => {
    const html = renderToStaticMarkup(
      <HowItWasRead
        report={{
          columns: [{ header: "Complaint Number", column: "complaint_id" }],
          ignored_columns: ["Patient Name"],
          notes: ["Read the first sheet of the Excel workbook."],
        }}
      />,
    );
    expect(html).toContain("Complaint Number → <code>complaint_id</code>");
    expect(html).toContain("Not used (not stored):</b> Patient Name");
    expect(html).toContain("Excel workbook");
    expect(renderToStaticMarkup(<HowItWasRead report={{}} />)).toBe("");
  });
});
