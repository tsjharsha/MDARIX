// Pure rules for "Resolve and close" (B7, spec 1.2): one screen and one signature from triage to closure on the
// routine path. The server (GET/POST /api/v1/complaints/{id}/resolve-and-close, complaint_disposition/resolve.py)
// pre-fills it, checks every rule again and signs; these only shape what the person sees and sends.
import { DISPOSITION_LIMITS, type DispositionScreen } from "./disposition";

export type ResolveScreen = {
  disposition: DispositionScreen;
  mode: "COMPLETE" | "CONNECT";
  button: string;
  offer: { full: boolean; blocking: string[]; routine: boolean };
  closed: boolean;
  closed_at: string | null;
  prefill: { troubleshooting: string; correction_type: string; service_ticket: string; problem_code: string };
  problem_code_read_only: boolean;
  /** The organisation's own problem codes, the picker's choices. */
  problem_codes: string[];
  /** The codes already recorded on this product (null: no product). Another code is a new failure mode. */
  product_codes: string[] | null;
  similar_last_12_months: number;
  owner: { id: string | null; name: string | null; is_me: boolean };
  reporters_with_contact: number;
  no_contact_reason: string | null;
  reasons: Record<string, string>;
  device_returned: Record<string, string>;
  told_how: Record<string, string>;
  ticket_corrections: string[];
};

export type ResolveForm = {
  problemCode: string;
  problemDescription: string;
  knownBehaviour: string;
  troubleshooting: string;
  correctionType: string;
  correction: string;
  result: string;
  serviceTicket: string;
  deviceReturned: string;
  reason: string;
  rationale: string;
  attribution: string;
  attributionReason: string;
  useEnvironment: string;
  useEnvironmentText: string;
  userType: string;
  userTypeText: string;
  toldHow: string;
  toldAt: string;
  toldNote: string;
  qmsLetterId: string;
  toldReason: string;
  takeOver: boolean;
  changeReason: string;
  password: string;
  code: string;
};

export const resolvePath = (complaintId: string, tail = "/resolve-and-close") =>
  `/api/v1/complaints/${encodeURIComponent(complaintId)}${tail}`;

const OTHER_REASON = "OTHER";
const WITHDREW = "REPORTER_WITHDREW";
const NOT_POSSIBLE = "NOT_POSSIBLE";
export const REOPEN_MIN = 20;
const KNOWN_BEHAVIOUR_MIN = 3;

const norm = (value: string) => value.trim().replace(/\s+/g, " ").toUpperCase();
const short = (value: string, min: number) => value.trim().replace(/\s+/g, " ").length < min;

/** Whether the decision tree is needed instead: a trigger other than a new failure mode (answered here, B7-D4), or an
 * open investigation that may be this known issue. A signed disposition is shown, not signed again here. */
export function needsTree(screen: ResolveScreen): boolean {
  const disposition = screen.disposition;
  if (screen.closed) return false;
  return (
    !!disposition.current ||
    disposition.candidates.length > 0 ||
    disposition.trigger_codes.some((code) => code !== "NEW_FAILURE_MODE")
  );
}

/** A code never recorded before on this product is a new failure mode (triggers.new_failure_mode). */
export function isNewCode(screen: ResolveScreen, code: string): boolean {
  const chosen = norm(code);
  if (!chosen || screen.product_codes === null || screen.problem_code_read_only) return false;
  return !screen.product_codes.includes(chosen);
}

/** The form as it opens, pre-filled from the Case (spec 1.2): troubleshooting, the correction its request suggests,
 * the ticket, the problem code; an anonymous reporter's customer told is "Not possible" with the Case's reason. */
export function resolveFormOf(screen: ResolveScreen): ResolveForm {
  const proposed = screen.disposition.classification;
  const anonymous = screen.reporters_with_contact === 0 && !!screen.no_contact_reason;
  return {
    problemCode: screen.prefill.problem_code,
    problemDescription: "",
    knownBehaviour: "",
    troubleshooting: screen.prefill.troubleshooting,
    correctionType: screen.prefill.correction_type,
    correction: "",
    result: "",
    serviceTicket: screen.prefill.service_ticket,
    deviceReturned: "",
    reason: "",
    rationale: "",
    attribution: screen.prefill.correction_type === "NO_FAULT_FOUND" ? "UNDETERMINED" : "",
    attributionReason: "",
    useEnvironment: proposed.use_environment,
    useEnvironmentText: proposed.use_environment_text ?? "",
    userType: proposed.user_type,
    userTypeText: proposed.user_type_text ?? "",
    toldHow: anonymous ? NOT_POSSIBLE : "",
    toldAt: "",
    toldNote: "",
    qmsLetterId: "",
    toldReason: anonymous ? `Anonymous: ${screen.no_contact_reason}` : "",
    takeOver: false,
    changeReason: "",
    password: "",
    code: "",
  };
}

/** Why the signature cannot be sent yet, in the server's words; null when it can. */
export function resolveProblem(screen: ResolveScreen, form: ResolveForm, trained: boolean): string | null {
  const { reasonMin, rationaleMin, textMax, ticketMax } = DISPOSITION_LIMITS;
  const disposition = screen.disposition;
  if (screen.closed) return "This complaint is closed: reopen it first, with your reason.";
  if (!screen.problem_code_read_only && !norm(form.problemCode))
    return "Choose the problem code: recurrence and new failure modes depend on it.";
  if (isNewCode(screen, form.problemCode) && short(form.knownBehaviour, KNOWN_BEHAVIOUR_MIN))
    return "This problem code is new on this product: name where the behaviour is documented, or escalate.";
  if (form.problemDescription.trim().length > textMax)
    return `Keep the problem description under ${textMax} characters.`;
  if (short(form.troubleshooting, reasonMin)) return "Describe the troubleshooting done.";
  if (!form.correctionType) return "Choose the correction.";
  if (short(form.correction, reasonMin)) return "Describe the correction.";
  if (short(form.result, 5)) return "Say what the correction achieved.";
  if (screen.ticket_corrections.includes(form.correctionType) && !form.serviceTicket.trim())
    return "Give the service ticket reference: service work was done.";
  if (form.serviceTicket.trim().length > ticketMax) return `Keep the ticket under ${ticketMax} characters.`;
  if (!form.reason) return `Choose why no investigation is needed (${disposition.no_investigation_clause}).`;
  if (form.reason === WITHDREW && disposition.reportability.on_watch)
    return "On the reportability watch a withdrawal does not settle it: choose another reason or escalate.";
  if (form.reason === OTHER_REASON && short(form.rationale, rationaleMin))
    return `Write why no investigation is needed in at least ${rationaleMin} characters.`;
  if (!form.attribution) return "Choose the cause.";
  if (form.correctionType === "NO_FAULT_FOUND" && form.attribution !== "UNDETERMINED")
    return "No fault found: the cause is undetermined; say why.";
  if (form.attribution === "UNDETERMINED" && short(form.attributionReason, reasonMin))
    return "Undetermined: say why the cause cannot be attributed.";
  if (form.useEnvironment === "OTHER" && !form.useEnvironmentText.trim())
    return 'Say what the "other" place of use is.';
  if (form.userType === "OTHER" && !form.userTypeText.trim()) return 'Say what the "other" user is.';
  const letter = screen.mode === "CONNECT" && !!form.qmsLetterId.trim() && form.toldHow !== NOT_POSSIBLE;
  if (!letter && !form.toldHow) return "Record how the customer was told, or that it was not possible and why.";
  if (form.toldHow === NOT_POSSIBLE && short(form.toldReason, reasonMin))
    return "Say why the customer could not be told (anonymous, unreachable).";
  if (screen.owner.id && !screen.owner.is_me && !form.takeOver)
    return `Tick "Take over as owner from ${screen.owner.name ?? "a colleague"}" to sign.`;
  if (disposition.current && short(form.changeReason, reasonMin)) return "Say why the disposition changes.";
  if (!trained) return "Record the practice training first.";
  if (!form.password) return "Enter your password to sign.";
  if (disposition.code_required && !/^\d{6}$/.test(form.code.trim()))
    return "Enter the 6-digit code from your authenticator app.";
  return null;
}

/** What the one signature sends, with what the person saw. ``close`` false: "Resolve" only (the disposition), when
 * something else still blocks closing. */
export function resolveBody(screen: ResolveScreen, form: ResolveForm, close: boolean) {
  const disposition = screen.disposition;
  const fresh = isNewCode(screen, form.problemCode) && !disposition.trigger_codes.includes("NEW_FAILURE_MODE");
  return {
    problem_code: form.problemCode.trim(),
    problem_description: form.problemDescription.trim(),
    known_behaviour_ref: form.knownBehaviour.trim(),
    service_record: {
      troubleshooting: form.troubleshooting,
      correction_type: form.correctionType,
      correction: form.correction,
      result: form.result,
      service_ticket: form.serviceTicket.trim(),
      no_investigation_reason: form.reason,
      no_investigation_rationale: form.reason === OTHER_REASON ? form.rationale : "",
      device_returned: form.deviceReturned,
    },
    attribution: form.attribution,
    attribution_reason: form.attribution === "UNDETERMINED" ? form.attributionReason : "",
    classification: {
      use_environment: form.useEnvironment,
      use_environment_text: form.useEnvironment === "OTHER" ? form.useEnvironmentText : null,
      user_type: form.userType,
      user_type_text: form.userType === "OTHER" ? form.userTypeText : null,
    },
    customer_told: {
      how: form.toldHow,
      at: form.toldAt ? new Date(form.toldAt).toISOString() : null,
      note: form.toldNote,
      qms_letter_id: form.qmsLetterId.trim(),
      reason: form.toldHow === NOT_POSSIBLE ? form.toldReason : "",
    },
    change_reason: form.changeReason,
    take_over: form.takeOver,
    close,
    // A new code's new failure mode is seen here and answered as known behaviour (B7-D4).
    seen_triggers: fresh ? [...disposition.trigger_codes, "NEW_FAILURE_MODE"] : disposition.trigger_codes,
    seen_version: disposition.version,
    opened_at: disposition.opened_at,
    password: form.password,
    mfa_code: form.code || null,
  };
}

/** The reportability line (spec 1.2 step 8): the routine basis, or each market's signed conclusion. */
export function reportabilityLine(screen: ResolveScreen): string {
  const disposition = screen.disposition;
  if (screen.offer.routine && disposition.routine.markets.length)
    return `Not reportable for ${disposition.routine.markets.map((market) => market.label).join(", ")}, on the routine basis.`;
  if (disposition.reportability.markets.length)
    return disposition.reportability.markets
      .map((market) => `${market.label}: ${market.state.replace(/_/g, " ").toLowerCase()}`)
      .join(" · ");
  return "No market to assess: off the reportability watch.";
}

/** What the one signature covers (B7-D1: two signed records, each with its meaning). */
export function resolveCovers(screen: ResolveScreen, close: boolean): string[] {
  const items = ["The disposition: resolved at service level, with the classification confirmed"];
  if (screen.offer.routine)
    for (const market of screen.disposition.routine.markets)
      items.push(`${market.label}: not reportable (routine basis)`);
  items.push("The customer told, in the communications log");
  if (close)
    items.push(
      screen.mode === "COMPLETE"
        ? "Ready to close, and the complaint closed in MDARIX"
        : "Ready to close in your QMS (your QMS closes it)",
    );
  return items;
}
