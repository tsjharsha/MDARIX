import { useState } from "react";
import { AlertTriangle, Play } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { useCan, useWorkspace } from "../workspaceContext";
import { countOf } from "./common";
import {
  RULE_LIMITS,
  RULE_REASON_MAX,
  ruleBody,
  ruleChanged,
  ruleForm,
  ruleProblem,
  ruleSentence,
  runIds,
  runSummary,
  type DetectionRule,
  type RuleForm,
  type RuleRunResult,
} from "../signals";

/**
 * Detection rules: the rule that opens signals from complaints (how many complaints about the same problem, within how
 * many days), changed only with a reason, and a run on demand. The server keeps every version of a rule.
 */
export function DetectionRules({ onOpenSignal }: { onOpenSignal: (reference: string) => void }) {
  const { notify } = useWorkspace();
  const canTriage = useCan("signal.triage");
  const rules = useResource<DetectionRule[]>("/api/v1/triage/rules");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RuleRunResult | null>(null);
  const [runError, setRunError] = useState("");
  const run = async () => {
    setRunning(true);
    setRunError("");
    try {
      const outcome = await send<RuleRunResult>("/api/v1/triage/rules/run", "POST");
      setResult(outcome ?? {});
      notify(runSummary(outcome ?? {}));
      rules.reload();
    } catch (reason) {
      setRunError(errorText(reason, "Detection could not be run."));
    } finally {
      setRunning(false);
    }
  };
  const items = listOf(rules.data) as DetectionRule[];
  return (
    <>
      <Panel
        eyebrow="Signals"
        title="Detection rules"
        source={rules}
        action={
          canTriage ? (
            <button type="button" className="ac-primary" disabled={running} onClick={() => void run()}>
              <Play size={16} aria-hidden="true" /> {running ? "Running…" : "Run detection now"}
            </button>
          ) : undefined
        }
      >
        <p className="ac-muted">
          A rule opens a signal for people to triage; it never decides anything about the complaints. Detection also
          runs on its own as complaints arrive.
        </p>
        {runError && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {runError}
          </p>
        )}
        {result && <RunResult result={result} onOpenSignal={onOpenSignal} />}
        {!items.length && <Empty title="No detection rules" detail="Your organization has no detection rule yet." />}
      </Panel>
      {items.map((rule) => (
        <RulePanel key={rule.rule_code} rule={rule} canEdit={canTriage} onSaved={rules.reload} />
      ))}
    </>
  );
}

function RunResult({ result, onOpenSignal }: { result: RuleRunResult; onOpenSignal: (reference: string) => void }) {
  const groups: Array<{ label: string; value: RuleRunResult[keyof RuleRunResult] }> = [
    { label: "Created", value: result.created },
    { label: "Updated", value: result.updated },
    { label: "Reopened from monitoring", value: result.monitor_reopened },
  ];
  return (
    <section className="ca-drawer-section" aria-label="Detection result" role="status">
      <h3>{runSummary(result)}</h3>
      {groups.map((group) => {
        const { ids } = runIds(group.value);
        if (!ids.length) return null;
        return (
          <p key={group.label}>
            {group.label}:{" "}
            {ids.map((id, index) => (
              <span key={id}>
                {index > 0 && ", "}
                <button type="button" className="ac-link" onClick={() => onOpenSignal(id)}>
                  {id}
                </button>
              </span>
            ))}
          </p>
        );
      })}
    </section>
  );
}

function RulePanel({ rule, canEdit, onSaved }: { rule: DetectionRule; canEdit: boolean; onSaved: () => void }) {
  const { notify } = useWorkspace();
  const [form, setForm] = useState<RuleForm>(() => ruleForm(rule));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const changed = ruleChanged(rule, form);
  const problem = ruleProblem(form);
  const name = safeText(rule.label) ?? "Complaint threshold";
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!changed || problem) return;
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/triage/rules/${encodeURIComponent(rule.rule_code)}`, "PUT", ruleBody(form));
      notify(`${name}: the rule was changed.`);
      setForm((current) => ({ ...current, reason: "" }));
      onSaved();
    } catch (reason) {
      setError(errorText(reason, "The rule was not changed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      eyebrow="Detection rule"
      title={name}
      action={<ToneBadge tone={rule.enabled ? "good" : "neutral"} label={rule.enabled ? "On" : "Off"} />}
    >
      {safeText(rule.description) && <p>{rule.description}</p>}
      <p>
        <strong>{ruleSentence(rule)}</strong>
      </p>
      <dl className="ca-facts">
        <div>
          <dt>Rule</dt>
          <dd>{rule.rule_code}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{rule.version ?? "—"}</dd>
        </div>
        <div>
          <dt>Changed</dt>
          <dd>
            {formatDate(rule.updated_at)}
            {safeText(rule.updated_by_name) ? ` · ${rule.updated_by_name}` : ""}
          </dd>
        </div>
        <div>
          <dt>Last run</dt>
          <dd>{rule.last_run_at ? formatDate(rule.last_run_at) : "Not run yet"}</dd>
        </div>
        {rule.defaults && (
          <div>
            <dt>Default setting</dt>
            <dd>
              {typeof rule.defaults.min_complaints === "number"
                ? countOf(rule.defaults.min_complaints, "complaint")
                : "— complaints"}{" "}
              in {typeof rule.defaults.window_days === "number" ? countOf(rule.defaults.window_days, "day") : "— days"}
            </dd>
          </div>
        )}
      </dl>
      {canEdit && (
        <form className="ca-form ca-drawer-section" onSubmit={submit}>
          <h3>Change the rule</h3>
          <label className="ca-check">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
            />
            The rule is on (it opens signals)
          </label>
          <div className="ca-form-grid">
            <label className="ca-field">
              Minimum complaints
              <input
                type="number"
                inputMode="numeric"
                min={RULE_LIMITS.minComplaints[0]}
                max={RULE_LIMITS.minComplaints[1]}
                step={1}
                value={form.minComplaints}
                onChange={(event) => setForm({ ...form, minComplaints: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Within (days)
              <input
                type="number"
                inputMode="numeric"
                min={RULE_LIMITS.windowDays[0]}
                max={RULE_LIMITS.windowDays[1]}
                step={1}
                value={form.windowDays}
                onChange={(event) => setForm({ ...form, windowDays: event.target.value })}
              />
            </label>
          </div>
          <label className="ca-field">
            Reason for the change
            <textarea
              required
              rows={3}
              maxLength={RULE_REASON_MAX}
              value={form.reason}
              placeholder="At least 10 characters"
              onChange={(event) => setForm({ ...form, reason: event.target.value })}
            />
          </label>
          {changed && problem && <p className="uw-hint">{problem}</p>}
          {error && (
            <p className="ca-inline-error" role="alert">
              <AlertTriangle size={15} aria-hidden="true" /> {error}
            </p>
          )}
          <p className="ac-muted">A change makes a new version of the rule, recorded in the audit trail.</p>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={busy || (!changed && !form.reason)}
              onClick={() => setForm(ruleForm(rule))}
            >
              Undo changes
            </button>
            <button type="submit" className="ac-primary" disabled={busy || !changed || !!problem}>
              {busy ? "Saving…" : "Save rule"}
            </button>
          </div>
        </form>
      )}
    </Panel>
  );
}
