import { Bot, Calculator, CircleHelp, FileCheck2, ListChecks, Quote, User } from "lucide-react";
import { AI_REVIEW_NOTE, statementBadge, statementOrigin } from "./epistemic";
import "./statement-kind.css";

const KIND_ICONS = {
  fact: FileCheck2,
  source: Quote,
  derived: Calculator,
  ai: Bot,
  hypothesis: CircleHelp,
} as const;

/**
 * What kind of statement this is and who made it, as two labelled parts (never colour alone). An AI interpretation is
 * dashed and violet with a robot icon, so it never looks like a fact or a signed record.
 */
export function StatementKind({
  kind,
  origin,
  kindLabel,
  originLabel,
}: {
  kind?: unknown;
  origin?: unknown;
  /** The server's label for the kind (ignored for AI output, which always reads "AI interpretation"). */
  kindLabel?: unknown;
  originLabel?: unknown;
}) {
  const badge = statementBadge({ kind, origin, kindLabel, originLabel });
  const KindIcon = KIND_ICONS[badge.style];
  const who = statementOrigin(origin);
  const OriginIcon = who === "AI" ? Bot : who === "SYSTEM" ? ListChecks : User;
  return (
    <span
      className={`sk-badge sk-${badge.style}`}
      title={badge.description}
      aria-label={badge.description}
      data-statement-kind={badge.kind}
    >
      <span className="sk-kind" aria-hidden="true">
        <KindIcon size={13} />
        {badge.kindLabel}
      </span>
      <span className="sk-origin" aria-hidden="true">
        <OriginIcon size={12} />
        {badge.originLabel}
      </span>
    </span>
  );
}

/** The note shown with each block of AI output, with an optional way to judge it where people record judgements. */
export function AiInterpretationNote({
  note,
  onJudge,
  judgeLabel = "Judge these in Intelligence",
}: {
  note?: string | null;
  onJudge?: () => void;
  judgeLabel?: string;
}) {
  return (
    <p className="sk-note" role="note">
      <StatementKind kind="AI_INTERPRETATION" origin="AI" />
      <span>{note && note.trim() ? note.trim() : AI_REVIEW_NOTE}</span>
      {onJudge && (
        <button type="button" className="sk-link" onClick={onJudge}>
          {judgeLabel}
        </button>
      )}
    </p>
  );
}
