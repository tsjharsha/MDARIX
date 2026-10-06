// What kind of statement a person is reading, and who made it (Phase 4). AI output must never look like a verified
// fact or a signed record: every statement shows its kind (fact, source assertion, derived observation, AI
// interpretation, or a hypothesis still under consideration) and its origin (a person, AI or MDARIX rules).

export const STATEMENT_KINDS = [
  "FACT",
  "SOURCE_ASSERTION",
  "DERIVED_OBSERVATION",
  "AI_INTERPRETATION",
  "HYPOTHESIS",
] as const;
export type StatementKindCode = (typeof STATEMENT_KINDS)[number];

export const STATEMENT_ORIGINS = ["PERSON", "AI", "SYSTEM"] as const;
export type StatementOriginCode = (typeof STATEMENT_ORIGINS)[number];

/**
 * How each kind reads. `style` picks the badge's look: only a fact is drawn solid; an AI interpretation is always
 * dashed and violet, never green, never with a check mark, so it cannot pass for a verified fact or a signature.
 */
export const STATEMENT_KIND: Record<
  StatementKindCode,
  { label: string; help: string; style: "fact" | "source" | "derived" | "ai" | "hypothesis" }
> = {
  FACT: { label: "Fact", help: "Recorded in a source record of your organization.", style: "fact" },
  SOURCE_ASSERTION: {
    label: "Source assertion",
    help: "What a source says. Not verified by MDARIX.",
    style: "source",
  },
  DERIVED_OBSERVATION: {
    label: "Derived observation",
    help: "Worked out from records (a count, a comparison, a pattern).",
    style: "derived",
  },
  AI_INTERPRETATION: {
    label: "AI interpretation",
    help: "Written by AI. Review it before relying on it: it is not a fact and not a signed record.",
    style: "ai",
  },
  HYPOTHESIS: {
    label: "Hypothesis",
    help: "A possible explanation under consideration. Not a conclusion.",
    style: "hypothesis",
  },
};

export const STATEMENT_ORIGIN: Record<StatementOriginCode, { label: string; help: string }> = {
  PERSON: { label: "Person", help: "Recorded by a person in your organization." },
  AI: { label: "AI", help: "Produced by AI." },
  SYSTEM: { label: "MDARIX rules", help: "Produced by MDARIX's deterministic rules." },
};

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const KIND_ALIASES: Record<string, StatementKindCode> = {
  FACT: "FACT",
  VERIFIED_FACT: "FACT",
  SOURCE_ASSERTION: "SOURCE_ASSERTION",
  ASSERTION: "SOURCE_ASSERTION",
  DERIVED_OBSERVATION: "DERIVED_OBSERVATION",
  DERIVED: "DERIVED_OBSERVATION",
  OBSERVATION: "DERIVED_OBSERVATION",
  AI_INTERPRETATION: "AI_INTERPRETATION",
  INTERPRETATION: "AI_INTERPRETATION",
  AI: "AI_INTERPRETATION",
  HYPOTHESIS: "HYPOTHESIS",
};

const ORIGIN_ALIASES: Record<string, StatementOriginCode> = {
  PERSON: "PERSON",
  HUMAN: "PERSON",
  USER: "PERSON",
  MANUAL: "PERSON",
  AI: "AI",
  AI_ADOPTED: "AI",
  LANGUAGE_MODEL: "AI",
  MODEL: "AI",
  SYSTEM: "SYSTEM",
  RULES: "SYSTEM",
  MDARIX: "SYSTEM",
  DETERMINISTIC: "SYSTEM",
};

/** The origin of a statement, or null when the response does not say (shown as "Origin not recorded"). */
export function statementOrigin(value: unknown): StatementOriginCode | null {
  return ORIGIN_ALIASES[code(value)] ?? null;
}

/**
 * The kind of a statement. Anything that comes from AI is an AI interpretation whatever kind it claims, so AI output
 * never reads as a fact; an unknown or missing kind reads as a source assertion (never as a fact).
 */
export function statementKind(value: unknown, origin?: unknown): StatementKindCode {
  if (statementOrigin(origin) === "AI") return "AI_INTERPRETATION";
  return KIND_ALIASES[code(value)] ?? "SOURCE_ASSERTION";
}

/** The origin's label; an AI result a person adopted says so. */
export function statementOriginLabel(value: unknown): string {
  if (code(value) === "AI_ADOPTED") return "AI, adopted by a person";
  const origin = statementOrigin(value);
  return origin ? STATEMENT_ORIGIN[origin].label : "Origin not recorded";
}

export type StatementBadgeModel = {
  kind: StatementKindCode;
  kindLabel: string;
  originLabel: string;
  style: (typeof STATEMENT_KIND)[StatementKindCode]["style"];
  /** The whole badge as one sentence, for assistive technology and the tooltip. */
  description: string;
};

/** What a kind badge shows: the kind (the server's label may name it, but AI output stays an AI interpretation). */
export function statementBadge(input: {
  kind?: unknown;
  origin?: unknown;
  kindLabel?: unknown;
  originLabel?: unknown;
}): StatementBadgeModel {
  const kind = statementKind(input.kind, input.origin);
  const serverKind = typeof input.kindLabel === "string" && input.kindLabel.trim() ? input.kindLabel.trim() : null;
  // A server label never turns AI output into something else.
  const kindLabel =
    kind === "AI_INTERPRETATION" ? STATEMENT_KIND[kind].label : (serverKind ?? STATEMENT_KIND[kind].label);
  const serverOrigin =
    typeof input.originLabel === "string" && input.originLabel.trim() ? input.originLabel.trim() : null;
  const originLabel = serverOrigin ?? statementOriginLabel(input.origin);
  return {
    kind,
    kindLabel,
    originLabel,
    style: STATEMENT_KIND[kind].style,
    description: `${kindLabel}, made by ${originLabel}. ${STATEMENT_KIND[kind].help}`,
  };
}

/** The sentence shown with every block of AI output. */
export const AI_REVIEW_NOTE = "AI interpretation — review before relying on it.";
