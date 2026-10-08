// The structured Ask MDARIX answer (Phase 4): `structured` on POST/GET /api/v1/stage3/interactions, normalized so the
// page can render it section by section. Anything missing or malformed is left out; when nothing usable is there the
// page keeps its existing rendering.

export type StructuredSource = {
  businessId: string | null;
  title: string | null;
  kind: string | null;
  relevance: number | null;
};
export type StructuredFact = { statement: string; kind: string | null; origin: string | null; sources: string[] };
export type StructuredItem = { statement: string; sources: string[] };
export type StructuredUnknown = { statement: string; businessId: string | null; status: string | null };
export type StructuredMissing = { statement: string; requestBusinessId: string | null };

export type StructuredAnswer = {
  summary: string | null;
  knownFacts: StructuredFact[];
  supporting: StructuredItem[];
  contradicting: StructuredItem[];
  unknowns: StructuredUnknown[];
  missing: StructuredMissing[];
  limitations: string[];
  nextSteps: string[];
  sources: StructuredSource[];
  /** False when MDARIX built the answer from records without AI; null when not said. */
  aiUsed: boolean | null;
  aiNote: string | null;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const text = (value: unknown): string | null => {
  if (typeof value !== "string" && typeof value !== "number") return null;
  const result = String(value).trim();
  return result && !UUID.test(result) ? result : null;
};

const isObject = (value: unknown): value is Record<string, any> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const list = (value: unknown): unknown[] => (Array.isArray(value) ? value.filter((item) => item != null) : []);

/** Source references as business IDs: strings as they are, objects by business_id (or evidence_identifier). */
const sourceIds = (value: unknown): string[] =>
  Array.from(
    new Set(
      list(value)
        .map((item) =>
          isObject(item) ? (text(item.business_id) ?? text(item.evidence_identifier) ?? text(item.title)) : text(item),
        )
        .filter((item): item is string => Boolean(item)),
    ),
  );

const statementOf = (item: unknown): string | null =>
  isObject(item) ? (text(item.statement) ?? text(item.text) ?? text(item.description)) : text(item);

const items = (value: unknown): StructuredItem[] =>
  list(value)
    .map((item) => {
      const statement = statementOf(item);
      return statement ? { statement, sources: isObject(item) ? sourceIds(item.sources) : [] } : null;
    })
    .filter((item): item is StructuredItem => Boolean(item));

const strings = (value: unknown): string[] =>
  list(value)
    .map(statementOf)
    .filter((item): item is string => Boolean(item));

/** The structured answer of an Ask response or stored interaction, or null when it has none. */
export function structuredAnswer(value: unknown): StructuredAnswer | null {
  if (!isObject(value)) return null;
  const relevance = (item: Record<string, any>) =>
    typeof item.relevance === "number" && Number.isFinite(item.relevance)
      ? Math.max(0, Math.min(1, item.relevance))
      : null;
  return {
    summary: text(value.summary),
    knownFacts: list(value.known_facts)
      .map((item) => {
        const statement = statementOf(item);
        if (!statement) return null;
        const row = isObject(item) ? item : {};
        return {
          statement,
          kind: text(row.epistemic_type),
          origin: text(row.origin),
          sources: sourceIds(row.sources),
        };
      })
      .filter((item): item is StructuredFact => Boolean(item)),
    supporting: items(value.supporting_evidence),
    contradicting: items(value.contradicting_evidence),
    unknowns: list(value.unknowns)
      .map((item) => {
        const statement = statementOf(item);
        if (!statement) return null;
        const row = isObject(item) ? item : {};
        return { statement, businessId: text(row.business_id), status: text(row.status) };
      })
      .filter((item): item is StructuredUnknown => Boolean(item)),
    missing: list(value.missing_evidence)
      .map((item) => {
        const statement = statementOf(item);
        if (!statement) return null;
        const row = isObject(item) ? item : {};
        return { statement, requestBusinessId: text(row.request_business_id) };
      })
      .filter((item): item is StructuredMissing => Boolean(item)),
    limitations: strings(value.limitations),
    nextSteps: strings(value.next_steps),
    sources: list(value.sources)
      .filter(isObject)
      .map((item) => ({
        businessId: text(item.business_id) ?? text(item.evidence_identifier),
        title: text(item.title),
        kind: text(item.kind),
        relevance: relevance(item),
      }))
      .filter((item) => item.businessId || item.title),
    aiUsed: typeof value.ai_used === "boolean" ? value.ai_used : null,
    aiNote: text(value.ai_note),
  };
}

/** Whether a structured answer has anything to show (otherwise the existing rendering is used). */
export function hasStructuredContent(answer: StructuredAnswer | null | undefined): answer is StructuredAnswer {
  if (!answer) return false;
  return Boolean(
    answer.summary ||
    answer.knownFacts.length ||
    answer.supporting.length ||
    answer.contradicting.length ||
    answer.unknowns.length ||
    answer.missing.length ||
    answer.limitations.length ||
    answer.nextSteps.length ||
    answer.sources.length,
  );
}

/** The structured answer of an Ask response: `structured` at the top, or inside `response`. */
export const structuredOf = (result: unknown): StructuredAnswer | null =>
  isObject(result)
    ? structuredAnswer(result.structured ?? (isObject(result.response) ? result.response.structured : null))
    : null;

/** How the answer was made, in the words the page shows; null when the response does not say. */
export function answerOriginText(answer: StructuredAnswer | null | undefined): string | null {
  if (!answer || answer.aiUsed === null) return null;
  return answer.aiUsed
    ? "AI interpretation of your records — review before relying on it"
    : "Answer built from your records (AI not used)";
}

/** The one-line summary of a stored conversation for My Work, or null when it has none. */
export const conversationSummary = (row: unknown): string | null => structuredOf(row)?.summary ?? null;

/** Section headings, in the order the page shows them. */
export const STRUCTURED_SECTIONS = {
  summary: "Summary",
  knownFacts: "Known facts",
  supporting: "Supporting evidence",
  contradicting: "Contradicting evidence",
  unknowns: "Unknowns",
  missing: "Missing evidence",
  limitations: "Limitations",
  nextSteps: "Suggested next steps",
  sources: "Sources",
} as const;
