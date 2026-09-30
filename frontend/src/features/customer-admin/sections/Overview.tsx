import { useMemo } from "react";
import { Activity, Bell, ChevronRight, KeyRound, Plug, ShieldCheck, UserPlus, Users } from "lucide-react";
import {
  BarList,
  ColumnChart,
  Empty,
  Panel,
  RingMeter,
  StatTile,
  ToneBadge,
  ToneIcon,
} from "../../admin/console/charts";
import { dailyCounts, runOutcomes, titleCase, worstTone, type Tone } from "../../admin/console/dashboardModel";
import { customerAttention, roleMix, seatUsage, userStatusSlices, type TenantUser } from "../customerAdminModel";
import { licensedSeatLimit, useConsole } from "../context";
import { formatDate, listOf, useResource } from "../shared";

const TREND_DAYS = 14;
const SEAT_STATUSES = ["ACTIVE", "INVITED", "PENDING_VERIFICATION"];

export function Overview() {
  const { context, open } = useConsole();
  const dashboard = useResource<any>("/api/v1/admin/tenant-dashboard");
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  const runs = useResource<any[]>("/api/v1/admin/integrations/runs");
  const audit = useResource<any[]>("/api/v1/admin/audit-history");
  const security = useResource<any>("/api/v1/admin/security-summary");
  const connectors = useResource<any[]>("/api/v1/admin/configuration/connectors");

  const model = useMemo(() => {
    const people = listOf(users.data) as TenantUser[];
    const seats = seatUsage(
      people.filter((user) => SEAT_STATUSES.includes(String(user.status).toUpperCase())).length,
      licensedSeatLimit(context),
    );
    const outcomes = runOutcomes(listOf(runs.data));
    const attention = customerAttention({
      alerts: dashboard.data?.health?.alerts ?? [],
      users: people,
      failedRuns: outcomes.failed,
      seats,
      daysToExpiry: null,
    });
    return {
      people,
      seats,
      outcomes,
      attention,
      statuses: userStatusSlices(people),
      roles: roleMix(people),
      runTrend: dailyCounts(
        listOf(runs.data).map((run) => run.started_at),
        TREND_DAYS,
      ),
      auditTrend: dailyCounts(
        listOf(audit.data).map((row) => row.created_at),
        TREND_DAYS,
      ),
    };
  }, [users.data, runs.data, audit.data, dashboard.data, context]);

  const loading = [dashboard, users].some((resource) => resource.state === "loading");
  const tone: Tone = loading ? "neutral" : worstTone(model.attention.map((item) => item.tone));
  const metrics = dashboard.data?.metrics ?? {};
  const active = model.people.filter((user) => String(user.status).toUpperCase() === "ACTIVE").length;
  const connectorList = listOf(connectors.data);
  const activeConnectors = connectorList.filter((row) => String(row.status).toUpperCase() === "ACTIVE").length;

  return (
    <div className="ac-overview">
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

      <section className="ac-stats" aria-label="Key figures">
        <StatTile
          label="Users"
          value={users.state === "ready" ? model.people.length : null}
          detail={`${active} active`}
          icon={<Users size={18} />}
          onOpen={() => open("Users")}
        />
        <StatTile
          label="Seats in use"
          value={users.state === "ready" ? model.seats.used : null}
          detail={model.seats.limit !== null ? `of ${model.seats.limit} licensed` : "No seat limit on this plan"}
          tone={model.seats.limit !== null ? model.seats.tone : undefined}
          icon={<KeyRound size={18} />}
          onOpen={() => open("Plan & Subscription")}
        />
        <StatTile
          label="Pending invitations"
          value={dashboard.state === "ready" ? (metrics.pending_invitations ?? 0) : null}
          detail="Waiting for the user to activate"
          icon={<UserPlus size={18} />}
          onOpen={() => open("Users")}
        />
        <StatTile
          label="Connections"
          value={connectors.state === "ready" ? connectorList.length : null}
          detail={`${activeConnectors} active`}
          icon={<Plug size={18} />}
          onOpen={() => open("Integrations")}
        />
        <StatTile
          label="Sync success"
          value={model.outcomes.successRate === null ? null : `${model.outcomes.successRate}%`}
          detail={
            model.outcomes.total
              ? `${model.outcomes.failed} failed of ${model.outcomes.total}`
              : "No syncs recorded yet"
          }
          tone={model.outcomes.total ? (model.outcomes.failed ? "critical" : "good") : undefined}
          icon={<Activity size={18} />}
          onOpen={() => open("Integrations", "Sync activity")}
        />
        <StatTile
          label="Security events"
          value={security.state === "ready" ? (security.data?.metrics?.security_events ?? 0) : null}
          detail="Denied or unauthorized access"
          tone={security.state === "ready" ? (security.data?.metrics?.security_events ? "serious" : "good") : undefined}
          icon={<Bell size={18} />}
          onOpen={() => open("Security", "Security events")}
        />
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
        <Panel eyebrow="People" title="Users by status" state={users.state} error={users.error}>
          {model.people.length ? (
            <>
              <BarList items={model.statuses} />
              <h3 className="ca-subhead">By base role</h3>
              <BarList items={model.roles} colour="series" />
            </>
          ) : (
            <Empty title="No users yet" detail="Invite your team to get started." />
          )}
        </Panel>
      </div>

      <div className="ac-grid two">
        <Panel
          eyebrow="Integrations"
          title={`Sync runs · last ${TREND_DAYS} days`}
          state={runs.state}
          error={runs.error}
          action={<OpenLink onClick={() => open("Integrations", "Sync activity")} />}
        >
          <ColumnChart data={model.runTrend} unit="runs" caption="by start date" />
        </Panel>
        <Panel
          eyebrow="Audit"
          title={`Administrative activity · last ${TREND_DAYS} days`}
          state={audit.state}
          error={audit.error}
          action={<OpenLink onClick={() => open("Audit")} />}
        >
          <ColumnChart data={model.auditTrend} unit="events" caption="from the latest 200 audit events" />
        </Panel>
      </div>

      <Panel
        eyebrow="Audit"
        title="Recent administration"
        state={audit.state}
        error={audit.error}
        action={<OpenLink onClick={() => open("Audit")} />}
      >
        {listOf(audit.data).length ? (
          <div className="ac-table-wrap">
            <table className="ac-table">
              <thead>
                <tr>
                  <th scope="col">Action</th>
                  <th scope="col">Object</th>
                  <th scope="col" className="num">
                    When
                  </th>
                </tr>
              </thead>
              <tbody>
                {listOf(audit.data)
                  .slice(0, 6)
                  .map((row, index) => (
                    <tr key={row.id ?? index}>
                      <td>{titleCase(row.action ?? "Event")}</td>
                      <td>{row.entity_type ? titleCase(row.entity_type) : "—"}</td>
                      <td className="num">{formatDate(row.created_at)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No administrative activity yet" detail="Every change you make is recorded here." />
        )}
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
