import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BadgeCheck,
  Bell,
  Building2,
  ChevronRight,
  Database,
  FileClock,
  KeyRound,
  Mail,
  Plug,
  Plus,
  ShieldCheck,
  Sparkles,
  Timer,
  Users,
  Workflow,
} from "lucide-react";
import { ApiError, requestJson } from "../../../app/apiClient";
import {
  BarList,
  ColumnChart,
  Empty,
  Panel,
  RingMeter,
  StatTile,
  ToneBadge,
  ToneIcon,
  type PanelState,
} from "./charts";
import {
  attentionItems,
  dailyCounts,
  expiryBuckets,
  healthSignals,
  isActiveTenant,
  planMix,
  runOutcomes,
  tenantStatusSlices,
  titleCase,
  worstTone,
  type AuditRow,
  type CustomerRow,
  type ExpiringSubscription,
  type IntegrationRun,
  type Tone,
} from "./dashboardModel";

const SOURCES = {
  customers: "/api/v1/platform-admin/customers?page_size=100",
  expiring: "/api/v1/platform/subscriptions/expiring",
  health: "/api/v1/admin/health-summary",
  operations: "/api/v1/admin/operations-summary",
  security: "/api/v1/admin/security-summary",
  ai: "/api/v1/admin/ai-summary",
  retention: "/api/v1/admin/retention-status",
  smtp: "/api/v1/admin/smtp-status",
  runs: "/api/v1/admin/integrations/runs",
  audit: "/api/v1/admin/audit-history",
  users: "/api/v1/admin/identity/users",
  connectors: "/api/v1/admin/configuration/connectors",
} as const;

type SourceKey = keyof typeof SOURCES;
type Source = { state: PanelState; data: any; error?: string };
type Sources = Record<SourceKey, Source>;

const TREND_DAYS = 14;
const initial = Object.fromEntries(
  Object.keys(SOURCES).map((key) => [key, { state: "loading", data: null }]),
) as Sources;
const asList = (value: any): any[] => (Array.isArray(value) ? value : (value?.items ?? []));
const MAX_CUSTOMER_PAGES = 20;

/** The customer directory is paged (100 per page); the dashboard needs every tenant for its counts. */
async function fetchAllCustomers() {
  const first = await requestJson<any>(SOURCES.customers);
  const pages = Math.min(Number(first?.pages) || 1, MAX_CUSTOMER_PAGES);
  const rest = await Promise.all(
    Array.from({ length: pages - 1 }, (_, index) => requestJson<any>(`${SOURCES.customers}&page=${index + 2}`)),
  );
  return { ...first, items: [first, ...rest].flatMap(asList) };
}

function useSources(refreshKey: number) {
  const [sources, setSources] = useState<Sources>(initial);
  const [refreshing, setRefreshing] = useState(false);
  useEffect(() => {
    let current = true;
    setRefreshing(true);
    const keys = Object.keys(SOURCES) as SourceKey[];
    Promise.allSettled(
      keys.map((key) => (key === "customers" ? fetchAllCustomers() : requestJson<any>(SOURCES[key]))),
    ).then((results) => {
      if (!current) return;
      const next = {} as Sources;
      results.forEach((result, index) => {
        next[keys[index]] =
          result.status === "fulfilled"
            ? { state: "ready", data: result.value }
            : {
                state: result.reason instanceof ApiError && result.reason.status === 403 ? "forbidden" : "error",
                data: null,
                error: result.reason instanceof Error ? result.reason.message : undefined,
              };
      });
      setSources(next);
      setRefreshing(false);
    });
    return () => {
      current = false;
    };
  }, [refreshKey]);
  return { sources, refreshing };
}

export type OverviewTarget = { domain: string; item?: string };

const SIGNAL_ICONS: Record<string, typeof Activity> = {
  connectors: Plug,
  deadLetter: Workflow,
  queue: Timer,
  security: ShieldCheck,
  invites: Mail,
  mappings: Database,
  ai: Sparkles,
  retention: FileClock,
  smtp: Mail,
  worker: Activity,
};

export function AdminOverview({
  refreshKey,
  onOpen,
  onCreateCustomer,
  onUpdated,
}: {
  refreshKey: number;
  onOpen: (target: OverviewTarget) => void;
  onCreateCustomer: () => void;
  onUpdated: (at: Date) => void;
}) {
  const { sources, refreshing } = useSources(refreshKey);
  const loading = Object.values(sources).some((source) => source.state === "loading");
  useEffect(() => {
    if (!loading) onUpdated(new Date());
  }, [loading]);

  const customers: CustomerRow[] = asList(sources.customers.data);
  const customerTotal: number = sources.customers.data?.total ?? customers.length;
  const expiring: ExpiringSubscription[] = asList(sources.expiring.data);
  const runs: IntegrationRun[] = asList(sources.runs.data);
  const audit: AuditRow[] = asList(sources.audit.data);
  const users: any[] = asList(sources.users.data);
  const connectors: any[] = asList(sources.connectors.data);

  const model = useMemo(() => {
    const signals = healthSignals({
      health: sources.health.data,
      operations: sources.operations.data,
      security: sources.security.data,
      ai: sources.ai.data,
      retention: sources.retention.data,
      smtp: sources.smtp.data,
    });
    const attention = attentionItems(customers, expiring, sources.health.data?.alerts ?? []);
    return {
      signals,
      attention,
      statuses: tenantStatusSlices(customers),
      expiry: expiryBuckets(expiring),
      plans: planMix(customers),
      outcomes: runOutcomes(runs),
      auditTrend: dailyCounts(
        audit.map((row) => row.created_at),
        TREND_DAYS,
      ),
      runTrend: dailyCounts(
        runs.map((run) => run.started_at),
        TREND_DAYS,
      ),
      active: customers.filter(isActiveTenant).length,
      seats: customers.reduce((sum, customer) => sum + (customer.seat_usage ?? 0), 0),
    };
  }, [sources]);

  const failingSources = (Object.keys(SOURCES) as SourceKey[]).filter((key) =>
    ["error", "forbidden"].includes(sources[key].state),
  );
  const overallTone: Tone = loading
    ? "neutral"
    : worstTone([...model.attention.map((item) => item.tone), ...model.signals.map((signal) => signal.tone)]);
  const needsAction = model.attention.length;
  const headline = loading
    ? "Checking platform status…"
    : overallTone === "good"
      ? "All monitored platform checks are healthy"
      : needsAction
        ? `${needsAction} ${needsAction === 1 ? "item needs" : "items need"} attention`
        : "Some checks need review";

  const expiringSoon = expiring.filter((row) => Number(row.days_remaining) <= 30).length;
  const openAlerts = (sources.health.data?.alerts ?? []).reduce(
    (sum: number, alert: any) => sum + (Number(alert.count) || 0),
    0,
  );

  return (
    <div className={`ac-overview ${refreshing && !loading ? "is-refreshing" : ""}`}>
      <section className={`ac-hero tone-${overallTone}`} aria-live="polite">
        <div className="ac-hero-status">
          <span className="ac-hero-icon">
            <ToneIcon tone={overallTone} size={34} />
          </span>
          <div>
            <p className="ac-eyebrow">Platform status</p>
            <h2>{headline}</h2>
            <p>
              {loading
                ? "Reading live administrator sources."
                : failingSources.length
                  ? `${failingSources.length} of ${Object.keys(SOURCES).length} data sources are unavailable; their panels say so.`
                  : `All ${Object.keys(SOURCES).length} administrator data sources responded.`}
            </p>
          </div>
        </div>
        <div className="ac-hero-meters">
          <RingMeter value={model.active} total={customers.length} label="Tenants active" />
          <RingMeter
            value={model.outcomes.succeeded}
            total={model.outcomes.succeeded + model.outcomes.failed}
            label="Finished runs succeeded"
          />
        </div>
        <div className="ac-hero-actions">
          <button type="button" className="ac-primary" onClick={onCreateCustomer}>
            <Plus size={16} /> Create customer
          </button>
          <button type="button" className="ac-secondary" onClick={() => onOpen({ domain: "Operations" })}>
            <Activity size={16} /> Operations
          </button>
        </div>
      </section>

      <section className="ac-stats" aria-label="Key figures">
        <StatTile
          label="Customers"
          value={sources.customers.state === "ready" ? customerTotal : null}
          detail={`${model.active} active tenants`}
          icon={<Building2 size={18} />}
          onOpen={() => onOpen({ domain: "Customers & Tenants", item: "Customer Directory" })}
        />
        <StatTile
          label="Seats in use"
          value={sources.customers.state === "ready" ? model.seats : null}
          detail="Tenant memberships"
          icon={<Users size={18} />}
          onOpen={() => onOpen({ domain: "Plans & Licensing", item: "Entitlements" })}
        />
        <StatTile
          label="Platform users"
          value={sources.users.state === "ready" ? users.length : null}
          detail={`${users.filter((user) => String(user.status).toUpperCase() === "ACTIVE").length} active`}
          icon={<KeyRound size={18} />}
          onOpen={() => onOpen({ domain: "Identity & Access", item: "Platform users" })}
        />
        <StatTile
          label="Expiring ≤ 30 days"
          value={sources.expiring.state === "ready" ? expiringSoon : null}
          detail={expiringSoon ? "Renewals to action" : "No renewals due"}
          tone={sources.expiring.state === "ready" ? (expiringSoon ? "warning" : "good") : undefined}
          icon={<FileClock size={18} />}
          onOpen={() => onOpen({ domain: "Plans & Licensing", item: "Expirations" })}
        />
        <StatTile
          label="Open alerts"
          value={sources.health.state === "ready" ? openAlerts : null}
          detail={openAlerts ? "Raised by health checks" : "No open alerts"}
          tone={sources.health.state === "ready" ? (openAlerts ? "critical" : "good") : undefined}
          icon={<Bell size={18} />}
          onOpen={() => onOpen({ domain: "Operations", item: "Incidents" })}
        />
        <StatTile
          label="Integration success"
          value={model.outcomes.successRate === null ? null : `${model.outcomes.successRate}%`}
          detail={
            sources.runs.state !== "ready"
              ? "Runs unavailable"
              : model.outcomes.total
                ? `${model.outcomes.failed} failed of ${model.outcomes.total} runs`
                : "No runs recorded yet"
          }
          tone={model.outcomes.total ? (model.outcomes.failed ? "critical" : "good") : undefined}
          icon={<Plug size={18} />}
          onOpen={() => onOpen({ domain: "Integrations", item: "Integration runs" })}
        />
      </section>

      <div className="ac-grid two">
        <Panel
          eyebrow="Customers & tenants"
          title="Tenant lifecycle"
          state={sources.customers.state}
          error={sources.customers.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Customers & Tenants", item: "Tenant Management" })} />}
        >
          {customers.length ? (
            <>
              <BarList items={model.statuses} />
              {customerTotal > customers.length && (
                <p className="ac-note">
                  Showing the first {customers.length} of {customerTotal} tenants.
                </p>
              )}
            </>
          ) : (
            <Empty title="No tenants yet" detail="Create a customer to provision the first tenant." />
          )}
        </Panel>
        <Panel eyebrow="Operations" title="Health checks">
          <ul className="ac-signals">
            {model.signals.map((signal) => {
              const Icon = SIGNAL_ICONS[signal.key] ?? Activity;
              return (
                <li key={signal.key} className={`tone-${signal.tone}`}>
                  <span className="ac-signal-picture" aria-hidden="true">
                    <Icon size={20} />
                    <ToneIcon tone={signal.tone} size={14} />
                  </span>
                  <span className="ac-signal-text">
                    <strong>{signal.label}</strong>
                    <small>{signal.detail}</small>
                  </span>
                  <span className="ac-signal-value">
                    {signal.value === null ? <ToneBadge tone="neutral" label="No data" /> : signal.value}
                  </span>
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>

      <div className="ac-grid two">
        <Panel
          eyebrow="Audit"
          title={`Audit activity · last ${TREND_DAYS} days`}
          state={sources.audit.state}
          error={sources.audit.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Security", item: "Security events" })} />}
        >
          <ColumnChart data={model.auditTrend} unit="events" caption="from the latest 200 audit events" />
        </Panel>
        <Panel
          eyebrow="Plans & licensing"
          title="Subscription expiry"
          state={sources.expiring.state}
          error={sources.expiring.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Plans & Licensing", item: "Expirations" })} />}
        >
          {expiring.length ? (
            <BarList items={model.expiry} />
          ) : (
            <Empty title="No subscriptions tracked" detail="Subscription lifecycles appear once plans are assigned." />
          )}
        </Panel>
      </div>

      <div className="ac-grid two">
        <Panel
          eyebrow="Integrations"
          title={`Integration runs · last ${TREND_DAYS} days`}
          state={sources.runs.state}
          error={sources.runs.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Integrations", item: "Integration runs" })} />}
        >
          <ColumnChart data={model.runTrend} unit="runs" caption="by start date" />
          <div className="ac-inline-stats">
            <span>
              <ToneIcon tone="good" size={14} /> {model.outcomes.succeeded} succeeded
            </span>
            <span>
              <ToneIcon tone={model.outcomes.failed ? "critical" : "good"} size={14} /> {model.outcomes.failed} failed
            </span>
            <span>
              <ToneIcon tone="neutral" size={14} /> {model.outcomes.inProgress} other / in progress
            </span>
            <span>
              <Plug size={14} aria-hidden="true" /> {connectors.length} connectors configured
            </span>
          </div>
        </Panel>
        <Panel
          eyebrow="Plans & licensing"
          title="Plan mix"
          state={sources.customers.state}
          error={sources.customers.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Plans & Licensing", item: "Plans" })} />}
        >
          {customers.length ? (
            <BarList items={model.plans} colour="series" />
          ) : (
            <Empty title="No plan assignments" detail="Tenants and their plans appear here." />
          )}
        </Panel>
      </div>

      <div className="ac-grid two">
        <Panel
          eyebrow="Requires attention"
          title="What needs action"
          state={loading ? "loading" : "ready"}
          action={
            needsAction ? <ToneBadge tone={overallTone} label={`${needsAction} open`} /> : <ToneBadge tone="good" />
          }
        >
          {needsAction ? (
            <ul className="ac-attention">
              {model.attention.slice(0, 8).map((item) => (
                <li key={item.key}>
                  <ToneIcon tone={item.tone} size={18} />
                  <span>
                    <strong>{item.title}</strong>
                    <small>{item.detail}</small>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="Nothing needs action" detail="Healthy systems stay quiet. Exceptions will appear here." />
          )}
        </Panel>
        <Panel
          eyebrow="Audit"
          title="Recent activity"
          state={sources.audit.state}
          error={sources.audit.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Customers & Tenants", item: "Tenant Audit" })} />}
        >
          {audit.length ? (
            <div className="ac-table-wrap">
              <table className="ac-table">
                <thead>
                  <tr>
                    <th scope="col">Action</th>
                    <th scope="col">Object</th>
                    <th scope="col">When</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.slice(0, 7).map((row, index) => (
                    <tr key={`${row.created_at}-${index}`}>
                      <td>{titleCase(row.action ?? "Event")}</td>
                      <td>{row.entity_type ? titleCase(row.entity_type) : "—"}</td>
                      <td className="num">{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty title="No audit events yet" detail="Administrative actions are recorded here." />
          )}
        </Panel>
      </div>

      <Panel eyebrow="Governance · declared by the security service" title="Security controls" className="ac-posture">
        <ul className="ac-posture-list">
          {(sources.security.data?.controls ?? []).map((control: string) => (
            <li key={control}>
              <BadgeCheck size={16} aria-hidden="true" /> {control}
            </li>
          ))}
          {sources.ai.data && (
            <li>
              <BadgeCheck size={16} aria-hidden="true" /> AI output requires human review
            </li>
          )}
          {sources.retention.data?.policy && (
            <li>
              <BadgeCheck size={16} aria-hidden="true" /> Audit retention: {sources.retention.data.policy}
            </li>
          )}
          {!sources.security.data && !sources.ai.data && !sources.retention.data && (
            <li className="ac-muted">Control evidence is unavailable.</li>
          )}
        </ul>
      </Panel>
    </div>
  );
}

function OpenLink({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="ac-link" onClick={onClick}>
      Open <ChevronRight size={14} aria-hidden="true" />
    </button>
  );
}
