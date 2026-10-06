// The latest honest evaluation of the real AI pipeline on the synthetic golden scenarios.
import { useEffect, useState } from "react";
import { Bot, CheckCircle2, CircleSlash, ListChecks, Loader2, XCircle } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { listOf, useResource } from "../../customer-admin/shared";
import "../../investigator/analysis-visuals.css";
import { formatDateTime } from "../../../app/dates";
import { ApiError, describeError, postJson, requestJson } from "../../../app/apiClient";
import { useCan } from "../workspaceContext";

const CHECK_LABELS: Record<string, string> = {
  CONTRADICTIONS_FOUND: "Contradictions found",
  UNKNOWNS_FOUND: "Unknowns found",
  NO_PROHIBITED: "No false or causal claim",
  CITATIONS_VALID: "Citations valid",
  GROUNDED: "Every statement cited",
};

function Score({ label, passed, total, detail }: { label: string; passed: number; total: number; detail: string }) {
  const share = total ? passed / total : 0;
  return (
    <div className="te-score">
      <span className="te-score-label">{label}</span>
      <strong>
        {passed}/{total}
      </strong>
      <div className="av-balance-track" role="img" aria-label={`${passed} of ${total} passed`}>
        {passed > 0 && <span className="av-balance-for" style={{ width: `${share * 100}%` }} />}
        {total - passed > 0 && <span className="av-balance-against" style={{ width: `${(1 - share) * 100}%` }} />}
      </div>
      <small>{detail}</small>
    </div>
  );
}

export function TrustEvaluation() {
  const resource = useResource<any>("/api/v1/evaluations/golden/latest");
  const evaluation = resource.data?.evaluation;
  return (
    <>
      <Panel eyebrow="Tested on synthetic scenarios" title="How the AI performs on our test cases" source={resource}>
        {!evaluation ? (
          <p className="ac-muted">No evaluation has been run yet.</p>
        ) : (
          <div className="av-stack te-stack">
            <div className="te-scores">
              <Score
                label="Scenarios that test something specific"
                passed={evaluation.passed_with_specific_expectations ?? 0}
                total={evaluation.with_specific_expectations ?? 0}
                detail="Expected contradictions or unknowns must be found, by meaning."
              />
              <Score
                label="All scenarios"
                passed={evaluation.passed ?? 0}
                total={evaluation.total ?? 0}
                detail="Includes scenarios that only check nothing false or causal was claimed."
              />
              <div className="te-score">
                <span className="te-score-label">Written by</span>
                <strong>
                  <Bot size={18} aria-hidden="true" /> {evaluation.model_written ?? 0}/{evaluation.total ?? 0}
                </strong>
                <small>{evaluation.model ?? "—"}</small>
              </div>
            </div>
            <ul className="te-scenarios">
              {listOf(evaluation.scenarios).map((scenario: any) => (
                <li key={scenario.scenario_id}>
                  <span className={`te-pill ${scenario.status === "PASS" ? "is-pass" : "is-fail"}`}>
                    {scenario.status === "PASS" ? (
                      <CheckCircle2 size={13} aria-hidden="true" />
                    ) : (
                      <XCircle size={13} aria-hidden="true" />
                    )}
                    {scenario.status === "PASS" ? "Pass" : "Fail"}
                  </span>
                  <div>
                    <strong>
                      {scenario.scenario_id} · {scenario.title}
                    </strong>
                    <small>
                      {scenario.specific_expectations
                        ? `${scenario.specific_expectations} specific expectations`
                        : "No specific expectations"}
                      {" · "}
                      {scenario.written_by === "LANGUAGE_MODEL" ? "AI-written" : "Rules"}
                      {scenario.seconds != null ? ` · ${scenario.seconds}s` : ""}
                    </small>
                    <span className="te-checks">
                      {listOf(scenario.checks).map((check: any) => (
                        <span
                          key={check.check}
                          className={`te-check ${check.status === "PASS" ? "is-pass" : "is-fail"}`}
                          title={listOf(check.matches)
                            .map((item: any) => `${item.expected}: similarity ${item.similarity}`)
                            .join("\n")}
                        >
                          {check.status === "PASS" ? (
                            <CheckCircle2 size={11} aria-hidden="true" />
                          ) : (
                            <CircleSlash size={11} aria-hidden="true" />
                          )}
                          {CHECK_LABELS[check.check] ?? titleCase(check.check)}
                        </span>
                      ))}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            <p className="av-note">
              <ListChecks size={14} aria-hidden="true" /> {evaluation.data_notice} The AI never sees the expected
              answers; they are compared only after it has answered.
              {evaluation.completed_at ? ` Last run ${formatDateTime(evaluation.completed_at)}.` : ""}
            </p>
          </div>
        )}
      </Panel>
      <RunEvaluation />
    </>
  );
}

/** The states of a run started here (POST /api/v1/evaluations/runs answers 202 RUNNING; the run ends PASS/FAIL/ERROR). */
export type EvaluationRun = {
  evaluation_run_id: string;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  results?: {
    total?: number;
    passed?: number;
    model?: string;
    error?: string;
    results?: Array<{ scenario_id: string; status: string; error?: string }>;
  } | null;
};

const FINISHED = ["PASS", "FAIL", "ERROR"];
export const runFinished = (status: unknown) => FINISHED.includes(String(status ?? "").toUpperCase());

/** Where to ask for a run's state: built from its id, never from a URL taken from a response. */
export const runPath = (id: string) => `/api/v1/evaluations/runs/${encodeURIComponent(id)}`;

/** Wait longer between checks as a run goes on: 3 s, then up to 15 s (a full run takes minutes). */
export const pollDelay = (attempt: number) => Math.min(15_000, 3_000 + attempt * 2_000);

/** The body that starts a run: every scenario, or only VS001 for a quick check. */
export const runRequest = (quick: boolean) => (quick ? { scenario_ids: ["VS001"] } : {});

/** A finished run in one line; null while it is still running (a running run has no result to show). */
export function runOutcome(run: EvaluationRun | null): { tone: "good" | "warning" | "critical"; text: string } | null {
  if (!run || !runFinished(run.status)) return null;
  const status = run.status.toUpperCase();
  const total = run.results?.total ?? 0;
  const passed = run.results?.passed ?? 0;
  if (status === "ERROR")
    return {
      tone: "critical",
      text: `The run could not complete${run.results?.error ? ` (${run.results.error})` : ""}; nothing was scored.`,
    };
  if (status === "PASS") return { tone: "good", text: `Every scenario passed: ${passed} of ${total}.` };
  return { tone: "warning", text: `${passed} of ${total} scenarios passed.` };
}

const LAST_RUN_KEY = "mdarix.evaluation.lastRun";
const remember = (id: string | null) => {
  try {
    if (id) window.sessionStorage.setItem(LAST_RUN_KEY, id);
    else window.sessionStorage.removeItem(LAST_RUN_KEY);
  } catch {
    // Storage can be unavailable (private windows); the run simply is not resumed after leaving the page.
  }
};
const remembered = () => {
  try {
    return window.sessionStorage.getItem(LAST_RUN_KEY);
  } catch {
    return null;
  }
};

/**
 * Start an evaluation of the real pipeline on the golden scenarios for this organization, and follow it: RUNNING
 * while it works (checked every few seconds, resumed if the person comes back to the page), then its computed
 * result. Results of a run started here are this organization's own; the published evaluation above is separate.
 */
function RunEvaluation() {
  const canRun = useCan("ai.run");
  const [run, setRun] = useState<EvaluationRun | null>(null);
  const [quick, setQuick] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // A run started earlier in this browser session is followed again.
  useEffect(() => {
    const id = remembered();
    if (id && canRun) setRun({ evaluation_run_id: id, status: "RUNNING" });
  }, [canRun]);
  useEffect(() => {
    if (!run || runFinished(run.status)) return;
    let attempt = 0;
    let stopped = false;
    let timer: number | undefined;
    const check = async () => {
      try {
        const next = await requestJson<EvaluationRun>(runPath(run.evaluation_run_id));
        if (stopped) return;
        if (runFinished(next.status)) {
          setRun(next);
          remember(null);
          return;
        }
        setRun((current) => (current ? { ...current, started_at: next.started_at } : current));
      } catch (reason) {
        if (stopped) return;
        if (reason instanceof ApiError && reason.status === 404) {
          remember(null);
          setRun(null);
          return;
        }
        setError(describeError(reason, "The run's progress could not be checked; still trying."));
      }
      attempt += 1;
      timer = window.setTimeout(() => void check(), pollDelay(attempt));
    };
    timer = window.setTimeout(() => void check(), pollDelay(0));
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [run?.evaluation_run_id, run && runFinished(run.status)]);
  if (!canRun) return null;
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      const started = await postJson<EvaluationRun>("/api/v1/evaluations/runs", runRequest(quick));
      remember(started.evaluation_run_id);
      setRun({ evaluation_run_id: started.evaluation_run_id, status: "RUNNING" });
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.code === "EVALUATION_ALREADY_RUNNING"
          ? "An evaluation is already running for your organization. Its result appears when it finishes."
          : describeError(reason, "The evaluation could not be started."),
      );
    } finally {
      setBusy(false);
    }
  };
  const running = !!run && !runFinished(run.status);
  const outcome = runOutcome(run);
  return (
    <Panel eyebrow="Run it yourself" title="Evaluate the AI on the test scenarios now">
      <p className="ac-muted">
        Runs the same analysis pipeline your investigations use on the synthetic scenarios and scores it against
        expected answers it never sees. A full run takes several minutes.
      </p>
      <div className="ca-action-row">
        <label className="ca-check">
          <input
            type="checkbox"
            checked={quick}
            disabled={running}
            onChange={(event) => setQuick(event.target.checked)}
          />
          Quick run: scenario VS001 only
        </label>
        <button type="button" className="ac-primary" disabled={busy || running} onClick={() => void start()}>
          {running ? "Running…" : busy ? "Starting…" : "Start evaluation"}
        </button>
      </div>
      {running && (
        <p className="ac-note" role="status" aria-live="polite">
          <Loader2 size={14} aria-hidden="true" /> Running
          {run?.started_at ? ` since ${formatDateTime(run.started_at)}` : ""}. Results appear here when the run
          completes; you can leave this page and come back.
        </p>
      )}
      {error && (
        <p className="ca-inline-error" role="alert">
          {error}
        </p>
      )}
      {outcome && run && (
        <div role="status">
          <ToneBadge tone={outcome.tone} label={titleCase(run.status)} /> {outcome.text}
          {run.results?.model && <small> Written by {run.results.model}.</small>}
          {run.completed_at && <small> Finished {formatDateTime(run.completed_at)}.</small>}
          {!!run.results?.results?.length && (
            <ul className="te-scenarios">
              {run.results.results.map((item) => (
                <li key={item.scenario_id}>
                  <span className={`te-pill ${item.status === "PASS" ? "is-pass" : "is-fail"}`}>
                    {item.status === "PASS" ? (
                      <CheckCircle2 size={13} aria-hidden="true" />
                    ) : (
                      <XCircle size={13} aria-hidden="true" />
                    )}
                    {item.status === "PASS" ? "Pass" : "Fail"}
                  </span>
                  <div>
                    <strong>{item.scenario_id}</strong>
                    {item.error && <small>{item.error}</small>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Panel>
  );
}
