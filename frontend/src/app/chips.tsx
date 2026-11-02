import { AlertCircle, CalendarClock, Clock } from "lucide-react";
import { timeLeft, type DueLike } from "./dates";

/*
 * The three kinds of label (V1-V4). Each says what it means in words, never by colour alone:
 * - a deadline: an icon and "3 days left", "Due today" or "2 days overdue" (app/dates.ts timeLeft); red only overdue;
 * - a state: neutral grey, whatever the state ("Open", "Closed", "Not started");
 * - a harm: outlined, with a shape (◆ death or critical, ▲ serious injury, ○ no harm or a malfunction only).
 */

export type DeadlineUrgency = "overdue" | "soon" | "later";

/** How urgent a time-left text is: overdue, due within the day (hours or "today"), or later. */
export const deadlineUrgency = (text: string): DeadlineUrgency =>
  /overdue/i.test(text) ? "overdue" : /^(Due today|Due now|\d+ h left)$/.test(text) ? "soon" : "later";

/** A deadline chip: icon and words from the one time-left helper; `prefix` names it ("Triage target"). */
export function DeadlineChip({ item, prefix, now }: { item: DueLike; prefix?: string; now?: Date }) {
  const text = timeLeft(item, now);
  if (!text) return null;
  const urgency = deadlineUrgency(text);
  const Icon = urgency === "overdue" ? AlertCircle : urgency === "soon" ? Clock : CalendarClock;
  return (
    <span className={`ms-chip ms-chip-deadline is-${urgency}`}>
      <Icon size={14} aria-hidden="true" />
      {prefix ? `${prefix}: ${text}` : text}
    </span>
  );
}

/** A record's state, neutral: the words carry it. */
export function StateChip({ label }: { label: string }) {
  return <span className="ms-chip ms-chip-state">{label}</span>;
}

export type Harm = "critical" | "serious" | "none";

const HARM_SHAPE: Record<Harm, string> = { critical: "◆", serious: "▲", none: "○" };

/** The harm a record reports, outlined, with its shape. */
export function HarmChip({ harm, label }: { harm: Harm; label: string }) {
  return (
    <span className={`ms-chip ms-chip-harm is-${harm}`}>
      <span className="ms-chip-shape" aria-hidden="true">
        {HARM_SHAPE[harm]}
      </span>
      {label}
    </span>
  );
}
