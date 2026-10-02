import { useMemo } from "react";
import { Activity, ChevronRight, KeyRound, LogIn, Plug, ShieldCheck, Sparkles, UserPlus, Users } from "lucide-react";
import { BarList, Empty, Panel, RingMeter, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { titleCase, worstTone, type Slice, type Tone } from "../../admin/console/dashboardModel";
import { KpiTile, TrendChart, toPoints, type DailyRow } from "../../admin/console/trendCharts";
import { customerAttention, roleMix, seatUsage, userStatusSlices, type TenantUser } from "../customerAdminModel";
import { licensedSeatLimit, useConsole } from "../context";
import { listOf, useResource } from "../shared";

const SEAT_STATUSES = ["ACTIVE", "INVITED", "PENDING_VERIFICATION"];

type Trends = {
  days: number;
  sign_ins: DailyRow[];
  new_users: DailyRow[];
  integration_runs: DailyRow[];
  ai_runs: DailyRow[];
  audit_events: DailyRow[];
  investigations_by_status: Array<{ label: string; count: number }>;
};

const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);

/** The organization at a glance: people, sign-ins, integrations, AI and audit activity, and what needs action. */
export function Dashboard() {
  const { context, open } = useConsole();
  const dashboard = useResource<any>("/api/v1/admin/tenant-dashboard");
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  const trends = useResource<Trends>("/api/v1/admin/dashboard-trends?days=30");
  const audit = useResource<any[]>("/api/v1/admin/audit-history");
  const security = useResource<any>("/api/v1/admin/security-summary");
  const connectors = useResource<any[]>("/api/v1/admin/configuration/connectors");

  const model = useMemo(() => {
    const people = listOf(users.data) as TenantUser[];
    const seats = seatUsage(
      people.filter((user) => SEAT_STATUSES.includes(String(user.status).toUpperCase())).length,
      licensedSeatLimit(context),
    );
    const data = trends.data;
    const signIns = toPoints(data?.sign_ins, "sign_ins");
    const newUsers = toPoints(data?.new_users, "users");
    const runs = toPoints(data?.integration_runs, "completed", "failed", true, ["warnings"]);
    const ai = toPoints(data?.ai_runs, "completed", "failed", true);
    const events = toPoints(data?.audit_events, "events", "refused");
    const runFailed = sum(runs.map((point) => point.secondary ?? 0));
    const investigations: Slice[] = (data?.investigations_by_status ?? []).map((row) => ({
      key: row.label,
      label: titleCase(row.label),
      count: row.count,
      tone: "neutral",
    }));
    return {
      people,
      seats,
      signIns,
      newUsers,
      runs,
      ai,
      events,
      runTotal: sum(runs.map((point) => point.primary)),
      runFailed,
      aiTotal: sum(ai.map((point) => point.primary)),
      aiFailed: sum(ai.map((point) => point.secondary ?? 0)),
      signInTotal: sum(signIns.map((point) => point.primary)),
      refused: sum(events.map((point) => point.secondary ?? 0)),
      investigations,
      attention: customerAttention({
        alerts: dashboard.data?.health?.alerts ?? [],
        users: people,
        failedRuns: runFailed,
        seats,
        daysToExpiry: null,
      }),
      statuses: userStatusSlices(people),
      roles: roleMix(people),
    };
  }, [users.data, trends.data, dashboard.data, context]);

  const loading = [dashboard, users].some((resource) => resource.state === "loading");
  const tone: Tone = loading ? "neutral" : worstTone(model.attention.map((item) => item.tone));
  const metrics = dashboard.data?.metrics ?? {};
  const active = model.people.filter((user) => String(user.status).toUpperCase() === "ACTIVE").length;
  const connectorList = listOf(connectors.data);
  const activeConnectors = connectorList.filter((row) => String(row.status).toUpperCase() === "ACTIVE").length;
  const trendsReady = trends.state === "ready";
  const days = trends.data?.days ?? 30;
  const recent = listOf(audit.data).slice(0, 8);

  return (
    <div className="ac-overview ac-dashboard">
      <section className={`ac-hero tone-${tone}`} aria-live="polite">
        <div className="ac-hero-status">
          <span className="ac-hero-icon">
            <ToneIcon tone={tone} size={34} />
          </span>
          <div>
            <p className="ac-eyebrow">{context?.current_tenant?.tenant_name ?? "Your organization"}</p>
            <h2>
              {loading
                ? "Checking your organization…"
                : model.attention.length
                  ? `${model.attention.length} ${model.attention.length === 1 ? "item needs" : "items need"} your attention`
                  : "Everything looks healthy"}
            </h2>
            <p>
              {context?.plan?.name ? `${context.plan.name} plan` : "No active plan"} · Licence{" "}
              {context?.license?.effective ? "active" : "inactive"}
            </p>
          </div>
        </div>
        <div className="ac-hero-meters">
          <RingMeter value={active} total={model.people.length} label="Users active" />
          {model.seats.limit !== null ? (
            <RingMeter value={model.seats.used} total={model.seats.limit} label="Seats used" />
          ) : (
            <RingMeter value={activeConnectors} total={connectorList.length} label="Connections active" />
          )}
          <RingMeter
            value={model.runTotal - model.runFailed}
            total={model.runTotal}
            label={`Syncs succeeded · ${days} days`}
          />
        </div>
        <div className="ac-hero-actions">
          <button type="button" className="ac-primary" onClick={() => open("Users", "Invite")}>
            <UserPlus size={16} /> Invite user
          </button>
          <button type="button" className="ac-secondary" onClick={() => open("Security")}>
            <ShieldCheck size={16} /> Security
          </button>
        </div>
      </section>

      <section className="ac-kpis" aria-label="Key figures">
        <KpiTile
          label="Users"
          value={users.state === "ready" ? model.people.length : null}
          detail={`${active} active`}
          icon={<Users size={18} />}
          series={model.newUsers.map((point) => point.primary)}
          seriesLabel={`New users per day, last ${days} days`}
          onOpen={() => open("Users")}
        />
        <KpiTile
          label="Sign-ins"
          value={trendsReady ? model.signInTotal : null}
          detail={`Last ${days} days`}
          icon={<LogIn size={18} />}
          series={model.signIns.map((point) => point.primary)}
          seriesLabel={`Sign-ins per day, last ${days} days`}
          onOpen={() => open("Security")}
        />
        <KpiTile
          label="Seats in use"
          value={users.state === "ready" ? model.seats.used : null}
          detail={model.seats.limit !== null ? `of ${model.seats.limit} licensed` : "No seat limit on this plan"}
          tone={model.seats.limit !== null ? model.seats.tone : undefined}
          icon={<KeyRound size={18} />}
          onOpen={() => open("Plan & Subscription")}
        />
        <KpiTile
          label="Pending invitations"
          value={dashboard.state === "ready" ? (metrics.pending_invitations ?? 0) : null}
          detail="Waiting for the user to activate"
          icon={<UserPlus size={18} />}
          onOpen={() => open("Users")}
        />
        <KpiTile
          label="Connections"
          value={connectors.state === "ready" ? connectorList.length : null}
          detail={`${activeConnectors} active`}
          icon={<Plug size={18} />}
          onOpen={() => open("Integrations")}
        />
        <KpiTile
          label="Sync runs"
          value={trendsReady ? model.runTotal : null}
          detail={`${model.runFailed} failed · last ${days} days`}
          tone={trendsReady && model.runTotal ? (model.runFailed ? "critical" : "good") : undefined}
          icon={<Activity size={18} />}
          series={model.runs.map((point) => point.primary)}
          seriesLabel={`Sync runs per day, last ${days} days`}
          onOpen={() => open("Integrations", "Sync activity")}
        />
        <KpiTile
          label="AI runs"
          value={trendsReady ? model.aiTotal : null}
          detail={`${model.aiFailed} failed · last ${days} days`}
          tone={trendsReady && model.aiTotal ? (model.aiFailed ? "warning" : "good") : undefined}
          icon={<Sparkles size={18} />}
          series={model.ai.map((point) => point.primary)}
          seriesLabel={`AI runs per day, last ${days} days`}
        />
        <KpiTile
          label="Security events"
          value={security.state === "ready" ? (security.data?.metrics?.security_events ?? 0) : null}
          detail="Denied or unauthorized access"
          tone={security.state === "ready" ? (security.data?.metrics?.security_events ? "serious" : "good") : undefined}
          icon={<ShieldCheck size={18} />}
          onOpen={() => open("Security", "Security events")}
        />
      </section>

      <section className="ac-grid three" aria-label={`Activity, last ${days} days`}>
        <Panel
          eyebrow={`Last ${days} days`}
          title="Sign-ins"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Security")} />}
        >
          <TrendChart data={model.signIns} primaryLabel="sign-ins" unit="sign-ins" />
        </Panel>
        <Panel
          eyebrow={`Last ${days} days`}
          title="Sync runs"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Integrations", "Sync activity")} />}
        >
          <TrendChart data={model.runs} primaryLabel="runs" secondaryLabel="failed" unit="sync runs" />
        </Panel>
        <Panel
          eyebrow={`Last ${days} days`}
          title="Audit events"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Audit")} />}
        >
          <TrendChart data={model.events} primaryLabel="events" secondaryLabel="refused" unit="audit events" />
        </Panel>
      </section>

      <section className="ac-grid three" aria-label="People and work">
        <Panel
          eyebrow="People"
          title="Users by status"
          state={users.state}
          error={users.error}
          action={<OpenLink onClick={() => open("Users")} />}
        >
          {model.people.length ? (
            <BarList items={model.statuses} />
          ) : (
            <Empty title="No users yet" detail="Invite your team to get started." />
          )}
        </Panel>
        <Panel
          eyebrow="People"
          title="Users by base role"
          state={users.state}
          error={users.error}
          action={<OpenLink onClick={() => open("Roles & Access")} />}
        >
          {model.people.length ? (
            <BarList items={model.roles} colour="series" />
          ) : (
            <Empty title="No users yet" detail="Roles appear once people are invited." />
          )}
        </Panel>
        <Panel eyebrow="Quality work" title="Investigations by status" state={trends.state} error={trends.error}>
          {model.investigations.length ? (
            <BarList items={model.investigations} colour="series" />
          ) : (
            <Empty title="No investigations yet" detail="Investigations your team opens are counted here." />
          )}
        </Panel>
      </section>

      <div className="ac-grid two">
        <Panel
          eyebrow="Needs attention"
          title="What to do next"
          state={loading ? "loading" : "ready"}
          action={
            model.attention.length ? (
              <ToneBadge tone={tone} label={`${model.attention.length} open`} />
            ) : (
              <ToneBadge tone="good" />
            )
          }
        >
          {model.attention.length ? (
            <ul className="ac-attention">
              {model.attention.map((item) => (
                <li key={item.key}>
                  <ToneIcon tone={item.tone} size={18} />
                  <span>
                    <strong>{item.title}</strong>
                    <small>{item.detail}</small>
                  </span>
                  <button type="button" className="ac-link ca-push" onClick={() => open(item.section)}>
                    {item.section} <ChevronRight size={14} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="Nothing needs action" detail="Alerts, failed syncs and seat limits will appear here." />
          )}
        </Panel>
        <Panel
          eyebrow="Audit"
          title="Recent activity"
          state={audit.state}
          error={audit.error}
          action={<OpenLink onClick={() => open("Audit")} />}
        >
          {recent.length ? (
            <ol className="ac-timeline">
              {recent.map((row, index) => (
                <li key={row.id ?? index}>
                  <span className="ac-timeline-dot" aria-hidden="true" />
                  <span className="ac-timeline-text">
                    <strong>{titleCase(row.action ?? "Event")}</strong>
                    <small>
                      {[row.actor_label, row.entity_type ? titleCase(row.entity_type) : null]
                        .filter(Boolean)
                        .join(" · ") || "Administration"}
                    </small>
                  </span>
                  <time className="ac-muted" dateTime={row.created_at}>
                    {row.created_at ? new Date(row.created_at).toLocaleString() : "—"}
                  </time>
                </li>
              ))}
            </ol>
          ) : (
            <Empty title="No administrative activity yet" detail="Every change you make is recorded here." />
          )}
        </Panel>
      </div>
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
