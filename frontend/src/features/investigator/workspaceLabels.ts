// What the case Workspace tab shows people, in plain words. The workspace API keeps its codes (NO_DIRECT_EVIDENCE,
// NO_RELEVANT_EVIDENCE, ...) for the audit trail and integrations; the screen reads them through these labels and
// never shows a code.

/** A code in sentence case (NO_MATCH -> "No match"), for a code this file does not know yet. */
const words = (code: string) =>
  code
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/^\w/, (letter) => letter.toUpperCase());

export type WorkspaceNote = { title: string; text: string };

const NOTES: Record<string, WorkspaceNote> = {
  NO_CAUSAL_CONCLUSION: {
    title: "MDARIX does not decide the root cause",
    text: "It shows what the records say; your team decides the cause.",
  },
  NO_ROOT_CAUSE: {
    title: "MDARIX does not decide the root cause",
    text: "It shows what the records say; your team decides the cause.",
  },
  NO_INVESTIGATION_CONCLUSION: {
    title: "The conclusion stays with people",
    text: "MDARIX organizes the case; a person reviews and signs the decision.",
  },
  NO_DIRECT_EVIDENCE: {
    title: "No evidence on this case yet",
    text: "Add or link evidence on the Evidence tab.",
  },
  NO_RELEVANT_EVIDENCE: {
    title: "No matching evidence found yet",
    text: "Add or link the evidence that belongs to this case on the Evidence tab.",
  },
  INSUFFICIENT_RELEVANT_EVIDENCE: {
    title: "Only loosely matching evidence",
    text: "Check the evidence list and link what belongs to this case.",
  },
  MISSING_MATERIALIZED_CHUNKS: {
    title: "Some evidence is still being indexed",
    text: "It is listed, but search may miss parts of it for a few minutes.",
  },
  UNRESOLVED_EVIDENCE_LINKS: {
    title: "Some evidence is not linked to a record yet",
    text: "Open it on the Evidence tab to link it to its product, lot or complaint.",
  },
};

// The search for more evidence found nothing, on a case that already has its own evidence: nothing is missing.
const NOTHING_MORE: WorkspaceNote = {
  title: "No further matching records",
  text: "The evidence listed is this case's own; a search of your other records for its question found nothing more.",
};
const SEARCH_EMPTY = new Set(["NO_RELEVANT_EVIDENCE", "INSUFFICIENT_RELEVANT_EVIDENCE"]);

/**
 * A workspace limitation as people read it: a title and a sentence, never its code. ``evidence`` is how many pieces
 * of evidence the case has: an empty search on a case with evidence is not "no evidence".
 */
export function workspaceNote(
  item: { code?: string | null; description?: string | null },
  evidence = 0,
): WorkspaceNote {
  const code = String(item.code ?? "").toUpperCase();
  if (evidence > 0 && SEARCH_EMPTY.has(code)) return NOTHING_MORE;
  return NOTES[code] ?? { title: words(code || "Note"), text: String(item.description ?? "") };
}

/** One note per title: two codes that say the same thing (no root cause, no conclusion) show once. */
export function workspaceNotes(
  items: Array<{ code?: string | null; description?: string | null }>,
  evidence = 0,
): WorkspaceNote[] {
  const seen = new Set<string>();
  return items
    .map((item) => workspaceNote(item, evidence))
    .filter((note) => !seen.has(note.title) && Boolean(seen.add(note.title)));
}

const SEARCH: Record<string, string> = {
  COMPLETED: "Matching evidence found",
  NO_RELEVANT_EVIDENCE: "No matching evidence yet",
  INSUFFICIENT_RELEVANT_EVIDENCE: "Only loosely matching evidence",
};

/** The case's evidence search (retrieval) result in words; ``evidence`` as for ``workspaceNote``. */
export function searchStatusText(status: string | null | undefined, evidence = 0): string {
  if (!status) return "Not searched yet";
  if (evidence > 0 && SEARCH_EMPTY.has(status.toUpperCase())) return "No further matching records";
  return SEARCH[status.toUpperCase()] ?? words(status);
}

/** Which records the case is read at: today's, as they were on a day, or as known on a day. */
export function pointInTimeText(mode: string | null | undefined, asOf?: string | null): string {
  const day = asOf ? String(asOf).slice(0, 10) : null;
  if (mode === "event") return day ? `As it happened on ${day}` : "As it happened";
  if (mode === "known") return day ? `As it was known on ${day}` : "As it was known then";
  return "Today's records";
}

/** A status code from an AI step or a brief (INSUFFICIENT_EVIDENCE, READY_FOR_REVIEW, ...) in words. */
export function stateText(value: string | null | undefined, fallback: string): string {
  return value ? words(value) : fallback;
}
