import { describe, expect, it } from "vitest";
import { supplierDateLabel, supplierRequestNote } from "./sections/MyWork";

// 0.10.62 (J33): a free trial saves a supplier request and e-mails nobody, so its screens say so.
describe("supplier evidence requests in a free trial", () => {
  it("say the request is saved, not e-mailed, and to send it from your own mail", () => {
    expect(supplierRequestNote(true)).toBe(
      "In the free trial MDARIX saves the request here and e-mails nobody: send it to the supplier from your own mail.",
    );
    expect(supplierRequestNote(true)).not.toContain("The email carries");
    expect(supplierDateLabel(true)).toBe("Saved");
  });

  it("keep the pilot's wording", () => {
    expect(supplierRequestNote(false)).toBe(
      "The email carries this text only, without links. Requests are limited per person and per day.",
    );
    expect(supplierDateLabel(false)).toBe("Sent");
  });
});
