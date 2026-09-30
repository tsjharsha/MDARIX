export type Product = {
  id: string;
  product_identifier: string;
  name: string;
  product_family: string | null;
  lifecycle_status: string;
  available_versions: string[];
};

export type InvestigationSummary = Record<string, string | null>;

export type TemporalMode = "current" | "event" | "known";

export type TimelineEvent = {
  event_id: string;
  event_type: string;
  category: string;
  title: string;
  event_time?: string;
  effective_time?: string;
  recorded_time?: string;
  knowledge_available_time?: string;
  description?: string;
  related_entity_type?: string;
  related_entity_id?: string;
  source?: string;
  metadata?: Record<string, unknown>;
  quality_status?: string;
  late_arriving: boolean;
};

export type Product360 = {
  product: Record<string, string | null>;
  selected_version: Record<string, string | null> | null;
  versions: Array<Record<string, string | null>>;
  overview: Record<string, number | boolean>;
  configuration: { components: Array<Record<string, string | null>>; suppliers: Array<Record<string, string | null>> };
  changes: Array<Record<string, string | null>>;
  manufacturing: { lots: Array<Record<string, string | null>>; sites: Array<Record<string, string | null>> };
  complaints: Array<Record<string, string | null>>;
  investigations: Array<Record<string, string | null>>;
  risks: Array<Record<string, string | null>>;
  failure_modes: Array<Record<string, string | null>>;
  controls: Array<Record<string, string | null>>;
  evidence: Array<Record<string, string | null>>;
  limitations: Array<{ code: string; severity: string; description: string }>;
  provenance: Array<Record<string, string | null>>;
  timeline: TimelineEvent[];
  temporal_context: Record<string, string | boolean | null>;
};

export type WorkspaceEvidence = {
  evidence_identifier: string;
  evidence_type: string;
  title: string;
  reliability_status: string;
  chunks: Array<{ source_anchor: Record<string, unknown>; excerpt: string; materialized: boolean }>;
  observations: Array<{ statement: string; quality_status: string; source_anchor: Record<string, unknown> }>;
  entity_links: Array<{ entity_type: string; resolution_status: string; source: string }>;
};

export type InvestigationWorkspace = {
  investigation: Record<string, string | null>;
  product_context: Record<string, unknown>;
  temporal_context: Record<string, string | boolean | number | null>;
  relationship_context: { nodes: unknown[]; relationships: unknown[]; metadata: Record<string, unknown> };
  evidence_context: WorkspaceEvidence[];
  retrieval_context: { status: string; results_count: number; limitations: string[] } | null;
  limitations: Array<{ code: string; severity: string; description: string }>;
  guardrails: Record<string, string | boolean>;
  metadata: Record<string, string | boolean>;
};

export type AnalysisItem = {
  item_id: string;
  semantic_type: string;
  statement: string;
  rationale?: string;
  grounding_status: string;
  source_references: unknown[];
};

export type InvestigationAnalysis = {
  analysis_id: string;
  status: string;
  observations: AnalysisItem[];
  temporal_patterns: AnalysisItem[];
  evidence_relationships: AnalysisItem[];
  possible_explanations: AnalysisItem[];
  contradictions: AnalysisItem[];
  missing_information: AnalysisItem[];
  questions_to_investigate: AnalysisItem[];
  limitations: AnalysisItem[];
  validation_summary: Record<string, number | string>;
  model_provenance: Record<string, string | boolean>;
};

export type InvestigationBrief = {
  id: string;
  investigation_id: string;
  brief_version: number;
  status: string;
  title: string;
  temporal_mode: string;
  temporal_cutoff?: string | null;
  human_review_state: string;
  content: Record<string, any>;
  provenance: Record<string, any>;
};

export type Hypothesis = {
  hypothesis_id: string;
  statement: string;
  scope: string;
  status: string;
  supporting_evidence: Array<{ relationship_type: string; rationale: string; source_references: unknown[] }>;
  contradicting_evidence: Array<{ relationship_type: string; rationale: string; source_references: unknown[] }>;
  contextual_evidence: Array<{ relationship_type: string; rationale: string; source_references: unknown[] }>;
  assumptions: string[];
  evidence_gaps: string[];
  falsification_conditions: string[];
  temporal_consistency: Record<string, string>;
};

export type HypothesisSet = {
  hypothesis_set_id: string;
  status: string;
  hypotheses: Hypothesis[];
  comparison: Array<Record<string, string | number | boolean>>;
  validation_summary: Record<string, number | string>;
  guardrails: Record<string, boolean>;
};

export type UnknownSet = {
  unknowns: Array<{
    unknown_id: string;
    category: string;
    statement: string;
    why_it_matters: string;
    resolution_requirement: string;
    status: string;
    materiality: string;
    provenance: Record<string, unknown>;
  }>;
};

export type FailureChainSet = {
  chains: Array<{
    chain_id: string;
    chain_statement: string;
    overall_status: string;
    links: Array<{
      link_id: string;
      from_entity_or_state: string;
      relationship: string;
      to_entity_or_state: string;
      epistemic_status: string;
      unknowns: string[];
    }>;
  }>;
};

export type ChallengeSet = {
  challenges: Array<{
    challenge_id: string;
    challenge_type: string;
    statement: string;
    rationale: string;
    materiality: string;
    status: string;
  }>;
};

export type EvidenceSummary = {
  id: string;
  evidence_identifier: string;
  evidence_type: string;
  title: string;
  source_system?: string | null;
  reliability_status?: string | null;
  fact_type?: string | null;
  document_ref?: string | null;
};

export type DecisionContext = {
  investigation: Record<string, string | null>;
  product_context: Record<string, any>;
  temporal_context: Record<string, any>;
  evidence: Array<Record<string, any>>;
  observations: Array<Record<string, any>>;
  contradictions: Array<Record<string, any>>;
  hypotheses: Array<Record<string, any>>;
  challenges: Array<Record<string, any>>;
  unknowns: Array<Record<string, any>>;
  failure_chains: Array<Record<string, any>>;
  limitations: Array<Record<string, any>>;
  readiness: { state: string; reasons: string[] };
  decision_options: string[];
};

export type AdminTenant = { id: string; tenant_key: string; name: string; status: string; created_at?: string | null };
