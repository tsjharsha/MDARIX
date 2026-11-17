// Pure rules for a case's intelligence (Phase 4): the views of the Intelligence tab, hypotheses and how people judge
// them, the evidence grouped by how it bears on a hypothesis, contradictions, unknowns and their status changes,
// failure chains (layout, legend, hand-built chains), observations, the history, and what to show when AI is off.
// The server owns every rule and refuses what it does not allow; these only shape what the person sees and sends.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const list = <T = Record<string, any>>(value: unknown): T[] =>
  Array.isArray(value) ? (value.filter((item) => item !== null && item !== undefined) as T[]) : [];

const isObject = (value: unknown): value is Record<string, any> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

// ---------------------------------------------------------------------------------------------------------------
// The Intelligence tab of Investigations and its views

// The method first, in the order a reader follows it (Overview opens), then the working views.
export const INTELLIGENCE_VIEWS = [
  // RCA tools: the read-only overview (MDARIX_RCA_INTELLIGENCE), the fishbone and the 5 Whys (MDARIX_RCA_METHODS).
  "Overview",
  "Fishbone",
  "5 Whys",
  "Hypotheses",
  "Failure chain",
  "Contradictions",
  "Unknowns",
  "Observations",
  // B5a: drafts and questions drawn by rule from the records (hidden while the switch is off).
  "Challenge",
  "History",
] as const;
export type IntelligenceView = (typeof INTELLIGENCE_VIEWS)[number];

/** The view to show: the one asked for when it is shown, else the first shown (a switched-off view never opens). */
export const shownIntelligenceView = (views: readonly IntelligenceView[], requested: IntelligenceView) =>
  views.includes(requested) ? requested : (views[0] ?? requested);

export const INTELLIGENCE_TAB = "Intelligence";

export const isIntelligenceView = (value: unknown): value is IntelligenceView =>
  typeof value === "string" && (INTELLIGENCE_VIEWS as readonly string[]).includes(value);

/** The Investigations tab name that opens the Intelligence tab on one view: "Intelligence?view=Unknowns". */
export function intelligenceTab(view?: IntelligenceView | null): string {
  return view && isIntelligenceView(view) ? `${INTELLIGENCE_TAB}?${new URLSearchParams({ view })}` : INTELLIGENCE_TAB;
}

/** The tab and Intelligence view a tab name passed to Investigations asks for (see intelligenceTab). */
export function parseInvestigationsTab(value: string | null | undefined): {
  tab: string;
  view: IntelligenceView | null;
} {
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  if (mark < 0) return { tab: text, view: null };
  const view = new URLSearchParams(text.slice(mark + 1)).get("view");
  return { tab: text.slice(0, mark), view: isIntelligenceView(view) ? view : null };
}

// ---------------------------------------------------------------------------------------------------------------
// Addresses (prefix /api/v1/investigations/{id}/intelligence)

export const intelligencePath = (investigationId: string, path: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/intelligence/${path}`;

export function hypothesesPath(
  investigationId: string,
  options: { includeRetired?: boolean; includeSuperseded?: boolean } = {},
): string {
  const params = new URLSearchParams();
  if (options.includeRetired) params.set("include_retired", "true");
  if (options.includeSuperseded) params.set("include_superseded", "true");
  const query = params.toString();
  return intelligencePath(investigationId, `hypotheses${query ? `?${query}` : ""}`);
}

export const unknownsPath = (investigationId: string, includeSuperseded = false) =>
  intelligencePath(investigationId, `unknowns${includeSuperseded ? "?include_superseded=true" : ""}`);

// ---------------------------------------------------------------------------------------------------------------
// Written text: statements, reasons and rationales

export const TEXT_MIN = 10;
export const TEXT_MAX = 2000;

/** Why a piece of text cannot be sent yet, or null when it can. */
export function textProblem(
  value: string,
  what: string,
  options: { min?: number; max?: number; required?: boolean } = {},
): string | null {
  const { min = TEXT_MIN, max = TEXT_MAX, required = true } = options;
  const text = value.trim();
  if (!text && !required) return null;
  if (text.length < min) return `Write ${what} of at least ${min} characters (${min - text.length} more).`;
  if (text.length > max) return `Keep ${what} to ${max} characters.`;
  return null;
}

// ---------------------------------------------------------------------------------------------------------------
// Hypotheses

export const HUMAN_STATUSES = [
  "PROPOSED",
  "HYPOTHESIZED",
  "PARTIALLY_SUPPORTED",
  "STRONGLY_SUPPORTED",
  "WEAKLY_SUPPORTED",
  "CONTRADICTED",
  "RETIRED",
] as const;
export type HumanStatus = (typeof HUMAN_STATUSES)[number];

export const HUMAN_STATUS: Record<HumanStatus, { label: string; tone: Tone; help: string }> = {
  PROPOSED: { label: "Proposed", tone: "neutral", help: "Put forward, not judged by a person yet." },
  HYPOTHESIZED: { label: "Hypothesized", tone: "neutral", help: "Worth investigating; evidence not weighed yet." },
  PARTIALLY_SUPPORTED: {
    label: "Partially supported",
    tone: "warning",
    help: "Some evidence is consistent with it; gaps remain.",
  },
  STRONGLY_SUPPORTED: {
    label: "Strongly supported",
    tone: "good",
    help: "Several independent records are consistent with it. Still not a concluded root cause.",
  },
  WEAKLY_SUPPORTED: {
    label: "Weakly supported",
    tone: "warning",
    help: "Little or weak evidence is consistent with it.",
  },
  CONTRADICTED: { label: "Contradicted", tone: "critical", help: "Evidence speaks against it." },
  RETIRED: { label: "Retired", tone: "neutral", help: "No longer considered. The reason stays in the history." },
};

export const humanStatusOf = (value: unknown): HumanStatus | null => {
  const status = code(value);
  return (HUMAN_STATUSES as readonly string[]).includes(status) ? (status as HumanStatus) : null;
};

/** A person's judgement of a hypothesis as people read it; "Not judged yet" before anyone judged it. */
export function humanStatusLabel(status: unknown, label?: unknown): string {
  const server = safeText(label);
  if (server) return server;
  const known = humanStatusOf(status);
  if (known) return HUMAN_STATUS[known].label;
  return status ? titleCase(String(status)) : "Not judged by a person yet";
}

export const humanStatusTone = (status: unknown): Tone => {
  const known = humanStatusOf(status);
  return known ? HUMAN_STATUS[known].tone : "neutral";
};

/** What the AI said about a hypothesis (its own status); a hypothesis a person added has none. */
export function aiStatusText(hypothesis: Pick<IntelHypothesis, "origin" | "ai_status" | "ai_status_label">): string {
  const label = safeText(hypothesis.ai_status_label);
  if (label) return label;
  if (hypothesis.ai_status) return titleCase(String(hypothesis.ai_status));
  return code(hypothesis.origin) === "AI" ? "No AI status recorded" : "Not proposed by AI";
}

/**
 * The judgements a person may record next. Proposed is where a hypothesis starts, never a judgement; the current
 * status is not offered again; a retired hypothesis can only be taken back into consideration (Hypothesized).
 * The server decides either way.
 */
export function allowedHumanStatuses(current: unknown): HumanStatus[] {
  const status = humanStatusOf(current);
  if (status === "RETIRED") return ["HYPOTHESIZED"];
  return HUMAN_STATUSES.filter((item) => item !== "PROPOSED" && item !== status);
}

export const RELATIONS = ["SUPPORTING", "CONTRADICTING", "CONTEXTUAL", "UNRESOLVED"] as const;
export type Relation = (typeof RELATIONS)[number];

export const RELATION: Record<Relation, { label: string; tone: Tone; help: string }> = {
  SUPPORTING: { label: "Supporting", tone: "good", help: "Consistent with this hypothesis." },
  CONTRADICTING: { label: "Contradicting", tone: "critical", help: "Speaks against this hypothesis." },
  CONTEXTUAL: { label: "Contextual", tone: "neutral", help: "Background that frames it." },
  UNRESOLVED: { label: "Unresolved", tone: "warning", help: "How it bears on this hypothesis is not settled yet." },
};

export type LinkedEvidence = {
  id?: string;
  business_id?: string | null;
  title?: string | null;
  evidence_type?: string | null;
};

export type EvidenceLink = {
  id: string;
  relation?: string | null;
  evidence?: LinkedEvidence | null;
  rationale?: string | null;
  added_by?: string | null;
  created_by_type?: string | null;
  created_at?: string | null;
  retracted?: boolean | null;
  retracted_by_name?: string | null;
  retraction_reason?: string | null;
};

export type IntelHypothesis = {
  id: string;
  business_id?: string | null;
  statement?: string | null;
  origin?: string | null;
  ai_status?: string | null;
  ai_status_label?: string | null;
  human_status?: string | null;
  human_status_label?: string | null;
  status_reason?: string | null;
  status_changed_by_name?: string | null;
  status_changed_at?: string | null;
  created_by_name?: string | null;
  kind_label?: string | null;
  /** Recorded with the sample: no model was called (W1). */
  recorded?: boolean | null;
  evidence?: Partial<Record<Lowercase<Relation>, EvidenceLink[] | null>> | EvidenceLink[] | null;
  unknowns?: Array<{
    id: string;
    business_id?: string | null;
    description?: string | null;
    status?: string | null;
  }> | null;
  actions?: { can_set_status?: boolean; can_link_evidence?: boolean } | null;
};

export type HypothesisList = { items?: IntelHypothesis[] | null; counts?: Record<string, number> | null };

export type EvidenceGroup = {
  relation: Relation;
  label: string;
  tone: Tone;
  active: EvidenceLink[];
  withdrawn: EvidenceLink[];
};

/**
 * A hypothesis's evidence grouped Supporting, Contradicting, Contextual, Unresolved (always all four, in that order),
 * each with its live links and, apart, the links someone withdrew. Accepts the grouped object or a flat list.
 */
export function groupEvidence(evidence: IntelHypothesis["evidence"]): EvidenceGroup[] {
  const byRelation = new Map<Relation, EvidenceLink[]>(RELATIONS.map((relation) => [relation, []]));
  if (Array.isArray(evidence)) {
    for (const link of evidence) {
      const relation = code(link?.relation) as Relation;
      if (link && byRelation.has(relation)) byRelation.get(relation)!.push(link);
    }
  } else if (isObject(evidence)) {
    for (const relation of RELATIONS)
      byRelation
        .get(relation)!
        .push(...list<EvidenceLink>((evidence as Record<string, unknown>)[relation.toLowerCase()]));
  }
  return RELATIONS.map((relation) => {
    const links = byRelation.get(relation)!;
    return {
      relation,
      label: RELATION[relation].label,
      tone: RELATION[relation].tone,
      active: links.filter((link) => link.retracted !== true),
      withdrawn: links.filter((link) => link.retracted === true),
    };
  });
}

/** Who linked a record to a hypothesis: the person's name, AI or MDARIX rules. */
export function addedByText(link: Pick<EvidenceLink, "added_by" | "created_by_type">): string {
  const type = code(link.created_by_type);
  if (type === "AI" || type === "LANGUAGE_MODEL") return "Added by AI";
  if (type === "SYSTEM") return "Added by MDARIX rules";
  const name = safeText(link.added_by);
  return name ? `Added by ${name}` : "Added by a person";
}

export const evidenceName = (evidence: LinkedEvidence | null | undefined) =>
  safeText(evidence?.business_id) ?? "Evidence";

export const NEW_HYPOTHESIS = { statement: "", rationale: "" };
export type HypothesisForm = typeof NEW_HYPOTHESIS;

export function hypothesisProblem(form: HypothesisForm): string | null {
  return (
    textProblem(form.statement, "the hypothesis") ??
    textProblem(form.rationale, "the rationale", { min: 0, required: false })
  );
}

export function hypothesisBody(form: HypothesisForm) {
  const rationale = form.rationale.trim();
  return { statement: form.statement.trim(), ...(rationale ? { rationale } : {}) };
}

export type StatusForm = { status: HumanStatus | ""; reason: string };

export function statusProblem(form: StatusForm): string | null {
  if (!form.status) return "Choose your judgement.";
  return textProblem(form.reason, "the reason");
}

export const statusBody = (form: StatusForm) => ({ human_status: form.status, reason: form.reason.trim() });

export type LinkForm = { evidenceId: string; relation: Relation | ""; rationale: string };

export function linkProblem(form: LinkForm): string | null {
  if (!form.evidenceId) return "Choose the evidence from this investigation.";
  if (!form.relation) return "Say how it bears on the hypothesis.";
  return textProblem(form.rationale, "the rationale");
}

export const linkBody = (form: LinkForm) => ({
  evidence_id: form.evidenceId,
  relation: form.relation,
  rationale: form.rationale.trim(),
});

export const retractProblem = (reason: string) => textProblem(reason, "the reason");

// ---------------------------------------------------------------------------------------------------------------
// Contradictions (rendered defensively: the response's exact shape may grow)

export type ContradictionView = {
  key: string;
  hypothesis: string | null;
  hypothesisStatement: string | null;
  evidence: string | null;
  evidenceTitle: string | null;
  rationale: string | null;
  origin: unknown;
  /** The statement kind the server gives the contradiction, if any (else it reads as a derived observation). */
  kind: unknown;
  kindLabel: string | null;
  label: string;
  /** Whether a person judged the hypothesis since the contradiction was recorded; null when not said. */
  judgedSince: boolean | null;
  addedBy: string | null;
};

export function contradictionView(item: unknown, index = 0): ContradictionView {
  const row = isObject(item) ? item : {};
  const hypothesis = isObject(row.hypothesis) ? row.hypothesis : {};
  const evidence = isObject(row.evidence) ? row.evidence : {};
  const judged =
    row.judged_since ?? row.human_judged_since ?? row.reviewed_since ?? row.hypothesis_judged_since ?? null;
  return {
    key: String(row.id ?? row.link_id ?? index),
    hypothesis: safeText(hypothesis.business_id) ?? safeText(row.hypothesis_business_id),
    hypothesisStatement: safeText(hypothesis.statement) ?? safeText(row.hypothesis_statement),
    evidence: safeText(evidence.business_id) ?? safeText(row.evidence_business_id),
    evidenceTitle: safeText(evidence.title) ?? safeText(row.evidence_title),
    rationale: safeText(row.rationale),
    origin: row.origin ?? row.created_by_type ?? null,
    kind: row.epistemic_type ?? row.kind ?? "DERIVED_OBSERVATION",
    kindLabel: safeText(row.kind_label) ?? safeText(row.epistemic_label),
    label: safeText(row.label) ?? safeText(row.status_label) ?? "Contradicting evidence",
    judgedSince: typeof judged === "boolean" ? judged : null,
    addedBy: safeText(row.added_by) ?? safeText(row.created_by_name),
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Unknowns

export const UNKNOWN_STATUSES = ["open", "in_progress", "resolved", "accepted_limitation", "superseded"] as const;
export type UnknownStatus = (typeof UNKNOWN_STATUSES)[number];

export const UNKNOWN_STATUS: Record<UnknownStatus, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "warning" },
  in_progress: { label: "Being worked on", tone: "warning" },
  resolved: { label: "Resolved", tone: "good" },
  accepted_limitation: { label: "Accepted as a limitation", tone: "serious" },
  superseded: { label: "Superseded", tone: "neutral" },
};

export const unknownStatusOf = (value: unknown): UnknownStatus | null => {
  const status = String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
  return (UNKNOWN_STATUSES as readonly string[]).includes(status) ? (status as UnknownStatus) : null;
};

export const unknownStatusLabel = (status: unknown, label?: unknown) =>
  safeText(label) ??
  (unknownStatusOf(status) ? UNKNOWN_STATUS[unknownStatusOf(status)!].label : status ? titleCase(String(status)) : "—");

export const unknownStatusTone = (status: unknown): Tone => {
  const known = unknownStatusOf(status);
  return known ? UNKNOWN_STATUS[known].tone : "neutral";
};

export type UnknownTransition = { to: UnknownStatus; label: string; prompt: string };

const UNKNOWN_MOVES: Record<UnknownStatus, UnknownTransition[]> = {
  open: [
    { to: "in_progress", label: "Start work on it", prompt: "What is being done to resolve it?" },
    { to: "resolved", label: "Mark resolved", prompt: "What resolved it (evidence, test, finding)?" },
    {
      to: "accepted_limitation",
      label: "Accept as a limitation",
      prompt: "Why can the investigation go on without resolving it, and what does that limit?",
    },
    { to: "superseded", label: "Mark superseded", prompt: "What replaces it, and why?" },
  ],
  in_progress: [
    { to: "resolved", label: "Mark resolved", prompt: "What resolved it (evidence, test, finding)?" },
    {
      to: "accepted_limitation",
      label: "Accept as a limitation",
      prompt: "Why can the investigation go on without resolving it, and what does that limit?",
    },
    { to: "open", label: "Back to open", prompt: "Why is work on it paused?" },
    { to: "superseded", label: "Mark superseded", prompt: "What replaces it, and why?" },
  ],
  resolved: [{ to: "open", label: "Reopen", prompt: "Why is it unknown again?" }],
  accepted_limitation: [{ to: "open", label: "Reopen", prompt: "Why must it be resolved after all?" }],
  superseded: [],
};

/** The status changes offered for an unknown in a status (none for a superseded one). */
export const unknownTransitions = (status: unknown): UnknownTransition[] => {
  const known = unknownStatusOf(status);
  return known ? UNKNOWN_MOVES[known] : [];
};

/** Evidence can still be requested for an unknown that is open or being worked on. */
export const canRequestForUnknown = (status: unknown) => {
  const known = unknownStatusOf(status);
  return known === "open" || known === "in_progress";
};

export type IntelUnknown = {
  id: string;
  business_id?: string | null;
  description?: string | null;
  category?: string | null;
  evidence_needed?: string | null;
  status?: string | null;
  status_label?: string | null;
  origin?: string | null;
  origin_label?: string | null;
  hypothesis?: { id: string; business_id?: string | null; statement?: string | null } | null;
  requests?: Array<{
    id: string;
    business_id?: string | null;
    status?: string | null;
    status_label?: string | null;
  }> | null;
  resolution?: string | null;
  status_changed_by_name?: string | null;
  status_changed_at?: string | null;
  created_by_name?: string | null;
};

export type UnknownList = { items?: IntelUnknown[] | null; counts?: Record<string, number> | null };

export const NEW_UNKNOWN = { description: "", category: "", evidenceNeeded: "", hypothesisId: "" };
export type UnknownForm = typeof NEW_UNKNOWN;

export const UNKNOWN_CATEGORIES = [
  "TEST_DATA",
  "MANUFACTURING",
  "SUPPLIER",
  "DESIGN",
  "SOFTWARE",
  "USE_ENVIRONMENT",
  "CLINICAL",
  "OTHER",
] as const;

export function unknownProblem(form: UnknownForm): string | null {
  return (
    textProblem(form.description, "what is unknown") ??
    textProblem(form.evidenceNeeded, "the evidence needed", { min: 0, required: false })
  );
}

export function unknownBody(form: UnknownForm) {
  const evidenceNeeded = form.evidenceNeeded.trim();
  return {
    description: form.description.trim(),
    ...(form.category ? { category: form.category } : {}),
    ...(evidenceNeeded ? { evidence_needed: evidenceNeeded } : {}),
    ...(form.hypothesisId ? { hypothesis_id: form.hypothesisId } : {}),
  };
}

export const unknownStatusProblem = (reason: string) => textProblem(reason, "the reason");
export const unknownStatusBody = (to: UnknownStatus, reason: string) => ({ status: to, reason: reason.trim() });

/** How an unknown reads in the evidence request form's list: "UNK000031 · Seal hardness of lot KS-5521". */
export const unknownOptionLabel = (unknown: Pick<IntelUnknown, "business_id" | "description">) =>
  `${safeText(unknown.business_id) ?? "Unknown"} · ${safeText(unknown.description) ?? "No description"}`;

// ---------------------------------------------------------------------------------------------------------------
// Failure chains

export const LINK_STATES = ["SUPPORTED", "PARTIALLY_SUPPORTED", "HYPOTHESIZED", "UNKNOWN", "CONTRADICTED"] as const;
export type LinkState = (typeof LINK_STATES)[number];

/** How each link state is drawn and read. The line style carries the meaning as well as the colour. */
export const LINK_STATE: Record<LinkState, { label: string; line: string; tone: Tone; help: string }> = {
  SUPPORTED: { label: "Supported", line: "solid", tone: "good", help: "Solid line: evidence supports this link." },
  PARTIALLY_SUPPORTED: {
    label: "Partially supported",
    line: "partial",
    tone: "warning",
    help: "Part solid, part dashed: some evidence supports it; gaps remain.",
  },
  HYPOTHESIZED: {
    label: "Hypothesized",
    line: "dashed",
    tone: "neutral",
    help: "Dashed line: plausible, not supported by evidence yet.",
  },
  UNKNOWN: { label: "Unknown", line: "dotted", tone: "neutral", help: "Dotted line, open end: not known yet." },
  CONTRADICTED: {
    label: "Contradicted",
    line: "contradicted",
    tone: "critical",
    help: "Red line with a cross: evidence speaks against this link.",
  },
};

export const LINK_LEGEND = LINK_STATES.map((state) => ({ state, ...LINK_STATE[state] }));

/** A link state from a stored chain, or from an AI chain's epistemic status (mapped onto the same five). */
export function linkStateOf(value: unknown): LinkState {
  const state = code(value);
  if ((LINK_STATES as readonly string[]).includes(state)) return state as LinkState;
  if (state.includes("CONTRADICT") || state.includes("REFUTED")) return "CONTRADICTED";
  if (state.includes("PARTIAL") || state.includes("MIXED")) return "PARTIALLY_SUPPORTED";
  if (
    state.includes("UNSUPPORTED") ||
    state.includes("UNRESOLVED") ||
    state.includes("UNKNOWN") ||
    /(^|_)NOT_|(^|_)NO_/.test(state)
  )
    return "UNKNOWN";
  if (
    state.includes("SUPPORT") ||
    state.includes("ESTABLISHED") ||
    state.includes("OBSERVED") ||
    state.includes("DERIVED")
  )
    return "SUPPORTED";
  if (
    state.includes("HYPOTH") ||
    state.includes("INFERRED") ||
    state.includes("PLAUSIBLE") ||
    state.includes("CANDIDATE")
  )
    return "HYPOTHESIZED";
  return "UNKNOWN";
}

export const linkStateLabel = (state: unknown, label?: unknown) =>
  safeText(label) ?? LINK_STATE[linkStateOf(state)].label;

export type ChainNode = { id: string; sequence?: number | null; label?: string | null };
export type ChainLink = {
  id: string;
  from_node_id?: string | null;
  to_node_id?: string | null;
  from_label?: string | null;
  to_label?: string | null;
  state?: string | null;
  state_label?: string | null;
  evidence?: { id: string; business_id?: string | null; title?: string | null } | null;
  rationale?: string | null;
  updated_by_name?: string | null;
  updated_at?: string | null;
};
export type StoredChain = {
  id: string;
  business_id?: string | null;
  name?: string | null;
  origin?: string | null;
  status?: string | null;
  created_by_name?: string | null;
  source_ai_execution_id?: string | null;
  nodes?: ChainNode[] | null;
  links?: ChainLink[] | null;
};
export type AiChain = {
  chain_id?: string;
  id?: string;
  chain_statement?: string | null;
  overall_status?: string | null;
  links?: Array<{
    link_id?: string;
    from_entity_or_state?: string | null;
    relationship?: string | null;
    to_entity_or_state?: string | null;
    epistemic_status?: string | null;
    rationale?: string | null;
  }> | null;
};
export type FailureChains = {
  stored?: StoredChain[] | null;
  ai_latest?: { ai_execution_id?: string | null; chains?: AiChain[] | null } | null;
};

/** One step of a drawn chain: the link from the previous node (none for the first), then the node. */
export type ChainSegment = {
  key: string;
  linkId: string | null;
  state: LinkState;
  stateLabel: string;
  relationship: string | null;
  evidence: string | null;
  rationale: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
};
export type ChainLayout = {
  nodes: Array<{ key: string; label: string }>;
  /** segments[i] joins nodes[i] and nodes[i + 1]; a missing link reads Unknown. */
  segments: ChainSegment[];
  /** Links that do not join two neighbouring nodes (a branch or a jump), listed under the chain. */
  other: Array<ChainSegment & { from: string; to: string }>;
};

const segmentOf = (link: ChainLink, key: string): ChainSegment => ({
  key,
  linkId: link.id ?? null,
  state: linkStateOf(link.state),
  stateLabel: linkStateLabel(link.state, link.state_label),
  relationship: null,
  evidence: safeText(link.evidence?.business_id),
  rationale: safeText(link.rationale),
  updatedBy: safeText(link.updated_by_name),
  updatedAt: safeText(link.updated_at),
});

const missingSegment = (key: string): ChainSegment => ({
  key,
  linkId: null,
  state: "UNKNOWN",
  stateLabel: "No link recorded",
  relationship: null,
  evidence: null,
  rationale: null,
  updatedBy: null,
  updatedAt: null,
});

/** A stored chain laid out left to right: nodes in sequence order, each joined to the next by its link. */
export function chainLayout(chain: Pick<StoredChain, "nodes" | "links">): ChainLayout {
  const nodes = [...list<ChainNode>(chain.nodes)].sort((a, b) => (Number(a.sequence) || 0) - (Number(b.sequence) || 0));
  const links = list<ChainLink>(chain.links);
  if (!nodes.length && links.length) {
    // An older or partial response without nodes: draw the links in order by their labels.
    const labels: string[] = [];
    for (const link of links) {
      for (const label of [safeText(link.from_label) ?? "?", safeText(link.to_label) ?? "?"])
        if (labels[labels.length - 1] !== label) labels.push(label);
    }
    return {
      nodes: labels.map((label, index) => ({ key: `n${index}`, label })),
      segments: links.map((link, index) => segmentOf(link, `l${index}`)),
      other: [],
    };
  }
  const used = new Set<ChainLink>();
  const segments = nodes.slice(1).map((node, index) => {
    const previous = nodes[index];
    const link = links.find((item) => item.from_node_id === previous.id && item.to_node_id === node.id);
    if (!link) return missingSegment(`gap-${index}`);
    used.add(link);
    return segmentOf(link, link.id ?? `l${index}`);
  });
  const name = (id: unknown, fallback: unknown) =>
    safeText(nodes.find((node) => node.id === id)?.label) ?? safeText(fallback) ?? "?";
  const other = links
    .filter((link) => !used.has(link))
    .map((link, index) => ({
      ...segmentOf(link, link.id ?? `o${index}`),
      from: name(link.from_node_id, link.from_label),
      to: name(link.to_node_id, link.to_label),
    }));
  return {
    nodes: nodes.map((node, index) => ({ key: node.id ?? `n${index}`, label: safeText(node.label) ?? "Unnamed step" })),
    segments,
    other,
  };
}

/** An AI chain laid out the same way, from its links' from/to states and epistemic status. */
export function aiChainLayout(chain: AiChain): ChainLayout {
  const links = list(chain.links);
  const nodes: Array<{ key: string; label: string }> = [];
  const segments: ChainSegment[] = [];
  const other: ChainLayout["other"] = [];
  links.forEach((link, index) => {
    const from = safeText(link.from_entity_or_state) ?? "?";
    const to = safeText(link.to_entity_or_state) ?? "?";
    const segment: ChainSegment = {
      key: String(link.link_id ?? index),
      linkId: null,
      state: linkStateOf(link.epistemic_status),
      stateLabel: LINK_STATE[linkStateOf(link.epistemic_status)].label,
      relationship: safeText(link.relationship),
      evidence: null,
      rationale: safeText(link.rationale),
      updatedBy: null,
      updatedAt: null,
    };
    if (!nodes.length) nodes.push({ key: `a0`, label: from });
    if (nodes[nodes.length - 1].label === from) {
      nodes.push({ key: `a${nodes.length}`, label: to });
      segments.push(segment);
    } else other.push({ ...segment, from, to });
  });
  return { nodes, segments, other };
}

export const chainName = (chain: Pick<StoredChain, "business_id" | "name">) =>
  [safeText(chain.business_id), safeText(chain.name)].filter(Boolean).join(" · ") || "Failure chain";

export type ManualLink = {
  fromIndex: number;
  toIndex: number;
  state: LinkState;
  evidenceId: string;
  rationale: string;
};
export type ManualChainForm = { name: string; nodes: string[]; links: ManualLink[] };

/** A new hand-built chain: two steps joined by a hypothesized link. */
export const newManualChain = (): ManualChainForm => ({
  name: "",
  nodes: ["", ""],
  links: [{ fromIndex: 0, toIndex: 1, state: "HYPOTHESIZED", evidenceId: "", rationale: "" }],
});

/** Add a step at the end, joined to the previous one by a hypothesized link. */
export function withNode(form: ManualChainForm): ManualChainForm {
  const index = form.nodes.length;
  return {
    ...form,
    nodes: [...form.nodes, ""],
    links: [
      ...form.links,
      { fromIndex: index - 1, toIndex: index, state: "HYPOTHESIZED", evidenceId: "", rationale: "" },
    ],
  };
}

/** Remove a step and every link to or from it; later steps move up by one. Two steps always stay. */
export function withoutNode(form: ManualChainForm, index: number): ManualChainForm {
  if (form.nodes.length <= 2 || index < 0 || index >= form.nodes.length) return form;
  const shift = (value: number) => (value > index ? value - 1 : value);
  return {
    ...form,
    nodes: form.nodes.filter((_, position) => position !== index),
    links: form.links
      .filter((link) => link.fromIndex !== index && link.toIndex !== index)
      .map((link) => ({ ...link, fromIndex: shift(link.fromIndex), toIndex: shift(link.toIndex) })),
  };
}

/** A supported link must name the evidence that supports it. */
export const stateNeedsEvidence = (state: LinkState) => state === "SUPPORTED" || state === "PARTIALLY_SUPPORTED";

export function manualChainProblem(form: ManualChainForm): string | null {
  if (form.name.trim().length < 3) return "Name the chain (at least 3 characters).";
  if (form.name.trim().length > 200) return "Keep the chain's name to 200 characters.";
  if (form.nodes.length < 2) return "A chain needs at least two steps.";
  const empty = form.nodes.findIndex((node) => !node.trim());
  if (empty >= 0) return `Describe step ${empty + 1}.`;
  if (form.nodes.some((node) => node.trim().length > 255)) return "Keep each step to 255 characters.";
  if (!form.links.length) return "Join the steps with at least one link.";
  const seen = new Set<string>();
  for (const [position, link] of form.links.entries()) {
    const number = position + 1;
    const valid = (value: number) => Number.isInteger(value) && value >= 0 && value < form.nodes.length;
    if (!valid(link.fromIndex) || !valid(link.toIndex)) return `Link ${number} joins a step that does not exist.`;
    if (link.fromIndex === link.toIndex) return `Link ${number} must join two different steps.`;
    const pair = `${link.fromIndex}>${link.toIndex}`;
    if (seen.has(pair)) return `Link ${number} repeats another link.`;
    seen.add(pair);
    if (stateNeedsEvidence(link.state) && !link.evidenceId)
      return `Link ${number} is ${LINK_STATE[link.state].label.toLowerCase()}: choose the evidence behind it.`;
    const rationale = textProblem(link.rationale, `the rationale of link ${number}`, { min: 0, required: false });
    if (rationale) return rationale;
  }
  return null;
}

export function manualChainBody(form: ManualChainForm) {
  return {
    name: form.name.trim(),
    nodes: form.nodes.map((node) => node.trim()),
    links: form.links.map((link) => ({
      from_index: link.fromIndex,
      to_index: link.toIndex,
      state: link.state,
      ...(link.evidenceId ? { evidence_id: link.evidenceId } : {}),
      ...(link.rationale.trim() ? { rationale: link.rationale.trim() } : {}),
    })),
  };
}

export type LinkStateForm = { state: LinkState | ""; reason: string; evidenceId: string };

export function linkStateProblem(form: LinkStateForm, current?: unknown): string | null {
  if (!form.state) return "Choose the link's new state.";
  if (current && linkStateOf(current) === form.state && !form.evidenceId)
    return "Choose a different state, or add evidence.";
  if (stateNeedsEvidence(form.state) && !form.evidenceId)
    return `A ${LINK_STATE[form.state].label.toLowerCase()} link needs the evidence behind it.`;
  return textProblem(form.reason, "the reason");
}

export const linkStateBody = (form: LinkStateForm) => ({
  state: form.state,
  reason: form.reason.trim(),
  ...(form.evidenceId ? { evidence_id: form.evidenceId } : {}),
});

/** The AI chain's id inside its execution (chain_id, else id), for adopting it. */
export const aiChainId = (chain: AiChain) =>
  safeText(chain.chain_id) ?? safeText(chain.id) ?? String(chain.chain_id ?? chain.id ?? "");

// ---------------------------------------------------------------------------------------------------------------
// Observations

export const OBSERVATION_KINDS = ["FACT", "SOURCE_ASSERTION", "DERIVED_OBSERVATION"] as const;
export type ObservationKind = (typeof OBSERVATION_KINDS)[number];

export type Observation = {
  id: string;
  statement?: string | null;
  epistemic_type?: string | null;
  epistemic_label?: string | null;
  origin?: string | null;
  origin_label?: string | null;
  evidence?: { id: string; business_id?: string | null; title?: string | null } | null;
  created_by_name?: string | null;
  quality_status?: string | null;
  limitations?: unknown;
  created_at?: string | null;
  /** "AI proposal, not reviewed" while nobody accepted or edited the model's extraction, with its output id. */
  ai_label?: string | null;
  ai_execution_id?: string | null;
  /** Recorded with the sample: no model was called (W1). */
  recorded?: boolean | null;
};

export type ObservationFilter = { kind: string; origin: string };
export const EMPTY_OBSERVATION_FILTER: ObservationFilter = { kind: "", origin: "" };

/** Observations of one kind and/or from one origin (AI, HUMAN, SYSTEM); an empty filter keeps them all. */
export function filterObservations(items: Observation[] | null | undefined, filter: ObservationFilter): Observation[] {
  return (items ?? []).filter(
    (item) =>
      (!filter.kind ||
        code(item.epistemic_type) === filter.kind ||
        (filter.kind === "AI_INTERPRETATION" && code(item.origin) === "AI")) &&
      (!filter.origin || originGroup(item.origin) === filter.origin),
  );
}

/** HUMAN, AI or SYSTEM for any spelling of an origin (AI_ADOPTED is AI). */
export function originGroup(origin: unknown): "HUMAN" | "AI" | "SYSTEM" | "" {
  const value = code(origin);
  if (value === "AI" || value === "AI_ADOPTED" || value === "LANGUAGE_MODEL") return "AI";
  if (value === "SYSTEM" || value === "RULES") return "SYSTEM";
  if (value === "HUMAN" || value === "PERSON" || value === "USER" || value === "MANUAL") return "HUMAN";
  return "";
}

export const ORIGIN_FILTERS = [
  { key: "HUMAN", label: "Person" },
  { key: "AI", label: "AI" },
  { key: "SYSTEM", label: "MDARIX rules" },
] as const;

export type ObservationForm = { evidenceId: string; statement: string; kind: ObservationKind | ""; rationale: string };
export const NEW_OBSERVATION: ObservationForm = { evidenceId: "", statement: "", kind: "", rationale: "" };

export function observationProblem(form: ObservationForm): string | null {
  if (!form.evidenceId) return "Choose the evidence the observation is about.";
  if (!form.kind) return "Say what kind of statement it is.";
  return (
    textProblem(form.statement, "the observation", { min: 5 }) ??
    textProblem(form.rationale, "the rationale", { min: 0, required: false })
  );
}

export function observationBody(form: ObservationForm) {
  const rationale = form.rationale.trim();
  return {
    evidence_id: form.evidenceId,
    statement: form.statement.trim(),
    epistemic_type: form.kind,
    ...(rationale ? { rationale } : {}),
  };
}

/** An observation's limitations as text (the server may send a string, a list of strings or of objects). */
export function limitationsText(value: unknown): string | null {
  if (typeof value === "string") return safeText(value);
  const parts = list(value)
    .map((item) =>
      typeof item === "string" ? safeText(item) : isObject(item) ? safeText(item.description ?? item.text) : null,
    )
    .filter(Boolean);
  return parts.length ? parts.join("; ") : null;
}

// ---------------------------------------------------------------------------------------------------------------
// History

export type IntelligenceEvent = {
  id?: string;
  object_type?: string | null;
  object_business_id?: string | null;
  object_label?: string | null;
  event_type?: string | null;
  event_label?: string | null;
  from_value?: string | null;
  to_value?: string | null;
  reason?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  created_at?: string | null;
};

const OBJECT_NAMES: Record<string, string> = {
  HYPOTHESIS: "Hypothesis",
  HYPOTHESIS_EVIDENCE: "Hypothesis evidence",
  UNKNOWN: "Unknown",
  FAILURE_CHAIN: "Failure chain",
  FAILURE_CHAIN_LINK: "Failure chain link",
  OBSERVATION: "Observation",
};

/** One history line: "Hypothesis HYP000012: Hypothesized → Contradicted". Never a UUID. */
export function historyEventText(event: IntelligenceEvent): string {
  const object =
    safeText(event.object_label) ??
    OBJECT_NAMES[code(event.object_type)] ??
    (event.object_type ? titleCase(String(event.object_type)) : "Record");
  const id = safeText(event.object_business_id);
  const what = safeText(event.event_label) ?? (event.event_type ? titleCase(String(event.event_type)) : "Changed");
  const from = safeText(event.from_value);
  const to = safeText(event.to_value);
  const change = from && to ? `${titleCase(from)} → ${titleCase(to)}` : to ? titleCase(to) : null;
  return `${object}${id ? ` ${id}` : ""}: ${what}${change ? ` (${change})` : ""}`;
}

/** The events of a (paged) history response, whatever its envelope ({items}, {events} or a list). */
export const historyEvents = (payload: unknown): IntelligenceEvent[] =>
  Array.isArray(payload) ? payload : isObject(payload) ? list(payload.items ?? payload.events) : [];

// ---------------------------------------------------------------------------------------------------------------
// AI status (GET /api/v1/ai/status): what to say, and what to offer instead, when AI cannot run

export type AiStatus = {
  enabled?: boolean | null;
  available?: boolean | null;
  budget?: { used?: number | null; limit?: number | null; remaining?: number | null } | null;
  reason_code?: string | null;
  message?: string | null;
  manual_paths?: unknown;
  /** A free trial, whose AI is off. */
  trial?: boolean | null;
  /** A free trial whose AI services are set up: AI may run on the sample data once it is switched on. */
  sample_data_only?: boolean | null;
};

export type AiBanner = {
  reason: "AI_DISABLED" | "PROVIDER_UNAVAILABLE" | "BUDGET_EXHAUSTED";
  title: string;
  message: string;
  /** Why the AI run buttons are off, for their tooltip and description. */
  disabledReason: string;
  /** The same reason in a few words, shown next to each button that is off. */
  shortReason: string;
  /** Where the same work can be done by hand; `add` opens the view's form to add one at once (DEV-019). */
  manual: Array<{ view: IntelligenceView; label: string; add?: boolean }>;
};

const MANUAL_PATHS: AiBanner["manual"] = [
  { view: "Hypotheses", label: "Add hypotheses by hand", add: true },
  { view: "Unknowns", label: "Record unknowns" },
  { view: "Failure chain", label: "Build a failure chain" },
  { view: "Observations", label: "Record observations" },
];

const BANNER_TEXT: Record<
  AiBanner["reason"] | "TRIAL" | "TRIAL_BUSY" | "TRIAL_ORG_OFF" | "TRIAL_USER_OFF",
  { title: string; message: string; disabled: string; short: string }
> = {
  AI_DISABLED: {
    title: "AI is switched off for your organization",
    message: "An administrator can enable it under Security › AI processing.",
    disabled: "AI is switched off for your organization.",
    short: "AI is switched off for your organization",
  },
  PROVIDER_UNAVAILABLE: {
    title: "The AI service is not available right now",
    message: "Try again in a few minutes.",
    disabled: "The AI service is not available right now.",
    short: "The AI service is not available right now",
  },
  BUDGET_EXHAUSTED: {
    title: "Your organization's AI allowance is used up",
    message: "An administrator can raise the monthly allowance.",
    disabled: "Your organization's AI allowance is used up.",
    short: "Your AI allowance is used up",
  },
  // A trial without AI services: said plainly, without pointing at a setting nobody in the trial can change. Never
  // "off for free trials", which is wrong for a trial that has AI (review G-07).
  TRIAL: {
    title: "AI is not switched on for this trial",
    message: "Every step works by hand, and Ask MDARIX answers from your records.",
    disabled: "AI is not switched on for this trial.",
    short: "AI is not switched on for this trial",
  },
  // The trial's AI services are set up and switched on, but none answers right now.
  TRIAL_BUSY: {
    title: "AI is busy",
    message: "Try again in a minute. Every step works by hand meanwhile.",
    disabled: "AI is busy right now.",
    short: "AI is busy, try again in a minute",
  },
  // The trial's AI services are ready; the person who started the trial has not switched AI on yet.
  TRIAL_ORG_OFF: {
    title: "AI is not switched on for your organization yet",
    message:
      "The person who started this trial switches it on under Settings › AI on the sample data. Until then every step works by hand.",
    disabled: "AI is not switched on for your organization yet.",
    short: "AI is not switched on yet",
  },
  TRIAL_USER_OFF: {
    title: "AI is not switched on for your account",
    message: "The person who started this trial can switch it on for you. Every step works by hand meanwhile.",
    disabled: "AI is not switched on for your account.",
    short: "AI is not on for your account",
  },
};

/**
 * The banner to show when AI cannot run, or null when it can (or when the status is not known: then nothing changes
 * and the server still decides). The server's message wins over the built-in sentence.
 */
export function aiStatusBanner(status: AiStatus | null | undefined): AiBanner | null {
  if (!isObject(status)) return null;
  const reasonCode = code(status.reason_code);
  const remaining = status.budget?.remaining;
  const reason: AiBanner["reason"] | null =
    reasonCode === "AI_DISABLED" || status.enabled === false
      ? "AI_DISABLED"
      : reasonCode === "BUDGET_EXHAUSTED" || (typeof remaining === "number" && remaining <= 0)
        ? "BUDGET_EXHAUSTED"
        : reasonCode === "PROVIDER_UNAVAILABLE" || status.available === false
          ? "PROVIDER_UNAVAILABLE"
          : null;
  if (!reason) return null;
  const trial = status.trial === true && reason !== "BUDGET_EXHAUSTED";
  const text =
    BANNER_TEXT[
      !trial
        ? reason
        : reasonCode === "USER_AI_INACTIVE"
          ? "TRIAL_USER_OFF"
          : status.sample_data_only === true && reason === "AI_DISABLED"
            ? "TRIAL_ORG_OFF"
            : status.sample_data_only === true && reason === "PROVIDER_UNAVAILABLE"
              ? "TRIAL_BUSY"
              : "TRIAL"
    ];
  const server = trial ? null : safeText(status.message);
  const offered = list<string>(status.manual_paths)
    .map((path) => MANUAL_PATHS.find((item) => code(item.view) === code(path) || code(path).includes(code(item.view))))
    .filter((item): item is AiBanner["manual"][number] => Boolean(item));
  return {
    reason,
    title: text.title,
    message: server ?? text.message,
    disabledReason: server ? `${text.disabled} ${server}` : text.disabled,
    shortReason: text.short,
    manual: offered.length ? Array.from(new Set(offered)) : MANUAL_PATHS,
  };
}

/** The `epistemic` block an AI set response carries, or null. */
export function epistemicOf(payload: unknown): { note: string | null; humanReviewRequired: boolean } | null {
  if (!isObject(payload) || !isObject(payload.epistemic)) return null;
  return {
    note: safeText(payload.epistemic.note),
    humanReviewRequired: payload.epistemic.human_review_required !== false,
  };
}

/** Why rules produced an AI step's result instead of AI (`ai_notice` on the response), or null. */
export function aiNoticeOf(payload: unknown): { message: string; manual: string | null } | null {
  if (!isObject(payload) || !isObject(payload.ai_notice)) return null;
  const message = safeText(payload.ai_notice.message);
  return message ? { message, manual: safeText(payload.ai_notice.manual_alternative) } : null;
}

// ---------------------------------------------------------------------------------- At a glance (W1, flagship step 3)

/** One line of "At a glance": what it says and the record it comes from. */
export type GlanceItem = { label: string; sources: string[] };
/** One dated record for the time order. */
export type GlanceEvent = { date: string; label: string; source: string };
export type EvidenceStates = {
  known: GlanceItem[];
  unknown: GlanceItem[];
  contradicted: GlanceItem[];
  missing: GlanceItem[];
  timeline: GlanceEvent[];
};
type Row = Record<string, string | null | undefined>;

/** What the version column says of a complaint (PV-1): from the complaint, from its lot, or not known, with the
 * versions released by then listed as candidates and never filled in. */
export function versionWords(item: {
  version?: { version_identifier: string } | null;
  version_source?: string | null;
  candidate_versions?: { version_identifier: string }[] | null;
}): { version: string; source: string; candidates: string[] } {
  if (item.version)
    return {
      version: item.version.version_identifier,
      source: item.version_source === "LOT" ? "From the lot" : "From the complaint",
      candidates: [],
    };
  return {
    version: "Version not known (unverified)",
    source: "Neither the complaint nor its lot names a version",
    candidates: (item.candidate_versions ?? []).map((row) => row.version_identifier),
  };
}

const linksOf = (hypothesis: IntelHypothesis, relation: Lowercase<Relation>): EvidenceLink[] => {
  const evidence = hypothesis.evidence;
  const all = Array.isArray(evidence)
    ? evidence.filter((link) => String(link.relation ?? "").toLowerCase() === relation)
    : (evidence?.[relation] ?? []);
  return all.filter((link) => !link.retracted);
};
const refOf = (evidence: LinkedEvidence | null | undefined) =>
  safeText(evidence?.business_id) ?? safeText(evidence?.title);

/**
 * The case at a glance, from the records it already holds (pure): known (evidence a person linked in support), unknown
 * (open questions), contradicted (explanations with evidence against them, AI ones included), missing (failure-chain
 * links nobody has shown yet) and the time order of the dated records (changes, version releases, the complaints' lots,
 * the complaints and the evidence).
 */
export function evidenceStates(input: {
  hypotheses?: IntelHypothesis[] | null;
  unknowns?: IntelUnknown[] | null;
  chains?: StoredChain[] | null;
  versions?: Array<{ anchor_date?: string | null; lot?: { identifier?: string | null } | null }> | null;
  product?: {
    changes?: Row[] | null;
    versions?: Row[] | null;
    lots?: Row[] | null;
    evidence?: Row[] | null;
  } | null;
}): EvidenceStates {
  const hypotheses = input.hypotheses ?? [];
  const known = new Map<string, GlanceItem>();
  for (const hypothesis of hypotheses) {
    if (String(hypothesis.origin ?? "").toUpperCase() === "AI") continue;
    for (const link of linksOf(hypothesis, "supporting")) {
      const ref = refOf(link.evidence);
      if (ref && !known.has(ref)) known.set(ref, { label: safeText(link.evidence?.title) ?? ref, sources: [ref] });
    }
  }
  const unknown = (input.unknowns ?? [])
    .filter((row) => ["open", "in_progress"].includes(String(row.status ?? "open").toLowerCase()))
    .map((row) => ({
      label: safeText(row.description) ?? "An open question",
      sources: [safeText(row.business_id) ?? ""],
    }));
  const contradicted = hypotheses
    .map((hypothesis) => ({
      label: `${String(hypothesis.origin ?? "").toUpperCase() === "AI" ? "AI proposal: " : ""}${safeText(hypothesis.statement) ?? "A hypothesis"}`,
      sources: [...new Set(linksOf(hypothesis, "contradicting").map((link) => refOf(link.evidence) ?? ""))].filter(
        Boolean,
      ),
    }))
    .filter((item) => item.sources.length > 0);
  const missing = (input.chains ?? []).flatMap((chain) =>
    (chain.links ?? [])
      .filter((link) => linkStateOf(link.state) === "UNKNOWN")
      .map((link) => ({
        label: `${safeText(link.from_label) ?? "?"} → ${safeText(link.to_label) ?? "?"}`,
        sources: [chainName(chain)],
      })),
  );
  const timeline: GlanceEvent[] = [];
  const add = (date: string | null | undefined, label: string, source: string) => {
    if (date) timeline.push({ date, label, source });
  };
  const product = input.product ?? {};
  for (const change of product.changes ?? [])
    add(
      change.event_timestamp ?? change.effective_timestamp,
      safeText(change.description) ?? "A change",
      change.change_identifier ?? "Change",
    );
  for (const version of product.versions ?? [])
    add(version.release_timestamp, `${version.version_identifier} released`, version.version_identifier ?? "Version");
  const lots = new Set((input.versions ?? []).map((row) => row.lot?.identifier).filter(Boolean));
  for (const lot of product.lots ?? [])
    if (lots.has(lot.lot_identifier))
      add(lot.manufactured_timestamp, `Lot ${lot.lot_identifier} made`, `Lot ${lot.lot_identifier}`);
  const dates = (input.versions ?? [])
    .map((row) => row.anchor_date)
    .filter((day): day is string => !!day)
    .sort();
  if (dates.length) {
    add(dates[0], `First complaint in scope (${dates.length} in all)`, "Complaints");
    if (dates.length > 1) add(dates[dates.length - 1], "Latest complaint in scope", "Complaints");
  }
  const cited = new Set([...known.keys(), ...contradicted.flatMap((item) => item.sources)]);
  for (const row of product.evidence ?? []) {
    const ref = [row.business_id, row.evidence_identifier].find((value) => !!value && cited.has(value));
    if (ref) add(row.source_timestamp ?? row.created_at, safeText(row.title) ?? ref, ref);
  }
  timeline.sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
  return { known: [...known.values()], unknown, contradicted, missing, timeline };
}
