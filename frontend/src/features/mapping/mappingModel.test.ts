import { describe, expect, it } from "vitest";
import { autoMatch, buildRules, columnLabel, defaultTransform, suggestSource, withFilter } from "./mappingModel";

// The TrackWise Digital complaint fields from master data (a subset).
const TRACKWISE = [
  "complaint_id",
  "complaint_number",
  "product_code",
  "product_revision",
  "event_date",
  "received_date",
  "problem_description",
  "lot_number",
  "status",
].map((name) => ({ name }));

describe("connector mapping format", () => {
  it("saves exactly the rules the import reads", () => {
    expect(
      buildRules("Complaint", [
        { source: "complaint_number", column: "complaint_id", transform: "trim" },
        { source: "event_date", column: "event_date", transform: "date" },
        { source: "", column: "status", transform: "trim" },
      ]),
    ).toEqual({
      complaint_number: { target_field: "Complaint.complaint_id", transform: "trim" },
      event_date: { target_field: "Complaint.event_date", transform: "date" },
    });
  });

  it("labels columns and picks a sensible conversion", () => {
    expect(columnLabel("received_date")).toBe("Received date");
    expect(columnLabel("product_id")).toBe("Product ID");
    expect(defaultTransform("event_date")).toBe("date");
    expect(defaultTransform("description")).toBe("trim");
  });
});

describe("matching TrackWise fields", () => {
  it("suggests the TrackWise field that carries each MDARIX field", () => {
    expect(suggestSource("product_id", TRACKWISE)).toBe("product_code");
    expect(suggestSource("description", TRACKWISE)).toBe("problem_description");
    expect(suggestSource("lot_id", TRACKWISE)).toBe("lot_number");
    expect(suggestSource("version", TRACKWISE)).toBe("product_revision");
    expect(suggestSource("unknown_column", TRACKWISE)).toBe("");
  });

  it("fills the required complaint fields once, without reusing a customer field", () => {
    const rules = autoMatch([], ["complaint_id", "product_id", "description"], TRACKWISE);
    expect(rules).toEqual([
      { source: "complaint_id", column: "complaint_id", transform: "trim" },
      { source: "product_code", column: "product_id", transform: "trim" },
      { source: "problem_description", column: "description", transform: "trim" },
    ]);
    // Running it again adds nothing.
    expect(autoMatch(rules, ["complaint_id", "product_id", "description"], TRACKWISE)).toHaveLength(3);
  });
});

describe("withFilter", () => {
  it("adds the row filter only when a field and at least one value are given", () => {
    const rules = { item_number: { target_field: "Product.product_id", transform: "trim" } };
    expect(withFilter(rules, "item_type", " Product , Assembly ,")).toEqual({
      ...rules,
      _filter: { field: "item_type", in: ["Product", "Assembly"] },
    });
    expect(withFilter(rules, "item_type", "  ")).toBe(rules);
    expect(withFilter(rules, "", "Product")).toBe(rules);
  });
});
