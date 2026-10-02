import { useState } from "react";
import { Activity, AlertTriangle, Bot, CheckCircle2, CircleSlash, Gauge, ShieldCheck } from "lucide-react";
import { BarList, Panel, StatTile } from "../console/charts";
import type { Slice } from "../console/dashboardModel";
import { Table, formatDate, useResource } from "../../customer-admin/shared";
import { TrustEvaluation } from "../../workspace/sections/TrustEvaluation";
import { titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { Intro, Pager, TenantCell } from "./common";

type Model = {
  provider: string;
  model: string;
  configured: boolean;
  configuration_version?: string;
  human_review_required?: boolean;
  hidden_chain_of_thought_persisted?: boolean;
};
type Fallback = { provider: string; model: string; configured: boolean; resting?: boolean };
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
  if (section === "Evaluations") return <TrustEvaluation />;
  if (section === "Executions") return <Executions />;
  if (section === "Agents & guardrails") return <Agents />;
  return <Overview />;
}

const seconds = (ms: number | null | undefined) =>
  ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1)} s`;

/** Which model is in use, and how the AI has been used across every tenant in the last 30 days. */
function Overview() {
  const models = useResource<{ models: Model[]; fallbacks?: Fallback[] }>("/api/v1/platform-admin/ai/models");
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
      <section className="ac-stats ar-stats-4" aria-label="AI in the last 30 days">
        <StatTile
          label="Model"
          value={model ? model.model : null}
          detail={model ? `${model.provider} · ${model.configured ? "connected" : "not connected"}` : "Loading"}
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
          label="Slowest 5%"
          value={data ? seconds(data.p95_latency_ms) : null}
          detail="95th percentile response time"
          icon={<Gauge size={18} />}
        />
      </section>
      <div className="ac-grid two">
        <Panel eyebrow="Last 30 days" title="AI runs by tenant" state={activity.state} error={activity.error}>
          {byTenant.length ? <BarList items={byTenant} colour="series" /> : <p className="ac-muted">No AI runs yet.</p>}
        </Panel>
        <Panel eyebrow="Last 30 days" title="Answer checks" state={activity.state} error={activity.error}>
          <Intro>Every AI answer is checked against its evidence before it is shown.</Intro>
          {byValidation.length ? <BarList items={byValidation} /> : <p className="ac-muted">No AI runs yet.</p>}
        </Panel>
      </div>
      <Panel eyebrow="Configuration" title="Model in use" state={models.state} error={models.error}>
        {model ? (
          <dl className="cc-details">
            <div>
              <dt>Provider</dt>
              <dd>{model.provider}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd>{model.model}</dd>
            </div>
            <div>
              <dt>Connection</dt>
              <dd>{model.configured ? "Connected" : "Not connected (rule-based fallback is used)"}</dd>
            </div>
            <div>
              <dt>Configuration version</dt>
              <dd>{model.configuration_version ?? "—"}</dd>
            </div>
            <div>
              <dt>Human review</dt>
              <dd>{model.human_review_required ? "Required for every decision" : "Not required"}</dd>
            </div>
            <div>
              <dt>Hidden reasoning stored</dt>
              <dd>{model.hidden_chain_of_thought_persisted ? "Yes" : "No"}</dd>
            </div>
          </dl>
        ) : (
          <p className="ac-muted">No model is configured.</p>
        )}
      </Panel>
      <Panel
        eyebrow="When the model is limited or down"
        title="Fallback providers"
        state={models.state}
        error={models.error}
      >
        <Intro>
          If the model in use hits its limit or does not answer, the next provider below answers instead, in this order;
          if none can, MDARIX gives its rule-based answer. Free tiers suit demonstrations on synthetic data only.
        </Intro>
        <Table
          caption="Fallback providers"
          rows={(models.data?.fallbacks ?? []).map((item, index) => ({ ...item, order: index + 1 }))}
          rowKey={(row) => row.provider}
          empty={{
            title: "No fallback configured",
            detail: "Set MDARIX_GENAI_FALLBACKS and each provider's key on the server (see the AI provider runbook).",
          }}
          columns={[
            { key: "order", label: "Order", numeric: true, render: (row) => row.order },
            { key: "provider", label: "Provider", render: (row) => <strong>{titleCase(row.provider)}</strong> },
            { key: "model", label: "Model", render: (row) => row.model },
            {
              key: "state",
              label: "State",
              render: (row) =>
                !row.configured ? (
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
    </div>
  );
}

/** The latest AI runs on the platform: what ran, where and how it went. Questions and answers stay private. */
function Executions() {
  const activity = useResource<AiActivity>("/api/v1/platform-admin/console/ai-activity");
  const [failedOnly, setFailedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const all = (activity.data?.latest ?? []).filter((row) => !failedOnly || row.failed);
  const pages = Math.max(1, Math.ceil(all.length / 15));
  const rows = all.slice((Math.min(page, pages) - 1) * 15, Math.min(page, pages) * 15);
  return (
    <Panel eyebrow="Latest 50 across all tenants" title="AI runs" state={activity.state} error={activity.error}>
      <Intro>
        What ran, for which tenant, and how it went. The questions asked and the answers given stay with the tenant and
        are not shown here.
      </Intro>
      <div className="ca-chips" role="group" aria-label="Show runs">
        <button
          type="button"
          className={failedOnly ? "" : "selected"}
          onClick={() => (setFailedOnly(false), setPage(1))}
        >
          All
        </button>
        <button
          type="button"
          className={failedOnly ? "selected" : ""}
          onClick={() => (setFailedOnly(true), setPage(1))}
        >
          Failed only
        </button>
      </div>
      <Table
        caption="AI runs"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{ title: failedOnly ? "No failed runs" : "No AI runs yet", detail: "Runs appear as people use AI." }}
        columns={[
          { key: "when", fields: ["at"], label: "When", render: (row) => formatDate(row.at) },
          {
            key: "tenant",
            fields: ["tenant_name", "tenant_key", "customer_name", "tenant_id"],
            label: "Tenant",
            render: (row) => <TenantCell row={row} />,
          },
          {
            key: "model",
            fields: ["model", "provider"],
            label: "Model",
            render: (row) => (
              <span className="cc-stack">
                <strong>{row.model}</strong>
                <small>{row.provider}</small>
              </span>
            ),
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
      <Pager page={Math.min(page, pages)} pages={pages} total={all.length} noun="run" onPage={setPage} />
    </Panel>
  );
}

type Agent = { code: string; label: string; allowed: string[]; forbidden: string[] };

/** The AI agents, what each may do, and what is always left to people. */
function Agents() {
  const catalog = useResource<{ agents: Agent[]; human_authority_required?: boolean }>("/api/v1/ai/agents/catalog");
  const agents = catalog.data?.agents ?? [];
  return (
    <Panel eyebrow="Agents and their limits" title="Agents & guardrails" state={catalog.state} error={catalog.error}>
      <p className="ar-notice" role="note">
        <ShieldCheck size={16} aria-hidden="true" /> AI suggests; people decide. No agent can approve, reject or declare
        a root cause{catalog.data?.human_authority_required ? ": a person with authority always does" : ""}.
      </p>
      <div className="ar-cards">
        {agents.map((agent) => (
          <article key={agent.code} className="ar-card">
            <header>
              <span className="cc-stack">
                <strong>{agent.label}</strong>
                <small>{agent.code}</small>
              </span>
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
