// 0.10.87, the owner-approved duplication review: the new navigation's shell says each thing once (rows 1-3, 7, 11,
// 13, 14, 18, 28, 44, 45, 47-49, 52).
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { contextPickerShown, pageHeadShown, trialShellShows, zoneLineShown } from "./HybridShell";
import { NEW_HEADS } from "./UserWorkspace";
import { HelpMenu } from "../shared/HelpMenu";
import { LOOK_AHEAD_SUMMARY } from "./partyPreview";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { TrialNextStepsSection } from "./sections/TrialNextSteps";
import userWorkspace from "./UserWorkspace.tsx?raw";

const help = (navigation: string, session: object = {}) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={{ navigation, isTrial: true, open: vi.fn(), session } as unknown as WorkspaceApi}>
      <HelpMenu onGettingStarted={vi.fn()} defaultOpen />
    </WorkspaceContext.Provider>,
  );

describe("the shell's page head", () => {
  it("is left out where the page has its own head: one report, Next steps, Home, Getting started", () => {
    expect(pageHeadShown("Reports", true, true, "?report=r1")).toBe(false);
    expect(pageHeadShown("Reports", true, true, undefined)).toBe(true);
    expect(pageHeadShown("Next steps", true, true)).toBe(false);
    expect(pageHeadShown("My Work", true, true)).toBe(false);
    expect(pageHeadShown("Getting started", true, true)).toBe(false);
    expect(pageHeadShown("Complaint", true, true)).toBe(false);
    // The classic navigation keeps its heads.
    expect(pageHeadShown("Next steps", false, true)).toBe(true);
    expect(pageHeadShown("Reports", false, true, "?report=r1")).toBe(true);
  });

  it("says the time zone only on pages that show times", () => {
    for (const section of [
      "Complaints",
      "Decision trees",
      "Reports",
      "Investigations",
      "Trends",
      "Records",
      "Settings",
    ])
      expect(zoneLineShown(section, true), section).toBe(true);
    for (const section of ["Look ahead", "Team", "Import your data", "Share feedback", "My Account"])
      expect(zoneLineShown(section, true), section).toBe(false);
    expect(zoneLineShown("Look ahead", false)).toBe(true);
  });

  it("gives Next steps one heading, its own intro, as the page's h1 on the new navigation", () => {
    const page = (navigation: string) =>
      renderToStaticMarkup(
        <WorkspaceContext.Provider value={{ navigation, isTrial: true, open: vi.fn() } as unknown as WorkspaceApi}>
          <TrialNextStepsSection />
        </WorkspaceContext.Provider>,
      );
    expect(page("new")).toContain('<h1 id="next-steps-title"');
    expect(page("classic")).toContain('<h2 id="next-steps-title"');
  });

  it("asks Look ahead's own question, with no second word of sample data in its guide", () => {
    expect(NEW_HEADS["Look ahead"]).toBe("What will your partners see?");
    expect(LOOK_AHEAD_SUMMARY).not.toContain("sample data");
  });

  it("says once on the report that MDARIX never submits, and once on Import what is checked", () => {
    expect(userWorkspace).not.toContain("you submit it through the authority");
    expect(userWorkspace).not.toContain("The sample stays until you remove it");
  });
});

describe("the shell's pickers, labels and banners", () => {
  it("shows the product picker only on Trends tabs without a filter of their own, never on Investigations", () => {
    expect(contextPickerShown("Investigations", "All investigations")).toBe(false);
    expect(contextPickerShown("Investigations", undefined)).toBe(false);
    expect(contextPickerShown("Trends", undefined)).toBe(false);
    expect(contextPickerShown("Trends", "Trend check?product=X")).toBe(false);
    expect(contextPickerShown("Trends", "Over time")).toBe(true);
  });

  it("drops the top bar's sample label on Getting started, the import button on its own page, and the old banners", () => {
    expect(trialShellShows("Getting started", true, "sample").sampleChip).toBe(false);
    expect(trialShellShows("Complaints", true, "sample").sampleChip).toBe(true);
    expect(trialShellShows("Import your data", true, "sample").importButton).toBe(false);
    expect(trialShellShows("Complaints", true, "sample").importButton).toBe(true);
    // The chapter banners only on the classic navigation; the story bar not on Home, which has its own banner.
    expect(trialShellShows("Complaints", true, "none").chapterDone).toBe(false);
    expect(trialShellShows("Complaints", false, "none").chapterDone).toBe(true);
    expect(trialShellShows("My Work", true, "none").storyBar).toBe(false);
    expect(trialShellShows("Complaint", true, "none").storyBar).toBe(true);
  });

  it("opens the trial's dates from the badge, which no longer repeats the practice note", () => {
    expect(userWorkspace).toContain('onClick={() => open("Getting started", "Your trial")}');
    expect(userWorkspace).not.toContain("title={`${tenantName}. ${TRIAL_DATA_NOTE}`}");
  });
});

describe("Help on the new navigation", () => {
  it("no longer repeats the import, the pilot conversation or Next steps; the classic Help keeps them", () => {
    const fresh = help("new");
    expect(fresh).not.toContain("Try your own data");
    expect(fresh).not.toContain("Getting started and import templates");
    expect(help("new", { sample_only: true })).not.toContain("Discuss a pilot");
    expect(help("classic")).toContain("Getting started and import templates");
    expect(help("classic", { sample_only: true })).toContain("Discuss a pilot");
  });

  it("names the trial guide without a step count that disagrees with the ten-step walkthrough", () => {
    expect(help("new")).toContain("The trial, step by step");
    expect(help("new")).not.toContain("7 steps");
  });
});
