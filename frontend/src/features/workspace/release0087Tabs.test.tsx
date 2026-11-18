// 0.10.87 (owner, 5 Nov 2026): Look ahead and Next steps were tabs for every persona of a free trial; since UX2 they are
// screens of Today (areas.ts, AreaNav). Pilots and paid organizations keep their persona's tabs.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { NavRail, PERSONA_TABS, tabOfSection, trialTabs, visibleTabs } from "./HybridShell";
import { HelpMenu } from "../shared/HelpMenu";
import { NEXT_STEPS_HELP } from "../help/trialNextSteps";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";

const PERSONAS = [
  ["home", "complaints", "investigations", "products", "decisions"],
  ["home", "complaints"],
  ["home", "products"],
  ["home"],
];
const ALLOWED = [
  "Getting started",
  "My Work",
  "Complaints",
  "Decision trees",
  "Reports",
  "Investigations",
  "Trends",
  "Product 360",
].concat(["Records", "Team", "Look ahead", "Next steps"]);

// UX2 (Persona Blueprint wave D): Look ahead and Next steps fold into Today, the work area they belong to.
describe("Look ahead and Next steps in Today (UX2)", () => {
  it("follow no persona's tabs: a trial's bar is Getting started, then the persona's areas", () => {
    for (const persona of PERSONAS) {
      const tabs = visibleTabs(trialTabs(persona, true), ALLOWED);
      expect(tabs).toEqual(["start", ...persona]);
    }
    expect(PERSONA_TABS.ahead).toBeUndefined();
    expect(PERSONA_TABS.next).toBeUndefined();
    expect(tabOfSection("Look ahead")).toBe("home");
    expect(tabOfSection("Next steps")).toBe("home");
  });

  it("are never added to a pilot's or a paid organization's bar", () => {
    for (const persona of PERSONAS) expect(trialTabs(persona, false)).toEqual(persona);
    expect(visibleTabs(["home", "ahead", "next"], ["My Work"])).toEqual(["home"]);
  });

  it("mark Today as the current page while one of them is open, with no tab of their own", () => {
    const bar = renderToStaticMarkup(
      <NavRail
        tabs={visibleTabs(trialTabs(["home"], true), ALLOWED)}
        current={tabOfSection("Next steps")}
        open={vi.fn()}
      />,
    );
    expect(bar.indexOf(">Getting started<")).toBeLessThan(bar.indexOf(">Today<"));
    expect(bar).toMatch(/aria-current="page" title="Today">/);
    expect(bar).not.toContain(">Look ahead<");
    expect(bar).not.toContain(">Next steps<");
    expect(bar).not.toContain("is-extra");
  });

  it("replace Help's Next steps entry on the new navigation; the classic one keeps it", () => {
    const help = (navigation: string) =>
      renderToStaticMarkup(
        <WorkspaceContext.Provider
          value={{ navigation, isTrial: true, open: vi.fn(), session: {} } as unknown as WorkspaceApi}
        >
          <HelpMenu onGettingStarted={vi.fn()} defaultOpen />
        </WorkspaceContext.Provider>,
      );
    expect(help("new")).not.toContain(NEXT_STEPS_HELP);
    expect(help("classic")).toContain(NEXT_STEPS_HELP);
  });
});
