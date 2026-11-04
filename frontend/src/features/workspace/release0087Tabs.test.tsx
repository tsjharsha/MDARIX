// 0.10.87 (owner, 5 Nov 2026): Look ahead and Next steps are tabs for every persona of a free trial, reached until now
// only from Help. Pilots and paid organizations keep their persona's tabs.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { PERSONA_TABS, TabBar, tabOfSection, trialTabs, visibleTabs } from "./HybridShell";
import { HelpMenu } from "../shared/HelpMenu";
import { NEXT_STEPS_HELP } from "../help/trialNextSteps";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";

const PERSONAS = [
  ["home", "complaints", "trees", "reports", "investigations", "trends", "records", "team"],
  ["home", "complaints"],
  ["home", "trends", "records"],
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
].concat(["Records", "Team", "Look ahead", "Next steps"]);

describe("Look ahead and Next steps as tabs of a trial", () => {
  it("follow every persona's tabs in a trial, with Getting started still first", () => {
    for (const persona of PERSONAS) {
      const tabs = visibleTabs(trialTabs(persona, true), ALLOWED);
      expect(tabs[0]).toBe("start");
      expect(tabs.slice(-2)).toEqual(["ahead", "next"]);
      expect(tabs.slice(1, -2)).toEqual(persona);
    }
    expect(PERSONA_TABS.ahead).toEqual({ label: "Look ahead", section: "Look ahead" });
    expect(PERSONA_TABS.next).toEqual({ label: "Next steps", section: "Next steps" });
    expect(tabOfSection("Look ahead")).toBe("ahead");
    expect(tabOfSection("Next steps")).toBe("next");
  });

  it("are never added to a pilot's or a paid organization's bar", () => {
    for (const persona of PERSONAS) expect(trialTabs(persona, false)).toEqual(persona);
    // Their screens are trial-only: outside a trial they are not among the allowed sections, so no tab shows.
    expect(visibleTabs(["home", "ahead", "next"], ["My Work"])).toEqual(["home"]);
  });

  it("show as tabs, the open one marked as the current page", () => {
    const bar = renderToStaticMarkup(
      <TabBar tabs={visibleTabs(trialTabs(["home"], true), ALLOWED)} current="next" open={vi.fn()} />,
    );
    expect(bar.indexOf(">Getting started<")).toBeLessThan(bar.indexOf(">Home<"));
    expect(bar.indexOf(">Home<")).toBeLessThan(bar.indexOf(">Look ahead<"));
    expect(bar).toContain('aria-current="page">Next steps');
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
