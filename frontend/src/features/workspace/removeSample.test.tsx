import { describe, expect, it } from "vitest";
import { restartChoices, sampleSummary } from "./sections/RemoveSample";

describe("removing the sample data", () => {
  it("names what goes as people read it", () => {
    expect(sampleSummary({ products: 3, complaints: 37, investigations: 1 })).toBe(
      "3 products, 37 complaints and 1 investigation",
    );
    expect(sampleSummary({ CAPAs: 1, risks: 3 })).toBe("1 CAPA and 3 risks");
    expect(sampleSummary({ products: 0 })).toBe("");
  });
});

describe("restarting the sample story", () => {
  it("says plainly what each choice removes", () => {
    const choices = restartChoices({ sample: { products: 3, complaints: 44 }, work_on_sample: 2, own_records: 120 });
    expect(choices.story).toBe(
      "Removes the sample (3 products and 44 complaints), and 2 records of practice on them, then brings it back dated today. Your own uploads and what you did with them stay.",
    );
    expect(choices.own).toBe("Also removes your own 120 uploaded records and everything you did with them.");
    expect(restartChoices({ sample: { products: 3 }, work_on_sample: 0, own_records: 0 }).own).toBe(
      "You have not uploaded records of your own, so nothing more goes.",
    );
  });
});
