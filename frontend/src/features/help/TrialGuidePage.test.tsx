import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TrialGuidePage } from "./TrialGuidePage";
import { GuideScene, shortTitle } from "./TrialGuideVisuals";
import { GUIDE_STEPS, SAMPLE_CHAPTERS_GOAL, TRIAL_GUIDE_PATH, journeyProgress } from "./trialGuide";
import { TrialJourney } from "../workspace/sections/TrialJourney";

describe("free trial user guide", () => {
  it("walks the whole journey in order, from the first visit to the demo", () => {
    expect(TRIAL_GUIDE_PATH).toBe("/help/trial-guide");
    expect(GUIDE_STEPS.map((step) => step.key)).toEqual([
      "open",
      "sign-in",
      "team",
      "sample",
      "own-data",
      "feedback",
      "demo",
    ]);
    for (const step of GUIDE_STEPS) {
      expect(step.actions.length).toBeGreaterThanOrEqual(3);
      expect(step.result.length).toBeGreaterThan(20);
      // Every step has a few words for the journey picture.
      expect(shortTitle(step.title)).not.toBe(step.title);
    }
    const text = JSON.stringify(GUIDE_STEPS);
    // The names people will see on screen.
    for (const label of [
      "Start free trial",
      "Request free trial",
      "Invite colleague",
      "Resend invitation",
      "Check file",
      "Send feedback",
      "Book a one-to-one demo",
      "Request the demo",
      "Download PDF",
      "Inspection pack (ZIP)",
    ])
      expect(text).toContain(label);
    // Nobody is ever sent a password.
    expect(text).toContain("MDARIX never sees it");
  });

  it("draws every step and the journey, and can be saved as a PDF", () => {
    const html = renderToStaticMarkup(<TrialGuidePage />);
    expect(html).toContain("Your MDARIX free trial, step by step");
    expect(html.match(/<svg[^>]*class="tg-(scene|journey)"/g)).toHaveLength(GUIDE_STEPS.length + 1);
    for (const step of GUIDE_STEPS) expect(html).toContain(step.title);
    expect(html).toContain("Save as PDF");
    expect(html).toContain("Step 7 of 7");
    expect(html).toContain("When the 30 days are over");
  });

  it("ticks the journey from the trial's own records", () => {
    const start = journeyProgress({ users: 1, userLimit: 3, chaptersTried: 0 });
    expect(start.filter((step) => step.done).map((step) => step.key)).toEqual(["open", "sign-in"]);
    expect(start.find((step) => step.key === "team")?.detail).toBe("0 of 2 colleagues invited");
    const half = journeyProgress({ users: 2, userLimit: 3, chaptersTried: SAMPLE_CHAPTERS_GOAL - 1, ownRecords: 4 });
    expect(half.find((step) => step.key === "team")?.done).toBe(false);
    expect(half.find((step) => step.key === "sample")?.done).toBe(false);
    expect(half.find((step) => step.key === "own-data")?.done).toBe(true);
    const all = journeyProgress({
      users: 3,
      userLimit: 3,
      chaptersTried: 9,
      ownComplaints: 12,
      feedbackSent: true,
      demoRequested: true,
    });
    expect(all.every((step) => step.done)).toBe(true);
    expect(all.find((step) => step.key === "team")?.detail).toBe("2 of 2 colleagues invited");
  });

  it("shows the journey in Getting started with the next step and the guide one click away", () => {
    const steps = journeyProgress({ users: 3, userLimit: 3, chaptersTried: 1 });
    const html = renderToStaticMarkup(<TrialJourney steps={steps} onGo={() => undefined} />);
    expect(html).toContain("3 of 7 steps done");
    expect(html).toContain("next: experience mdarix on the sample data");
    expect(html).toContain("Continue the story");
    expect(html).toContain(`href="${TRIAL_GUIDE_PATH}"`);
    expect(html).toContain("Free trial user guide");
  });
});

describe("free trial user guide illustrations", () => {
  it("show the address people type, mdarix.in", () => {
    const html = GUIDE_STEPS.map((step) => renderToStaticMarkup(<GuideScene step={step.key} />)).join("");
    expect(html).toContain("mdarix.in/activate-account");
    expect(html).not.toContain("mdarix.com");
  });
});
