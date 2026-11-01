// The free trial user guide (/help/trial-guide, TrialGuidePage.tsx): the journey a trial organization follows from
// the first visit to the one-to-one demo, step by step. Getting started shows the same journey with each step's
// progress (journeyProgress), so the guide and the workspace never disagree. The facts here (limits, button names,
// what counts as trying a chapter) follow the product: backend/app/trial/service.py, story.py, team.py. The chapter
// after the seven steps, After your trial, is the Next steps page's words (trialNextSteps.ts).

import { CALL_TO_ACTION, NEXT_STEPS_SECTION } from "./trialNextSteps";

export { TRIAL_GUIDE_PATH } from "./paths";

export type GuideStep = {
  key: JourneyKey;
  title: string;
  /** About how long the step takes. */
  time: string;
  /** Why this step, in one sentence. */
  why: string;
  /** What to do, in order. */
  actions: readonly string[];
  /** What you see when it worked. */
  result: string;
  tip?: string;
};

export type JourneyKey = "open" | "sign-in" | "team" | "sample" | "own-data" | "feedback" | "demo";

export const TRIAL_FACTS: readonly [string, string][] = [
  ["30 days", "free, no credit card"],
  ["3 people", "you and two colleagues"],
  ["5,000 rows", "of your own data, 2 MB a file"],
  ["10 chapters", "a story on sample data, routine complaints first"],
];

export const GUIDE_STEPS: readonly GuideStep[] = [
  {
    key: "open",
    title: "Open MDARIX and request your trial",
    time: "3 minutes",
    why: "Your request tells us your devices and markets, so your workspace starts ready for you.",
    actions: [
      "Before you start, have an authenticator app on your phone (Microsoft Authenticator, Google Authenticator, 1Password or similar): every account uses two-factor sign-in (MFA), set up at your first sign-in.",
      "Open the MDARIX website and choose Start free trial.",
      "Step 1, About you: your name, job title, work email, company and country (a phone number is optional).",
      "Step 2, Your trial: company size, device class, the devices you make, your markets, where complaints are handled today and what you want to improve. Tick that you will not upload patient-identifiable data.",
      "Choose Request free trial. Sending the request accepts the Terms of Service and the Free Trial Agreement and acknowledges the Privacy Policy; MDARIX records which version of each you accepted.",
    ],
    result:
      "With a company or personal email the trial is approved automatically and the activation email arrives within minutes, up to a daily limit of new trials. Requests from disposable email addresses, and any beyond that limit, are reviewed by the MDARIX team, usually within one business day.",
    tip: "Use an address you read every day: a company or personal email gets its trial within minutes, and every trial message goes there.",
  },
  {
    key: "sign-in",
    title: "Activate your account and sign in",
    time: "5 minutes",
    why: "Your password is yours alone: MDARIX stores only a salted hash of it, so no one at MDARIX can read it, and it never sends one.",
    actions: [
      "Open the invitation email and choose the activation link (valid for 48 hours).",
      "Choose a password of at least 12 characters. A phrase of several words works well.",
      "Sign in with your email and new password.",
      "When asked, add MDARIX to an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password and others) and enter its 6-digit code. Keep the recovery codes somewhere safe.",
    ],
    result:
      "You land on Getting started: your free trial as a story, with the quality loop at the top and the days left beside your organization's name.",
    tip: "The authenticator code is also what signs decisions later, like a handwritten signature.",
  },
  {
    key: "team",
    title: "Invite two colleagues",
    time: "2 minutes",
    why: "Quality work is a team sport: a complaint handler and a regulatory colleague see the value from their own side.",
    actions: [
      "In Getting started, open the Team tab below the story.",
      "Enter your colleague's name and work email, then choose Invite colleague.",
      "Repeat for the second colleague. The trial has three seats: you and two others.",
      "If an invitation is not found, choose Resend invitation beside the colleague's name.",
    ],
    result:
      "Both colleagues are listed as Invited, then Active once they set their own password from their email (the link is valid for 48 hours).",
    tip: "Only the person who started the trial can invite. Each colleague chooses their own password; nobody shares one. If someone leaves, choose Remove from trial to free their seat.",
  },
  {
    key: "sample",
    title: "Experience MDARIX on the sample data",
    time: "45 to 60 minutes",
    why: "The sample is a fictional manufacturer built from the pain points inspectors keep finding, so every screen has something to show from the first minute.",
    actions: [
      "At the top of Getting started, tick what FDA, a notified body or your own audit cited you for: the story starts with those chapters.",
      "In Getting started, open About the sample data: seven points, each with what is in the sample, why it matters and a button to the screen that shows it.",
      "Follow Your story, chapter by chapter. The quality loop at the top always names the next chapter; its button opens the right screen.",
      "Before the chapters, Before a complaint opens Complaints › First contact and Triage: log a call from a hospital and see it become a complaint, a service job, both or pending; urgent intakes and calls that mention harm reach the triage list at once, with their clocks running from awareness. The sample has four calls, an urgent intake and a likely duplicate to link.",
      "After a conclusion, Complaints › Reports drafts the US Form FDA 3500A or India MvPI worksheet in the authority's field order: a colleague approves the snapshot, you enter it in the authority's route and record the submission and the receipt. MDARIX never submits. The sample has a finished US report (SAMPLE-RV-09) and an India report to correct after a bounced e-mail (SAMPLE-RV-10); SAMPLE-RV-06's worksheet opens once you sign its US conclusion.",
      "Complaints › Decision guides shows the sample's own US guide, US-v2 (its help text and a VMSR question, approved by a colleague), and a draft US-v3 whose own test fails, so you can see what blocks publication. Complaints › Communications holds a reporter follow-up with two unanswered attempts, an answered distributor question and a hospital request unresolved after attempts; MDARIX sends nothing.",
      "The bell and the top of My Work show your reminders and escalations: the reporter's reply on SAMPLE-RV-08 is overdue and escalated, and the MDARIX sample author is away with you as backup. Readiness › Oversight lists everything overdue or due soon with its owner, and each event's closure checklist: SAMPLE-RV-08 is not ready; SAMPLE-RT-03's checklist is clear, so you sign it ready to close and file its decision record.",
      "On a case, Lot impact asks what else is out there: open the OrbitCare case (or one you opened from its signal) and keep the suggested sensor lot, NS-SL-2417 (Sample). Two lots with complaints and three more built with the same sensor lot, with units in India, the US and Europe and some still in stock; lot 008 has no distribution imported. Leave a lot out with a reason, keep the list with the case and sign it. MDARIX lists; you decide any field action in your QMS.",
      "A chapter counts as tried when you act in it: close a routine complaint, record a reporting decision, confirm or dismiss a record in the second look, open a case from a signal, ask MDARIX a question about the case, sign a decision, plan an effectiveness check, complete a risk review, sign a document.",
      "After the last chapter, the Look ahead card opens three read-only previews with sample data: How a distributor reports, As your distributor sees it, and As your authorised representative sees it. Nothing there can be sent or changed.",
      "Finish in Records › Reports: choose Management review report and Generate, cut-off now, write Actions decided, choose Save the section, then Sign the document; its PDF and DOCX are what you would file in your QMS. Readiness keeps Download PDF for the readiness summary and Inspection pack (ZIP) with every record behind each check.",
    ],
    result:
      "The chapters tick off one by one, the loop fills in, and Readiness shows what an inspector would find first: the weakest link.",
    tip: "The sample case's Decision Brief is already written by a sample author, who also recorded by hand two competing hypotheses, two open questions and a failure chain (Intelligence tab), so you can review it and sign alone: whoever writes a brief never reviews or signs it. Before you sign you confirm that you have read its open questions; signing asks for your password and authenticator code, exactly as on your live data.",
  },
  {
    key: "own-data",
    title: "Upload your own data",
    time: "30 minutes",
    why: "The same checks then run on your records, and that is where MDARIX shows what it would find in your own quality system.",
    actions: [
      "Open Import data (or the Your data tab in Getting started): it opens on Complaints.",
      "Choose your complaints export as it comes from your quality system, an Excel workbook or a CSV file. MDARIX reads its column names (Complaint Number, Product Code, Lot # and the like) and leaves out the columns it does not need, without storing them.",
      "Pick the date format of a CSV file (Excel dates are read as they are), then choose Check file: you see how each column was read, and the products and lots the file adds, before anything is saved.",
      "Then add your lots with their quantities, so trends are counted per unit in the field, and your investigations, CAPAs and risks, so every inspection check reads your own records. Download gives a template for any of them.",
      "After each import choose See its data-quality report: rows read, written and set aside, each row set aside with its reason. A complaint's disposition shows where it came from (file and row) and its IMDRF codes.",
    ],
    result:
      "Your records sit beside the sample, and Readiness, Complaints, Signals and Records show findings from your own data. The chapter See it on your own data is ticked.",
    tip: "Keep your quality system's own statuses (Cancelled, Void, Inquiry...): the second look reads them to find complaints that were closed off. Personal details in the text can be replaced by placeholders such as [PERSON]. The sample never counts toward your 5,000 rows.",
  },
  {
    key: "feedback",
    title: "Share your feedback",
    time: "3 minutes",
    why: "Your feedback decides what we build next, and it is read by the people who build MDARIX.",
    actions: [
      "Open Share feedback in the menu (MDARIX also invites you from day 3, or once you have uploaded your own data).",
      "Answer what you like in five short parts: about you, your ratings, what you tried, what to improve, and how we may use your words.",
      "Only the overall rating and the last question are required. Choose Send feedback.",
    ],
    result:
      "Thank you, with your feedback listed. You may withdraw permission to quote you at any time; private feedback stays private.",
  },
  {
    key: "demo",
    title: "Book your one-to-one demo",
    time: "2 minutes",
    why: "In a one-to-one session the MDARIX team walks through what your trial found and how a pilot on your live data would run.",
    actions: [
      "In Getting started, choose Book a one-to-one demo, under the story's chapters.",
      "Give the times that suit you and, if you like, a phone number.",
      "Tick the chapters you want to focus on and add a note, for example an audit that is coming up.",
      "Choose Request the demo.",
    ],
    result:
      "The button changes to Demo requested, and the MDARIX team contacts you to agree a time. The demo starts from your own trial.",
    tip: "Nothing is booked until we agree a time together.",
  },
];

export const AFTER_THE_TRIAL: readonly string[] = [
  "The trial runs for 30 days. The days left are shown at the top of every screen.",
  "When it ends, the workspace closes and your trial data is kept for 30 more days, then deleted, unless you asked for it to be moved into your pilot.",
  `To continue, open ${NEXT_STEPS_SECTION} in your workspace and choose ${CALL_TO_ACTION.action}: the pilot runs on your real data, in a database set up only for your organization and run by MDARIX (see After your trial, above).`,
  "To stop sooner, the person who started the trial chooses End my trial early at the bottom of Getting started. The MDARIX team confirms it by email and, if you ask, deletes all your trial data.",
];

/** What Getting started knows about the trial, to tick the journey's steps. */
export type JourneyInput = {
  users?: number | null;
  userLimit?: number | null;
  chaptersTried?: number | null;
  ownComplaints?: number | null;
  ownRecords?: number | null;
  feedbackSent?: boolean | null;
  demoRequested?: boolean | null;
};

export type JourneyStep = { key: JourneyKey; title: string; done: boolean; detail: string };

/** Three chapters tried is the point where a trial has felt the story (the Platform Admin's "engaged" is the same). */
export const SAMPLE_CHAPTERS_GOAL = 3;

/** The journey's steps with what is done, from the trial's own records (a signed-in person has opened and signed in). */
export function journeyProgress(input: JourneyInput): JourneyStep[] {
  const limit = Math.max(1, input.userLimit ?? 3);
  const invited = Math.max(0, (input.users ?? 1) - 1);
  const wanted = limit - 1;
  const tried = input.chaptersTried ?? 0;
  const own = (input.ownComplaints ?? 0) + (input.ownRecords ?? 0);
  const detail: Record<JourneyKey, [boolean, string]> = {
    open: [true, "Trial approved"],
    "sign-in": [true, "Signed in"],
    team: [invited >= wanted, `${Math.min(invited, wanted)} of ${wanted} colleagues invited`],
    sample: [tried >= SAMPLE_CHAPTERS_GOAL, `${tried} of 10 chapters tried`],
    "own-data": [own > 0, own > 0 ? "Your own data is in" : "Not uploaded yet"],
    feedback: [!!input.feedbackSent, input.feedbackSent ? "Thank you" : "Not sent yet"],
    demo: [!!input.demoRequested, input.demoRequested ? "Demo requested" : "Not booked yet"],
  };
  return GUIDE_STEPS.map((step) => ({
    key: step.key,
    title: step.title,
    done: detail[step.key][0],
    detail: detail[step.key][1],
  }));
}
