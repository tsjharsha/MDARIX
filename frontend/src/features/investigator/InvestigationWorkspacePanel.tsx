import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CircleDot, ClipboardList, FileText, GitBranch, Network, ShieldCheck } from "lucide-react";
import { humanize } from "../../app/format";
import { Metric, Panel } from "../../app/ui";
import { AnalysisVisual, BriefVisual, ChallengeBoard, HypothesisBoard, UnknownsBoard } from "./AnalysisVisuals";
import {
  TemporalMode,
  InvestigationWorkspace,
  InvestigationAnalysis,
  InvestigationBrief,
  HypothesisSet,
  UnknownSet,
  FailureChainSet,
  ChallengeSet,
} from "../../app/types";
import { api } from "../../app/api";
import { useCan } from "../workspace/workspaceContext";

export function InvestigationTabSummary({
  activeTab,
  workspace,
  analysis,
  hypothesisSet,
  unknownSet,
  failureChains,
  brief,
  onOpenDecision,
}: {
  activeTab: string;
  workspace: InvestigationWorkspace | null;
  analysis: InvestigationAnalysis | null;
  hypothesisSet: HypothesisSet | null;
  unknownSet: UnknownSet | null;
  failureChains: FailureChainSet | null;
  brief: InvestigationBrief | null;
  onOpenDecision: () => void;
}) {
  const summaries: Record<string, { title: string; description: string; count: string; state: string }> = {
    overview: {
      title: "Investigation overview",
      description: "Server-authorized product, temporal, evidence, and guardrail context for this case.",
      count: `${workspace?.evidence_context.length ?? 0} evidence records`,
      state: workspace ? "Context loaded" : "Loading context",
    },
    evidence: {
      title: "Evidence review",
      description: "Inspect source anchors, reliability, and gaps before interpreting the case.",
      count: `${workspace?.evidence_context.length ?? 0} linked records`,
      state: workspace?.retrieval_context?.status ?? "Not requested",
    },
    analysis: {
      title: "Observations and analysis",
      description: "Review grounded observations, contradictions, possible explanations, and missing information.",
      count: `${analysis?.observations.length ?? 0} observations`,
      state: analysis?.status ?? "Not run",
    },
    hypotheses: {
      title: "Competing hypotheses",
      description: "Compare support and contradiction without selecting an unverified winner.",
      count: `${hypothesisSet?.hypotheses.length ?? 0} hypotheses`,
      state: hypothesisSet?.status ?? "Not run",
    },
    challenger: {
      title: "Challenger review",
      description: "Test the current interpretation for unsupported assumptions and material challenges.",
      count: "Advisory only",
      state: "Human review required",
    },
    unknowns: {
      title: "Unknowns and gaps",
      description: "Make missing tests, unresolved questions, and materiality visible.",
      count: `${unknownSet?.unknowns.length ?? 0} unknowns`,
      state: "Evidence gap posture",
    },
    "failure-chain": {
      title: "Failure chain",
      description: "Show supportable relationships while preserving unresolved links and epistemic status.",
      count: `${failureChains?.chains.length ?? 0} chains`,
      state: "Causality not established",
    },
    counterfactual: {
      title: "Constrained scenario",
      description: "Explore bounded alternatives; scenario output is hypothetical, not observed evidence.",
      count: "Bounded comparison",
      state: "Human interpretation required",
    },
    brief: {
      title: "Investigation brief",
      description: "Assemble a versioned, provenance-aware package for human review.",
      count: brief ? `Version ${brief.brief_version}` : "Not generated",
      state: brief?.human_review_state ?? "Human review required",
    },
    assurance: {
      title: "AI assurance",
      description: "Inspect grounding, provenance, temporal scope, and safety limitations.",
      count: "No hidden reasoning stored",
      state: "Advisory only",
    },
    decision: {
      title: "Decision readiness",
      description: "Prepare the case for an authorized reviewer; MDARIX never makes the regulated decision.",
      count: "Human authority",
      state: "Open Decision Center",
    },
  };
  const summary = summaries[activeTab] ?? summaries.overview;
  return (
    <section className="investigation-tab-summary" aria-live="polite">
      <div>
        <span className="eyebrow">Active workspace tab</span>
        <h3>{summary.title}</h3>
        <p>{summary.description}</p>
      </div>
      <div className="investigation-tab-status">
        <strong>{summary.count}</strong>
        <span>{summary.state}</span>
        {activeTab === "decision" && (
          <button className="primary-action" onClick={onOpenDecision}>
            Open Decision Center
          </button>
        )}
      </div>
    </section>
  );
}

export function InvestigationWorkspacePanel({
  investigationId,
  temporalMode: mode,
  asOf,
  onOpenDecision,
}: {
  investigationId: string;
  temporalMode: TemporalMode;
  asOf: string;
  onOpenDecision: () => void;
}) {
  const [workspace, setWorkspace] = useState<InvestigationWorkspace | null>(null);
  const [analysis, setAnalysis] = useState<InvestigationAnalysis | null>(null);
  const [hypothesisSet, setHypothesisSet] = useState<HypothesisSet | null>(null);
  const [unknownSet, setUnknownSet] = useState<UnknownSet | null>(null);
  const [failureChains, setFailureChains] = useState<FailureChainSet | null>(null);
  const [challengeSet, setChallengeSet] = useState<ChallengeSet | null>(null);
  const [activeTab, setActiveTab] = useState<
    | "overview"
    | "evidence"
    | "analysis"
    | "hypotheses"
    | "challenger"
    | "unknowns"
    | "failure-chain"
    | "counterfactual"
    | "brief"
    | "assurance"
    | "decision"
  >("overview");
  const [brief, setBrief] = useState<InvestigationBrief | null>(null);
  const [counterfactual, setCounterfactual] = useState<any>(null);
  const [counterfactualTarget, setCounterfactualTarget] = useState("Component Rev B");
  const [counterfactualType, setCounterfactualType] = useState("REMOVE_CHANGE");
  const [counterfactualStatus, setCounterfactualStatus] = useState("IDLE");
  const [error, setError] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const requestSequence = useRef(0);
  // Viewers can read every result; only roles allowed to run AI see the run buttons (the server enforces it too).
  const canRun = useCan("ai.run");

  useEffect(() => {
    const sequence = ++requestSequence.current;
    const params = new URLSearchParams({ temporal_mode: mode, retrieval_top_k: "8" });
    if (mode !== "current") params.set("as_of", `${asOf}T00:00:00Z`);
    api<InvestigationWorkspace>(`/api/v1/investigations/${investigationId}/workspace?${params}`)
      .then((item) => {
        if (sequence !== requestSequence.current) return;
        setWorkspace(item);
        setAnalysis(null);
        setHypothesisSet(null);
        setUnknownSet(null);
        setFailureChains(null);
        setChallengeSet(null);
        setError("");
        setActionStatus("");
        setPendingAction(null);
      })
      .catch((err) => {
        if (sequence === requestSequence.current) {
          setError(err.message);
          setActionStatus("BACKEND ERROR: Investigation context could not be loaded.");
          setPendingAction(null);
        }
      });
  }, [investigationId, mode, asOf]);

  const runAnalysis = () => {
    const sequence = requestSequence.current;
    setPendingAction("Run Analysis");
    setActionStatus("RUNNING: AI Investigator analysis...");
    setError("");
    const body = {
      investigation_id: investigationId,
      temporal_mode: mode,
      as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
      analysis_mode: "standard",
      retrieval_top_k: 8,
    };
    fetch(`/api/v1/investigations/${investigationId}/analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setAnalysis(payload.analysis);
        setActionStatus(
          payload.analysis?.observations?.length
            ? "SUCCESS: Analysis results are displayed below."
            : "EMPTY RESULT: No observations were returned for this context.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => {
        if (sequence === requestSequence.current) {
          setError(err.message);
          setActionStatus(`BACKEND ERROR: Analysis could not be completed (${err.message}).`);
          setPendingAction(null);
        }
      });
  };

  const runHypotheses = () => {
    const sequence = requestSequence.current;
    setPendingAction("Generate Hypotheses");
    setActionStatus("RUNNING: Generating competing hypotheses...");
    setError("");
    const body = {
      investigation_id: investigationId,
      temporal_mode: mode,
      as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
      investigator_question: "Generate competing hypotheses from the validated investigation analysis.",
      // Build on the analysis on screen instead of running it again.
      source_analysis_id: analysis?.analysis_id ?? null,
    };
    fetch(`/api/v1/investigations/${investigationId}/hypotheses`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setHypothesisSet(payload.hypothesis_set);
        const count = payload.hypothesis_set?.hypotheses?.length ?? 0;
        setActionStatus(
          count
            ? `SUCCESS: ${count} competing hypothesis result(s) are displayed below.`
            : "INSUFFICIENT EVIDENCE: No supportable hypotheses are available for this temporal context.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => {
        if (sequence === requestSequence.current) {
          setError(err.message);
          setActionStatus(`BACKEND ERROR: Hypotheses could not be generated (${err.message}).`);
          setPendingAction(null);
        }
      });
  };

  const runDay14 = () => {
    const sequence = requestSequence.current;
    setPendingAction("Run Unknowns & Chain");
    setActionStatus("RUNNING: Evaluating Unknowns Radar and Failure Chain...");
    setError("");
    const body = {
      investigation_id: investigationId,
      temporal_mode: mode,
      as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
    };
    fetch(`/api/v1/investigations/${investigationId}/challenges`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Challenge the hypotheses on screen instead of regenerating them.
      body: JSON.stringify({ ...body, hypothesis_set_id: hypothesisSet?.hypothesis_set_id ?? null }),
    })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return Promise.reject(new Error("STALE_CONTEXT"));
        setChallengeSet(payload.challenge_set);
        return fetch(`/api/v1/investigations/${investigationId}/unknowns`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return Promise.reject(new Error("STALE_CONTEXT"));
        setUnknownSet(payload.unknown_set);
        return fetch(`/api/v1/investigations/${investigationId}/failure-chains`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      })
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setFailureChains(payload.failure_chain_set);
        setActionStatus(
          payload.failure_chain_set?.chains?.length
            ? "SUCCESS: Unknowns and Failure Chain results are displayed below."
            : "INSUFFICIENT EVIDENCE: No supportable failure chain is available; the controlled result remains unresolved.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => {
        if (sequence === requestSequence.current && err.message !== "STALE_CONTEXT") {
          setError(err.message);
          setActionStatus(`BACKEND ERROR: Unknowns and Failure Chain could not be completed (${err.message}).`);
          setPendingAction(null);
        }
      });
  };
  const runCounterfactual = () => {
    const sequence = requestSequence.current;
    setCounterfactualStatus("VALIDATING");
    setCounterfactual(null);
    fetch(`/api/v1/investigations/${investigationId}/counterfactuals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        temporal_mode: mode,
        as_of: mode === "current" ? null : `${asOf}T00:00:00Z`,
        intervention_type: counterfactualType,
        intervention_target: counterfactualTarget,
        intervention_description: `Explore the constrained alternative condition where ${counterfactualTarget} is removed from the candidate explanation.`,
      }),
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail?.message ?? response.statusText);
        return payload;
      })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setCounterfactual(payload.result);
        setCounterfactualStatus(payload.status ?? "SUCCESS");
      })
      .catch((err) => {
        if (sequence === requestSequence.current)
          setCounterfactualStatus(
            err.message.includes("INSUFFICIENT") ? "INSUFFICIENT EVIDENCE" : `ERROR: ${err.message}`,
          );
      });
  };
  const generateBrief = () => {
    setActionStatus("RUNNING: Generating Investigation Brief...");
    fetch(`/api/v1/investigations/${investigationId}/briefs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ temporal_mode: mode, as_of: mode === "current" ? null : `${asOf}T00:00:00Z` }),
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail?.message ?? response.statusText);
        return payload;
      })
      .then((payload) => {
        setBrief(payload);
        setActiveTab("brief");
        setActionStatus(`SUCCESS: Investigation Brief v${payload.brief_version} generated for review.`);
      })
      .catch((err) => setActionStatus(`BACKEND ERROR: Brief could not be generated (${err.message}).`));
  };

  return (
    <section id="investigation-workspace" className="workspace-section">
      <div className="workspace-header">
        <div>
          <div className="section-title">
            <ClipboardList size={18} /> Investigation Workspace
          </div>
          <h2>{workspace?.investigation.investigation_identifier ?? "Investigation context"}</h2>
          <p>{workspace?.investigation.investigation_question ?? "Loading deterministic investigation context."}</p>
        </div>
        <div className="toolbar compact">
          <span className="context-summary">
            {humanize(mode)} {mode === "current" ? "context" : `as of ${asOf}`}
          </span>
          <div className="segmented">
            {(["current", "event", "known"] as const).map((item) => (
              <button key={item} className={mode === item ? "selected" : ""} disabled>
                {item}
              </button>
            ))}
          </div>
          {canRun ? (
            <>
              <button className="primary-action" onClick={runAnalysis} disabled={Boolean(pendingAction)}>
                {" "}
                {pendingAction === "Run Analysis" ? "Running Analysis…" : "Run Analysis"}
              </button>
              <button className="primary-action secondary" onClick={runHypotheses} disabled={Boolean(pendingAction)}>
                {" "}
                {pendingAction === "Generate Hypotheses" ? "Generating…" : "Generate Hypotheses"}
              </button>
              <button className="primary-action secondary" onClick={runDay14} disabled={Boolean(pendingAction)}>
                {" "}
                {pendingAction === "Run Unknowns & Chain" ? "Running Unknowns & Chain…" : "Run Unknowns & Chain"}
              </button>
              <button className="primary-action" onClick={generateBrief}>
                Generate Investigation Brief
              </button>
            </>
          ) : (
            <span className="context-summary" role="note">
              View only: your role can review results but not run AI analysis.
            </span>
          )}
        </div>
      </div>
      <div className="workflow-tabs" role="tablist" aria-label="Investigation workflow">
        {(
          [
            "overview",
            "evidence",
            "analysis",
            "hypotheses",
            "challenger",
            "unknowns",
            "failure-chain",
            "counterfactual",
            "brief",
            "assurance",
            "decision",
          ] as const
        ).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            className={activeTab === tab ? "active" : ""}
            onClick={() => {
              setActiveTab(tab);
              document.getElementById(`workflow-${tab}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          >
            {humanize(tab)}
          </button>
        ))}
      </div>
      <InvestigationTabSummary
        activeTab={activeTab}
        workspace={workspace}
        analysis={analysis}
        hypothesisSet={hypothesisSet}
        unknownSet={unknownSet}
        failureChains={failureChains}
        brief={brief}
        onOpenDecision={onOpenDecision}
      />
      {(actionStatus || pendingAction) && (
        <div className={`action-feedback ${actionStatus.startsWith("BACKEND") ? "error-feedback" : ""}`} role="status">
          {pendingAction ? actionStatus : actionStatus}
        </div>
      )}
      {error && <div className="error inline">{error}</div>}
      {workspace && (
        <div id="workflow-overview" className="workspace-grid">
          <Panel title="Context Health" icon={<ShieldCheck />}>
            <div className="context-health">
              <Metric icon={<FileText />} label="Evidence" value={workspace.evidence_context.length} />
              <Metric
                icon={<Network />}
                label="Graph Nodes"
                value={
                  workspace.relationship_context.metadata.node_count ?? workspace.relationship_context.nodes.length
                }
              />
              <Metric
                icon={<GitBranch />}
                label="Relationships"
                value={
                  workspace.relationship_context.metadata.relationship_count ??
                  workspace.relationship_context.relationships.length
                }
              />
            </div>
            <ul className="limitations">
              {workspace.limitations.slice(0, 5).map((item) => (
                <li key={item.code}>
                  <strong>{item.code}</strong>
                  <span>{item.description}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Evidence Context" icon={<FileText />}>
            <div className="evidence-list">
              {workspace.evidence_context.slice(0, 6).map((item) => (
                <article key={item.evidence_identifier}>
                  <strong>{item.evidence_identifier}</strong>
                  <span>{item.title}</span>
                  <small>
                    {item.evidence_type} | {item.reliability_status} | anchors{" "}
                    {item.chunks.filter((chunk) => chunk.source_anchor).length}
                  </small>
                </article>
              ))}
            </div>
          </Panel>
          <Panel title="Retrieval & Guardrails" icon={<CircleDot />}>
            <div className="guardrail-list">
              <p>
                <strong>Retrieval:</strong> {workspace.retrieval_context?.status ?? "Not requested"} (
                {workspace.retrieval_context?.results_count ?? 0} results)
              </p>
              <p>
                <strong>Temporal mode:</strong> {String(workspace.temporal_context.mode)}{" "}
                {workspace.temporal_context.as_of ? `as of ${workspace.temporal_context.as_of}` : ""}
              </p>
              <p>
                <strong>Human authority:</strong>{" "}
                {workspace.guardrails.human_authority_required ? "Required" : "Not recorded"}
              </p>
              <p>
                <strong>Causality:</strong> {workspace.guardrails.generates_causality ? "Generated" : "Not generated"}
              </p>
            </div>
          </Panel>
        </div>
      )}
      <section id="workflow-analysis" className="workflow-action">
        <h3>Analysis</h3>
        <p>Grounded observations and possible explanations for the selected context.</p>
        {canRun && (
          <button className="primary-action" onClick={runAnalysis} disabled={Boolean(pendingAction)}>
            {pendingAction === "Run Analysis" ? "Running Analysis…" : "Run Analysis"}
          </button>
        )}
      </section>
      {analysis && <AnalysisVisual analysis={analysis} />}
      <section id="workflow-hypotheses" className="workflow-action">
        <h3>Competing hypotheses</h3>
        <p>Preserves support, contradiction, gaps, and falsification conditions without choosing a winner.</p>
        {canRun && (
          <button className="primary-action secondary" onClick={runHypotheses} disabled={Boolean(pendingAction)}>
            {pendingAction === "Generate Hypotheses" ? "Generating…" : "Generate Hypotheses"}
          </button>
        )}
      </section>
      {hypothesisSet && (
        <div className="hypothesis-section">
          <div className="section-title">
            <GitBranch size={18} /> Competing Hypotheses
          </div>
          <HypothesisBoard set={hypothesisSet} />
        </div>
      )}
      <section id="workflow-challenger" className="workflow-action">
        <h3>Challenger, unknowns, and failure chain</h3>
        <p>Surfaces challenges and material unknowns. An unresolved failure chain is a valid controlled result.</p>
        {canRun && (
          <button className="primary-action secondary" onClick={runDay14} disabled={Boolean(pendingAction)}>
            {pendingAction === "Run Unknowns & Chain"
              ? "Running controlled checks…"
              : "Run Challenger, Unknowns & Chain"}
          </button>
        )}
      </section>
      {challengeSet && (
        <div className="hypothesis-section">
          <div className="section-title">
            <ShieldCheck size={18} /> Challenger review
          </div>
          <ChallengeBoard set={challengeSet} />
        </div>
      )}
      {unknownSet && (
        <div id="workflow-unknowns" className="analysis-grid">
          <Panel title="Unknowns Radar" icon={<AlertTriangle />}>
            <UnknownsBoard set={unknownSet} />
          </Panel>
          <div id="workflow-failure-chain">
            <Panel title="Failure Chain Intelligence" icon={<GitBranch />}>
              <div className="analysis-list">
                {!failureChains?.chains.length && (
                  <p className="empty">
                    No supportable failure chain is available for this context. The chain remains unresolved.
                  </p>
                )}
                {failureChains?.chains.map((chain) => (
                  <article key={chain.chain_id}>
                    <span>{chain.overall_status}</span>
                    <p>{chain.chain_statement}</p>
                    {chain.links.map((link) => (
                      <small key={link.link_id}>
                        {link.from_entity_or_state} — {link.relationship} → {link.to_entity_or_state} [
                        {link.epistemic_status}]
                      </small>
                    ))}
                  </article>
                ))}
              </div>
            </Panel>
          </div>
        </div>
      )}
      <section id="workflow-evidence" className="panel empty-state">
        <h3>Evidence review</h3>
        <p>
          Use the evidence context above to see identifiers, reliability, and source anchors for the selected
          investigation.
        </p>
      </section>
      <section id="workflow-counterfactual" className="panel counterfactual-panel">
        <div className="section-title">
          <GitBranch size={18} /> Constrained Counterfactual
        </div>
        <p className="helper-copy">
          Explore how the current explanation changes under a controlled alternative condition. Results are hypothetical
          and are not observed evidence.
        </p>
        <div className="counterfactual-controls">
          <select
            value={counterfactualType}
            onChange={(event) => setCounterfactualType(event.target.value)}
            aria-label="Intervention type"
          >
            <option value="REMOVE_CHANGE">Remove change</option>
            <option value="REPLACE_COMPONENT_REVISION">Replace component revision</option>
            <option value="REMOVE_SUPPLIER_CHANGE">Remove supplier change</option>
            <option value="REMOVE_FAILURE_CHAIN_LINK">Remove failure-chain link</option>
          </select>
          <input
            value={counterfactualTarget}
            onChange={(event) => setCounterfactualTarget(event.target.value)}
            aria-label="Counterfactual target"
            placeholder="Readable target, e.g. Component Rev B"
          />
          {canRun && (
            <button
              className="primary-action"
              onClick={runCounterfactual}
              disabled={counterfactualStatus === "VALIDATING"}
            >
              {counterfactualStatus === "VALIDATING" ? "Validating…" : "Run Counterfactual"}
            </button>
          )}
        </div>
        <p className="action-feedback" role="status">
          Status: {counterfactualStatus}
        </p>
        {counterfactual && (
          <div className="counterfactual-result">
            <strong>{counterfactual.label}</strong>
            <h3>What stays the same</h3>
            <ul>
              {counterfactual.invariants?.map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>What changes / becomes unsupported</h3>
            <ul>
              {counterfactual.relationships_no_longer_supported?.map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>What remains unexplained</h3>
            <ul>
              {counterfactual.observations_still_unexplained?.map((item: string) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <h3>Limitations</h3>
            <ul>
              {counterfactual.limitations?.map((item: any, index: number) => (
                <li key={index}>{typeof item === "string" ? item : item.description}</li>
              ))}
            </ul>
            <p>
              <strong>Conclusion:</strong> {counterfactual.conclusion}
            </p>
          </div>
        )}
      </section>
      <section id="workflow-brief" className="panel brief-panel">
        <div className="section-title">
          <FileText size={18} /> Investigation Brief
        </div>
        {!brief ? (
          <>
            <p>Assemble a versioned, evidence-grounded package for human review.</p>
            {canRun && (
              <button className="primary-action" onClick={generateBrief}>
                Generate Investigation Brief
              </button>
            )}
          </>
        ) : (
          <>
            <h2>{brief.title}</h2>
            <BriefVisual brief={brief} />
          </>
        )}
      </section>
      <section id="workflow-assurance" className="panel">
        <div className="section-title">
          <ShieldCheck size={18} /> AI Assurance
        </div>
        <h2>Deterministic Trust Engine</h2>
        <p>
          Assurance validates evidence grounding, citation integrity, tenant and ProductVersion context, temporal
          context, unsupported claims, causality restraint, provenance, and human authority.
        </p>
        <div className="guardrail-list">
          <p>
            <strong>Status:</strong> Assurance results are persisted per AI execution.
          </p>
          <p>
            <strong>Policy:</strong> Controlled AI Trust Policy
          </p>
          <p>
            <strong>Causality:</strong> NOT ESTABLISHED by assurance.
          </p>
          <p>
            <strong>Human review:</strong> REQUIRED. Assurance does not approve decisions.
          </p>
          <p>
            <strong>Confidence:</strong> No fabricated numeric confidence score is used.
          </p>
        </div>
      </section>
      <section id="workflow-decision" className="panel empty-state">
        <h3>Decision readiness</h3>
        <p>AI outputs inform the workflow. Authorized humans record decisions in the Decision Center.</p>
        <button className="primary-action" onClick={onOpenDecision}>
          Open Decision Center
        </button>
      </section>
    </section>
  );
}
