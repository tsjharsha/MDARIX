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
import { AI_TIMEOUT_MS, describeError, postJson } from "../../app/apiClient";
import { useCan } from "../workspace/workspaceContext";
import { CaseRecordDownload } from "../reports/CaseRecordDownload";
import { displayId } from "../../app/displayId";
import { hasSavedResults, loadSavedResults } from "./savedResults";
import { AiInterpretationNote } from "../shared/StatementKind";
import { useAiBanner } from "../workspace/useAiStatus";
import { aiNoticeOf, epistemicOf, type IntelligenceView } from "../workspace/intelligence";

type AiBlock = "analysis" | "hypotheses" | "challenges" | "unknowns" | "failureChains" | "counterfactual" | "brief";
type AiBlockLabel = { note: string | null; notice: { message: string; manual: string | null } | null };

/**
 * The label every block of AI output carries (an AI interpretation to review), the reason rules wrote it when AI
 * could not, and the way to judge it where people record their judgements.
 */
function AiBlockNote({ label, onJudge }: { label?: AiBlockLabel; onJudge?: () => void }) {
  return (
    <>
      <AiInterpretationNote note={label?.note} onJudge={onJudge} />
      {label?.notice && (
        <p className="ac-muted" role="note">
          {label.notice.message}
          {label.notice.manual ? ` ${label.notice.manual}` : ""}
        </p>
      )}
    </>
  );
}

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
  onOpenIntelligence,
}: {
  investigationId: string;
  temporalMode: TemporalMode;
  asOf: string;
  onOpenDecision: () => void;
  /** Opens the case's Intelligence tab on a view, where people judge AI output and do the work by hand. */
  onOpenIntelligence?: (view: IntelligenceView) => void;
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
  const [counterfactualTarget, setCounterfactualTarget] = useState("");
  const [counterfactualType, setCounterfactualType] = useState("REMOVE_CHANGE");
  const [counterfactualStatus, setCounterfactualStatus] = useState("Not run yet");
  const [error, setError] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const requestSequence = useRef(0);
  // Set once a scenario is run for this case, so a saved scenario arriving later never replaces it.
  const counterfactualRequested = useRef(false);
  // Viewers can read every result; only roles allowed to run AI see the run buttons (the server enforces it too).
  const canRun = useCan("ai.run");
  // When AI is off, unavailable or over its allowance, say so and offer the manual way; otherwise nothing changes.
  const aiBanner = useAiBanner();
  const aiBlocked = Boolean(aiBanner);
  const runTitle = aiBanner ? aiBanner.disabledReason : undefined;
  const runDescribedBy = aiBanner ? "ai-status-banner" : undefined;
  // What each AI response says it is (an AI interpretation) and, when rules wrote it, why.
  const [labels, setLabels] = useState<Partial<Record<AiBlock, AiBlockLabel>>>({});
  const remember = (block: AiBlock, payload: unknown) =>
    setLabels((current) => ({
      ...current,
      [block]: { note: epistemicOf(payload)?.note ?? null, notice: aiNoticeOf(payload) },
    }));
  const judge = (view: IntelligenceView) => (onOpenIntelligence ? () => onOpenIntelligence(view) : undefined);

  useEffect(() => {
    const sequence = ++requestSequence.current;
    const current = () => sequence === requestSequence.current;
    // A different case or point in time starts clean: nothing from the previous one stays on screen.
    setWorkspace(null);
    setAnalysis(null);
    setHypothesisSet(null);
    setUnknownSet(null);
    setFailureChains(null);
    setChallengeSet(null);
    setBrief(null);
    setCounterfactual(null);
    setCounterfactualStatus("Not run yet");
    counterfactualRequested.current = false;
    setLabels({});
    setError("");
    setActionStatus("");
    setPendingAction(null);
    const params = new URLSearchParams({ temporal_mode: mode, retrieval_top_k: "8" });
    if (mode !== "current") params.set("as_of", `${asOf}T00:00:00Z`);
    api<InvestigationWorkspace>(`/api/v1/investigations/${investigationId}/workspace?${params}`)
      .then((item) => {
        if (!current()) return;
        setWorkspace(item);
      })
      .catch((err) => {
        if (current()) {
          setError(describeError(err, "The investigation could not be loaded."));
          setActionStatus("BACKEND ERROR: Investigation context could not be loaded.");
          setPendingAction(null);
        }
      });
    // Show the latest saved AI results instead of making people pay for the same runs again. A result produced by
    // an action started meanwhile is newer, so it is kept (each setter only fills what is still empty).
    loadSavedResults(investigationId, api).then((saved) => {
      if (!current()) return;
      setAnalysis((shown) => shown ?? saved.analysis);
      setHypothesisSet((shown) => shown ?? saved.hypothesisSet);
      setChallengeSet((shown) => shown ?? saved.challengeSet);
      setUnknownSet((shown) => shown ?? saved.unknownSet);
      setFailureChains((shown) => shown ?? saved.failureChains);
      setBrief((shown) => shown ?? saved.brief);
      if (saved.counterfactual && !counterfactualRequested.current) {
        setCounterfactual(saved.counterfactual.result);
        setCounterfactualStatus(saved.counterfactual.status);
      }
      if (hasSavedResults(saved))
        setActionStatus(
          (status) =>
            status ||
            "SAVED RESULTS: Showing the latest saved AI results for this investigation. Run a step again to refresh it.",
        );
    });
  }, [investigationId, mode, asOf]);

  // AI actions can take a while; each waits up to a minute, then says so instead of spinning forever.
  const ai = <T,>(path: string, body: unknown) =>
    postJson<T>(`/api/v1/investigations/${investigationId}/${path}`, body, { timeoutMs: AI_TIMEOUT_MS });
  const failed = (sequence: number, what: string, err: unknown) => {
    if (sequence !== requestSequence.current) return;
    const text = describeError(err, `${what} could not be completed.`);
    setError(text);
    setActionStatus(`BACKEND ERROR: ${what} could not be completed. ${text}`);
    setPendingAction(null);
  };
  const temporal = () => ({ temporal_mode: mode, as_of: mode === "current" ? null : `${asOf}T00:00:00Z` });

  const runAnalysis = () => {
    const sequence = requestSequence.current;
    setPendingAction("Run Analysis");
    setActionStatus("RUNNING: AI Investigator analysis...");
    setError("");
    ai<any>("analysis", {
      investigation_id: investigationId,
      ...temporal(),
      analysis_mode: "standard",
      retrieval_top_k: 8,
    })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setAnalysis(payload.analysis);
        remember("analysis", payload);
        setActionStatus(
          payload.analysis?.observations?.length
            ? "SUCCESS: Analysis results are displayed below."
            : "EMPTY RESULT: No observations were returned for this context.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => failed(sequence, "Analysis", err));
  };

  const runHypotheses = () => {
    const sequence = requestSequence.current;
    setPendingAction("Generate Hypotheses");
    setActionStatus("RUNNING: Generating competing hypotheses...");
    setError("");
    ai<any>("hypotheses", {
      investigation_id: investigationId,
      ...temporal(),
      investigator_question: "Generate competing hypotheses from the validated investigation analysis.",
      // Build on the analysis on screen instead of running it again.
      source_analysis_id: analysis?.analysis_id ?? null,
    })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setHypothesisSet(payload.hypothesis_set);
        remember("hypotheses", payload);
        const count = payload.hypothesis_set?.hypotheses?.length ?? 0;
        setActionStatus(
          count
            ? `SUCCESS: ${count} competing hypothesis result(s) are displayed below.`
            : "INSUFFICIENT EVIDENCE: No supportable hypotheses are available for this temporal context.",
        );
        setPendingAction(null);
        setError("");
      })
      .catch((err) => failed(sequence, "Hypothesis generation", err));
  };

  const runDay14 = async () => {
    const sequence = requestSequence.current;
    const current = () => sequence === requestSequence.current;
    setPendingAction("Run Unknowns & Chain");
    setActionStatus("RUNNING: Evaluating Unknowns Radar and Failure Chain...");
    setError("");
    const body = { investigation_id: investigationId, ...temporal() };
    try {
      // Challenge the hypotheses on screen instead of regenerating them.
      const challenges = await ai<any>("challenges", {
        ...body,
        hypothesis_set_id: hypothesisSet?.hypothesis_set_id ?? null,
      });
      if (!current()) return;
      setChallengeSet(challenges.challenge_set);
      remember("challenges", challenges);
      const unknowns = await ai<any>("unknowns", body);
      if (!current()) return;
      setUnknownSet(unknowns.unknown_set);
      remember("unknowns", unknowns);
      const chains = await ai<any>("failure-chains", body);
      if (!current()) return;
      setFailureChains(chains.failure_chain_set);
      remember("failureChains", chains);
      setActionStatus(
        chains.failure_chain_set?.chains?.length
          ? "SUCCESS: Unknowns and Failure Chain results are displayed below."
          : "INSUFFICIENT EVIDENCE: No supportable failure chain is available; the controlled result remains unresolved.",
      );
      setPendingAction(null);
      setError("");
    } catch (err) {
      failed(sequence, "Unknowns and Failure Chain", err);
    }
  };
  const runCounterfactual = () => {
    const sequence = requestSequence.current;
    const target = counterfactualTarget.trim();
    if (!target) {
      setCounterfactualStatus("Name the change, component or link to take away first.");
      return;
    }
    counterfactualRequested.current = true;
    setCounterfactualStatus("VALIDATING");
    setCounterfactual(null);
    ai<any>("counterfactuals", {
      ...temporal(),
      intervention_type: counterfactualType,
      intervention_target: target,
      intervention_description: `Explore the constrained alternative condition where ${target} is removed from the candidate explanation.`,
    })
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setCounterfactual(payload.result);
        remember("counterfactual", payload);
        setCounterfactualStatus(payload.status ?? "SUCCESS");
      })
      .catch((err) => {
        if (sequence === requestSequence.current)
          setCounterfactualStatus(
            err instanceof Error && err.message.includes("INSUFFICIENT")
              ? "INSUFFICIENT EVIDENCE"
              : `ERROR: ${describeError(err, "The scenario could not be run.")}`,
          );
      });
  };
  const generateBrief = () => {
    const sequence = requestSequence.current;
    setPendingAction("Generate Investigation Brief");
    setActionStatus("RUNNING: Generating Investigation Brief...");
    setError("");
    ai<InvestigationBrief>("briefs", temporal())
      .then((payload) => {
        if (sequence !== requestSequence.current) return;
        setBrief(payload);
        remember("brief", payload);
        setActiveTab("brief");
        setActionStatus(`SUCCESS: Investigation Brief v${payload.brief_version} generated for review.`);
        setPendingAction(null);
      })
      .catch((err) => {
        if (sequence !== requestSequence.current) return;
        setActionStatus(`BACKEND ERROR: Brief could not be generated. ${describeError(err, "Try again.")}`);
        setPendingAction(null);
      });
  };

  return (
    <section id="investigation-workspace" className="workspace-section">
      <div className="workspace-header">
        <div>
          <div className="section-title">
            <ClipboardList size={18} /> Investigation Workspace
          </div>
          <h2>
            {workspace
              ? displayId(workspace.investigation, "investigation_identifier", "Investigation context")
              : "Investigation context"}
          </h2>
          <p>{workspace?.investigation.investigation_question ?? "Loading this investigation…"}</p>
          <CaseRecordDownload
            investigationId={investigationId}
            label={
              workspace ? displayId(workspace.investigation, "investigation_identifier", "") || undefined : undefined
            }
          />
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
              <button
                className="primary-action"
                onClick={runAnalysis}
                disabled={Boolean(pendingAction) || aiBlocked}
                title={runTitle}
                aria-describedby={runDescribedBy}
              >
                {" "}
                {pendingAction === "Run Analysis" ? "Running Analysis…" : "Run Analysis"}
              </button>
              <button
                className="primary-action secondary"
                onClick={runHypotheses}
                disabled={Boolean(pendingAction) || aiBlocked}
                title={runTitle}
                aria-describedby={runDescribedBy}
              >
                {" "}
                {pendingAction === "Generate Hypotheses" ? "Generating…" : "Generate Hypotheses"}
              </button>
              <button
                className="primary-action secondary"
                onClick={runDay14}
                disabled={Boolean(pendingAction) || aiBlocked}
                title={runTitle}
                aria-describedby={runDescribedBy}
              >
                {" "}
                {pendingAction === "Run Unknowns & Chain" ? "Running Unknowns & Chain…" : "Run Unknowns & Chain"}
              </button>
              <button
                className="primary-action"
                onClick={generateBrief}
                disabled={Boolean(pendingAction) || aiBlocked}
                title={runTitle}
                aria-describedby={runDescribedBy}
              >
                {pendingAction === "Generate Investigation Brief"
                  ? "Generating Brief…"
                  : "Generate Investigation Brief"}
              </button>
            </>
          ) : (
            <span className="context-summary" role="note">
              View only: your role can review results but not run AI analysis.
            </span>
          )}
        </div>
      </div>
      {aiBanner && (
        <div id="ai-status-banner" className="ac-message tone-warning ai-status-banner" role="status">
          <div>
            <strong>{aiBanner.title}.</strong> {aiBanner.message} The AI run buttons are off; you can do the same work
            by hand.
          </div>
          {onOpenIntelligence && (
            <div className="ai-status-manual">
              {aiBanner.manual.map((path) => (
                <button
                  type="button"
                  key={path.view}
                  className="primary-action secondary"
                  onClick={() => onOpenIntelligence(path.view)}
                >
                  {path.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
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
                  <strong>{displayId(item, "evidence_identifier")}</strong>
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
          <button
            className="primary-action"
            onClick={runAnalysis}
            disabled={Boolean(pendingAction) || aiBlocked}
            title={runTitle}
            aria-describedby={runDescribedBy}
          >
            {pendingAction === "Run Analysis" ? "Running Analysis…" : "Run Analysis"}
          </button>
        )}
      </section>
      {analysis && (
        <>
          <AiBlockNote label={labels.analysis} onJudge={judge("Observations")} />
          <AnalysisVisual analysis={analysis} />
        </>
      )}
      <section id="workflow-hypotheses" className="workflow-action">
        <h3>Competing hypotheses</h3>
        <p>Preserves support, contradiction, gaps, and falsification conditions without choosing a winner.</p>
        {canRun && (
          <button
            className="primary-action secondary"
            onClick={runHypotheses}
            disabled={Boolean(pendingAction) || aiBlocked}
            title={runTitle}
            aria-describedby={runDescribedBy}
          >
            {pendingAction === "Generate Hypotheses" ? "Generating…" : "Generate Hypotheses"}
          </button>
        )}
      </section>
      {hypothesisSet && (
        <div className="hypothesis-section">
          <div className="section-title">
            <GitBranch size={18} /> Competing Hypotheses
          </div>
          <AiBlockNote label={labels.hypotheses} onJudge={judge("Hypotheses")} />
          <HypothesisBoard set={hypothesisSet} />
        </div>
      )}
      <section id="workflow-challenger" className="workflow-action">
        <h3>Challenger, unknowns, and failure chain</h3>
        <p>Surfaces challenges and material unknowns. An unresolved failure chain is a valid controlled result.</p>
        {canRun && (
          <button
            className="primary-action secondary"
            onClick={runDay14}
            disabled={Boolean(pendingAction) || aiBlocked}
            title={runTitle}
            aria-describedby={runDescribedBy}
          >
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
          <AiBlockNote label={labels.challenges} onJudge={judge("Contradictions")} />
          <ChallengeBoard set={challengeSet} />
        </div>
      )}
      {unknownSet && (
        <div id="workflow-unknowns" className="analysis-grid">
          <Panel title="Unknowns Radar" icon={<AlertTriangle />}>
            <AiBlockNote label={labels.unknowns} onJudge={judge("Unknowns")} />
            <UnknownsBoard set={unknownSet} />
          </Panel>
          <div id="workflow-failure-chain">
            <Panel title="Failure Chain Intelligence" icon={<GitBranch />}>
              <AiBlockNote label={labels.failureChains} onJudge={judge("Failure chain")} />
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
            placeholder="What to take away, e.g. a component revision or supplier change"
          />
          {canRun && (
            <button
              className="primary-action"
              onClick={runCounterfactual}
              disabled={counterfactualStatus === "VALIDATING" || !counterfactualTarget.trim() || aiBlocked}
              title={runTitle}
              aria-describedby={runDescribedBy}
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
            <AiBlockNote label={labels.counterfactual} />
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
              <button
                className="primary-action"
                onClick={generateBrief}
                disabled={Boolean(pendingAction) || aiBlocked}
                title={runTitle}
                aria-describedby={runDescribedBy}
              >
                {pendingAction === "Generate Investigation Brief"
                  ? "Generating Brief…"
                  : "Generate Investigation Brief"}
              </button>
            )}
          </>
        ) : (
          <>
            <h2>{brief.title}</h2>
            <AiBlockNote label={labels.brief} />
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
