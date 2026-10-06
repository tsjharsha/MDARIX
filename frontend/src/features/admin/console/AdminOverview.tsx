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
import { BarList, ColumnChart, Empty, Panel, RingMeter, ToneBadge, ToneIcon, type PanelState } from "./charts";
import {
  attentionItems,
  healthSignals,
  isActiveTenant,
  tenantStatusSlices,
  titleCase,
  worstTone,
  type CustomerRow,
  type ExpiringSubscription,
  type Slice,
  type Tone,
} from "./dashboardModel";
import { KpiTile, TrendChart, toPoints, type DailyRow, type TrendPoint } from "./trendCharts";
import { formatDateTime } from "../../../app/dates";
import { safeText } from "../../../app/displayId";

type DashboardTrends = {
  days: number;
  ai_runs: DailyRow[];
  integration_runs: DailyRow[];
  audit_events: DailyRow[];
  new_tenants: DailyRow[];
  tenants_by_plan: Array<{ label: string; count: number }>;
  tenants_by_region: Array<{ label: string; count: number }>;
  licences_ending: Array<{ month: string; count: number }>;
};

const slices = (
  rows: Array<{ label: string; count: number }> | undefined,
  rename = (label: string) => label,
): Slice[] =>
  (rows ?? []).map((row) => ({ key: row.label, label: rename(row.label), count: row.count, tone: "neutral" }));

const SOURCES = {
  customers: "/api/v1/platform-admin/customers?page_size=100",
  expiring: "/api/v1/platform/subscriptions/expiring",
  health: "/api/v1/admin/health-summary",
  operations: "/api/v1/admin/operations-summary",
  security: "/api/v1/admin/security-summary",
  ai: "/api/v1/admin/ai-summary",
  retention: "/api/v1/admin/retention-status",
  smtp: "/api/v1/admin/smtp-status",
  // Platform-wide: daily activity and the shape of the customer base, and the latest audit events of every tenant.
  dashboard: "/api/v1/platform-admin/console/dashboard",
  audit: "/api/v1/platform-admin/console/audit?page_size=8",
  users: "/api/v1/admin/identity/users",
} as const;

type SourceKey = keyof typeof SOURCES;
type Source = { state: PanelState; data: any; error?: string };
type Sources = Record<SourceKey, Source>;

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
  const audit: any[] = asList(sources.audit.data);
  const users: any[] = asList(sources.users.data);
  const trends: DashboardTrends | null = sources.dashboard.data;

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
    const ai = toPoints(trends?.ai_runs, "completed", "failed", true);
    const runs = toPoints(trends?.integration_runs, "completed", "failed", true, ["warnings"]);
    const events = toPoints(trends?.audit_events, "events", "refused");
    const tenants = toPoints(trends?.new_tenants, "tenants");
    const sum = (points: TrendPoint[], key: "primary" | "secondary") =>
      points.reduce((total, point) => total + (point[key] ?? 0), 0);
    return {
      signals,
      attention,
      statuses: tenantStatusSlices(customers),
      active: customers.filter(isActiveTenant).length,
      seats: customers.reduce((sum, customer) => sum + (customer.seat_usage ?? 0), 0),
      ai,
      runs,
      events,
      tenants,
      aiTotal: sum(ai, "primary"),
      aiFailed: sum(ai, "secondary"),
      runTotal: sum(runs, "primary"),
      runFailed: sum(runs, "secondary"),
      eventTotal: sum(events, "primary"),
      refused: sum(events, "secondary"),
      plans: slices(trends?.tenants_by_plan),
      regions: slices(trends?.tenants_by_region, (label) => (label === "UNSPECIFIED" ? "Not specified" : label)),
      renewals: (trends?.licences_ending ?? []).map((row) => ({
        date: row.month,
        label: new Date(`${row.month}T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "2-digit" }),
        count: row.count,
      })),
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
  const trendsReady = sources.dashboard.state === "ready";
  const days = trends?.days ?? 30;

  return (
    <div className={`ac-overview ac-dashboard ${refreshing && !loading ? "is-refreshing" : ""}`}>
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
            value={model.runTotal - model.runFailed}
            total={model.runTotal}
            label={`Integration runs succeeded · ${days} days`}
          />
          <RingMeter
            value={model.aiTotal - model.aiFailed}
            total={model.aiTotal}
            label={`AI runs completed · ${days} days`}
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

      <section className="ac-kpis" aria-label="Key figures">
        <KpiTile
          label="Customers"
          value={sources.customers.state === "ready" ? customerTotal : null}
          detail={`${model.active} active tenants`}
          icon={<Building2 size={18} />}
          series={model.tenants.map((point) => point.primary)}
          seriesLabel={`New tenants per day, last ${days} days`}
          onOpen={() => onOpen({ domain: "Customers & Tenants", item: "Customers" })}
        />
        <KpiTile
          label="Seats in use"
          value={sources.customers.state === "ready" ? model.seats : null}
          detail="Tenant memberships"
          icon={<Users size={18} />}
          onOpen={() => onOpen({ domain: "Plans & Licensing", item: "Subscriptions" })}
        />
        <KpiTile
          label="Platform users"
          value={sources.users.state === "ready" ? users.length : null}
          detail={`${users.filter((user) => String(user.status).toUpperCase() === "ACTIVE").length} active`}
          icon={<KeyRound size={18} />}
          onOpen={() => onOpen({ domain: "Identity & Access", item: "Platform users" })}
        />
        <KpiTile
          label="Renewals ≤ 30 days"
          value={sources.expiring.state === "ready" ? expiringSoon : null}
          detail={expiringSoon ? "Licenses to renew" : "No renewals due"}
          tone={sources.expiring.state === "ready" ? (expiringSoon ? "warning" : "good") : undefined}
          icon={<FileClock size={18} />}
          onOpen={() => onOpen({ domain: "Plans & Licensing", item: "Renewals" })}
        />
        <KpiTile
          label="AI runs"
          value={trendsReady ? model.aiTotal : null}
          detail={`${model.aiFailed} failed · last ${days} days`}
          tone={trendsReady ? (model.aiFailed ? "warning" : "good") : undefined}
          icon={<Sparkles size={18} />}
          series={model.ai.map((point) => point.primary)}
          seriesLabel={`AI runs per day, last ${days} days`}
          onOpen={() => onOpen({ domain: "AI Control Center", item: "Executions" })}
        />
        <KpiTile
          label="Integration runs"
          value={trendsReady ? model.runTotal : null}
          detail={`${model.runFailed} failed · last ${days} days`}
          tone={trendsReady ? (model.runFailed ? "critical" : "good") : undefined}
          icon={<Plug size={18} />}
          series={model.runs.map((point) => point.primary)}
          seriesLabel={`Integration runs per day, last ${days} days`}
          onOpen={() => onOpen({ domain: "Integrations", item: "Runs & failures" })}
        />
        <KpiTile
          label="Audit events"
          value={trendsReady ? model.eventTotal : null}
          detail={`${model.refused} refused or failed`}
          tone={trendsReady ? (model.refused ? "warning" : "good") : undefined}
          icon={<ShieldCheck size={18} />}
          series={model.events.map((point) => point.primary)}
          seriesLabel={`Audit events per day, last ${days} days`}
          onOpen={() => onOpen({ domain: "Security", item: "Audit trail" })}
        />
        <KpiTile
          label="Open alerts"
          value={sources.health.state === "ready" ? openAlerts : null}
          detail={openAlerts ? "Raised by health checks" : "No open alerts"}
          tone={sources.health.state === "ready" ? (openAlerts ? "critical" : "good") : undefined}
          icon={<Bell size={18} />}
          onOpen={() => onOpen({ domain: "Operations", item: "System health" })}
        />
      </section>

      <section className="ac-grid three" aria-label={`Activity, last ${days} days`}>
        <Panel
          eyebrow={`Last ${days} days · all tenants`}
          title="AI runs"
          state={sources.dashboard.state}
          error={sources.dashboard.error}
          action={<OpenLink onClick={() => onOpen({ domain: "AI Control Center", item: "Executions" })} />}
        >
          <TrendChart data={model.ai} primaryLabel="runs" secondaryLabel="failed" unit="AI runs" />
        </Panel>
        <Panel
          eyebrow={`Last ${days} days · all tenants`}
          title="Integration runs"
          state={sources.dashboard.state}
          error={sources.dashboard.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Integrations", item: "Runs & failures" })} />}
        >
          <TrendChart data={model.runs} primaryLabel="runs" secondaryLabel="failed" unit="integration runs" />
        </Panel>
        <Panel
          eyebrow={`Last ${days} days · all tenants`}
          title="Audit events"
          state={sources.dashboard.state}
          error={sources.dashboard.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Security", item: "Audit trail" })} />}
        >
          <TrendChart data={model.events} primaryLabel="events" secondaryLabel="refused" unit="audit events" />
        </Panel>
      </section>

      <section className="ac-grid three" aria-label="Customer base">
        <Panel
          eyebrow="Customer base"
          title="Tenants by plan"
          state={sources.dashboard.state}
          error={sources.dashboard.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Plans & Licensing", item: "Subscriptions" })} />}
        >
          {model.plans.length ? (
            <BarList items={model.plans} colour="series" />
          ) : (
            <Empty title="No plans assigned" detail="Tenants and their plans appear here." />
          )}
        </Panel>
        <Panel
          eyebrow="Customer base"
          title="Tenants by data region"
          state={sources.dashboard.state}
          error={sources.dashboard.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Security", item: "Overview" })} />}
        >
          {model.regions.length ? (
            <BarList items={model.regions} colour="series" />
          ) : (
            <Empty title="No tenants yet" detail="Data regions appear once tenants exist." />
          )}
        </Panel>
        <Panel
          eyebrow="Next 12 months"
          title="Licenses ending"
          state={sources.dashboard.state}
          error={sources.dashboard.error}
          action={<OpenLink onClick={() => onOpen({ domain: "Plans & Licensing", item: "Renewals" })} />}
        >
          <ColumnChart data={model.renewals} unit="licenses" caption="by month of end date" />
        </Panel>
      </section>

      <div className="ac-grid two">
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
        <div className="ac-grid">
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
                {model.attention.slice(0, 6).map((item) => (
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
            eyebrow="Customers & tenants"
            title="Tenant lifecycle"
            state={sources.customers.state}
            error={sources.customers.error}
            action={<OpenLink onClick={() => onOpen({ domain: "Customers & Tenants", item: "Tenants" })} />}
          >
            {customers.length ? (
              <BarList items={model.statuses} />
            ) : (
              <Empty title="No tenants yet" detail="Create a customer to provision the first tenant." />
            )}
          </Panel>
        </div>
      </div>

      <Panel
        eyebrow="All tenants"
        title="Recent activity"
        state={sources.audit.state}
        error={sources.audit.error}
        action={<OpenLink onClick={() => onOpen({ domain: "Security", item: "Audit trail" })} />}
      >
        {audit.length ? (
          <ol className="ac-timeline">
            {audit.slice(0, 8).map((row) => (
              <li key={row.id}>
                <span className="ac-timeline-dot" aria-hidden="true" />
                <span className="ac-timeline-text">
                  <strong>{titleCase(row.action ?? "Event")}</strong>
                  <small>
                    {[
                      row.tenant_name,
                      safeText(row.actor) ?? safeText(row.actor_business_id),
                      row.entity_type ? titleCase(row.entity_type) : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </span>
                <time className="ac-muted" dateTime={row.at}>
                  {row.at ? formatDateTime(row.at) : "—"}
                </time>
              </li>
            ))}
          </ol>
        ) : (
          <Empty title="No audit events yet" detail="Administrative actions are recorded here." />
        )}
      </Panel>

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
