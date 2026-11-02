import { describe, expect, it } from "vitest";
import { GUIDE_PARTS } from "../features/help/userGuide";
import { NEW_PLACES, PLACES, newPathText } from "./linkTable";

/** 7.10: the user guide's "A › B" paths name the new places for an organization on the new navigation. */
describe("words that point somewhere", () => {
  it("rewrites a classic path to its new place", () => {
    expect(newPathText("Open Complaints › Reports and start the worksheet")).toBe(
      "Open Complaints › Reporting and start the worksheet",
    );
    expect(newPathText("Readiness › Oversight shows it")).toBe("Home › Team overview shows it");
    expect(newPathText("Complaints › First contact")).toBe("Home › Queues › Calls to check");
    expect(newPathText("Signals › Detection rules")).toBe("Settings › Trend rules");
    expect(newPathText("Getting started › Team")).toBe("Team");
    // Text without a screen path stays as written.
    expect(newPathText("Help › Pilot guide")).toBe("Help › Pilot guide");
  });

  it("leaves no classic-only screen in the user guide", () => {
    const text = newPathText(JSON.stringify(GUIDE_PARTS));
    const classicOnly = Object.keys(PLACES).filter((name) => !NEW_PLACES[name]);
    for (const name of classicOnly) expect(text, name).not.toMatch(new RegExp(`(?<![A-Za-z])${name} › `));
    // Tabs that moved never stay under their old screen.
    for (const moved of [
      "Complaints › Reports",
      "Complaints › Triage",
      "Complaints › Decision guides",
      "Records › Reports",
    ])
      expect(text, moved).not.toContain(moved);
  });
});
