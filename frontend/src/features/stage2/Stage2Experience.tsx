import { useEffect, useState } from "react";
import { describeError, requestJson } from "../../app/apiClient";
import { formatDateTime } from "../../app/dates";
import { ToneBadge } from "../admin/console/charts";
import { storyStage, storySummary, type StoryStage } from "./storyModel";
import "./story.css";
import { displayId, referenceId } from "../../app/displayId";
import { investigationRequestFor, useOpenInvestigation } from "../workspace/workspaceContext";

type Stage2Mode = "signals" | "story" | "evidence" | "persona";

const personas = ["investigator", "quality-manager", "regulatory", "risk-manager", "approver", "executive"];

export function Stage2Experience({ mode, investigationId }: { mode: Stage2Mode; investigationId?: string }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [persona, setPersona] = useState("investigator");
  const signalId = mode === "signals" ? new URLSearchParams(window.location.search).get("signal_id") : null;

  useEffect(() => {
    const path =
      mode === "signals"
        ? signalId
          ? `/api/v1/signals/${encodeURIComponent(signalId)}`
          : "/api/v1/analytics/signals"
        : mode === "evidence"
          ? "/api/v1/analytics/evidence"
          : mode === "persona"
            ? `/api/v1/analytics/persona/${persona}`
            : investigationId
              ? `/api/v1/story/${investigationId}`
              : "";
    if (!path) return;
    setError("");
    requestJson<any>(path)
      .then(setData)
      .catch((reason) => setError(describeError(reason, "This view could not be loaded.")));
  }, [mode, investigationId, persona, signalId]);

  const content =
    mode === "signals"
      ? {
          title: "Signals & Complaints",
          copy: "Start with what changed in the field. Review complaint patterns with product, version, lot, supplier, and investigation context before deciding whether a signal needs action.",
        }
      : mode === "evidence"
        ? {
            title: "Evidence Intelligence",
            copy: "See the evidence behind the investigation. Each record stays connected to its source, product scope, time context, provenance, limitations, and review status.",
          }
        : mode === "persona"
          ? {
              title: "Persona Dashboard",
              copy: "Focus the workspace on the decisions and evidence that matter to the selected role. You still see only your organization's data, as your role allows.",
            }
          : {
              title: "Connected Story View",
              copy: "Follow one investigation from the opening signal through product context, evidence review, assessment, and an accountable human decision.",
            };

  return (
    <div className="content stage2-experience">
      <section className="product-header">
        <div>
          <p className="eyebrow">MDARIX investigation journey</p>
          <h2>{content.title}</h2>
          <p>{content.copy}</p>
        </div>
        <div className="version-pill">Human review required</div>
      </section>
      <nav className="journey-strip" aria-label="Investigation journey">
        <span className={mode === "signals" ? "active" : ""}>01 Signal</span>
        <span>02 Product context</span>
        <span className={mode === "evidence" ? "active" : ""}>03 Evidence</span>
        <span className={mode === "story" ? "active" : ""}>04 Assessment</span>
        <span>05 Human decision</span>
      </nav>
      {mode === "persona" && (
        <select
          className="persona-select"
          value={persona}
          onChange={(event) => setPersona(event.target.value)}
          aria-label="Persona"
        >
          {personas.map((item) => (
            <option key={item} value={item}>
              {item.replace("-", " ")}
            </option>
          ))}
        </select>
      )}
      {error && <div className="error">{error}</div>}
      {mode === "signals" && signalId && data?.signal ? (
        <SignalDetail data={data} />
      ) : (
        data && (
          <section className="panel stage2-results">
            <div className="section-title">Results for your organization</div>
            {mode === "signals" && (
              <div className="evidence-list">
                {(data.signals ?? []).map((item: any) => (
                  <button
                    className="evidence-list article-button"
                    key={item.signal_id}
                    onClick={() => {
                      window.history.pushState({}, "", `/app/signals?signal_id=${encodeURIComponent(item.signal_id)}`);
                      window.dispatchEvent(new PopStateEvent("popstate"));
                    }}
                  >
                    <strong>{displayId(item, "signal_id", "Complaint")}</strong>
                    <span>{item.description ?? "Description not recorded"}</span>
                    <small>
                      {item.severity ?? "Severity not recorded"} · {item.status ?? "Status not recorded"}
                    </small>
                  </button>
                ))}
              </div>
            )}
            {mode === "evidence" && (
              <div className="evidence-list">
                {(data.evidence ?? []).map((item: any) => (
                  <article key={item.id}>
                    <strong>{displayId(item, "evidence_identifier")}</strong>
                    <span>{item.title ?? "Title not recorded"}</span>
                    <small>
                      {item.evidence_type} · {item.reliability_status ?? "Reliability not recorded"}
                    </small>
                  </article>
                ))}
              </div>
            )}
            {mode === "story" && <StoryStages stages={data.stages ?? []} />}
            {mode === "persona" && (
              <div className="home-insight-grid">
                <article>
                  <span className="eyebrow">Persona</span>
                  <strong>{data.persona}</strong>
                  <p>Primary review emphasis</p>
                  <span>{data.emphasis}</span>
                </article>
                <article>
                  <span className="eyebrow">Investigations</span>
                  <strong>{data.counts?.investigations ?? 0}</strong>
                  <p>Separate workspace for each organization</p>
                </article>
                <article>
                  <span className="eyebrow">Evidence</span>
                  <strong>{data.counts?.evidence ?? 0}</strong>
                  <p>Records available for review</p>
                </article>
              </div>
            )}
            <ul className="limitations">
              {(data.limitations ?? []).map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )
      )}
    </div>
  );
}

/** Each stage of the case with its state (records available, complete, pending) and how many records it has. */
function StoryStages({ stages }: { stages: StoryStage[] }) {
  return (
    <>
      <p className="muted">{storySummary(stages)}</p>
      <ol className="evidence-list story-stages">
        {stages.map((item) => {
          const view = storyStage(item);
          return (
            <li key={item.key}>
              <article>
                <strong>{item.label}</strong>
                <ToneBadge tone={view.tone} label={view.label} />
                <small>{view.records}</small>
              </article>
            </li>
          );
        })}
      </ol>
    </>
  );
}

function SignalDetail({ data }: { data: any }) {
  const signal = data.signal ?? {};
  // Only inside the workspace, for a role that may change records (null otherwise, so no button).
  const openInvestigation = useOpenInvestigation();
  const request = investigationRequestFor(signal);
  return (
    <section className="panel stage2-results signal-detail">
      <button
        className="text-button"
        onClick={() => {
          window.history.pushState({}, "", "/app/signals");
          window.dispatchEvent(new PopStateEvent("popstate"));
        }}
      >
        ← Back to signals
      </button>
      <div className="section-title">Signal detail · {displayId(signal, "signal_id")}</div>
      <div className="home-insight-grid">
        <article>
          <span className="eyebrow">Product</span>
          <strong>{signal.product_name ?? "Not recorded"}</strong>
          <p>{referenceId(signal, "product", signal.product_identifier, "Product ID unavailable")}</p>
        </article>
        <article>
          <span className="eyebrow">Product version</span>
          <strong>{signal.version_identifier ?? "Not recorded"}</strong>
          <p>{formatDateTime(signal.event_timestamp ?? signal.complaint_timestamp, "Event time unavailable")}</p>
        </article>
        <article>
          <span className="eyebrow">Review state</span>
          <strong>Human review required</strong>
          <p>Source record in your organization</p>
        </article>
      </div>
      <p>{signal.description ?? "No source description recorded."}</p>
      <p className="muted">Recorded severity · {signal.severity ?? "Not recorded"}</p>
      {openInvestigation && request && (
        <button type="button" className="text-button" onClick={() => openInvestigation(request)}>
          Open investigation for this signal
        </button>
      )}
      <h3>Related investigations</h3>
      <div className="evidence-list">
        {(data.related_investigations ?? []).map((item: any) => (
          <article key={item.id ?? item.investigation_identifier}>
            <strong>{displayId(item, "investigation_identifier")}</strong>
            <span>{item.investigation_question ?? "Question not recorded"}</span>
            <small>{item.status ?? "Status not recorded"}</small>
          </article>
        ))}
      </div>
      <div className="advisory-box">
        <strong>Interpretation boundary</strong>
        <p>
          {data.interpretation?.observed} {data.interpretation?.correlation} {data.interpretation?.unknown}
        </p>
        <p>{data.interpretation?.missing_evidence}</p>
      </div>
    </section>
  );
}
