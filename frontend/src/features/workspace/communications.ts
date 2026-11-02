// Pure rules for Complaints › Communications (T-G30): the external communications log. The server
// (/api/v1/communications, backend/app/communications) records every entry and attempt and applies the escalation rule;
// these only shape what the person sees and what is sent. MDARIX sends nothing to an external contact.
import type { Tone } from "../admin/console/dashboardModel";
import { formatDay } from "../../app/dates";

export const COMMUNICATIONS = "/api/v1/communications";
export const COMMUNICATIONS_TAB = "Communications";
export const REASON_MIN = 10;

export type Status = "OPEN" | "ANSWERED" | "UNRESOLVED" | "CLOSED";
export type Contact = { name: string | null; details: string | null };

export type Party = {
  id: string;
  type: string;
  type_label: string;
  name: string;
  complaint_id: string | null;
  primary: Contact;
  second: Contact | null;
  note: string | null;
  sample: boolean;
};

export type Attempt = {
  number: number;
  at: string;
  channel: string;
  channel_label: string;
  contact: "PRIMARY" | "SECOND";
  contact_name: string;
  outcome: string;
  outcome_label: string;
  unanswered: boolean;
  note: string | null;
  logged_at: string;
  logged_by: string;
  in_mdarix: boolean | null;
};

export type Entry = {
  id: string;
  complaint_id: string | null;
  complaint_ref: string | null;
  intake_reference: string | null;
  party: Party | null;
  direction: "SENT" | "RECEIVED";
  direction_label: string;
  purpose: string;
  purpose_label: string;
  subject: string;
  note: string | null;
  channel: string;
  channel_label: string;
  occurred_at: string;
  logged_at: string;
  logged_by: string;
  in_mdarix: boolean | null;
  owner_id: string | null;
  owner: string | null;
  reply_due_on: string | null;
  overdue: boolean;
  status: Status;
  status_label: string;
  is_request: boolean;
  not_sent_yet: boolean;
  current_contact: "PRIMARY" | "SECOND";
  contact_now: Contact | null;
  attempts: Attempt[];
  unanswered: number;
  attempts_limit: number;
  evidence: string[];
  qms_reference: string | null;
  in_reply_to: string | null;
  origin: { type: string; label: string | null; questions?: string[] } | null;
  closed_at: string | null;
  closed_by: string | null;
  close_note: string | null;
  sample: boolean;
  replies?: Entry[];
  never_sends?: string;
};

export type Labels = {
  party_types: Record<string, string>;
  purposes: Record<string, string>;
  directions: Record<string, string>;
  statuses: Record<string, string>;
  channels: Record<string, string>;
  outcomes: Record<string, string>;
};

export type CommunicationList = {
  complaint: { id: string; ref: string; identifier: string; description: string; sample: boolean } | null;
  items: Entry[];
  counts: { open: number; overdue: number; unresolved: number };
  s4: { in_mdarix: number; outside: number };
  parties: Party[];
  colleagues: Array<{ id: string; name: string }>;
  attempts_limit: number;
  labels: Labels;
  never_sends: string;
};

export function statusTone(entry: Pick<Entry, "status" | "overdue">): Tone {
  if (entry.status === "UNRESOLVED") return "critical";
  if (entry.status === "OPEN") return entry.overdue ? "critical" : "warning";
  return entry.status === "ANSWERED" ? "good" : "neutral";
}

/** "2 of 3 attempts to the primary contact unanswered", or the state of a request that is not open. */
export function attemptsText(
  entry: Pick<Entry, "status" | "not_sent_yet" | "unanswered" | "attempts_limit" | "current_contact" | "attempts">,
): string {
  if (entry.not_sent_yet) return "Not sent yet: record the first attempt when you send it";
  const who = entry.current_contact === "SECOND" ? "the second contact" : "the primary contact";
  if (entry.status !== "OPEN") return `${entry.attempts.length} attempts in all`;
  return `${entry.unanswered} of ${entry.attempts_limit} attempts to ${who} unanswered`;
}

export function dueText(entry: Pick<Entry, "status" | "reply_due_on" | "overdue">): string {
  if (entry.status !== "OPEN" || !entry.reply_due_on) return "";
  // The reply's day on the organization's calendar (the server's), shown as a day: the same day the task names (J16).
  return entry.overdue
    ? `Reply was due ${formatDay(entry.reply_due_on)}: overdue`
    : `Reply due ${formatDay(entry.reply_due_on)}`;
}

export function s4Text(s4: CommunicationList["s4"]): string {
  const total = s4.in_mdarix + s4.outside;
  return total
    ? `Recorded in MDARIX: ${s4.in_mdarix} of ${total} messages (logged before sending, or within one working hour); ${s4.outside} recorded later.`
    : "No message recorded yet.";
}

/** The local date-time an input shows, as the ISO time with its zone the server takes. */
export const isoOf = (local: string) => new Date(local).toISOString();

export type EntryForm = {
  partyId: string;
  direction: "SENT" | "RECEIVED";
  purpose: string;
  subject: string;
  channel: string;
  occurredAt: string;
  ownerId: string;
  replyDueOn: string;
  note: string;
  evidence: string;
  qmsReference: string;
};

export const isRequest = (form: Pick<EntryForm, "direction" | "purpose">) =>
  form.direction === "SENT" && form.purpose === "INFORMATION_REQUEST";

/** What the browser can tell is missing before recording (the server checks it all again). */
export function entryProblem(form: EntryForm): string | null {
  if (!form.partyId) return "Choose the party";
  if (form.subject.trim().length < 5) return "Say in a few words what was asked or said";
  if (!form.occurredAt) return "Give the time it was sent or received";
  if (form.direction === "RECEIVED" && form.purpose === "INFORMATION_REQUEST")
    return "A message you received is a response or an update";
  if (isRequest(form) && (!form.ownerId || !form.replyDueOn))
    return "A request needs its owner and the date a reply is due";
  return null;
}

const lines = (text: string) =>
  text
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

export function entryBody(form: EntryForm, complaintId: string) {
  const request = isRequest(form);
  return {
    complaint_id: complaintId,
    party_id: form.partyId,
    direction: form.direction,
    purpose: form.purpose,
    subject: form.subject.trim(),
    channel: form.channel,
    occurred_at: isoOf(form.occurredAt),
    owner_id: request ? form.ownerId : null,
    reply_due_on: request ? form.replyDueOn : null,
    note: form.note,
    evidence: lines(form.evidence),
    qms_reference: form.qmsReference,
  };
}

export const evidenceLines = lines;

/** The tab name that opens one complaint's log ("Communications?complaint=<id>"), and its reading. */
export function communicationsTab(complaintId?: string | null): string {
  return complaintId ? `${COMMUNICATIONS_TAB}?complaint=${encodeURIComponent(complaintId)}` : COMMUNICATIONS_TAB;
}

export function parseCommunicationsTab(tab: string | null | undefined): { isLog: boolean; complaintId: string | null } {
  if (!tab || !(tab === COMMUNICATIONS_TAB || tab.startsWith(`${COMMUNICATIONS_TAB}?`)))
    return { isLog: false, complaintId: null };
  return { isLog: true, complaintId: new URLSearchParams(tab.slice(COMMUNICATIONS_TAB.length + 1)).get("complaint") };
}
