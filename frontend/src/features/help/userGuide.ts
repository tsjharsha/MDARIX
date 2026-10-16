// The step-by-step user guide (/help/user-guide, UserGuidePage.tsx): how to use every screen of the MDARIX workspace,
// task by task, with the names of the buttons and fields exactly as they appear. The free trial user guide
// (trialGuide.ts) is the short journey through a trial; this one is the full manual. Keep the labels in step with the
// screens they describe (frontend/src/features/workspace/**, auth/AuthPage.tsx, help/HelpMenu.tsx) and describe the
// MVP screens (app/featureSet.ts), which every workspace uses.

export const USER_GUIDE_PATH = "/help/user-guide";

export type GuideTask = {
  title: string;
  /** What to do, in order, with the on-screen names. */
  steps: readonly string[];
  /** What you see when it worked. */
  result?: string;
  /** Who may do it, when the task needs a permission. */
  who?: string;
  note?: string;
};

export type GuideSection = {
  id: string;
  title: string;
  /** Where to find it: the sidebar item and tab. */
  where: string;
  /** What it is for, in a sentence or two. */
  purpose: string;
  tasks: readonly GuideTask[];
  tips?: readonly string[];
};

export type GuidePart = { id: string; title: string; summary: string; sections: readonly GuideSection[] };

export const ROLE_SUMMARY: readonly [string, string][] = [
  ["Viewer", "Reads everything their organization shares; changes nothing."],
  ["PMS / Signal Triage Lead", "Triages signals, opens and assigns investigations, changes the complaint settings."],
  ["Quality Investigator", "Works investigations: evidence, hypotheses, unknowns, scope and the Decision Brief."],
  ["Risk Reviewer", "Records risk reviews and reviews evidence."],
  ["Regulatory Reviewer", "Records regulatory reviews and reportability decisions, and sets the reporting windows."],
  ["Quality Reviewer", "Reviews Decision Briefs and signs CAPA effectiveness results."],
  ["Authorized Decision Maker", "Signs decisions and reportability, and signs CAPA effectiveness results."],
  ["Leader (Quality Manager)", "Everything above. Every free trial user is a Leader."],
  ["Customer Administrator", "Manages people and settings for the organization; never reviews or signs."],
];

export const GUIDE_PARTS: readonly GuidePart[] = [
  {
    id: "basics",
    title: "The basics",
    summary: "Signing in, finding your way around and getting help.",
    sections: [
      {
        id: "sign-in",
        title: "Sign in and keep your account safe",
        where: "The sign-in page (/signin)",
        purpose:
          "Every person signs in with their own work email, a password only they know, and a code from an authenticator app.",
        tasks: [
          {
            title: "Activate your account (first time)",
            steps: [
              "Open the invitation email and choose the activation link. It works once and is valid for 48 hours.",
              "On Activate your MDARIX account, choose a New password: 12 to 128 characters. A phrase of several words works well; do not include your email name.",
              "Choose Activate account. You are signed in and asked to set up your authenticator app.",
            ],
            result: "MDARIX never sees or sends your password: only you know it.",
          },
          {
            title: "Set up your authenticator app",
            steps: [
              "On Set up your authenticator app, scan the QR code with an authenticator app on your phone (Microsoft Authenticator, Google Authenticator, 1Password and others). No camera? Type the key shown into the app instead.",
              "Enter the 6-digit code the app shows in Six digit authentication code and choose Verify and turn on MFA.",
              "Save your recovery codes: each one signs you in once if your phone is lost. They are shown only now; print them or keep them in a password manager.",
              "Choose I have saved these codes, continue.",
            ],
            note: "The same authenticator code confirms your identity when you sign a decision or a CAPA effectiveness result.",
          },
          {
            title: "Sign in",
            steps: [
              "Enter your Work email and Password and choose Sign in.",
              "On Verify your identity, enter the 6-digit code from your authenticator app and choose Verify.",
              "Without your phone, choose Use a recovery code and enter one of your recovery codes (each works once).",
              "If your email has accounts in more than one organization, choose the organization to open.",
            ],
            result: "You land on your workspace. Five wrong passwords or codes lock sign-in for 15 minutes.",
          },
          {
            title: "Reset a forgotten password",
            steps: [
              "On the sign-in page choose Forgot password?.",
              "Enter your Work email and choose Send reset link.",
              "Open the email within one hour, choose a New password and choose Set new password.",
            ],
            result: "Your password is changed and every other session is signed out.",
          },
          {
            title: "Sign out, and how sessions end",
            steps: [
              "Choose Logout at the top right to sign out.",
              "MDARIX signs you out after 30 minutes without activity. Two minutes before, it asks: choose Stay signed in to continue.",
              "No session lasts longer than 12 hours, even when you are active. Sign in again to continue where you left off.",
            ],
          },
        ],
        tips: [
          "Lost your phone and your recovery codes? Ask your administrator to reset your multi-factor authentication.",
        ],
      },
      {
        id: "find-your-way",
        title: "Find your way around",
        where: "Every workspace screen",
        purpose:
          "The sidebar on the left opens each part of MDARIX; the bar at the top of some screens chooses the product, version and investigation you are looking at.",
        tasks: [
          {
            title: "Use the sidebar",
            steps: [
              "Getting started (free trials only): your trial as a story, chapter by chapter.",
              "Readiness: what an inspector would find in your records today.",
              "My Work: your tasks, approvals and evidence requests.",
              "Complaints: the second look, the backlog, reportability and the reporting windows.",
              "Signals: the signal inbox, the trend check and the detection rules.",
              "Investigations: open and work your cases, from evidence to the signed decision.",
              "Records: CAPA effectiveness checks, risk file input, the audit trail, reports and signature verification.",
              "Import data: bring in your CSV or Excel exports.",
              "My Account: your profile, security and access. Share feedback: tell the MDARIX team what to improve.",
            ],
            note: "You see only the sections your role includes, and only your organization's data.",
          },
          {
            title: "Use the context bar",
            steps: [
              "On My Work, Signals and Investigations, choose the Product, its Version and the Investigation in the bar at the top.",
              "As of picks the date to look from. Choose Current for the latest recorded state, As it happened for the state on the event date, or As known then for only what was known on that date.",
            ],
            result: "Every tab below the bar follows your choice.",
          },
          {
            title: "Read the header",
            steps: [
              "Your organization's name shows which organization's data you see.",
              "During a free trial, Free trial · N days left opens Getting started.",
              "Help opens the guides, Contact support, Report a problem and Security and privacy.",
            ],
          },
        ],
      },
      {
        id: "help",
        title: "Get help and report a problem",
        where: "Help, at the top right of every screen",
        purpose: "The guides, the support address and a way to tell the MDARIX team something went wrong.",
        tasks: [
          {
            title: "Open a guide",
            steps: [
              "Choose Help.",
              "Step-by-step user guide: this guide, every screen task by task.",
              "Free trial user guide (free trials): the seven steps of a trial, from the request to the demo.",
              "Pilot guide: roles, the minimum team and the investigation workflow for a design-partner pilot.",
            ],
          },
          {
            title: "Report a problem",
            steps: [
              "Choose Help, then Report a problem.",
              "Fill in What went wrong, in a few words and Details: what you did, what happened, what you expected. Do not include patient or personal data.",
              "Choose Send report. The page you are on is sent with it.",
            ],
            result: "Thank you. Your report has reached the MDARIX team, with its reference. We reply by email.",
          },
        ],
      },
    ],
  },
  {
    id: "home",
    title: "Your home screens",
    summary: "Where to start each day: your trial story, inspection readiness and your own work.",
    sections: [
      {
        id: "getting-started",
        title: "Getting started (free trial)",
        where: "Getting started · Your free trial, as a story",
        purpose:
          "The quality loop MDARIX closes, chapter by chapter: what your records show in each, why inspectors care, and where to try it. Start on the sample data, then on your own export.",
        tasks: [
          {
            title: "Follow the story",
            steps: [
              "The ring at the top shows how much of the loop you have tried. Its main button opens the next chapter.",
              "Under Your story, chapter by chapter, each of the nine chapters shows what your records show now.",
              "Open What MDARIX does here, and why it matters to read the chapter in two sentences.",
              "Choose the chapter's button (for example Review hidden complaints) to try it. A chapter counts as tried when you act in it: decide, record, run or sign.",
            ],
            result:
              "A green banner says Chapter N done, with Continue to the next one. Tried chapters show Done and an Open again button.",
          },
          {
            title: "Start where it hurts",
            steps: [
              "Under Start where it hurts, tick what FDA, a notified body or your own audit found.",
              "Choose Start the story there.",
            ],
            result: "Those chapters are marked You were cited for this and come first.",
          },
          {
            title: "Follow your trial journey",
            steps: [
              "Your trial journey shows the seven steps of the trial and the next one to do.",
              "Use its buttons: Invite colleagues, Continue the story, Upload your data, Share feedback and Book the demo.",
            ],
          },
          {
            title: "Invite colleagues",
            who: "The person who started the trial.",
            steps: [
              "Open the Team tab.",
              "Fill in Colleague's name and Work email and choose Invite colleague.",
              "For someone who has not activated yet, choose Resend invitation.",
            ],
            result: "Invitation emailed. The link is valid for 48 hours. A trial includes up to 3 users.",
          },
          {
            title: "See your trial's dates and limits",
            steps: [
              "Open the Your trial tab: Trial ends (and when the data is deleted), Users, and Uploaded rows.",
              "Open About the sample data to read what the fictional sample company holds and why.",
            ],
          },
        ],
      },
      {
        id: "readiness",
        title: "Readiness",
        where: "Readiness · What an inspector would find",
        purpose:
          "What an FDA investigator or a notified-body auditor would find in your complaints, reports, trends and CAPAs today, read from your own records. Rules only, no AI.",
        tasks: [
          {
            title: "Read the inspection checks",
            steps: [
              "The ring shows how many inspection checks are clear.",
              "Each check shows its state (Clear, Needs attention, Critical or Not set up), the records behind it and Why it matters.",
              "Choose Open on a check to go to the screen where you act on it.",
            ],
            note: "The eight checks: Complaints to recheck, Complaints past target, Reporting clocks, Trends without CAPA or risk review, Post-market data not in the risk file, Harm complaints closed without an investigation, CAPAs without a verified effect, Signals waiting past their triage date.",
          },
          {
            title: "Download the summary for management review or an inspector",
            who: "Every role except Viewer.",
            steps: [
              "Under Summary for management review, choose the period: Last 90 days, Last 6 months or Last 12 months.",
              "Choose Download PDF for the readiness summary, or Inspection pack (ZIP) for the summary, every check and every record behind it as CSV, with SHA-256 fingerprints.",
            ],
            result: "Downloaded, with the file's name.",
          },
        ],
      },
      {
        id: "my-work",
        title: "My Work",
        where: "My Work · Your tasks, approvals and requests",
        purpose:
          "Everything waiting for you: tasks assigned to you, work your roles can pick up, decisions awaiting your signature and evidence requests.",
        tasks: [
          {
            title: "Work a task",
            steps: [
              "Choose a tab: Assigned to me, Role queues, Waiting, Returned to me, Due soon, Overdue or Completed.",
              "Choose Open to go to the task's case or screen, or Details to see its history.",
              "Use the actions offered: Accept or Claim act at once; Decline, Release and Reassign need a reason of at least 10 characters; Complete takes an optional note.",
            ],
            result: "Recorded in the task's history and the audit trail.",
          },
          {
            title: "Sign the decisions waiting for you",
            who: "Authorized Decision Maker and Leader.",
            steps: [
              "Open the Approvals tab.",
              "Under Briefs awaiting your decision, choose Open to go to the case's Decision step.",
            ],
            note: "You never sign a brief you prepared or reviewed, and administrators never sign.",
          },
          {
            title: "Answer or send evidence requests",
            steps: [
              "Open the Evidence requests tab and choose Received or Sent.",
              "On a request, choose Acknowledge, Respond (your answer and optional files), or Cannot provide with a reason.",
              "On a request you sent, choose Review into evidence to accept the response as evidence or reject it with a reason.",
            ],
            note: "A response is never evidence by itself: the person who asked reviews it into the case's evidence.",
          },
        ],
      },
    ],
  },
  {
    id: "complaints-signals",
    title: "Complaints and signals",
    summary: "Find the complaints that hide, keep every reporting clock, and turn a rising trend into a case.",
    sections: [
      {
        id: "second-look",
        title: "Second look: complaints hidden as inquiries",
        where: "Complaints › Second look",
        purpose:
          "Find complaints hidden as cancellations, inquiries or No Fault Found. A person decides; MDARIX never changes your records.",
        tasks: [
          {
            title: "Decide whether a record is a complaint",
            who: "PMS / Signal Triage Lead, Quality Investigator, Quality Reviewer, Leader.",
            steps: [
              "Read the records to review, most serious first. Each card shows why it was flagged and the signs of a complaint (for example Death reported or Malfunction).",
              "Choose It is a complaint or Not a complaint.",
              "Write the Reason in your own words, at least 10 characters. You can begin with a Start with: sentence and finish it yourself.",
              "Choose It is a complaint or Not a complaint to save.",
            ],
            result:
              "Confirmed as a complaint (it joins the backlog) or Dismissed (it leaves the second look, its reason kept in the audit trail). To revise, choose Change decision.",
          },
        ],
        tips: ["A confirmed complaint card has an Open investigation link."],
      },
      {
        id: "backlog",
        title: "Backlog",
        where: "Complaints › Backlog",
        purpose: "See which open complaints wait in no signal and no case past your target.",
        tasks: [
          {
            title: "Work the oldest complaints first",
            steps: [
              "Filter All open, Past target or Due soon, and pick a product.",
              "Read Open complaints, oldest first: each shows its age and whether it is Past target, Due soon or On track.",
              "Choose Open investigation on a complaint that needs one.",
            ],
          },
          {
            title: "Change the target and the complaint words",
            who: "PMS / Signal Triage Lead and Leader.",
            steps: [
              "Open Complaints › Review settings.",
              "Set the Backlog target (days from receipt) and the Words that suggest a complaint (one per line).",
              "Give a Reason for the change and choose Save settings.",
            ],
          },
        ],
      },
      {
        id: "reportability",
        title: "Reportability: every report inside its window",
        where: "Complaints › Reportability and Complaints › Reporting windows",
        purpose:
          "MDARIX keeps the reporting clock of every complaint from your procedure's windows; it never decides reportability or submits a report.",
        tasks: [
          {
            title: "Enter your reporting windows (once)",
            who: "Regulatory Reviewer, Authorized Decision Maker, Leader.",
            steps: [
              "Open Complaints › Reporting windows and choose Add a window.",
              "Start from a template (FDA MDR, EU MDR, MHRA or Health Canada) or A blank window.",
              "Check each window's Name, Days, Counted in (Calendar days or Work days), what starts the clock (Death, Serious injury, Malfunction) and its Markets.",
              "Give a Reason for the change (for example your procedure's revision) and choose Save reporting windows.",
            ],
          },
          {
            title: "Record a reportability decision",
            who: "Regulatory Reviewer, Authorized Decision Maker, Leader.",
            steps: [
              "On Complaints › Reportability, filter Needs a decision, Overdue, Due soon or Missing answers.",
              "Each card shows its clock (for example Due in 5 days), the awareness date and any Missing answers to follow up.",
              "Choose Record decision. Under Decision choose Reported to the authority (with the Report reference and the Filed on date) or Not reportable.",
              "Write the Rationale, at least 10 characters, and choose Record decision.",
            ],
            result: "The card shows Reported or Not reportable, and Inside the window or After the window.",
            note: "MDARIX does not submit reports: record what was filed in the authority's system.",
          },
        ],
      },
      {
        id: "signals",
        title: "Signals: triage a pattern of complaints",
        where: "Signals › Signal inbox",
        purpose:
          "Review new signals, decide what each needs and follow complaint trends. Signals are recorded observations, not conclusions about cause.",
        tasks: [
          {
            title: "Find the signals that need you",
            steps: [
              "Filter by status (Open, All and each status), priority, product, origin and owner, and sort by Priority, Due date, Latest complaint, Complaints or Created.",
              "Choose a signal to open it: its complaints, what they have in common (straight from the records, each point linked to its complaints) and its trend check.",
            ],
          },
          {
            title: "Open a case in one click",
            who: "PMS / Signal Triage Lead, Quality Investigator, Leader.",
            steps: ["On the signal, choose Open case."],
            result:
              "The signal is marked as needing an investigation and a case opens with every complaint. To choose the question, the complaints or the investigator first, choose Open case with options….",
          },
          {
            title: "Triage a signal",
            who: "PMS / Signal Triage Lead and Leader.",
            steps: [
              "Start triage begins the triage.",
              "Set priority: confirm MDARIX's suggestion, or choose Critical, High, Medium or Low and say why.",
              "Record disposition: Investigation required, Escalate, Monitor (with a date to review again), No action needed, or Duplicate of another signal, with a Reason.",
              "Merge signals or Add complaints, each with a Reason of at least 10 characters.",
            ],
            result: "Every change is recorded in the signal's history and the audit trail.",
          },
          {
            title: "Create a signal yourself",
            who: "PMS / Signal Triage Lead and Leader.",
            steps: [
              "Choose New signal.",
              "Give a Title, choose the Product (and optionally the Version), and tick at least one complaint.",
              "Optionally set a Priority and say why, then choose Create signal.",
            ],
          },
        ],
      },
      {
        id: "trend-check",
        title: "Trend check and detection rules",
        where: "Signals › Trend check and Signals › Detection rules",
        purpose:
          "The trend check compares each version's last 30 days with its own history, counted per unit in the field where lot quantities exist. It is a check, never a verdict.",
        tasks: [
          {
            title: "Read the trend check",
            steps: [
              "Group By version, By problem code or By complaint type.",
              "Each row's Result is Significant rise (chance under 1% if nothing changed), Higher than usual (under 5%), In line with history, Too few to assess or History too short.",
              "On a rising row with no open signal, choose Raise a signal (PMS / Signal Triage Lead and Leader).",
            ],
          },
          {
            title: "Change a detection rule",
            who: "PMS / Signal Triage Lead and Leader.",
            steps: [
              "Open Signals › Detection rules. A rule opens a signal when enough complaints about the same problem arrive within a number of days.",
              "In Change the rule, set Minimum complaints and Within (days), give a Reason for the change and choose Save rule.",
              "Choose Run detection now to apply it at once.",
            ],
          },
        ],
        tips: ["Add lot quantities through Import data to count complaints per unit in the field from day one."],
      },
    ],
  },
  {
    id: "investigations",
    title: "Investigations",
    summary: "Work a case from its question to a signed decision and its CAPA.",
    sections: [
      {
        id: "cases",
        title: "Open and manage a case",
        where: "Investigations › All investigations and Workspace",
        purpose:
          "Open a case and work through it step by step. MDARIX organizes evidence and possible explanations; it never concludes a root cause for you.",
        tasks: [
          {
            title: "Open an investigation",
            steps: [
              "Choose the product in the context bar, then choose Open an investigation.",
              "Write The question this investigation must answer (at least 10 characters), for example: Why did occlusion alarms rise after release B?",
              "Tick the Complaints that prompted it (optional) and choose Open investigation.",
            ],
            result: "The investigation opens, assigned to you, on its Workspace.",
          },
          {
            title: "Follow the case progress",
            steps: [
              "On Workspace, Where this case stands shows the steps: Overview, Scope, Evidence, Analysis, Hypotheses, Gaps and open questions, Risk and regulatory review, Investigation brief, Human review and decision.",
              "Choose a step to go to it. The Readiness checklist (Show each check) lists what is in place and what is missing.",
            ],
          },
          {
            title: "Change the case's state, owner, priority or due date",
            steps: [
              "Start work, Put on hold, Resume or Cancel case: each asks why, at least 10 characters.",
              "Priority and due date (or Manage on the list): give a Reason for the change, then change the question, Assign to a colleague, or set the Priority and Due date.",
              "When the case is done, Manage shows the criteria Before closing and Close investigation.",
            ],
          },
        ],
      },
      {
        id: "evidence",
        title: "Evidence",
        where: "Investigations › Evidence",
        purpose:
          "The case's evidence, each with two separate judgements: its review status (can it be relied on?) and its relationship to the question (does it support, contradict or give context?).",
        tasks: [
          {
            title: "Link evidence to the case",
            steps: [
              "Choose Link evidence, search the evidence library and tick the records.",
              "Optionally set the Relationship and say why they belong, then choose Link record.",
            ],
            note: "Linked records start unreviewed: linking is not accepting.",
          },
          {
            title: "Review a piece of evidence",
            steps: [
              "On a row, choose Review.",
              "Choose the Review status (Accepted, Accepted with limitation, Rejected, Quarantined or Superseded) and the Relationship (Supporting, Contradicting, Contextual, Unresolved or Unrelated).",
              "Give a reason where asked and choose Record review.",
            ],
            result:
              "Every review is kept in the evidence's history and the audit trail. Provenance shows where a record came from.",
          },
          {
            title: "Request evidence from a colleague or a supplier",
            steps: [
              "Choose Request evidence and choose A colleague or role, or A supplier.",
              "Fill in What you need and Documents or data requested (one per line); optionally why, the unknown it resolves, a due date and the priority.",
              "Choose Send request. The answer comes back to you in My Work › Evidence requests.",
            ],
          },
        ],
      },
      {
        id: "intelligence",
        title: "Hypotheses, unknowns and failure chains",
        where: "Investigations › Intelligence",
        purpose:
          "Every statement shows what kind it is and who made it; a person's judgement is recorded with its reason. Everything here works by hand.",
        tasks: [
          {
            title: "Add and judge a hypothesis",
            steps: [
              "On Hypotheses choose Add hypothesis, write The possible explanation and choose Add hypothesis.",
              "Choose Judge, pick Your judgement (from Hypothesized to Strongly supported, Contradicted or Retired), give the Reason and choose Record judgement.",
              "Choose Link evidence to tie evidence to it as Supporting, Contradicting, Contextual or Unresolved, with a rationale.",
            ],
          },
          {
            title: "Record what is still unknown",
            steps: [
              "On Unknowns choose Add unknown and write What is not known yet; optionally its category, the evidence that would resolve it and the hypothesis it bears on.",
              "Move it on as work goes: Start work on it, Mark resolved or Accept as a limitation, each with a reason.",
              "Choose Request evidence on an open unknown to ask for what would resolve it.",
            ],
          },
          {
            title: "Build a failure chain",
            steps: [
              "On Failure chain choose Build a chain by hand.",
              "Name it, add at least two steps in order, and link the steps with their State (Supported, Partially supported, Hypothesized or Unknown) and evidence.",
              "Choose Record chain. It is a working explanation, not a concluded root cause.",
            ],
          },
          {
            title: "Record an observation",
            steps: [
              "On Observations choose Record observation, choose the evidence it is about and its kind (Fact, Source assertion or Derived observation), write it and choose Record observation.",
            ],
          },
        ],
      },
      {
        id: "ask",
        title: "Ask MDARIX",
        where: "Investigations › Ask MDARIX",
        purpose:
          "Ask a question about the active case and get an answer built from the case's records, each point linked to its source. A person reviews every answer.",
        tasks: [
          {
            title: "Ask a question about the case",
            steps: [
              "Choose the case in the context bar.",
              "Write your Question, for example: What changed in Rev B, and what evidence is still missing?",
              "Choose Ask MDARIX.",
            ],
            result:
              "The MDARIX answer: a Summary, Known facts, Supporting and Contradicting evidence, Unknowns, Missing evidence, Suggested next steps and the Sources it used.",
            note: "While AI is off for your organization (as in every free trial), the answer comes from your records only and says so. When AI is switched on, AI interpretations are labelled and still cite their sources.",
          },
        ],
      },
      {
        id: "scope-reviews",
        title: "Scope and reviews",
        where: "Investigations › Scope and Investigations › Reviews",
        purpose:
          "The scope says exactly what the case covers; risk and regulatory reviewers judge it with their own rationale.",
        tasks: [
          {
            title: "Set the scope",
            steps: [
              "Choose Set the scope (or Change the scope).",
              "Check the question, tick the Product versions, put each complaint In scope or Kept out (with a reason), and tick the Lots, Markets and Failure modes.",
              "Choose Save scope. Every version is kept; a change needs Why the scope changes.",
            ],
          },
          {
            title: "Request a risk or regulatory review",
            steps: [
              "On Reviews, see Which reviews this case needs (Required or Not required by your policy).",
              "Choose Request risk review or Request regulatory review, optionally say what to look at, and confirm.",
            ],
          },
          {
            title: "Record a review",
            who: "Risk Reviewer or Regulatory Reviewer, and Leader.",
            steps: [
              "Open the review and choose Start review.",
              "Choose Record outcome, pick the Outcome your review supports and write the Rationale (at least 20 characters).",
              "Choose Record outcome.",
            ],
            note: "MDARIX does not suggest an outcome.",
          },
        ],
      },
      {
        id: "brief",
        title: "The Decision Brief",
        where: "Investigations › Decision Brief",
        purpose:
          "The brief gathers what the records establish, what is still unknown and what reviewers found. It informs the decision maker; it never makes the decision.",
        tasks: [
          {
            title: "Write and submit the brief (investigator)",
            who: "Quality Investigator and Leader.",
            steps: [
              "Choose Compose the brief: it is composed from the case's records.",
              "In Narrative, write the Problem statement, the Proposed conclusion (your own words), the Recommended actions (one per line) and optional Notes for the reviewer. Choose Save narrative.",
              "Check the Readiness scorecard, then choose Submit for quality review.",
            ],
            result: "The version is fixed once submitted; changes after a return make a new version.",
          },
          {
            title: "Review the brief (quality reviewer)",
            who: "Quality Reviewer and Leader, never the brief's author.",
            steps: [
              "Read the brief, then under Review of this brief choose Start review.",
              "In Your review choose Accept for decision, a Return for more evidence, analysis, a risk or a regulatory review, Reject the proposed conclusion, or Escalate. Every choice except Accept needs a Comment of at least 10 characters.",
              "Choose Record review.",
            ],
            result: "Accepted, the brief is Approved for decision and the case is ready for a decision.",
          },
        ],
        tips: ["The person who writes or submits a brief never reviews or signs it."],
      },
      {
        id: "decision",
        title: "Decide and sign",
        where: "Investigations › Decision",
        purpose:
          "The decision is yours: the outcome, the conditions and the rationale are written by you, and signed with your password and authenticator code.",
        tasks: [
          {
            title: "Decide",
            who: "Authorized Decision Maker and Leader, never the brief's author or an administrator.",
            steps: [
              "Read What you decide on: the accepted brief, its facts, reviews and fingerprint.",
              "Under Outcome choose Accept the conclusion, Accept with conditions (write the conditions), Reject the conclusion, or Close with no further action.",
              "Under Follow-up actions required, tick what the decision needs: CAPA required, Product change required, Field action review required, Risk reassessment required or Regulatory action required.",
              "Write Your rationale (in your own words), at least 20 characters, and read What your signature means.",
            ],
          },
          {
            title: "Sign",
            steps: [
              "Choose Continue to sign.",
              "In Sign the decision, enter Your password and the Authenticator code, and choose Sign decision.",
            ],
            result:
              "The signed record opens: who signed, when, the meaning of the signature and a fingerprint of the brief version reviewed, so any later change is detected.",
          },
          {
            title: "Open the CAPA and carry out the follow-ups",
            steps: [
              "Under After the decision, Follow-ups lists each follow-up. Choose Act.",
              "For CAPA required, choose Create CAPA, give the CAPA title (and optionally a due date) and choose Create CAPA.",
              "For the others, choose Start and later Complete with what was done.",
            ],
            result: "The CAPA is raised and linked to the signed decision; it is listed on the CAPAs tab.",
          },
          {
            title: "Not ready to decide",
            steps: [
              "Choose Return to the investigator and write what is missing. This is not a decision and needs no signature.",
            ],
          },
        ],
      },
      {
        id: "record",
        title: "The case record",
        where: "Investigations › Record and Investigations › CAPAs",
        purpose:
          "Everything a case holds, from its question and evidence to its reviews, decision and audit trail, in one record you can hand an inspector.",
        tasks: [
          {
            title: "Download the case record",
            who: "Every role except Viewer.",
            steps: ["On Record, under Download case record, choose PDF, CSV or JSON."],
          },
          {
            title: "See the case's CAPAs",
            steps: ["Open CAPAs: each CAPA with its type, the case it came from, its status and due date."],
          },
        ],
      },
    ],
  },
  {
    id: "records",
    title: "Records",
    summary: "What you hand an inspector or a management review.",
    sections: [
      {
        id: "effectiveness",
        title: "CAPA effectiveness checks",
        where: "Records › Effectiveness checks",
        purpose:
          "Prove each CAPA worked: plan its check with criteria and a date, then sign the result with the complaint recurrence seen.",
        tasks: [
          {
            title: "Plan a check",
            who: "Quality Investigator, Quality Reviewer, Leader.",
            steps: [
              "Filter Needs attention to see checks that are overdue, due soon or not planned.",
              "Choose Open check, then Plan the check.",
              "Write What will show the action worked, set Measure from and Check on, and choose Save the plan.",
            ],
            result: "The quality reviewers get a reminder 14 days before the check day.",
          },
          {
            title: "Sign the result",
            who: "Quality Reviewer, Authorized Decision Maker, Leader.",
            steps: [
              "On the check, read the criteria and the complaint recurrence Before and Since.",
              "Choose Effective: the criteria are met, or Not effective: plan a further action.",
              "Write What you found, enter Your password and the Authenticator code, and choose Sign the result.",
            ],
          },
        ],
      },
      {
        id: "risk-file",
        title: "Risk file input",
        where: "Records › Risk file input",
        purpose:
          "Whether post-market data reached the risk file (ISO 14971 clause 10), product by product. A person decides what the risk file must say.",
        tasks: [
          {
            title: "See what the risk file still needs",
            steps: [
              "Choose the Period: Last 6 months, Last 12 months or Last 2 years.",
              "Each product shows its state, for example Not reviewed against the risk file or Reviewed.",
              "Choose Risks and reviews to see the risks, the risk reviews and the reassessments open.",
            ],
            note: "Input reaches the risk file through a case's risk review and the Risk reassessment required follow-up of a signed decision.",
          },
        ],
      },
      {
        id: "audit",
        title: "Audit trail, reports and signatures",
        where: "Records › Audit trail, Reports and Verify a signature",
        purpose: "Every recorded step of a case, who made it and when, and proof that nothing changed since.",
        tasks: [
          {
            title: "Read a case's timeline",
            steps: [
              "Choose the investigation in the context bar and open Case timeline.",
              "Filter by category, person and dates. Each event says who made it: a person, AI or MDARIX itself.",
              "Choose JSON or CSV under Export to download it.",
            ],
          },
          {
            title: "Check that nothing changed",
            steps: [
              "Open Integrity: MDARIX checks each signature, the case's audit chain and each brief's fingerprint.",
              "Verified means every event was checked and none changed.",
            ],
          },
          {
            title: "Replay a case and verify a signature",
            steps: [
              "Open Replay to see the case as known when the decision was signed, or at a moment you choose.",
              "Open Verify a signature, choose the Investigation and Decision, and choose Check signatures.",
            ],
          },
        ],
      },
    ],
  },
  {
    id: "data-account",
    title: "Your data and your account",
    summary: "Bring in your own exports, look after your account and your team.",
    sections: [
      {
        id: "import",
        title: "Import your data",
        where: "Import data · Bring in CSV files (in a trial also Getting started › Your data)",
        purpose:
          "Bring in exports from your quality, product and supplier systems as they are. Every file is checked for problems and personal data before anything is saved.",
        tasks: [
          {
            title: "Import a file",
            steps: [
              "Choose the data type, for example Complaints. The page lists the Required and Optional columns.",
              "Choose Download complaints.csv for the template, or use your own export.",
              "Set Dates in the file, what to do with Rows with problems, and Personal details in the text (refuse them, or replace them with [PERSON], [PHONE] and similar).",
              "Choose a file (Excel or CSV) and choose Check file. Nothing is saved yet.",
              "Read how your columns were read and the preview. Fix any problems, or download the rows to fix.",
              "Choose Import N rows.",
            ],
            result:
              "Imported, with how many records are new and updated. Importing the file again updates the same records.",
            note: "Free trial: 5,000 uploaded rows in all (the sample data does not count) and 2 MB a file. Do not upload patient-identifiable data.",
          },
          {
            title: "Remove the sample data (free trial)",
            who: "The person who started the trial.",
            steps: [
              "Once your own complaints are in, open Getting started › About the sample data.",
              "Read what is Removed and what is Kept, and tick I understand the sample data cannot be brought back.",
              "Choose Remove the sample data.",
            ],
            result: "Every screen now shows your own data. Chapters you already tried stay counted.",
          },
        ],
      },
      {
        id: "account",
        title: "My Account",
        where: "My Account · Profile, security, access",
        purpose: "Your profile, how your sign-in is protected, and what your role lets you do.",
        tasks: [
          {
            title: "Change your password",
            steps: [
              "Open Security.",
              "Enter your Current password, a New password and Confirm new password, and choose Change password.",
            ],
            result: "Your other sessions are signed out.",
          },
          {
            title: "See your access and settings",
            steps: [
              "Profile shows your name, email, role and organization, which your administrator manages. Tick Send me the weekly readiness email to receive it.",
              "Access shows the sections you can open and what your role allows you to do.",
            ],
          },
        ],
      },
      {
        id: "team",
        title: "Your team and its administration",
        where: "Getting started › Team (free trial), or the Admin console (customer administrators)",
        purpose: "Who works in your organization's MDARIX, and with which role.",
        tasks: [
          {
            title: "Invite colleagues to a free trial",
            who: "The person who started the trial.",
            steps: [
              "Open Getting started › Team, fill in Colleague's name and Work email and choose Invite colleague.",
            ],
            note: "A trial includes up to 3 users, each a Leader (Quality Manager).",
          },
          {
            title: "Manage people (customer administrators)",
            who: "Customer Administrator.",
            steps: [
              "In the Admin console open Users › Invite: fill in the name, Work email, Company and Base role, and choose Send invitation.",
              "Open a person to Send password reset, Reset MFA, Suspend, Restore access or Offboard them, or to change their workflow roles.",
            ],
            note: "Administrators never see or type a person's password, and never review or sign.",
          },
          {
            title: "Switch AI on or off (customer administrators)",
            who: "Customer Administrator.",
            steps: [
              "In the Admin console open Security › AI processing.",
              "Choose Turn AI on or Turn AI off, give a Reason for the change and, to switch on, acknowledge where the records go.",
            ],
            note: "AI is off for a new organization, and stays off in free trials during the product validation phase.",
          },
        ],
      },
    ],
  },
  {
    id: "trial",
    title: "Feedback, demo and the end of a trial",
    summary: "Tell us what you think, see MDARIX on your own records, and what happens after 30 days.",
    sections: [
      {
        id: "feedback",
        title: "Share feedback",
        where: "Share feedback · Tell us what to improve",
        purpose: "About three minutes. Only the overall rating and whether we may share your feedback are required.",
        tasks: [
          {
            title: "Send feedback",
            steps: [
              "Rate your experience (Overall experience is required) and how likely you are to recommend MDARIX.",
              "Tick what you tried and say what you liked and what to improve.",
              "Answer May we share your feedback? and choose Send feedback.",
            ],
            result: "Nothing is published until the MDARIX team reviews it, and only as you allowed.",
          },
        ],
      },
      {
        id: "demo",
        title: "Book a one-to-one demo (free trial)",
        where: "Getting started › See it on your own records, one to one",
        purpose: "A session with the MDARIX team on your own trial and records.",
        tasks: [
          {
            title: "Request the demo",
            steps: [
              "Choose Book a one-to-one demo.",
              "Give Times that suit you, tick What should we focus on? and add anything else.",
              "Choose Request the demo.",
            ],
            result: "The MDARIX team contacts you to agree a time. Nothing is booked until then.",
          },
        ],
      },
      {
        id: "trial-end",
        title: "When the trial ends",
        where: "Getting started › Your trial",
        purpose: "A trial lasts 30 days. Reminders arrive 7 days and 1 day before it ends, and on the day.",
        tasks: [
          {
            title: "What happens at day 30",
            steps: [
              "Access stops, and the screen says Your free trial has ended with Contact us to continue.",
              "Your workspace and data are kept for 30 more days, then deleted unless you continue.",
            ],
          },
          {
            title: "End your trial early",
            who: "The person who started the trial.",
            steps: [
              "On Your trial choose End my trial early.",
              "Optionally say why, keep or untick Delete our data when the trial ends, and confirm you understand.",
              "Choose Send the request. Until the MDARIX team confirms, you can Withdraw my request.",
            ],
          },
        ],
      },
    ],
  },
];

/** Every section, in reading order (for the contents and the tests). */
export const GUIDE_SECTIONS: readonly GuideSection[] = GUIDE_PARTS.flatMap((part) => part.sections);
