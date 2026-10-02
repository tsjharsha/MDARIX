import { describe, expect, it } from "vitest";
import { AREA_SECTIONS, LEGACY_SECTIONS, parseThresholds, previewTemplate, templateVariables } from "./sections";

describe("platform administrator areas", () => {
  it("keeps each area short: 24 sections instead of 55", () => {
    const counts = Object.values(AREA_SECTIONS).map((sections) => sections.length);
    expect(counts.reduce((sum, count) => sum + count, 0)).toBe(24);
    expect(Math.max(...counts)).toBeLessThanOrEqual(5);
  });

  it("sends every old section name to a section that exists", () => {
    const all = new Set(Object.values(AREA_SECTIONS).flat());
    for (const [old, now] of Object.entries(LEGACY_SECTIONS)) {
      expect(all.has(now), `${old} -> ${now}`).toBe(true);
    }
  });
});

describe("reminder schedule", () => {
  it("reads days in any order and keeps them unique, largest first", () => {
    expect(parseThresholds("14, 90 45, 14")).toEqual({ days: [90, 45, 14] });
    expect(parseThresholds("0")).toEqual({ days: [0] });
  });

  it("explains what is wrong instead of sending it", () => {
    expect(parseThresholds("").error).toMatch(/at least one/);
    expect(parseThresholds("30, soon").error).toMatch(/whole numbers/);
    expect(parseThresholds("-5").error).toMatch(/whole numbers/);
    expect(parseThresholds("400").error).toMatch(/365/);
  });
});

describe("reminder email", () => {
  it("previews with sample values and leaves unknown placeholders visible", () => {
    expect(
      previewTemplate("Hi {{customer_name}}, ends {{ expiry_date }} {{oops}}", {
        customer_name: "Apex",
        expiry_date: "1 May",
      }),
    ).toBe("Hi Apex, ends 1 May {{oops}}");
  });

  it("declares only the values the message uses", () => {
    expect(templateVariables("{{customer_name}} {{expiry_date}} {{customer_name}}")).toEqual([
      "customer_name",
      "expiry_date",
    ]);
  });
});
