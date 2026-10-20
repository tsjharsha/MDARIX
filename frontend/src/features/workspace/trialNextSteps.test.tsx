import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  MvpRequestForm,
  TrialNextStepsSection,
  isOpenMvpRequest,
  mvpRequestText,
  type DataMove,
  type MvpRequest,
} from "./sections/TrialNextSteps";
import {
  CALL_TO_ACTION,
  MVP_STEPS,
  NEXT_STEPS_INTRO,
  NEXT_STEPS_PATH,
  NEXT_STEPS_SUBTITLE,
  QUESTIONS,
  TRIAL_TO_MVP,
  dataMoveExplanation,
} from "../help/trialNextSteps";
import { AFTER_THE_TRIAL } from "../help/trialGuide";
import { TrialGuidePage } from "../help/TrialGuidePage";
import { TRIAL_ONLY_SECTIONS, WORKSPACE_SECTIONS, sectionAllowed } from "./workspaceContext";
import { addressFor } from "./workspaceAddress";
import { APP_ROUTES, viewFromPath } from "../../app/router";
import { WORKSPACE_VIEWS } from "../../app/navigationPolicy";
import { mvpDataText, mvpRequestLines } from "../admin/MvpRequestsWorkspace";
import { CompanyPage } from "../../site/pages";
import { afterTheTrial } from "../../site/content";

const request = (overrides: Partial<MvpRequest> = {}): MvpRequest => ({
  id: "m1",
  status: "NEW",
  expectations: "Find hidden complaints across two pump lines.",
  scope: null,
  phone: null,
  contact_preference: null,
  move_trial_data: false,
  requested_by: "Priya Sharma",
  created_at: "2026-10-18T09:00:00Z",
  updated_at: "2026-10-18T09:00:00Z",
  ...overrides,
});
const move = (overrides: Partial<DataMove> = {}): DataMove => ({
  allowed: false,
  reason: "SAMPLE_DATA_PRESENT",
  sample_records: 120,
  own_records: 0,
  ...overrides,
});
// A price or a discount figure: a currency, a percentage, or "per month/user".
const PRICE = /[$€£₹]|\d\s?%|\bper (month|user|year)\b|\bINR\b|\bUSD\b/i;

describe("Next steps, from trial to pilot", () => {
  it("shows every section of the approved page, in order, and no price", () => {
    const html = renderToStaticMarkup(<TrialNextStepsSection />);
    const order = [
      NEXT_STEPS_INTRO.title,
      NEXT_STEPS_INTRO.talk,
      NEXT_STEPS_INTRO.download,
      "The pilot works only with your real data",
      "What changes from the trial to the pilot",
      "How the pilot starts",
      "How your data is connected",
      "A new role: Customer Administrator",
      "What we need from you",
      "Price",
      "Common questions",
      CALL_TO_ACTION.title,
      CALL_TO_ACTION.action,
    ];
    let at = -1;
    for (const text of order) {
      const found = html.indexOf(text, at + 1);
      expect(found, text).toBeGreaterThan(at);
      at = found;
    }
    for (const row of TRIAL_TO_MVP) expect(html).toContain(row.mvp);
    // The paid step after the trial is a pilot wherever a customer reads it; "MVP" stays an internal word (UX-09).
    expect(html).not.toContain("MVP");
    expect(NEXT_STEPS_SUBTITLE).toBe("From trial to pilot");
    expect(MVP_STEPS).toHaveLength(5);
    for (const step of MVP_STEPS) expect(html).toContain(step.title);
    for (const item of QUESTIONS) expect(html).toContain(item.question);
    expect(html).toContain(
      "A dedicated MDARIX transactional database, set up only for your organization and run by MDARIX",
    );
    expect(html).toContain("3 months to 1 year");
    expect(html).toContain('href="mailto:support@mdarix.in"');
    // The page heading is the workspace's own h1; the page has none of its own.
    expect(html).not.toContain("<h1");
    expect(html).not.toMatch(PRICE);
  });

  it("offers the data move only when the server allows it, and explains why not otherwise", () => {
    const allowed = renderToStaticMarkup(
      <MvpRequestForm
        request={null}
        dataMove={move({ allowed: true, reason: null, sample_records: 0, own_records: 40 })}
        onClose={() => undefined}
        onSent={() => undefined}
      />,
    );
    expect(allowed).toContain("Move our trial data into the pilot");
    expect(allowed).toContain('type="checkbox"');
    expect(allowed).toContain("What do you expect from the pilot?");
    expect(allowed).toContain("Products, sites and systems you have in mind (optional)");
    expect(allowed).toContain("Contact preferences (optional)");
    expect(allowed).toContain("Send the request");

    const sample = renderToStaticMarkup(
      <MvpRequestForm request={null} dataMove={move()} onClose={() => undefined} onSent={() => undefined} />,
    );
    expect(sample).not.toContain('type="checkbox"');
    expect(sample).toContain("Your trial still holds the sample data");
    expect(dataMoveExplanation("NO_OWN_DATA")).toContain("none of your own data yet");
    expect(dataMoveExplanation(null)).toContain("deleted 30 days after the trial ends");

    // An open request is updated, with what it said.
    const update = renderToStaticMarkup(
      <MvpRequestForm
        request={request({ scope: "OrbitCare 300" })}
        dataMove={move()}
        onClose={() => undefined}
        onSent={() => undefined}
      />,
    );
    expect(update).toContain("Update the request");
    expect(update).toContain("OrbitCare 300");
  });

  it("says where the organization's request stands", () => {
    expect(mvpRequestText(null)).toBeNull();
    expect(mvpRequestText(request())).toContain("You asked for a pilot conversation on");
    expect(mvpRequestText(request({ status: "CONTACTED" }))).toContain("has been in touch about your pilot");
    expect(mvpRequestText(request({ status: "CLOSED" }))).toBeNull();
    expect(isOpenMvpRequest(request())).toBe(true);
    expect(isOpenMvpRequest(request({ status: "CONTACTED" }))).toBe(true);
    expect(isOpenMvpRequest(request({ status: "CLOSED" }))).toBe(false);
  });

  it("is a trial-only section everyone in the trial sees, with its own address", () => {
    expect(WORKSPACE_SECTIONS).toContain("Next steps");
    expect(TRIAL_ONLY_SECTIONS).toContain("Next steps");
    // No menu key or permission: every role in a trial organization has it.
    expect(sectionAllowed("Next steps", [], [])).toBe(true);
    expect(APP_ROUTES["next-steps"]).toBe(NEXT_STEPS_PATH);
    expect(viewFromPath(NEXT_STEPS_PATH)).toBe("next-steps");
    expect(WORKSPACE_VIEWS).toContain("next-steps");
    expect(addressFor({ section: "Next steps" })).toBe(NEXT_STEPS_PATH);
  });

  it("shows Platform Admin what the trial expects and what to do with its data", () => {
    expect(mvpDataText({ move_trial_data: true })).toBe("Move the trial data into the pilot");
    expect(mvpDataText({ move_trial_data: false })).toBe("Start the pilot without the trial data");
    expect(mvpRequestLines({ scope: "Pumps", contact_preference: "Tuesday", days_left: 1 })).toEqual([
      "In scope: Pumps",
      "Reach them: Tuesday",
      "1 day left in the trial",
    ]);
  });
});

describe("the trial user guide's After your trial chapter", () => {
  it("tells the same story as Next steps", () => {
    const html = renderToStaticMarkup(<TrialGuidePage />);
    expect(html).toContain('id="after-your-trial"');
    expect(html).toContain('href="#after-your-trial"');
    for (const step of MVP_STEPS) expect(html).toContain(step.title);
    expect(html).toContain("The pilot works only with your real data");
    expect(html).not.toContain("MVP");
    expect(html).not.toMatch(PRICE);
    // Trial data is moved only on request: it never simply stays where it is.
    expect(AFTER_THE_TRIAL.join(" ")).not.toContain("your records stay where they are");
    expect(AFTER_THE_TRIAL.join(" ")).toContain(CALL_TO_ACTION.action);
  });
});

describe("the website's After the trial section", () => {
  it("says what follows the trial, with no price and no link into the application", () => {
    const html = renderToStaticMarkup(<CompanyPage />);
    const start = html.indexOf('id="after-the-trial"');
    expect(start).toBeGreaterThan(-1);
    const section = html.slice(start, html.indexOf("</section>", start));
    for (const [title] of afterTheTrial.points) expect(section).toContain(title);
    expect(section).toContain("dedicated MDARIX transactional database");
    expect(section).toContain("2 to 3 weeks");
    expect(section).toContain("Design partners receive a discount");
    expect(section).not.toMatch(PRICE);
    expect(section).not.toContain("href=");
  });
});
