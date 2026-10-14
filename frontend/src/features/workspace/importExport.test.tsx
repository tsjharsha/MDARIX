import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HowItWasRead, alsoCreatesText, importedText } from "./sections/ImportData";

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
    expect(html).toContain("Left out, not stored:</b> Patient Name");
    expect(html).toContain("Excel workbook");
    expect(renderToStaticMarkup(<HowItWasRead report={{}} />)).toBe("");
  });
});
