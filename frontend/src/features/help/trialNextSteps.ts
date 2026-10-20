// Next steps, from trial to pilot: the words of the trial workspace's Next steps page
// (workspace/sections/TrialNextSteps.tsx) and of the free trial user guide's "After your trial" chapter
// (TrialGuidePage.tsx), kept here once so the two never disagree. The paid step after the trial is called a pilot
// wherever a customer reads it (UX-09); "MVP" stays an internal word (identifiers, the `mvp` feature set). The owner's
// decisions they follow: the pilot runs on a dedicated MDARIX transactional database for the organization, hosted and
// run by MDARIX; it uses real data only; trial data moves into it only on request, and only when the organization
// removed the sample data and imported its own (backend/app/trial/mvp_request.py checks it too); it lasts 3 months to 1
// year; its price comes in a written proposal (no prices or discount figures anywhere).

/** The workspace section's name and its line in the menu. */
export const NEXT_STEPS_SECTION = "Next steps";
export const NEXT_STEPS_SUBTITLE = "From trial to pilot";
/** How a link to the page names it (Getting started, End your trial early). */
export const NEXT_STEPS_LINK = `${NEXT_STEPS_SECTION}: from trial to pilot`;
/** The page in one line, where it is linked (the menu's page heading, Getting started). */
export const NEXT_STEPS_SUMMARY =
  "The pilot is MDARIX on your real data: what changes from the trial, how the pilot starts, and what we need from you.";
/** The page's own address, linked from the trial's last reminder emails (auth/emailer.py send_trial_reminder). */
export const NEXT_STEPS_PATH = "/app/next-steps";

export const NEXT_STEPS_INTRO = {
  eyebrow: "After your free trial",
  title: "Next steps: from your free trial to an MDARIX pilot",
  lede: "The trial shows how MDARIX works, using sample data. The pilot is the next step: MDARIX working on your real complaints, connected to your own systems, run by your own team. This page explains what changes, how the pilot starts, and what we need from you.",
  talk: "Talk to us about a pilot",
  download: "Download this page as PDF",
} as const;

export const REAL_DATA_NOTICE = {
  title: "The pilot works only with your real data",
  text: "There is no sample data in the pilot. The pilot starts with your own records, in a database set up only for your organization. If you uploaded your own data in the trial and removed the sample data, we can move that data into your pilot on request. Otherwise nothing is moved, and your trial data is deleted 30 days after the trial ends.",
} as const;

export type TrialToMvpChange = { aspect: string; trial: string; mvp: string };

export const CHANGES_TITLE = "What changes from the trial to the pilot";
export const CHANGES_COLUMNS = { trial: "Free trial (now)", mvp: "Pilot" } as const;
export const TRIAL_TO_MVP: readonly TrialToMvpChange[] = [
  { aspect: "Data", trial: "Sample data, plus exports you upload", mvp: "Your real data only. No sample data." },
  {
    aspect: "Where your data lives",
    trial: "The shared MDARIX trial environment",
    mvp: "A dedicated MDARIX transactional database, set up only for your organization and run by MDARIX",
  },
  {
    aspect: "How data gets in",
    trial: "You upload CSV or Excel files by hand",
    mvp: "Your systems (complaints, QMS, PLM, ERP) are connected through an approved mapping file and refreshed on a schedule",
  },
  {
    aspect: "People",
    trial: "Up to 3 users",
    mvp: "Your team, each with a workflow role, plus a new role: the Customer Administrator",
  },
  {
    aspect: "Start",
    trial: "Immediately after sign-up",
    mvp: "After 2 to 3 weeks of setup, configuration and validation testing",
  },
  { aspect: "Length", trial: "30 days", mvp: "3 months to 1 year, agreed in your proposal" },
  {
    aspect: "Cost",
    trial: "Free",
    mvp: "Paid, priced for your scope and usage. Design partners receive a discount.",
  },
  {
    aspect: "Support",
    trial: "Questions by email, no response times",
    mvp: "A named MDARIX contact, with support terms agreed in your proposal",
  },
];

export type MvpStep = { label: string; title: string; text: string };

export const START_TITLE = "How the pilot starts";
export const START_LEDE =
  "Setup takes at least 2 to 3 weeks. The pilot itself starts only when the setup is validated and you have signed it off.";
export const MVP_STEPS: readonly MvpStep[] = [
  {
    label: "Step 1 · Week 0",
    title: "Agree the scope",
    text: "A call to agree your goals and which products, sites and systems are in scope. You receive a written proposal with the pilot length and price. Then the agreement and the data processing agreement are signed.",
  },
  {
    label: "Step 2 · Week 1",
    title: "Install and secure",
    text: "MDARIX sets up the dedicated database for your organization. Your Customer Administrator is set up with two-factor sign-in and configures users, roles and security settings.",
  },
  {
    label: "Step 3 · Week 2",
    title: "Connect and map your data",
    text: "Each source system gets a mapping file: which field in your system becomes which field in MDARIX. A test load is checked against your record counts, then the mapping is approved and released.",
  },
  {
    label: "Step 4 · Week 3",
    title: "Validate and sign off",
    text: "Validation testing against your intended use, your own acceptance testing and training for your team. You sign off the setup.",
  },
  {
    label: "Step 5 · Pilot starts",
    title: "Work on your real complaints",
    text: "Your team takes real complaints from signal to signed decision. We review progress with you regularly against success criteria agreed at the start.",
  },
];

export const CONNECTION_TITLE = "How your data is connected";
export const CONNECTION: readonly { title: string; text: string }[] = [
  { title: "Your systems", text: "Complaint handling, QMS, PLM, ERP. They stay your systems of record." },
  {
    title: "Mapping file",
    text: "Field by field, reviewed by you, versioned, and approved before use. Every change is recorded.",
  },
  { title: "MDARIX database", text: "Dedicated to your organization and run by MDARIX. Only your data." },
  { title: "Your MDARIX workspace", text: "The same screens you used in the trial, on your real records." },
];

export const CUSTOMER_ADMINISTRATOR = {
  title: "A new role: Customer Administrator",
  lede: "One person in your organization runs MDARIX for you:",
  duties: [
    "Invites users and gives them their roles",
    "Manages the connections to your systems and approves data mapping releases",
    "Sets security settings and exports the audit trail",
  ],
  note: "The Customer Administrator never signs decisions. If the same person also investigates, they use a second account for case work.",
} as const;

export const WHAT_WE_NEED = {
  title: "What we need from you",
  items: [
    "A sponsor who owns the pilot's goals",
    "A named Customer Administrator",
    "An IT contact for the installation and the connections",
    "The list of systems in scope, with a sample export from each",
    "At least two quality team members for the workflow",
    "Time for validation testing in week 3",
  ],
} as const;

export const PRICE = {
  title: "Price",
  text: "The pilot is a paid engagement, from 3 months to 1 year. Its price depends on what you expect from it and how you will use it: the products, sites, systems and people in scope. Design partners, who help shape MDARIX with regular feedback, receive a discount. You receive a written proposal with the price before anything is signed.",
} as const;

export const QUESTIONS_TITLE = "Common questions";
export const QUESTIONS: readonly { question: string; answer: string }[] = [
  {
    question: "Can we keep what we did in the trial?",
    answer:
      "If you uploaded your own data and removed the sample data, yes: ask us and we move your data into your pilot database. Otherwise the pilot starts clean, with your real data from your connected systems.",
  },
  {
    question: "Who owns the data?",
    answer:
      "You do. Your systems stay the systems of record, and your MDARIX database holds only your organization's data.",
  },
  {
    question: "Is MDARIX a validated system?",
    answer:
      "MDARIX is not a validated (GxP) system out of the box. The validation testing in week 3 checks the setup against your intended use. Your quality system and its validation stay yours.",
  },
  {
    question: "What happens after the pilot?",
    answer:
      "We review the results with you against the agreed success criteria. You then decide whether to continue on a subscription.",
  },
];

export const CALL_TO_ACTION = {
  title: "Ready to talk about a pilot?",
  text: "Tell us which products and systems you have in mind, and what you expect from the pilot. We reply to arrange a scoping call.",
  action: "Request a pilot conversation",
} as const;

/** The request form (TrialNextSteps.tsx MvpRequestForm) and what it says back. */
export const MVP_REQUEST = {
  title: "Request a pilot conversation",
  intro: CALL_TO_ACTION.text,
  expectations: "What do you expect from the pilot?",
  expectationsHint:
    "For example: find the complaints closed as inquiries across our two infusion pump lines, and show our CAPA effectiveness checks to the notified body.",
  scope: "Products, sites and systems you have in mind (optional)",
  scopeHint: "For example: OrbitCare 300 pumps, made in Pune; complaints in TrackWise, lots in SAP.",
  phone: "Phone (optional)",
  contact: "How and when to reach you (optional)",
  contactHint: "For example: a video call, Tuesday or Wednesday afternoon IST",
  move: "Move our trial data into the pilot",
  moveDetail:
    "The records your organization uploaded in the trial are moved into your pilot database. Without this, the pilot starts clean and your trial data is deleted 30 days after the trial ends.",
  account: "Your name and email come from your account. We reply to arrange a scoping call.",
  send: "Send the request",
  update: "Update the request",
  sent: "Thank you. The MDARIX team will reply to arrange a scoping call.",
  updated: "Your request is updated. The MDARIX team will reply to arrange a scoping call.",
} as const;

/** Why the data-move option is not offered, as the server says it (backend/app/trial/mvp_request.py data_move). */
export function dataMoveExplanation(reason: string | null | undefined): string {
  const rule =
    "Your trial data can be moved into the pilot only when you have removed the sample data and imported your own data.";
  if (reason === "SAMPLE_DATA_PRESENT")
    return `${rule} Your trial still holds the sample data, so nothing will be moved, and your trial data is deleted 30 days after the trial ends.`;
  if (reason === "NO_OWN_DATA")
    return `${rule} Your trial holds none of your own data yet, so nothing will be moved, and your trial data is deleted 30 days after the trial ends.`;
  return `${rule} Otherwise nothing is moved, and your trial data is deleted 30 days after the trial ends.`;
}

/** The trial user guide's "After your trial" chapter: the same words, in the order a reader needs them. */
export const AFTER_YOUR_TRIAL = {
  title: "After your trial",
  lede: NEXT_STEPS_INTRO.lede.replace("This page explains", "This chapter explains"),
  where: `In your workspace, ${NEXT_STEPS_SECTION} (${NEXT_STEPS_SUBTITLE}) shows the same, and its ${CALL_TO_ACTION.action} button sends your request to the MDARIX team.`,
} as const;
