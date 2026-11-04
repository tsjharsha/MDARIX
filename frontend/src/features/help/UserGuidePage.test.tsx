import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { UserGuidePage } from "./UserGuidePage";
import { GUIDE_PARTS, GUIDE_SECTIONS, USER_GUIDE_PATH } from "./userGuide";
import { TRIAL_GUIDE_PATH } from "./trialGuide";
import { NEXT_STEPS_HELP } from "./trialNextSteps";
import { HelpMenu, VIDEOS_PATH } from "../shared/HelpMenu";
import { TrialJourney } from "../workspace/sections/TrialJourney";

// The screens' source as text (Vite's ?raw), so a test can check that the guide quotes their labels exactly.
const SOURCES = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;
const source = (path: string) => {
  const text = SOURCES[path];
  if (text === undefined) throw new Error(`no source file ${path}`);
  return text;
};

describe("step-by-step user guide", () => {
  it("covers every screen, each topic with tasks to follow", () => {
    expect(USER_GUIDE_PATH).toBe("/help/user-guide");
    expect(GUIDE_PARTS.map((part) => part.title)).toEqual([
      "The basics",
      "Your home screens",
      "Complaints and trends",
      "Investigations",
      "Records",
      "Your data and your account",
      "Feedback, demo and the end of a trial",
    ]);
    const ids = GUIDE_SECTIONS.map((section) => section.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const section of GUIDE_SECTIONS) {
      expect(section.where.length).toBeGreaterThan(5);
      expect(section.tasks.length).toBeGreaterThan(0);
      for (const task of section.tasks) expect(task.steps.length).toBeGreaterThan(0);
    }
  });

  it("names the buttons and fields exactly as the screens do", () => {
    const guide = JSON.stringify(GUIDE_PARTS);
    // [label, the screen that shows it]
    const labels: [string, string][] = [
      ["Verify and turn on MFA", "../auth/AuthPage.tsx"],
      ["Use a recovery code", "../auth/AuthPage.tsx"],
      ["Send reset link", "../auth/AuthPage.tsx"],
      ["Generate new recovery codes", "../shared/TwoFactorSettings.tsx"],
      ["Generate new codes", "../shared/TwoFactorSettings.tsx"],
      ["I have saved these codes", "../shared/TwoFactorSettings.tsx"],
      ["Replace authenticator app", "../shared/TwoFactorSettings.tsx"],
      ["Replace authenticator app", "../auth/MfaAlreadyOn.tsx"],
      ["Stay signed in", "../shared/SessionTimeout.tsx"],
      ["Start the story there", "../workspace/sections/CitedFor.tsx"],
      ["Send the invitation", "../workspace/sections/TrialTeam.tsx"],
      ["Persona", "../workspace/sections/TrialTeam.tsx"],
      ["Resend invitation", "../workspace/sections/TrialTeam.tsx"],
      ["Remove from trial", "../workspace/sections/TrialTeam.tsx"],
      ["Reset MFA", "../workspace/sections/TrialTeam.tsx"],
      ["Approve", "../workspace/sections/TrialSupportAccess.tsx"],
      ["Deny", "../workspace/sections/TrialSupportAccess.tsx"],
      ["Revoke", "../workspace/sections/TrialSupportAccess.tsx"],
      ["History", "../workspace/sections/TrialSupportAccess.tsx"],
      ["Inspection pack (ZIP)", "../workspace/sections/Readiness.tsx"],
      ["Change decision", "../workspace/sections/Complaints.tsx"],
      ["Save reporting windows", "../workspace/sections/ReportingWindows.tsx"],
      ["Assess per market", "../workspace/sections/ReportabilityWatch.tsx"],
      ["Save answers", "../workspace/sections/MarketAssessment.tsx"],
      ["Save and sign", "../workspace/sections/MarketAssessment.tsx"],
      ["Record the filing", "../workspace/sections/MarketAssessment.tsx"],
      ["Create trend", "../workspace/sections/SignalInbox.tsx"],
      ["Open an investigation", "../workspace/sections/SignalDetail.tsx"],
      ["Raise a trend", "../workspace/sections/TrendCheck.tsx"],
      ["Run detection now", "../workspace/sections/DetectionRules.tsx"],
      ["Open an investigation", "../workspace/sections/Investigations.tsx"],
      ["Link evidence", "../workspace/sections/CaseEvidence.tsx"],
      ["Request evidence", "../workspace/sections/CaseEvidence.tsx"],
      ["Add hypothesis", "../workspace/sections/caseIntelligence/Hypotheses.tsx"],
      ["Record judgement", "../workspace/sections/caseIntelligence/Hypotheses.tsx"],
      ["Add unknown", "../workspace/sections/caseIntelligence/Unknowns.tsx"],
      ["Build a chain by hand", "../workspace/sections/caseIntelligence/FailureChain.tsx"],
      ["Record observation", "../workspace/sections/caseIntelligence/Observations.tsx"],
      ["Save scope", "../workspace/sections/CaseScope.tsx"],
      ["Record outcome", "../workspace/sections/CaseReviews.tsx"],
      ["Compose the brief", "../workspace/sections/CaseDecisionBrief.tsx"],
      ["Submit for quality review", "../workspace/sections/CaseDecisionBrief.tsx"],
      ["Start review", "../workspace/sections/CaseDecisionBrief.tsx"],
      ["Record review", "../workspace/sections/CaseDecisionBrief.tsx"],
      ["Continue to sign", "../workspace/sections/CaseDecision.tsx"],
      ["Sign decision", "../workspace/sections/CaseDecision.tsx"],
      ["Return to the investigator", "../workspace/sections/CaseDecision.tsx"],
      ["Plan the check", "../workspace/sections/Records.tsx"],
      ["Sign the result", "../workspace/sections/Records.tsx"],
      ["Check file", "../workspace/sections/ImportData.tsx"],
      ["Remove the sample data", "../workspace/sections/RemoveSample.tsx"],
      ["Change password", "../workspace/sections/Account.tsx"],
      ["Send feedback", "../workspace/sections/Feedback.tsx"],
      ["Request the demo", "../workspace/sections/BookDemo.tsx"],
      ["End my trial early", "../workspace/sections/EndTrial.tsx"],
    ];
    for (const [label, file] of labels) {
      expect(guide, label).toContain(label);
      expect(source(file), `${label} in ${file}`).toContain(label);
    }
  });

  it("opens with the contents, links the short trial guide, and lists the roles", () => {
    const html = renderToStaticMarkup(<UserGuidePage />);
    expect(html).toContain("Step-by-step user guide");
    expect(html).toContain("MDARIX, screen by screen");
    expect(html).toContain(`href="${TRIAL_GUIDE_PATH}"`);
    for (const section of GUIDE_SECTIONS) expect(html).toContain(`href="#${section.id}"`);
    expect(html).toContain("Leader (Quality Manager)");
    expect(html).toContain("Save as PDF");
  });

  it("says what MDARIX covers by device category, in Help, not in a new tab (J32)", () => {
    const html = renderToStaticMarkup(<UserGuidePage />);
    expect(html).toContain('href="#coverage"');
    expect(html).toContain("What MDARIX covers");
    for (const category of [
      "Implant",
      "Single-use",
      "Reusable or capital equipment",
      "Software",
      "IVD (in-vitro diagnostic)",
      "Kit",
    ])
      expect(html).toContain(`<h3>${category}</h3>`);
    expect(html.split("Not covered yet").length - 1).toBe(6);
    expect(html).toContain("EU IVDR Art. 82 (starter)");
    expect(html).toContain("for your regulatory consultant to confirm");
  });

  it("is told apart from the free trial user guide wherever both are offered", () => {
    const journey = renderToStaticMarkup(<TrialJourney steps={[]} source={{ state: "ready" }} onGo={() => {}} />);
    expect(journey).toContain(`href="${TRIAL_GUIDE_PATH}"`);
    expect(journey).toContain(`href="${USER_GUIDE_PATH}"`);
    expect(journey).toContain("Free trial user guide");
    expect(journey).toContain("Step-by-step user guide");
    // The help menu opens on demand; its source holds both links with their own line of explanation.
    const menu = source("../shared/HelpMenu.tsx");
    expect(menu).toContain("Every screen, task by task");
    expect(menu).toContain("The trial, step by step");
    expect(renderToStaticMarkup(<HelpMenu />)).toContain("Open help menu");
    // The website's videos, in a new tab.
    expect(menu).toContain("Watch the videos");
    expect(menu).toContain('href={VIDEOS_PATH} target="_blank"');
    expect(VIDEOS_PATH).toBe("/videos");
    // In a trial, "Talk to us about the next step" opens Next steps, from trial to pilot (UX-25).
    expect(NEXT_STEPS_HELP).toBe("Talk to us about the next step");
    expect(menu).toContain("{NEXT_STEPS_HELP}");
    expect(menu).toContain("<small>{NEXT_STEPS_LINK}</small>");
    expect(menu).toContain('workspace.open("Next steps")');
  });
});
