/**
 * "Why am I asked?" (quality plan stage 8, 8.2): one line for every question and step a person meets on the way from a
 * complaint to its decision, with the regulation it answers to (the catalog in shared/standards.ts). A market's
 * reportability questions carry their own locked clause and MDARIX note from the decision guide (stage 3); these are
 * the rest. The reasons are starter text, like the guides: the clause is the basis, the procedure is the customer's.
 */
export type Why = { why: string; basis: readonly string[] };

const COMPLAINT = ["ISO13485_8_2_2"];
const REPORTING = ["ISO13485_8_2_3", "CFR803_50", "MDR_87", "IN_MDR"];
const INVESTIGATION = ["ISO13485_8_5_2"];

/** Each step of one complaint (the checklist codes of backend/app/oversight/closure.py, and READY). */
export const COMPLAINT_STEP_WHY: Readonly<Record<string, Why>> = {
  TRIAGE: {
    why: "Every complaint is looked at promptly: how serious it is, who owns it and what is done now.",
    basis: COMPLAINT,
  },
  FIRST_CONTACT: {
    why: "A call or message is checked once against the complaint definition, so no complaint is missed.",
    basis: ["ISO13485_8_2_1", "ISO13485_8_2_2"],
  },
  MARKETS: {
    why: "Each market where the device is sold decides by its own rules whether this is reportable, and by when.",
    basis: REPORTING,
  },
  OBLIGATIONS: {
    why: "A reportable event is reported to the authority before its legal deadline; MDARIX never submits it.",
    basis: REPORTING,
  },
  DECISION: {
    why: "Every complaint is investigated, or the reason it needs no investigation is recorded and signed.",
    basis: COMPLAINT,
  },
  REQUESTS: {
    why: "Questions still open with the reporter or a partner are answered or closed first.",
    basis: COMPLAINT,
  },
  TASKS: { why: "Work still open on the complaint is finished before it is called ready.", basis: COMPLAINT },
  CAPA: { why: "Your QMS keeps the corrective action until it is closed there.", basis: ["ISO13485_8_5_2"] },
  READY: {
    why: "The event owner confirms the complaint record is complete before your QMS closes it.",
    basis: [...COMPLAINT, "CFR820_35"],
  },
};

/** Each step of an investigation (backend/app/case_workflow/readiness.py STEPS). */
export const CASE_STEP_WHY: Readonly<Record<string, Why>> = {
  overview: { why: "The question is what the investigation must answer.", basis: INVESTIGATION },
  scope: {
    why: "What the investigation covers decides which complaints, lots and evidence count.",
    basis: INVESTIGATION,
  },
  evidence: { why: "A conclusion rests only on evidence someone has judged reliable.", basis: INVESTIGATION },
  analysis: { why: "The data is analysed before a cause is named.", basis: ["ISO13485_8_4", ...INVESTIGATION] },
  hypotheses: {
    why: "Possible causes are weighed against the evidence before one is relied on.",
    basis: INVESTIGATION,
  },
  gaps: {
    why: "What is still unknown is answered, or accepted as a limitation, before anyone decides.",
    basis: INVESTIGATION,
  },
  risk_regulatory: {
    why: "The risk file and the reporting decision are checked against what was found.",
    basis: ["ISO14971_10", "ISO13485_8_2_3"],
  },
  brief: { why: "A second person checks that the brief is fit to decide on.", basis: INVESTIGATION },
  human_review: {
    why: "A person decides and signs; the signature is linked to exactly what was decided.",
    basis: ["CFR11_50", "CFR11_70"],
  },
};

/** The first-contact questions (backend/app/intake/rules.py QUESTIONS): why each is asked of a call. */
export const FIRST_CONTACT_WHY: Readonly<Record<string, Why>> = {
  Q1: { why: "An alleged shortfall in the device is what makes a call a complaint.", basis: COMPLAINT },
  Q2: { why: "An inaccurate reading is a deficiency, so it is a complaint.", basis: COMPLAINT },
  Q3: { why: "A malfunction is a complaint, and may be reportable.", basis: [...COMPLAINT, "CFR803_50", "MDR_87"] },
  Q4: { why: "Harm, or harm that could have happened, decides how fast it is handled.", basis: REPORTING },
  Q5: { why: "A death or serious injury starts the shortest legal reporting clocks.", basis: REPORTING },
  Q6: { why: "A malfunction that could cause serious harm again is reportable in most markets.", basis: REPORTING },
  Q7: {
    why: "Routine service with no fault alleged is not a complaint; it is recorded as service.",
    basis: COMPLAINT,
  },
  Q8: { why: "A repair beyond routine service suggests a fault, so it is checked as a complaint.", basis: COMPLAINT },
  Q9: { why: "A repeat on the same device or lot may be a trend to analyse.", basis: ["ISO13485_8_4"] },
};

/** The triage record's fields. */
export const TRIAGE_WHY: Readonly<Record<string, Why>> = {
  severity: { why: "Severity sets how urgent the complaint is and which clocks may apply.", basis: ["ISO14971_10"] },
  owners: { why: "One named owner answers for the complaint until it is ready to close.", basis: COMPLAINT },
  action: {
    why: "What is done now to protect patients, or why nothing is needed, is part of the record.",
    basis: COMPLAINT,
  },
  awareness: { why: "Every legal reporting clock counts from the day you became aware.", basis: REPORTING },
};

/** A market's reportability question: the guide's own note and its locked clause, else this line. */
export const MARKET_QUESTION_WHY = "The answer decides whether this is reportable in this market, and by when.";

/** The disposition's four questions, asked in this order. */
export const DISPOSITION_WHY: Readonly<Record<number, Why>> = {
  1: {
    why: "An escalation trigger means the complaint needs an investigation, whatever else is true.",
    basis: COMPLAINT,
  },
  2: {
    why: "A known issue already under investigation takes the complaint into that investigation.",
    basis: COMPLAINT,
  },
  3: {
    why: "A complaint resolved at service level needs the reason no investigation is needed, recorded and signed.",
    basis: COMPLAINT,
  },
  4: { why: "Anything else may still deserve an investigation: you can open one by choice.", basis: COMPLAINT },
};
