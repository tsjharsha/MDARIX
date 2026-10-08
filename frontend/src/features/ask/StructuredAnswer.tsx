import { FileText, Info } from "lucide-react";
import { Inline } from "../shared/Markdown";
import { StatementKind } from "../shared/StatementKind";
import { STRUCTURED_SECTIONS, type StructuredAnswer } from "./structuredModel";

function SourceIds({ ids, citations }: { ids: string[]; citations: Set<string> }) {
  if (!ids.length) return null;
  return (
    <span className="ask-source-ids" aria-label={`Sources: ${ids.join(", ")}`}>
      {ids.map((id) => (
        <span key={id} className={`md-cite${citations.has(id) ? " is-known" : ""}`}>
          {id}
        </span>
      ))}
    </span>
  );
}

/**
 * The structured Ask answer, section by section. Known facts carry their own kind; the other statements carry the
 * answer's kind: an AI interpretation when AI wrote it, a derived observation by MDARIX rules when it did not.
 */
export function StructuredAnswerView({ answer, citations }: { answer: StructuredAnswer; citations: Set<string> }) {
  const derived = answer.aiUsed === false;
  const kind = derived ? "DERIVED_OBSERVATION" : "AI_INTERPRETATION";
  const origin = derived ? "SYSTEM" : "AI";
  const all = new Set([...citations, ...answer.sources.map((source) => source.businessId ?? "").filter(Boolean)]);
  const heading = (title: string, badge = true) => (
    <h4>
      {title} {badge && <StatementKind kind={kind} origin={origin} />}
    </h4>
  );
  return (
    <div className="ask-structured">
      {answer.summary && (
        <div className="ask-section">
          {heading(STRUCTURED_SECTIONS.summary)}
          <p>
            <Inline text={answer.summary} citations={all} />
          </p>
        </div>
      )}
      {answer.knownFacts.length > 0 && (
        <div className="ask-section">
          {heading(STRUCTURED_SECTIONS.knownFacts, false)}
          <ul className="ask-statements">
            {answer.knownFacts.map((fact, index) => (
              <li key={index}>
                <StatementKind kind={fact.kind} origin={fact.origin ?? origin} />{" "}
                <Inline text={fact.statement} citations={all} /> <SourceIds ids={fact.sources} citations={all} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {(
        [
          [STRUCTURED_SECTIONS.supporting, answer.supporting],
          [STRUCTURED_SECTIONS.contradicting, answer.contradicting],
        ] as const
      )
        .filter(([, rows]) => rows.length > 0)
        .map(([title, rows]) => (
          <div className="ask-section" key={title}>
            {heading(title)}
            <ul>
              {rows.map((row, index) => (
                <li key={index}>
                  <Inline text={row.statement} citations={all} /> <SourceIds ids={row.sources} citations={all} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      {answer.unknowns.length > 0 && (
        <div className="ask-section">
          {heading(STRUCTURED_SECTIONS.unknowns)}
          <ul>
            {answer.unknowns.map((row, index) => (
              <li key={index}>
                {row.businessId && <strong>{row.businessId} </strong>}
                <Inline text={row.statement} citations={all} />
                {row.status && <small className="ac-muted"> · {row.status.replace(/_/g, " ")}</small>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.missing.length > 0 && (
        <div className="ask-section">
          {heading(STRUCTURED_SECTIONS.missing)}
          <ul>
            {answer.missing.map((row, index) => (
              <li key={index}>
                <Inline text={row.statement} citations={all} />{" "}
                <small className="ac-muted">
                  {row.requestBusinessId ? `Requested in ${row.requestBusinessId}` : "Not requested yet"}
                </small>
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.limitations.length > 0 && (
        <div className="ask-section">
          <h4>{STRUCTURED_SECTIONS.limitations}</h4>
          <ul>
            {answer.limitations.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {answer.nextSteps.length > 0 && (
        <div className="ask-section">
          {heading(STRUCTURED_SECTIONS.nextSteps)}
          <ol>
            {answer.nextSteps.map((item, index) => (
              <li key={index}>
                <Inline text={item} citations={all} />
              </li>
            ))}
          </ol>
        </div>
      )}
      {answer.sources.length > 0 && (
        <div className="ask-section">
          <h4>
            {STRUCTURED_SECTIONS.sources} ({answer.sources.length})
          </h4>
          <ul className="ask-sources">
            {answer.sources.map((source, index) => (
              <li key={source.businessId ?? index}>
                <FileText size={15} aria-hidden="true" />
                <div>
                  <span className="md-cite is-known">{source.businessId ?? "Record"}</span>{" "}
                  <strong>{source.title ?? "Untitled record"}</strong>
                  {source.kind && <small>{source.kind.replace(/_/g, " ").toLowerCase()}</small>}
                  {source.relevance !== null && (
                    <span
                      className="ask-relevance"
                      role="img"
                      aria-label={`Relevance ${Math.round(source.relevance * 100)}%`}
                    >
                      <span style={{ width: `${source.relevance * 100}%` }} />
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {answer.aiNote && (
        <p className="ask-note">
          <Info size={14} aria-hidden="true" /> {answer.aiNote}
        </p>
      )}
    </div>
  );
}
