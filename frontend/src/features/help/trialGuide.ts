// The free trial user guide (/help/trial-guide, TrialGuidePage.tsx): the journey a trial organization follows from
// the first visit to the one-to-one demo, step by step. Getting started shows the same journey with each step's
// progress (journeyProgress), so the guide and the workspace never disagree. The facts here (limits, button names,
// what counts as trying a chapter) follow the product: backend/app/trial/service.py, story.py, team.py.

export const TRIAL_GUIDE_PATH = "/help/trial-guide";

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
  ["9 chapters", "a story on sample data"],
];

export const GUIDE_STEPS: readonly GuideStep[] = [
  {
    key: "open",
    title: "Open MDARIX and request your trial",
    time: "3 minutes",
    why: "Your request tells us your devices and markets, so your workspace starts ready for you.",
    actions: [
      "Open the MDARIX website and choose Start free trial.",
      "Step 1, About you: your name, job title, work email, company and country (a phone number is optional).",
      "Step 2, Your trial: company size, device class, the devices you make, your markets, where complaints are handled today and what you want to improve. Tick that you will not upload patient-identifiable data.",
      "Choose Request free trial. Sending the request accepts the Terms of Service and the Free Trial Agreement.",
    ],
    result:
      "With a company email your workspace is prepared at once and the activation email arrives within minutes. Other requests are reviewed, usually within one business day.",
    tip: "Use your work email: a company email gets its trial at once, and every trial message goes there.",
  },
  {
    key: "sign-in",
    title: "Activate your account and sign in",
    time: "5 minutes",
    why: "Your password is yours alone: MDARIX never sees it and never sends one.",
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
    tip: "Only the person who started the trial can invite. Each colleague chooses their own password; nobody shares one.",
  },
  {
    key: "sample",
    title: "Experience MDARIX on the sample data",
    time: "45 to 60 minutes",
    why: "The sample is a fictional manufacturer built from the pain points inspectors keep finding, so every screen has something to show from the first minute.",
    actions: [
      "In Getting started, open About the sample data: seven points, each with what is in the sample, why it matters and a button to the screen that shows it.",
      "Follow Your story, chapter by chapter. The quality loop at the top always names the next chapter; its button opens the right screen.",
      "A chapter counts as tried when you act in it: confirm or dismiss a record in the second look, record a reporting decision, open a case from a signal, ask MDARIX a question about the case, sign a decision, plan an effectiveness check, complete a risk review.",
      "Finish in Readiness: choose Download PDF for the readiness summary, or Inspection pack (ZIP) for the summary with every record behind each check, the files you would hand an inspector.",
    ],
    result:
      "The chapters tick off one by one, the loop fills in, and Readiness shows what an inspector would find first: the weakest link.",
    tip: "The sample case's Decision Brief is already written by a sample author, so you can review it and sign alone: whoever writes a brief never reviews or signs it. Signing asks for your password and authenticator code, exactly as on your live data.",
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
  "When it ends, the workspace closes and your trial data is kept for 30 more days, then deleted, unless you continue.",
  "To continue, ask for a pilot on your live data in your one-to-one demo: your records stay where they are.",
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
    sample: [tried >= SAMPLE_CHAPTERS_GOAL, `${tried} of 9 chapters tried`],
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
