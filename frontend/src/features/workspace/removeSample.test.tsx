import { describe, expect, it } from "vitest";
import { sampleSummary } from "./sections/RemoveSample";

describe("removing the sample data", () => {
  it("names what goes as people read it", () => {
    expect(sampleSummary({ products: 3, complaints: 37, investigations: 1 })).toBe(
      "3 products, 37 complaints and 1 investigation",
    );
    expect(sampleSummary({ CAPAs: 1, risks: 3 })).toBe("1 CAPA and 3 risks");
    expect(sampleSummary({ products: 0 })).toBe("");
  });
});
