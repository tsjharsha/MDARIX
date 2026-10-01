// Visual, low-text views of the AI analysis: summary cards, evidence chips and for/against bars.
// Every status keeps a text label next to its colour, so nothing is conveyed by colour alone.
import { AlertTriangle, Bot, CheckCircle2, CircleHelp, FileText, ListChecks, Scale, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { humanize } from "../../app/format";
import type {
  ChallengeSet,
  HypothesisSet,
  InvestigationAnalysis,
  InvestigationBrief,
  UnknownSet,
} from "../../app/types";
import "./analysis-visuals.css";

type Ref = { evidence_identifier?: string | null };
type Item = { item_id?: string; statement: string; source_references?: unknown[] };

// Plain-language status labels; the raw code stays in the title for reviewers.
const STATUS_LABELS: Record<string, string> = {
  COMPLETED: "Complete",
  COMPLETED_WITH_LIMITATIONS: "Complete, with limits noted",
  ABSTAINED_INSUFFICIENT_EVIDENCE: "No conclusion: evidence is not enough",
  FAILED_VALIDATION: "Needs review: a check failed",
  MIXED_EVIDENCE: "Evidence points both ways",
  UNDER_INVESTIGATION: "Under investigation",
  NO_CURRENTLY_SUPPORTABLE_HYPOTHESIS: "Not supported yet",
  NOT_REVIEWED: "Not reviewed yet",
};

export function StatusPill({ status }: { status?: string | null }) {
  if (!status) return null;
  return (
    <span className="av-status" title={status}>
      {STATUS_LABELS[status] ?? humanize(status)}
    </span>
  );
}

const evidenceIds = (refs: unknown[] | undefined): string[] =>
  Array.from(
    new Set(
      (refs ?? [])
        .map((ref) => (ref as Ref)?.evidence_identifier)
        .filter((id): id is string => typeof id === "string" && id.length > 0),
    ),
  );

export function EvidenceChips({ ids, tone = "neutral" }: { ids: string[]; tone?: "neutral" | "for" | "against" }) {
  if (!ids.length) return null;
  return (
    <span className="av-chips" aria-label={`Evidence: ${ids.join(", ")}`}>
      {ids.map((id) => (
        <span key={id} className={`av-chip av-chip-${tone}`}>
          <FileText size={11} aria-hidden="true" />
          {id}
        </span>
      ))}
    </span>
  );
}

// Why the rules wrote a result instead of the AI, in plain words. Not configured is the normal rules-only setup.
const FALLBACK_REASONS: Record<string, string> = {
  MODEL_CALL_FAILED: "the AI service was busy or unreachable",
  MODEL_EMPTY_RESPONSE: "the AI reply was empty",
  MODEL_INVALID_JSON: "the AI reply was unusable",
  MODEL_OUTPUT_FAILED_CHECKS: "the AI output did not pass the checks",
  ANALYSIS_NOT_MODEL_WRITTEN: "it builds on a rules-written analysis",
  HYPOTHESES_NOT_MODEL_WRITTEN: "it builds on rules-written hypotheses",
  ANALYSIS_FOR_ANOTHER_TIME: "run the analysis for this date first",
  NO_EVIDENCE: "the investigation has no evidence yet",
  NO_CITED_EVIDENCE: "the analysis cites no evidence",
};

export function AuthorBadge({ author, reason }: { author?: string | null; reason?: string | null }) {
  if (author === "LANGUAGE_MODEL") {
    return (
      <span className="av-author av-author-ai">
        <Bot size={14} aria-hidden="true" /> Written by AI · checked by MDARIX rules
      </span>
    );
  }
  return (
    <span
      className="av-author"
      title={reason && reason !== "MODEL_NOT_CONFIGURED" ? `Reason code: ${reason}` : undefined}
    >
      <ListChecks size={14} aria-hidden="true" /> Written by MDARIX rules
      {reason && reason !== "MODEL_NOT_CONFIGURED"
        ? ` (AI not used: ${FALLBACK_REASONS[reason] ?? humanize(reason).toLowerCase()})`
        : ""}
    </span>
  );
}

function Tile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`av-tile av-tone-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function StatementCard({
  title,
  icon,
  items,
  tone,
  empty,
}: {
  title: string;
  icon: ReactNode;
  items: Item[];
  tone: string;
  empty: string;
}) {
  return (
    <section className={`av-card av-tone-${tone}`}>
      <h4>
        {icon}
        {title} <span className="av-count">{items.length}</span>
      </h4>
      {items.length === 0 ? (
        <p className="av-empty">{empty}</p>
      ) : (
        <ul className="av-statements">
          {items.map((item, index) => (
            <li key={item.item_id ?? index}>
              <span>{item.statement}</span>
              <EvidenceChips ids={evidenceIds(item.source_references)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function AnalysisVisual({ analysis }: { analysis: InvestigationAnalysis }) {
  const provenance = analysis.model_provenance as Record<string, any>;
  const dropped = Number(analysis.validation_summary?.model_statements_dropped_by_checks ?? 0);
  const gaps = analysis.missing_information;
  return (
    <div className="av-stack">
      <section className="av-summary">
        <div className="av-summary-head">
          <AuthorBadge author={analysis.analysis_author} reason={provenance?.fallback_reason} />
          <StatusPill status={analysis.status} />
        </div>
        <p className="av-headline">
          {analysis.summary ?? "Review the evidence below. MDARIX does not decide the cause; a person does."}
        </p>
        <div className="av-tiles">
          <Tile label="Observations" value={analysis.observations.length} tone="info" />
          <Tile label="Contradictions" value={analysis.contradictions.length} tone="against" />
          <Tile label="Gaps" value={gaps.length} tone="warn" />
          <Tile label="Questions" value={analysis.questions_to_investigate.length} tone="neutral" />
        </div>
        {dropped > 0 && (
          <p className="av-note">
            <ShieldCheck size={14} aria-hidden="true" /> {dropped} AI statement{dropped === 1 ? "" : "s"} removed by the
            checks (uncited, unknown evidence, or a causal claim).
          </p>
        )}
      </section>
      <div className="av-grid">
        <StatementCard
          title="What the evidence shows"
          icon={<FileText size={16} aria-hidden="true" />}
          items={analysis.observations.slice(0, 8)}
          tone="info"
          empty="No observations for this context."
        />
        <StatementCard
          title="Contradictions"
          icon={<Scale size={16} aria-hidden="true" />}
          items={analysis.contradictions.slice(0, 4)}
          tone="against"
          empty="No contradictions found in this evidence."
        />
        <StatementCard
          title="Possible explanations"
          icon={<CircleHelp size={16} aria-hidden="true" />}
          items={analysis.possible_explanations.slice(0, 4)}
          tone="neutral"
          empty="No explanation is supported yet."
        />
        <StatementCard
          title="What is missing"
          icon={<AlertTriangle size={16} aria-hidden="true" />}
          items={gaps.slice(0, 6)}
          tone="warn"
          empty="No gaps recorded."
        />
        <StatementCard
          title="Questions to investigate"
          icon={<ListChecks size={16} aria-hidden="true" />}
          items={analysis.questions_to_investigate.slice(0, 5)}
          tone="neutral"
          empty="No open questions."
        />
      </div>
    </div>
  );
}

export function ForAgainstBar({ support, against }: { support: number; against: number }) {
  const total = Math.max(support + against, 1);
  return (
    <div className="av-balance" role="img" aria-label={`${support} supporting, ${against} contradicting evidence`}>
      <div className="av-balance-track">
        {support > 0 && <span className="av-balance-for" style={{ width: `${(support / total) * 100}%` }} />}
        {against > 0 && <span className="av-balance-against" style={{ width: `${(against / total) * 100}%` }} />}
      </div>
      <div className="av-balance-legend">
        <span>
          <CheckCircle2 size={12} aria-hidden="true" /> {support} for
        </span>
        <span>
          <AlertTriangle size={12} aria-hidden="true" /> {against} against
        </span>
      </div>
    </div>
  );
}

export function HypothesisBoard({ set }: { set: HypothesisSet }) {
  const provenance = (set as any).provenance ?? {};
  return (
    <div className="av-stack">
      <div className="av-summary-head">
        <AuthorBadge author={provenance.author} reason={provenance.fallback_reason} />
        <span className="av-status">No winner is chosen · a person decides</span>
      </div>
      {set.hypotheses.length === 0 && (
        <p className="av-empty">No supportable hypothesis yet. That is a careful result, not a negative finding.</p>
      )}
      <div className="av-grid">
        {set.hypotheses.map((hypothesis) => {
          const support = hypothesis.supporting_evidence.flatMap((rel) => evidenceIds(rel.source_references));
          const against = hypothesis.contradicting_evidence.flatMap((rel) => evidenceIds(rel.source_references));
          return (
            <article className="av-card av-hypothesis" key={hypothesis.hypothesis_id}>
              <StatusPill status={hypothesis.status} />
              <h4>{hypothesis.statement.replace(/^Hypothesis:\s*/i, "")}</h4>
              <ForAgainstBar support={support.length} against={against.length} />
              <div className="av-evidence-row">
                <EvidenceChips ids={support} tone="for" />
                <EvidenceChips ids={against} tone="against" />
              </div>
              {hypothesis.falsification_conditions.length > 0 && (
                <details>
                  <summary>How to rule it out ({hypothesis.falsification_conditions.length})</summary>
                  <ul>
                    {hypothesis.falsification_conditions.slice(0, 4).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </details>
              )}
              {hypothesis.contradicting_evidence[0] && (
                <p className="av-against-note">
                  <AlertTriangle size={13} aria-hidden="true" /> {hypothesis.contradicting_evidence[0].rationale}
                </p>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

const SEVERITY_TONE: Record<string, string> = { HIGH: "against", CRITICAL: "against", MEDIUM: "warn", LOW: "neutral" };

export function ChallengeBoard({ set }: { set: ChallengeSet }) {
  const provenance = (set as any).provenance ?? {};
  const challenges = [...set.challenges].sort(
    (a: any, b: any) => ["HIGH", "MEDIUM", "LOW"].indexOf(a.severity) - ["HIGH", "MEDIUM", "LOW"].indexOf(b.severity),
  );
  return (
    <div className="av-stack">
      <div className="av-summary-head">
        <AuthorBadge author={provenance.author} reason={provenance.fallback_reason} />
      </div>
      {challenges.length === 0 && <p className="av-empty">No material challenge identified.</p>}
      <ul className="av-challenges">
        {challenges.map((item: any) => (
          <li key={item.challenge_id} className={`av-tone-${SEVERITY_TONE[item.severity] ?? "neutral"}`}>
            <span className="av-severity">{humanize(item.severity ?? "MEDIUM")}</span>
            <div>
              <strong>{item.statement}</strong>
              <small>{humanize(item.challenge_type)}</small>
              <EvidenceChips ids={evidenceIds(item.evidence_references)} />
              {item.missing_information?.length > 0 && (
                <p className="av-missing">To resolve: {item.missing_information.slice(0, 2).join("; ")}</p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function UnknownsBoard({ set }: { set: UnknownSet }) {
  const material = set.unknowns.filter((item) => item.materiality === "MATERIAL");
  const counts = set.unknowns.reduce<Record<string, number>>((acc, item) => {
    acc[item.category] = (acc[item.category] ?? 0) + 1;
    return acc;
  }, {});
  const shown = [...material, ...set.unknowns.filter((item) => item.materiality !== "MATERIAL")];
  return (
    <div className="av-stack">
      <div className="av-tiles">
        <Tile label="Unknowns" value={set.unknowns.length} tone="warn" />
        <Tile label="Material" value={material.length} tone="against" />
        {Object.entries(counts)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 2)
          .map(([category, count]) => (
            <Tile key={category} label={humanize(category)} value={count} tone="neutral" />
          ))}
      </div>
      {set.unknowns.length === 0 && <p className="av-empty">No material unknowns identified.</p>}
      <ul className="av-challenges">
        {shown.slice(0, 8).map((item) => (
          <UnknownRow key={item.unknown_id} item={item} />
        ))}
      </ul>
      {shown.length > 8 && (
        <details className="av-raw">
          <summary>Show {shown.length - 8} more</summary>
          <ul className="av-challenges">
            {shown.slice(8).map((item) => (
              <UnknownRow key={item.unknown_id} item={item} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function UnknownRow({ item }: { item: UnknownSet["unknowns"][number] }) {
  const material = item.materiality === "MATERIAL";
  return (
    <li className={`av-tone-${material ? "warn" : "neutral"}`}>
      <span className="av-severity">{material ? "Material" : "Minor"}</span>
      <div>
        <strong>{item.statement}</strong>
        <small>{humanize(item.category)}</small>
        <details>
          <summary>Why it matters and how to resolve it</summary>
          <p className="av-missing">{item.why_it_matters}</p>
          <p className="av-missing">{item.resolution_requirement}</p>
        </details>
      </div>
    </li>
  );
}

const BRIEF_SECTIONS: [string, string, string][] = [
  ["what_we_know", "What we know", "info"],
  ["what_conflicts", "What conflicts", "against"],
  ["what_is_missing", "What is missing", "warn"],
  ["leading_hypotheses", "Leading hypotheses", "neutral"],
  ["next_steps", "Next steps", "neutral"],
];

export function BriefVisual({ brief }: { brief: InvestigationBrief }) {
  const content = brief.content ?? {};
  const ai = content.ai_brief ?? {};
  const sections = ai.sections ?? {};
  const known: string[] = (content.executive_summary?.observed_facts ?? []).filter(Boolean);
  return (
    <div className="av-stack">
      <section className="av-summary">
        <div className="av-summary-head">
          <AuthorBadge author={ai.author} reason={ai.fallback_reason} />
          <span className="av-status">
            Version {brief.brief_version} ·{" "}
            {STATUS_LABELS[brief.human_review_state] ?? humanize(brief.human_review_state)}
          </span>
        </div>
        <p className="av-headline">{ai.headline ?? content.executive_summary?.text}</p>
      </section>
      {ai.author === "LANGUAGE_MODEL" ? (
        <div className="av-grid">
          {BRIEF_SECTIONS.map(([key, title, tone]) => (
            <section key={key} className={`av-card av-tone-${tone}`}>
              <h4>
                {title} <span className="av-count">{(sections[key] ?? []).length}</span>
              </h4>
              <ul className="av-statements">
                {(sections[key] ?? []).map((item: { statement: string; evidence: string[] }, index: number) => (
                  <li key={index}>
                    <span>{item.statement}</span>
                    <EvidenceChips ids={item.evidence ?? []} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        known.length > 0 && (
          <section className="av-card av-tone-info">
            <h4>What we know</h4>
            <ul className="av-statements">
              {known.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </section>
        )
      )}
      <p className="av-note">
        <ShieldCheck size={14} aria-hidden="true" /> This brief does not establish root cause or causality. A person
        reviews and decides.
      </p>
      <details className="av-raw">
        <summary>Full brief data and provenance</summary>
        <pre>{JSON.stringify({ content, provenance: brief.provenance }, null, 2)}</pre>
      </details>
    </div>
  );
}
