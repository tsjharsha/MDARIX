import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, FileText, Info, Search } from "lucide-react";
import { Inline, Markdown } from "../shared/Markdown";
import { useCan } from "../workspace/workspaceContext";
import { refusalOf, scopeLabel } from "./refusal";
import { StatementKind } from "../shared/StatementKind";
import { answerOriginText, hasStructuredContent, structuredOf } from "./structuredModel";
import { StructuredAnswerView } from "./StructuredAnswer";
import { TrustBadge } from "../workspace/sections/TrustBadge";
import { onQuestionHanded, pendingQuestion, takeQuestion } from "./pendingQuestion";

// Structured sections the service may return. Only sections with content are shown.
const SECTIONS: [string, string][] = [
  ["what_is_known", "What is known"],
  ["relevant_evidence", "Relevant evidence"],
  ["what_may_be_related", "What may be related"],
  ["contradictions", "Contradictions"],
  ["unknowns", "Unknowns"],
  ["missing_evidence", "Missing evidence"],
  ["suggested_next_questions", "Suggested next questions"],
  ["suggested_next_actions", "Suggested next actions"],
];

type Source = {
  evidence_identifier?: string;
  title?: string;
  source_reference?: string;
  temporal?: { effective_timestamp?: string };
  found_by?: "search" | "investigation";
  relevance?: number;
};

const asText = (item: unknown) => (typeof item === "string" ? item : JSON.stringify(item));
const listOf = (value: unknown): unknown[] => (Array.isArray(value) ? value.filter((item) => item != null) : []);
const formatDate = (value: unknown) => {
  const date = typeof value === "string" ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
    : null;
};

export function AskMdarixPage({
  investigationId,
  productVersionId,
}: {
  investigationId?: string;
  productVersionId?: string;
}) {
  // A question handed over by another screen (pendingQuestion.ts) fills the box once, ready to send; never sent here.
  const [handed] = useState(pendingQuestion);
  const [question, setQuestion] = useState(handed ?? "");
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const fill = (text: string) => {
      takeQuestion(text);
      setQuestion(text);
      const field = box.current;
      if (field) {
        field.focus();
        field.setSelectionRange(text.length, text.length);
      }
    };
    if (handed) fill(handed);
    return onQuestionHanded(fill);
  }, [handed]);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const canAsk = useCan("ai.run");
  const ask = async () => {
    if (!question.trim() || loading) return;
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const response = await fetch("/api/v1/stage3/interactions", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Correlation-ID": `UI-ASK-${Date.now()}` },
        body: JSON.stringify({
          prompt: question.trim(),
          investigation_id: investigationId || null,
          product_version_id: productVersionId || null,
          page_context: "ASK_MDARIX",
          temporal_mode: "CURRENT",
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail?.message || payload.detail || "Ask request failed");
      setResult(payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ask request failed");
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Ask MDARIX</p>
          <h2>Ask about the active case</h2>
          <p>
            Your question inherits the authenticated tenant, role, ProductVersion, investigation, and temporal Case
            Context.
          </p>
        </div>
        <div className="version-pill">Human review required</div>
      </section>
      <section className="panel">
        <label htmlFor="ask-question">Question</label>
        <textarea
          id="ask-question"
          ref={box}
          rows={5}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What is known, what changed, and what evidence is missing?"
        />
        {canAsk ? (
          <button className="primary-action" onClick={ask} disabled={!question.trim() || loading}>
            {loading ? "Searching your records…" : "Ask MDARIX"}
          </button>
        ) : (
          <p className="ask-hint" role="note">
            <Info size={14} aria-hidden="true" /> View only: your role cannot ask MDARIX questions.
          </p>
        )}
        {!investigationId && (
          <p className="ask-hint">
            <Info size={14} aria-hidden="true" /> No investigation is selected, so MDARIX searches all of your records.
            Choose one in the bar above to focus the answer on that case.
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </section>
      {result && <AskAnswer result={result} />}
    </div>
  );
}

function AskAnswer({ result }: { result: any }) {
  const response = result?.response ?? {};
  const answer: string | null = response.provider_output?.answer ?? null;
  const sources = listOf(response.sources_provenance) as Source[];
  const citations = new Set(sources.map((source) => source.evidence_identifier).filter(Boolean) as string[]);
  // Narrowed to one investigation (answers stored before investigation_scoped existed used the older flag).
  const grounded = (response.grounding?.investigation_scoped ?? response.grounding?.tenant_scope_enforced) === true;
  const searched = response.grounding?.searched_tenant_evidence === true;
  const unverified = listOf(response.answer_check?.unverified_citations).map(asText);
  const sections = SECTIONS.map(([key, title]) => [title, listOf(response[key])] as const).filter(
    ([, items]) => items.length > 0,
  );
  const notes = listOf(response.limitations).map(asText);
  // Why no model answered (AI switched off, allowance used up, ...), with what the user can do about it.
  const refusal = refusalOf(response);
  // The structured answer (Phase 4), shown section by section when the service sends one; else the answer as before.
  const structured = structuredOf(result);
  const showStructured = hasStructuredContent(structured);
  const madeBy = answerOriginText(structured);
  return (
    <section className="panel ask-answer" aria-labelledby="ask-answer-title">
      <header className="ask-answer-head">
        <h3 id="ask-answer-title">MDARIX answer</h3>
        <div className="ask-answer-badges">
          {grounded ? (
            <span className="ask-badge is-good">
              <CheckCircle2 size={14} aria-hidden="true" /> Based on this investigation&apos;s records
            </span>
          ) : searched ? (
            <span className="ask-badge is-good">
              <Search size={14} aria-hidden="true" /> Based on a search of your records
            </span>
          ) : (
            <span className="ask-badge is-warn">
              <AlertTriangle size={14} aria-hidden="true" /> No matching evidence found
            </span>
          )}
          <span className="ask-badge">Human review required</span>
          {structured?.aiUsed === false ? (
            <span className="ask-badge" data-ai-used="false">
              <Info size={14} aria-hidden="true" /> {madeBy}
            </span>
          ) : structured?.aiUsed === true ? (
            <StatementKind kind="AI_INTERPRETATION" origin="AI" />
          ) : null}
          {/* The automatic trust check of a model-written answer (sources, wording, provenance). */}
          {response.trust?.author === "AI" && <TrustBadge trust={response.trust} />}
        </div>
      </header>

      {showStructured ? (
        <>
          {structured.aiUsed === true && <p className="ask-note">{madeBy}.</p>}
          {structured.aiUsed !== true && refusal && (
            <p className="ask-note" role="note" data-refusal-code={refusal.code}>
              <Info size={14} aria-hidden="true" /> {refusal.message}
            </p>
          )}
          <StructuredAnswerView answer={structured} citations={citations} />
        </>
      ) : answer ? (
        <Markdown source={answer} citations={citations} />
      ) : refusal ? (
        <p className="ask-unavailable" role="status" data-refusal-code={refusal.code}>
          <AlertTriangle size={16} aria-hidden="true" /> {refusal.message}
        </p>
      ) : (
        <p className="ask-unavailable">
          <AlertTriangle size={16} aria-hidden="true" /> The AI answer is not available right now.{" "}
          {notes[0] ?? "Please try again in a moment."}
        </p>
      )}

      {unverified.length > 0 && (
        <p className="ask-unavailable" role="note">
          <AlertTriangle size={16} aria-hidden="true" /> The answer mentions {unverified.join(", ")}, which MDARIX did
          not give it. Treat that part with caution.
        </p>
      )}

      {!showStructured &&
        sections.map(([title, items]) => (
          <div className="ask-section" key={title}>
            <h4>{title}</h4>
            <ul>
              {items.map((item, index) => (
                <li key={index}>
                  <Inline text={asText(item)} citations={citations} />
                </li>
              ))}
            </ul>
          </div>
        ))}

      {!showStructured && sources.length > 0 && (
        <div className="ask-section">
          <h4>Sources used ({sources.length})</h4>
          <ul className="ask-sources">
            {sources.map((source, index) => (
              <li key={source.evidence_identifier ?? index}>
                <FileText size={15} aria-hidden="true" />
                <div>
                  <span className="md-cite is-known">{source.evidence_identifier ?? "Evidence"}</span>{" "}
                  <strong>{source.title ?? "Untitled evidence"}</strong>
                  <small>
                    {[
                      source.found_by === "search" ? "Found by search" : null,
                      source.source_reference,
                      formatDate(source.temporal?.effective_timestamp),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                  {typeof source.relevance === "number" && (
                    <span
                      className="ask-relevance"
                      role="img"
                      aria-label={`Relevance ${Math.round(Math.max(0, Math.min(1, source.relevance)) * 100)}%`}
                    >
                      <span style={{ width: `${Math.max(0, Math.min(1, source.relevance)) * 100}%` }} />
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(answer || showStructured) && notes.length > 0 && (
        <p className="ask-note">
          <Info size={14} aria-hidden="true" /> {notes.join(" ")} AI suggestions are advisory; a person decides.
        </p>
      )}

      <details className="ask-details">
        <summary>Technical details</summary>
        <dl>
          <dt>Interaction</dt>
          <dd>{result.interaction_id ?? "—"}</dd>
          <dt>Context policy</dt>
          <dd>{response.grounding?.policy_version ?? "—"}</dd>
          <dt>Scoped to investigation</dt>
          <dd>{scopeLabel(grounded)}</dd>
          <dt>Field policy</dt>
          <dd>{response.grounding?.field_policy ?? "—"}</dd>
        </dl>
      </details>
    </section>
  );
}
