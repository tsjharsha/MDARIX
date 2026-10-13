import { useMemo, useState } from "react";
import { Activity, ChevronRight, KeyRound, LogIn, Plug, ShieldCheck, Sparkles, UserPlus, Users } from "lucide-react";
import { BarList, Empty, Panel, RingMeter, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { titleCase, worstTone, type Slice, type Tone } from "../../admin/console/dashboardModel";
import { KpiTile, toPoints, type DailyRow } from "../../admin/console/trendCharts";
import {
  ActivityExplorer,
  Donut,
  PlatformPulse,
  RangeSwitch,
  busyness,
  type Range,
} from "../../admin/console/dashboardVisuals";
import { customerAttention, roleMix, seatUsage, userStatusSlices, type TenantUser } from "../customerAdminModel";
import { licensedSeatLimit, useConsole } from "../context";
import { listOf, useResource } from "../shared";
import { formatDateTime } from "../../../app/dates";
import { PARKED_CUSTOMER_ADMIN_SECTIONS, featureSetOf } from "../../../app/featureSet";
import { safeText } from "../../../app/displayId";

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
  // Under the MVP feature set connections and sync runs are parked (app/featureSet.ts): nothing here looks like a live
  // source-system integration, and data comes in through Import data.
  const mvp = featureSetOf(context?.feature_set) === "mvp";
  const dashboard = useResource<any>("/api/v1/admin/tenant-dashboard");
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  const [range, setRange] = useState<Range>(30);
  const trends = useResource<Trends>(`/api/v1/admin/dashboard-trends?days=${range}`);
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
        failedRuns: mvp ? 0 : runFailed,
        seats,
        daysToExpiry: null,
      }).filter((item) => !mvp || !PARKED_CUSTOMER_ADMIN_SECTIONS.includes(item.section)),
      statuses: userStatusSlices(people),
      roles: roleMix(people),
    };
  }, [users.data, trends.data, dashboard.data, context, mvp]);

  const loading = [dashboard, users].some((resource) => resource.state === "loading");
  const tone: Tone = loading ? "neutral" : worstTone(model.attention.map((item) => item.tone));
  const metrics = dashboard.data?.metrics ?? {};
  const active = model.people.filter((user) => String(user.status).toUpperCase() === "ACTIVE").length;
  const connectorList = listOf(connectors.data);
  const activeConnectors = connectorList.filter((row) => String(row.status).toUpperCase() === "ACTIVE").length;
  const trendsReady = trends.state === "ready";
  const days = trends.data?.days ?? 30;
  const recent = listOf(audit.data).slice(0, 8);

  const perDay = (total: number) => (days ? total / days : 0);
  const rates = {
    signIns: perDay(model.signInTotal),
    runs: perDay(model.runTotal),
    ai: perDay(model.aiTotal),
    events: perDay(sum(model.events.map((point) => point.primary))),
  };
  const busiest = Math.max(...Object.values(rates));
  const pulse = [
    {
      key: "people",
      label: "People",
      value: users.state === "ready" ? model.people.length : null,
      detail: `${active} active`,
      icon: <Users size={20} />,
      tone: (model.seats.limit !== null ? model.seats.tone : "good") as Tone,
      onOpen: () => open("Users"),
    },
    {
      key: "signins",
      label: "Sign-ins",
      value: trendsReady ? model.signInTotal : null,
      detail: `last ${days} days`,
      icon: <LogIn size={20} />,
      tone: (trendsReady && model.signInTotal ? "good" : "neutral") as Tone,
      activity: busyness(rates.signIns, busiest),
      onOpen: () => open("Security"),
    },
    {
      key: "connections",
      label: "Connections",
      value: connectors.state === "ready" ? connectorList.length : null,
      detail: `${activeConnectors} active`,
      icon: <Plug size={20} />,
      tone: (!connectorList.length ? "neutral" : activeConnectors < connectorList.length ? "warning" : "good") as Tone,
      activity: busyness(rates.runs, busiest),
      onOpen: () => open("Integrations"),
    },
    {
      key: "runs",
      label: "Sync runs",
      value: trendsReady ? model.runTotal : null,
      detail: `${model.runFailed} failed`,
      icon: <Activity size={20} />,
      tone: (!trendsReady || !model.runTotal ? "neutral" : model.runFailed ? "critical" : "good") as Tone,
      activity: busyness(rates.runs, busiest),
      onOpen: () => open("Integrations", "Sync activity"),
    },
    {
      key: "ai",
      label: "AI assist",
      value: trendsReady ? model.aiTotal : null,
      detail: `${model.aiFailed} failed`,
      icon: <Sparkles size={20} />,
      tone: (!trendsReady || !model.aiTotal ? "neutral" : model.aiFailed ? "warning" : "good") as Tone,
      activity: busyness(rates.ai, busiest),
    },
    {
      key: "audit",
      label: "Audit trail",
      value: trendsReady ? sum(model.events.map((point) => point.primary)) : null,
      detail: `${model.refused} refused`,
      icon: <ShieldCheck size={20} />,
      tone: (!trendsReady ? "neutral" : model.refused ? "warning" : "good") as Tone,
      activity: busyness(rates.events, busiest),
      onOpen: () => open("Audit"),
    },
  ].filter((item) => !mvp || (item.key !== "connections" && item.key !== "runs"));

  return (
    <div className="ac-overview ac-dashboard">
      <section className={`ac-hero ac-hero-pulse tone-${tone}`}>
        <div className="ac-hero-top">
          <div className="ac-hero-status" aria-live="polite">
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
                {context?.plan?.name ? `${context.plan.name} plan` : "No active plan"} · License{" "}
                {context?.license?.effective ? "active" : "inactive"} · {model.people.length}{" "}
                {model.people.length === 1 ? "person" : "people"}, {active} active. Activity below covers the last{" "}
                {days} days.
              </p>
            </div>
          </div>
          <div className="ac-hero-controls">
            <RangeSwitch days={range} onChange={setRange} />
            <span className="ac-hero-actions">
              <button type="button" className="ac-primary" onClick={() => open("Users", "Invite")}>
                <UserPlus size={16} /> Invite user
              </button>
              <button type="button" className="ac-secondary" onClick={() => open("Security")}>
                <ShieldCheck size={16} /> Security
              </button>
            </span>
          </div>
        </div>
        <PlatformPulse nodes={pulse} />
      </section>

      <nav className="ac-jump" aria-label="On this page">
        {[
          ["ac-figures", "Key figures"],
          ["ac-activity", "Activity"],
          ["ac-people", "People and work"],
          ["ac-health", "What to do next"],
        ].map(([id, label]) => (
          <a key={id} href={`#${id}`}>
            {label}
          </a>
        ))}
      </nav>

      <section id="ac-figures" className="ac-kpis" aria-label="Key figures">
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
        {!mvp && (
          <>
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
          </>
        )}
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

      <section id="ac-activity" className="ac-grid ac-grid-wide" aria-label={`Activity, last ${days} days`}>
        <Panel eyebrow={`Last ${days} days`} title="Activity explorer" source={trends}>
          <ActivityExplorer
            series={[
              {
                key: "signins",
                label: "Sign-ins",
                points: model.signIns,
                primaryLabel: "sign-ins",
                unit: "sign-ins",
                explain: "How often your team signed in each day.",
              },
              {
                key: "runs",
                label: "Sync runs",
                points: model.runs,
                primaryLabel: "runs",
                secondaryLabel: "failed",
                unit: "sync runs",
                explain: "Data brought in from your connected systems each day, and how many runs failed.",
              },
              {
                key: "ai",
                label: "AI runs",
                points: model.ai,
                primaryLabel: "runs",
                secondaryLabel: "failed",
                unit: "AI runs",
                explain: "AI assistance your team used each day, and how many runs failed.",
              },
              {
                key: "audit",
                label: "Audit events",
                points: model.events,
                primaryLabel: "events",
                secondaryLabel: "refused",
                unit: "audit events",
                explain: "Every recorded action each day, and how many were refused.",
              },
              {
                key: "users",
                label: "New users",
                points: model.newUsers,
                primaryLabel: "new users",
                unit: "new users",
                explain: "People added to your organization each day.",
              },
            ].filter((item) => !mvp || item.key !== "runs")}
          />
        </Panel>
        <Panel eyebrow={`Last ${days} days`} title="At a glance" source={trends}>
          <div className="ac-rate-rings">
            <RingMeter value={active} total={model.people.length} label="Users active" />
            {model.seats.limit !== null ? (
              <RingMeter value={model.seats.used} total={model.seats.limit} label="Seats used" />
            ) : (
              !mvp && <RingMeter value={activeConnectors} total={connectorList.length} label="Connections active" />
            )}
            {!mvp && (
              <RingMeter value={model.runTotal - model.runFailed} total={model.runTotal} label="Syncs succeeded" />
            )}
            <RingMeter value={model.aiTotal - model.aiFailed} total={model.aiTotal} label="AI runs completed" />
          </div>
        </Panel>
      </section>

      <section id="ac-people" className="ac-grid three" aria-label="People and work">
        <Panel
          eyebrow="People"
          title="Users by status"
          source={users}
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
          source={users}
          action={<OpenLink onClick={() => open("Roles & Access")} />}
        >
          {model.people.length ? (
            <Donut items={model.roles} unit="people" />
          ) : (
            <Empty title="No users yet" detail="Roles appear once people are invited." />
          )}
        </Panel>
        <Panel eyebrow="Quality work" title="Investigations by status" source={trends}>
          {model.investigations.length ? (
            <Donut items={model.investigations} unit="investigations" />
          ) : (
            <Empty title="No investigations yet" detail="Investigations your team opens are counted here." />
          )}
        </Panel>
      </section>

      <div id="ac-health" className="ac-grid two">
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
          source={audit}
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
                      {[safeText(row.actor_label), row.entity_type ? titleCase(row.entity_type) : null]
                        .filter(Boolean)
                        .join(" · ") || "Administration"}
                    </small>
                  </span>
                  <time className="ac-muted" dateTime={row.created_at}>
                    {row.created_at ? formatDateTime(row.created_at) : "—"}
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
