import { useState } from "react";
import { Activity, AlertTriangle, Bot, CheckCircle2, CircleSlash, Gauge, ShieldCheck } from "lucide-react";
import { BarList, Empty, Panel, StatTile } from "../console/charts";
import type { Slice } from "../console/dashboardModel";
import { Table, formatDate, useResource } from "../../customer-admin/shared";
import { TrustEvaluation } from "../../workspace/sections/TrustEvaluation";
import { displayCode, titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { Intro, TenantCell } from "./common";
import { AiReleaseGate, type ReleaseGate } from "../../customer-admin/sections/AiReleaseGate";

type Model = {
  provider: string;
  model: string;
  configured: boolean;
  configuration_version?: string;
  human_review_required?: boolean;
  hidden_chain_of_thought_persisted?: boolean;
};
type Fallback = { provider: string; model: string; configured: boolean; resting?: boolean; skipped?: string };
type Execution = {
  id: string;
  at?: string | null;
  tenant_name?: string | null;
  tenant_key?: string | null;
  customer_name?: string | null;
  provider: string;
  model: string;
  prompt_version?: string | null;
  validation_status?: string | null;
  confidence?: string | null;
  latency_ms?: number | null;
  failed: boolean;
};
type AiActivity = {
  window_days: number;
  total: number;
  failed: number;
  p95_latency_ms: number | null;
  by_tenant: Array<{ tenant_id: string; tenant_name?: string | null; customer_name?: string | null; count: number }>;
  by_model: Array<{ provider: string; model: string; count: number }>;
  by_validation: Record<string, number>;
  latest: Execution[];
};

export function AiControlCenter({ section }: { section: string }) {
  if (section === "Evaluations") return <TrustEvaluation canStart />;
  if (section === "AI runs") return <Executions />;
  if (section === "Agents & guardrails") return <Agents />;
  return <Overview />;
}

const seconds = (ms: number | null | undefined) =>
  ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1)} s`;

/** Which model is in use, and how the AI has been used across every tenant in the last 30 days. */
function Overview() {
  const models = useResource<{ models: Model[]; fallbacks?: Fallback[]; skipped_fallbacks?: Record<string, string> }>(
    "/api/v1/platform-admin/ai/models",
  );
  // Providers named in the setting that cannot be used are listed last, with the reason, instead of disappearing.
  const fallbackRows: Array<Fallback & { order?: number }> = [
    ...(models.data?.fallbacks ?? []).map((item, index) => ({ ...item, order: index + 1 })),
    ...Object.entries(models.data?.skipped_fallbacks ?? {}).map(([provider, reason]) => ({
      provider,
      model: "—",
      configured: false,
      skipped: reason,
    })),
  ];
  const activity = useResource<AiActivity>("/api/v1/platform-admin/console/ai-activity");
  const model = models.data?.models?.[0];
  const data = activity.data;
  const byTenant: Slice[] = (data?.by_tenant ?? []).map((row) => ({
    key: row.tenant_id,
    label:
      row.customer_name && row.customer_name !== row.tenant_name
        ? `${row.customer_name} · ${row.tenant_name}`
        : (row.tenant_name ?? "Tenant"),
    count: row.count,
    tone: "neutral",
  }));
  const byValidation: Slice[] = Object.entries(data?.by_validation ?? {}).map(([key, count]) => ({
    key,
    label: titleCase(key),
    count,
    tone: /FAIL|REJECT|INVALID/i.test(key) ? "critical" : /PASS|VALID/i.test(key) ? "good" : "neutral",
  }));
  return (
    <div className="ac-grid">
      {/* Hero review 2 (F-X1): lead with how AI is used; the pilot gate is folded at the end, and no provider, model
          id, setting name or command is shown (they stay in the runbook). */}
      <section className="ac-stats ar-stats-4" aria-label="AI in the last 30 days">
        <StatTile
          label="Model in use"
          value={model ? (model.configured ? "Configured" : "Not connected") : null}
          detail={
            model ? (model.configured ? "Answers checked before they are shown" : "Rule-based answers") : "Loading"
          }
          icon={<Bot size={18} />}
          tone={model ? (model.configured ? "good" : "warning") : undefined}
        />
        <StatTile
          label="AI runs (30 days)"
          value={data ? data.total : null}
          detail="All tenants"
          icon={<Activity size={18} />}
        />
        <StatTile
          label="Failed runs"
          value={data ? data.failed : null}
          detail={data && data.total ? `${Math.round((data.failed / data.total) * 100)}% of runs` : "No runs"}
          icon={<AlertTriangle size={18} />}
          tone={data ? (data.failed ? "warning" : "good") : undefined}
        />
        <StatTile
          label="Slowest responses (1 in 20)"
          value={data ? seconds(data.p95_latency_ms) : null}
          detail="19 in 20 answers are faster than this"
          icon={<Gauge size={18} />}
        />
      </section>
      <div className="ac-grid two">
        <Panel eyebrow="Last 30 days" title="AI runs by tenant" source={activity}>
          {byTenant.length ? <BarList items={byTenant} colour="series" /> : <p className="ac-muted">No AI runs yet.</p>}
        </Panel>
        <Panel eyebrow="Last 30 days" title="Answer checks" source={activity}>
          <Intro>Every AI answer is checked against its evidence before it is shown.</Intro>
          {byValidation.length ? <BarList items={byValidation} /> : <p className="ac-muted">No AI runs yet.</p>}
        </Panel>
      </div>
      <Panel eyebrow="Configuration" title="Model in use" source={models}>
        {model ? (
          <dl className="cc-details">
            <div>
              <dt>Connection</dt>
              <dd>{model.configured ? "Connected" : "Not connected (rule-based fallback is used)"}</dd>
            </div>
            <div>
              <dt>Human review</dt>
              <dd>{model.human_review_required ? "Required for every decision" : "Not required"}</dd>
            </div>
          </dl>
        ) : (
          <p className="ac-muted">No model is configured.</p>
        )}
        {model && (
          <>
            <h4 className="ar-subhead">Technical detail</h4>
            <dl className="cc-details">
              <div>
                <dt>Configuration version</dt>
                <dd>{model.configuration_version ?? "—"}</dd>
              </div>
              <div>
                <dt>Model&apos;s hidden reasoning stored</dt>
                <dd>{model.hidden_chain_of_thought_persisted ? "Yes" : "No"}</dd>
              </div>
            </dl>
          </>
        )}
      </Panel>
      <Panel eyebrow="When the model is limited or down" title="Backup AI providers" source={models}>
        <Intro>
          If the model in use hits its limit or does not answer, the next provider below answers instead, in this order;
          if none can, MDARIX gives its rule-based answer. Free tiers suit demonstrations on synthetic data only.
        </Intro>
        <Table
          caption="Backup AI providers"
          rows={fallbackRows}
          rowKey={(row) => row.provider}
          empty={{
            title: "No backup AI provider",
            detail: "No backup AI provider is set up. Ask your technical team to add one.",
          }}
          columns={[
            {
              key: "provider",
              label: "Backup",
              render: (row) => <strong>{row.order ? `Backup provider ${row.order}` : "Backup provider"}</strong>,
            },
            {
              key: "state",
              label: "State",
              render: (row) =>
                row.skipped ? (
                  <span className="ar-no">
                    <CircleSlash size={14} aria-hidden="true" /> Not used: {row.skipped}
                  </span>
                ) : !row.configured ? (
                  <span className="ar-no">
                    <CircleSlash size={14} aria-hidden="true" /> No key set
                  </span>
                ) : row.resting ? (
                  <span className="ar-no">
                    <AlertTriangle size={14} aria-hidden="true" /> Resting after a limit
                  </span>
                ) : (
                  <span className="ar-yes">
                    <CheckCircle2 size={14} aria-hidden="true" /> Ready
                  </span>
                ),
            },
          ]}
        />
      </Panel>
      <ReleaseGateStatus />
    </div>
  );
}

/** The latest AI runs on the platform: what ran, where and how it went. Questions and answers stay private. */
function Executions() {
  const activity = useResource<AiActivity>("/api/v1/platform-admin/console/ai-activity");
  const [failedOnly, setFailedOnly] = useState(false);
  const rows = (activity.data?.latest ?? []).filter((row) => !failedOnly || row.failed);
  return (
    <Panel eyebrow="Latest 50 across all tenants" title="AI runs" source={activity}>
      <Intro>
        What ran, for which tenant, and how it went. The questions asked and the answers given stay with the tenant and
        are not shown here.
      </Intro>
      <div className="ca-chips" role="group" aria-label="Show runs">
        <button type="button" className={failedOnly ? "" : "selected"} onClick={() => setFailedOnly(false)}>
          All
        </button>
        <button type="button" className={failedOnly ? "selected" : ""} onClick={() => setFailedOnly(true)}>
          Failed only
        </button>
      </div>
      <Table
        caption="AI runs"
        rows={rows}
        rowKey={(row) => row.id}
        pageSize={15}
        pageNoun="run"
        empty={{ title: failedOnly ? "No failed runs" : "No AI runs yet", detail: "Runs appear as people use AI." }}
        // The AI run's ID is not shown by default; it can be added from the field chooser.
        columns={[
          { key: "when", fields: ["at"], label: "When", render: (row) => formatDate(row.at) },
          {
            key: "tenant",
            fields: ["tenant_name", "tenant_key", "customer_name", "tenant_business_id", "tenant_id"],
            label: "Tenant",
            render: (row) => <TenantCell row={row} />,
          },
          {
            key: "check",
            fields: ["validation_status"],
            label: "Answer check",
            render: (row) => (row.validation_status ? <StatusBadge status={row.validation_status} /> : "—"),
          },
          { key: "confidence", label: "Confidence", render: (row) => titleCase(row.confidence ?? "—") },
          {
            key: "time",
            fields: ["latency_ms"],
            label: "Time",
            numeric: true,
            render: (row) => seconds(row.latency_ms),
          },
          {
            key: "result",
            fields: ["failed"],
            label: "Result",
            render: (row) =>
              row.failed ? (
                <span className="ar-no">
                  <CircleSlash size={14} aria-hidden="true" /> Failed
                </span>
              ) : (
                <span className="ar-yes">
                  <CheckCircle2 size={14} aria-hidden="true" /> Completed
                </span>
              ),
          },
        ]}
      />
    </Panel>
  );
}

/** The AI release gate's four bars, folded: it is about pilots, and what to do for each bar is in the runbook. */
export function ReleaseGateStatus() {
  const gate = useResource<ReleaseGate>("/api/v1/ai/release-gate");
  if (!gate.data) return null;
  return (
    <details className="ar-gate-fold">
      <summary>
        Before AI goes to a pilot · {gate.data.met} of {gate.data.total} checks done
      </summary>
      <AiReleaseGate gate={gate.data} />
    </details>
  );
}

type Agent = { code: string; label: string; allowed: string[]; forbidden: string[] };
type TrustPolicy = {
  policy: string;
  applies_to: string[];
  checks: { check: string; title: string; what: string; on_failure: "BLOCKED" | "WARNING" }[];
  limitation: string;
  feature_set: string;
};

/** The guardrails: the trust check every AI result gets as it is saved, and (full product only) the agent catalog. */
function Agents() {
  const policy = useResource<TrustPolicy>("/api/v1/ai/trust-policy");
  return (
    <>
      <Panel eyebrow="Checked on every AI result" title="Automatic trust check" source={policy}>
        {policy.data && (
          <>
            <p className="ar-notice" role="note">
              <ShieldCheck size={16} aria-hidden="true" /> Every AI result is checked as it is saved, before anyone
              reads it: {policy.data.applies_to.join("; ")}. {policy.data.limitation}
            </p>
            <div className="ar-cards">
              {policy.data.checks.map((check) => (
                <article key={check.check} className="ar-card">
                  <header>
                    <strong>{check.title}</strong>
                  </header>
                  <p>{check.what}</p>
                  <p>
                    {check.on_failure === "BLOCKED" ? (
                      <span className="ar-no">
                        <CircleSlash size={14} aria-hidden="true" /> Blocks the result when it fails
                      </span>
                    ) : (
                      <span className="ar-warn">
                        <AlertTriangle size={14} aria-hidden="true" /> Warns the reader when it fails
                      </span>
                    )}
                  </p>
                </article>
              ))}
            </div>
            <p className="ar-muted">Policy {policy.data.policy}</p>
          </>
        )}
      </Panel>
      {policy.data?.feature_set === "full" && <AgentCatalog />}
    </>
  );
}

/** The AI agents, what each may do, and what is always left to people (the full product only). */
function AgentCatalog() {
  const catalog = useResource<{ agents: Agent[]; human_authority_required?: boolean }>("/api/v1/ai/agents/catalog");
  const agents = catalog.data?.agents ?? [];
  return (
    <Panel eyebrow="Agents and their limits" title="Agents & guardrails" source={catalog}>
      <p className="ar-notice" role="note">
        <ShieldCheck size={16} aria-hidden="true" /> AI suggests; people decide. No agent can approve, reject or declare
        a root cause{catalog.data?.human_authority_required ? ": a person with authority always does" : ""}.
      </p>
      {catalog.data && !agents.length && (
        <Empty title="No AI agents yet" detail="The AI assistants and their limits appear here once they are set up." />
      )}
      <div className="ar-cards">
        {agents.map((agent) => (
          <article key={agent.code} className="ar-card">
            <header>
              <strong>{agent.label || displayCode(agent.code)}</strong>
            </header>
            <h4>May</h4>
            <ul className="ar-chips">
              {agent.allowed.map((action) => (
                <li key={action}>{titleCase(action)}</li>
              ))}
            </ul>
            <h4>Never</h4>
            <ul className="ar-chips ar-chips-no">
              {agent.forbidden.map((action) => (
                <li key={action}>{titleCase(action)}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </Panel>
  );
}
