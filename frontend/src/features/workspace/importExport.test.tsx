import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HowItWasRead, alsoCreatesText } from "./sections/ImportData";

describe("uploading a quality system's export as it comes", () => {
  it("says what a complaints file adds besides its complaints", () => {
    expect(alsoCreatesText({ products: 1, lots: 2 })).toBe("1 product and 2 lots");
    expect(alsoCreatesText({ products: 2, versions: 1, lots: 1 })).toBe("2 products, 1 version and 1 lot");
    expect(alsoCreatesText({})).toBe("");
    expect(alsoCreatesText(undefined)).toBe("");
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
