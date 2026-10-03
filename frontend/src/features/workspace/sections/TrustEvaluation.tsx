// The latest honest evaluation of the real AI pipeline on the synthetic golden scenarios.
import { Bot, CheckCircle2, CircleSlash, ListChecks, XCircle } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { listOf, useResource } from "../../customer-admin/shared";
import "../../investigator/analysis-visuals.css";
import { formatDateTime } from "../../../app/dates";

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
    <Panel
      eyebrow="Tested on synthetic scenarios"
      title="How the AI performs on our test cases"
      state={resource.state}
      error={resource.error}
    >
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
            <ListChecks size={14} aria-hidden="true" /> {evaluation.data_notice} The AI never sees the expected answers;
            they are compared only after it has answered.
            {evaluation.completed_at ? ` Last run ${formatDateTime(evaluation.completed_at)}.` : ""}
          </p>
        </div>
      )}
    </Panel>
  );
}
