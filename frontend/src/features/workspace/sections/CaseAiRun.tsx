import { useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleDashed, CircleSlash, Loader2, RefreshCw, Sparkles, XCircle } from "lucide-react";
import { ToneBadge } from "../../admin/console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { useCan } from "../workspaceContext";
import { isRunning, runHeadline, runPath, runProgress, type CaseAiRun, type CaseAiRunStep } from "../signalAi";
import { InlineError } from "./boardParts";
import { TrustBadge } from "./TrustBadge";

const POLL_MS = 3000;

/**
 * The case's AI analysis in one run: it starts by itself the first time the case opens (for someone allowed to run
 * AI, when the case has no AI work yet), shows each step as it finishes, and can be run again after new evidence.
 * ``onFinished`` lets the page reload the results below once a run ends.
 */
export function CaseAiRunCard({ caseId, onFinished }: { caseId: string; onFinished: () => void }) {
  const canRun = useCan("ai.run");
  const state = useResource<{ run: CaseAiRun | null }>(runPath(caseId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const autoTried = useRef(false);
  const wasRunning = useRef(false);
  const run = state.data?.run ?? null;
  const running = isRunning(run);

  const start = async (trigger: "AUTO" | "MANUAL") => {
    setBusy(true);
    setError("");
    try {
      await send(runPath(caseId), "POST", { trigger });
      state.reload();
    } catch (failure) {
      if (trigger === "MANUAL") setError(errorText(failure, "The AI analysis could not start."));
    } finally {
      setBusy(false);
    }
  };

  // The first time the case opens with no AI work yet, the analysis starts by itself (the server never repeats it).
  useEffect(() => {
    if (!canRun || autoTried.current || state.state !== "ready" || run) return;
    autoTried.current = true;
    void start("AUTO");
  }, [canRun, state.state, run]);

  // While it runs, follow it; when it ends, the results below are reloaded.
  useEffect(() => {
    if (running) {
      wasRunning.current = true;
      const timer = window.setTimeout(state.reload, POLL_MS);
      return () => window.clearTimeout(timer);
    }
    if (wasRunning.current) {
      wasRunning.current = false;
      onFinished();
    }
    return undefined;
  }, [running, run?.steps?.length, run?.status]);

  if (state.state !== "ready" && !run) return null;
  return (
    <RunView run={run} running={running} canRun={canRun} busy={busy} error={error} onRun={() => void start("MANUAL")} />
  );
}

/** The run's headline and steps (exported for its unit test). */
export function RunView({
  run,
  running,
  canRun,
  busy,
  error,
  onRun,
}: {
  run: CaseAiRun | null;
  running: boolean;
  canRun: boolean;
  busy: boolean;
  error: string;
  onRun: () => void;
}) {
  const headline = runHeadline(run);
  const { done, total } = runProgress(run);
  return (
    <section
      className={`ac-hero uw-cr-hero uw-ai-run tone-${headline.tone}`}
      aria-live="polite"
      aria-label="AI analysis"
    >
      <div className="ac-hero-status">
        <span className="ac-hero-icon" aria-hidden="true">
          {running ? <Loader2 size={26} className="uw-spin" /> : <Sparkles size={26} />}
        </span>
        <div>
          <p className="ac-eyebrow">
            AI analysis{run ? ` · ${run.trigger === "AUTO" ? "started by itself" : "started by a person"}` : ""}
          </p>
          <h2>{headline.title}</h2>
          <p>{headline.detail}</p>
        </div>
      </div>
      {run && (
        <ol className="uw-ai-steps" aria-label={`${done} of ${total} steps done`}>
          {run.steps.map((step) => (
            <StepItem key={step.step} step={step} />
          ))}
        </ol>
      )}
      <div className="ca-action-row">
        {canRun && !running && (
          <button type="button" className={run ? "ac-secondary" : "ac-primary"} disabled={busy} onClick={onRun}>
            <RefreshCw size={15} aria-hidden="true" /> {run ? "Run the analysis again" : "Run the analysis"}
          </button>
        )}
        <span className="ac-muted">
          AI explains with sources; it never decides the cause, reportability or closure.
        </span>
      </div>
      <InlineError text={error} />
    </section>
  );
}

function StepItem({ step }: { step: CaseAiRunStep }) {
  const icon =
    step.status === "DONE" ? (
      <CheckCircle2 size={15} className="ac-tone-icon tone-good" aria-hidden="true" />
    ) : step.status === "FAILED" ? (
      <XCircle size={15} className="ac-tone-icon tone-critical" aria-hidden="true" />
    ) : step.status === "SKIPPED" ? (
      <CircleSlash size={15} className="ac-tone-icon tone-neutral" aria-hidden="true" />
    ) : (
      <CircleDashed size={15} className="ac-tone-icon tone-neutral" aria-hidden="true" />
    );
  return (
    <li className={`uw-ai-step is-${step.status.toLowerCase()}`}>
      {icon}
      <span>{step.label}</span>
      {step.status === "DONE" && (
        <ToneBadge tone="neutral" label={step.author === "AI" ? "Written by AI" : "From the rules"} />
      )}
      {step.status === "DONE" && step.trust && <TrustBadge trust={step.trust} />}
      {step.status === "SKIPPED" && (
        <small className="ac-muted">Not run in this edition: a fixed template, not an analysis</small>
      )}
      {step.status === "FAILED" && <small className="uw-flag-critical">{step.error ?? "Failed"}</small>}
    </li>
  );
}
