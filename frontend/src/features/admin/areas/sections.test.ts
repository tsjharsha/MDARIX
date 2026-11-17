import { describe, expect, it } from "vitest";
import {
  AREA_SECTIONS,
  DATA_AND_INTEGRATIONS,
  DATA_INTEGRATION_GUIDE,
  DATA_INTEGRATION_SECTIONS,
  DATA_INTEGRATION_STAGES,
  DOMAIN_ALIASES,
  LEGACY_SECTIONS,
  dataIntegrationStep,
  parseThresholds,
  previewTemplate,
  templateVariables,
} from "./sections";

describe("platform administrator areas", () => {
  it("keeps each area short: 34 sections instead of 80, a guided sequence only where setup is one", () => {
    const counts = Object.entries(AREA_SECTIONS).map(([area, sections]) => [area, sections.length] as const);
    // 33, and Operations > Problem reports since 0.10.37 (FUN-07); Identity & Access > Onboarding moved to Trial
    // organizations > Requests (TO-1), an area of its own.
    // 34 with Security > Validation evidence (E2).
    expect(counts.reduce((sum, [, count]) => sum + count, 0)).toBe(34);
    for (const [area, count] of counts) if (area !== DATA_AND_INTEGRATIONS) expect(count).toBeLessThanOrEqual(6);
  });

  it("lays out Data & Integrations as stages that cover every step once, in order, each explained", () => {
    expect(DATA_INTEGRATION_STAGES.flatMap((stage) => [...stage.sections])).toEqual([...DATA_INTEGRATION_SECTIONS]);
    for (const section of DATA_INTEGRATION_SECTIONS) expect(DATA_INTEGRATION_GUIDE[section]).toBeTruthy();
    expect(dataIntegrationStep("Data model")).toEqual({ number: 1, total: 10, stage: "Define" });
    expect(dataIntegrationStep("Reconciliation")).toEqual({ number: 10, total: 10, stage: "Run" });
    expect(dataIntegrationStep("Plans")).toBeNull();
  });

  it("sends the former Data & Configuration and Integrations areas to Data & Integrations", () => {
    expect(DOMAIN_ALIASES["Data & Configuration"]).toBe(DATA_AND_INTEGRATIONS);
    expect(DOMAIN_ALIASES.Integrations).toBe(DATA_AND_INTEGRATIONS);
    expect(LEGACY_SECTIONS["API & schemas"]).toBe("Source schemas");
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
