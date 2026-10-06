import type { ReactNode } from "react";
import {
  Activity,
  BadgeCheck,
  Ban,
  Boxes,
  Building2,
  Database,
  FileClock,
  FileSearch,
  GitBranch,
  KeyRound,
  ListChecks,
  LogIn,
  Mail,
  Plug,
  Scale,
  ShieldAlert,
  ShieldCheck,
  Timer,
  UserCheck,
  UserPlus,
  Users,
  UserX,
  WalletCards,
} from "lucide-react";
import { BarList, Empty, Panel } from "../../admin/console/charts";
import { titleCase, type Slice } from "../../admin/console/dashboardModel";
import { KpiTile, TrendChart, toPoints, type DailyRow } from "../../admin/console/trendCharts";
import { roleMix, seatUsage, userStatusSlices, type TenantUser } from "../customerAdminModel";
import { licensedSeatLimit, useConsole, type Section } from "../context";
import { listOf, useResource } from "../shared";

/*
 * A visual summary at the top of each customer administration page: four key figures (with a 30-day trend line
 * where the server keeps one) and charts of the page's data. Everything is read from the same tenant-scoped
 * endpoints the page uses; nothing here changes data.
 */

type Trends = {
  days: number;
  sign_ins: DailyRow[];
  new_users: DailyRow[];
  integration_runs: DailyRow[];
  audit_events: DailyRow[];
  investigations_by_status: Array<{ label: string; count: number }>;
};

const TRENDS = "/api/v1/admin/dashboard-trends?days=30";
const MAX_BARS = 6;
const upper = (value: unknown) => String(value ?? "").toUpperCase();
const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);
const countWhere = (rows: any[], test: (row: any) => boolean) => rows.filter(test).length;
const isActive = (row: any) => ["ACTIVE", "RELEASED", "PUBLISHED", "ENABLED"].includes(upper(row?.status));

/** Rows counted by one field (ignoring case), largest first; beyond the sixth, the rest are folded into "Other". */
export function slicesBy(rows: any[], field: (row: any) => unknown, rename = titleCase): Slice[] {
  const counts = new Map<string, { label: string; count: number }>();
  for (const row of rows) {
    const value = String(field(row) ?? "").trim() || "Not set";
    const group = counts.get(value.toUpperCase()) ?? { label: value, count: 0 };
    group.count += 1;
    counts.set(value.toUpperCase(), group);
  }
  const sorted = [...counts.values()].sort((a, b) => b.count - a.count);
  const shown = sorted.slice(0, MAX_BARS - (sorted.length > MAX_BARS ? 1 : 0));
  const rest = sum(sorted.slice(shown.length).map((group) => group.count));
  return [
    ...shown.map(({ label, count }) => ({
      key: label,
      label: label === "Not set" ? label : rename(label),
      count,
      tone: "neutral" as const,
    })),
    ...(rest ? [{ key: "__other", label: "Other", count: rest, tone: "neutral" as const }] : []),
  ];
}

function Layout({ label, tiles, charts }: { label: string; tiles: ReactNode; charts?: ReactNode }) {
  return (
    <div className="ca-summary ac-dashboard" aria-label={label}>
      <section className="ac-kpis" aria-label="Key figures">
        {tiles}
      </section>
      {charts && <section className="ac-grid three">{charts}</section>}
    </div>
  );
}

function Bars({
  eyebrow,
  title,
  items,
  state,
  empty,
  colour = "series",
}: {
  eyebrow: string;
  title: string;
  items: Slice[];
  state: "loading" | "ready" | "error" | "forbidden";
  empty: string;
  colour?: "tone" | "series";
}) {
  return (
    <Panel eyebrow={eyebrow} title={title} state={state}>
      {items.length ? <BarList items={items} colour={colour} /> : <Empty title="Nothing yet" detail={empty} />}
    </Panel>
  );
}

const ready = (resource: { state: string }) => resource.state === "ready";

function UsersSummary() {
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  const trends = useResource<Trends>(TRENDS);
  const people = listOf(users.data) as TenantUser[];
  const days = trends.data?.days ?? 30;
  const newUsers = toPoints(trends.data?.new_users, "users");
  const signIns = toPoints(trends.data?.sign_ins, "sign_ins");
  const waiting = countWhere(people, (user) => ["INVITED", "PENDING_VERIFICATION"].includes(upper(user.status)));
  const blocked = countWhere(people, (user) => ["SUSPENDED", "LOCKED", "DEACTIVATED"].includes(upper(user.status)));
  return (
    <Layout
      label="Users at a glance"
      tiles={
        <>
          <KpiTile
            label="Users"
            value={ready(users) ? people.length : null}
            detail={`${sum(newUsers.map((point) => point.primary))} new · last ${days} days`}
            icon={<Users size={18} />}
            series={newUsers.map((point) => point.primary)}
            seriesLabel={`New users per day, last ${days} days`}
          />
          <KpiTile
            label="Active"
            value={ready(users) ? countWhere(people, (user) => upper(user.status) === "ACTIVE") : null}
            detail="Can sign in"
            icon={<UserCheck size={18} />}
            tone="good"
          />
          <KpiTile
            label="Awaiting activation"
            value={ready(users) ? waiting : null}
            detail="Invited, not yet signed in"
            icon={<UserPlus size={18} />}
            tone={waiting ? "warning" : "good"}
          />
          <KpiTile
            label="Suspended or locked"
            value={ready(users) ? blocked : null}
            detail="Cannot sign in"
            icon={<UserX size={18} />}
            tone={blocked ? "warning" : "good"}
          />
        </>
      }
      charts={
        <>
          <Bars
            eyebrow="People"
            title="Users by status"
            items={userStatusSlices(people)}
            state={users.state}
            empty="Invite your team to get started."
            colour="tone"
          />
          <Bars
            eyebrow="People"
            title="Users by base role"
            items={roleMix(people)}
            state={users.state}
            empty="Roles appear once people are invited."
          />
          <Panel eyebrow={`Last ${days} days`} title="Sign-ins" source={trends}>
            <TrendChart data={signIns} primaryLabel="sign-ins" unit="sign-ins" />
          </Panel>
        </>
      }
    />
  );
}

function AccessSummary() {
  const roles = useResource<any[]>("/api/v1/admin/identity/roles");
  const sets = useResource<any[]>("/api/v1/admin/identity/permission-sets");
  const policies = useResource<any>("/api/v1/admin/governance/policies");
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  const roleRows = listOf(roles.data);
  const setRows = listOf(sets.data);
  const authorities = listOf(policies.data?.approval_authorities);
  const sod = listOf(policies.data?.sod_policies);
  return (
    <Layout
      label="Roles and access at a glance"
      tiles={
        <>
          <KpiTile
            label="Roles"
            value={ready(roles) ? roleRows.length : null}
            detail={`${countWhere(roleRows, isActive)} active`}
            icon={<KeyRound size={18} />}
          />
          <KpiTile
            label="Permission sets"
            value={ready(sets) ? setRows.length : null}
            detail={`${countWhere(setRows, isActive)} active`}
            icon={<ListChecks size={18} />}
          />
          <KpiTile
            label="Approval rules"
            value={ready(policies) ? authorities.length : null}
            detail="Who may approve what"
            icon={<BadgeCheck size={18} />}
          />
          <KpiTile
            label="Separation of duties"
            value={ready(policies) ? sod.length : null}
            detail="Rules that stop self-approval"
            icon={<Scale size={18} />}
            tone={ready(policies) ? (sod.length ? "good" : "warning") : undefined}
          />
        </>
      }
      charts={
        <>
          <Bars
            eyebrow="Roles"
            title="Roles by status"
            items={slicesBy(roleRows, (row) => row.status)}
            state={roles.state}
            empty="Create a role to get started."
          />
          <Bars
            eyebrow="Permission sets"
            title="Permission sets by status"
            items={slicesBy(setRows, (row) => row.status)}
            state={sets.state}
            empty="Permission sets appear here."
          />
          <Bars
            eyebrow="People"
            title="Users by base role"
            items={roleMix(listOf(users.data) as TenantUser[])}
            state={users.state}
            empty="Roles appear once people are invited."
          />
        </>
      }
    />
  );
}

function IntegrationsSummary() {
  const connectors = useResource<any[]>("/api/v1/admin/configuration/connectors");
  const runs = useResource<any[]>("/api/v1/admin/integrations/runs");
  const records = useResource<any[]>("/api/v1/admin/integrations/reconciliation");
  const trends = useResource<Trends>(TRENDS);
  const connectorRows = listOf(connectors.data);
  const runRows = listOf(runs.data);
  const days = trends.data?.days ?? 30;
  const daily = toPoints(trends.data?.integration_runs, "completed", "failed", true, ["warnings"]);
  const failed = sum(daily.map((point) => point.secondary ?? 0));
  const unresolved = sum(listOf(records.data).map((row) => Number(row.unresolved_count ?? 0)));
  return (
    <Layout
      label="Integrations at a glance"
      tiles={
        <>
          <KpiTile
            label="Connections"
            value={ready(connectors) ? connectorRows.length : null}
            detail={`${countWhere(connectorRows, isActive)} active`}
            icon={<Plug size={18} />}
          />
          <KpiTile
            label="Sync runs"
            value={ready(trends) ? sum(daily.map((point) => point.primary)) : null}
            detail={`${failed} failed · last ${days} days`}
            tone={ready(trends) && daily.some((point) => point.primary) ? (failed ? "critical" : "good") : undefined}
            icon={<Activity size={18} />}
            series={daily.map((point) => point.primary)}
            seriesLabel={`Sync runs per day, last ${days} days`}
          />
          <KpiTile
            label="Records accepted"
            value={ready(runs) ? sum(runRows.map((row) => Number(row.records_accepted ?? 0))) : null}
            detail={`${sum(runRows.map((row) => Number(row.records_rejected ?? 0)))} rejected · latest runs`}
            icon={<Database size={18} />}
          />
          <KpiTile
            label="Unreconciled records"
            value={ready(records) ? unresolved : null}
            detail={unresolved ? "Source and MDARIX counts differ" : "Source and MDARIX counts match"}
            tone={ready(records) ? (unresolved ? "warning" : "good") : undefined}
            icon={<GitBranch size={18} />}
          />
        </>
      }
      charts={
        <>
          <Panel eyebrow={`Last ${days} days`} title="Sync runs" source={trends}>
            <TrendChart data={daily} primaryLabel="runs" secondaryLabel="failed" unit="sync runs" />
          </Panel>
          <Bars
            eyebrow="Latest runs"
            title="Runs by source system"
            items={slicesBy(
              runRows,
              (row) => row.source_system,
              (value) => value,
            )}
            state={runs.state}
            empty="Runs appear after the first sync."
          />
          <Bars
            eyebrow="Connections"
            title="Connections by status"
            items={slicesBy(connectorRows, (row) => row.status)}
            state={connectors.state}
            empty="Add a connection to get started."
          />
        </>
      }
    />
  );
}

function DataMappingSummary() {
  const mappings = useResource<any[]>("/api/v1/admin/configuration/mappings");
  const fields = useResource<any[]>("/api/v1/admin/configuration/data-mappings");
  const mappingRows = listOf(mappings.data);
  const fieldRows = listOf(fields.data);
  const drafts = countWhere(mappingRows, (row) => upper(row.status) === "DRAFT");
  return (
    <Layout
      label="Data mapping at a glance"
      tiles={
        <>
          <KpiTile
            label="Mappings"
            value={ready(mappings) ? mappingRows.length : null}
            detail={`${countWhere(mappingRows, isActive)} in use`}
            icon={<GitBranch size={18} />}
          />
          <KpiTile
            label="Drafts"
            value={ready(mappings) ? drafts : null}
            detail="Not yet released"
            tone={ready(mappings) ? (drafts ? "warning" : "good") : undefined}
            icon={<FileClock size={18} />}
          />
          <KpiTile
            label="Mapped fields"
            value={ready(fields) ? fieldRows.length : null}
            detail={`${countWhere(fieldRows, (row) => row.required)} required`}
            icon={<ListChecks size={18} />}
          />
          <KpiTile
            label="Source systems"
            value={ready(fields) ? new Set(fieldRows.map((row) => row.source_system).filter(Boolean)).size : null}
            detail="Feeding MDARIX"
            icon={<Database size={18} />}
          />
        </>
      }
      charts={
        <>
          <Bars
            eyebrow="Mappings"
            title="Mappings by status"
            items={slicesBy(mappingRows, (row) => row.status)}
            state={mappings.state}
            empty="Create a mapping to get started."
          />
          <Bars
            eyebrow="Fields"
            title="Fields by MDARIX record"
            items={slicesBy(
              fieldRows,
              (row) => row.target_entity ?? row.target_table,
              (value) => value,
            )}
            state={fields.state}
            empty="Mapped fields appear here."
          />
          <Bars
            eyebrow="Fields"
            title="Fields by source system"
            items={slicesBy(
              fieldRows,
              (row) => row.source_system,
              (value) => value,
            )}
            state={fields.state}
            empty="Mapped fields appear here."
          />
        </>
      }
    />
  );
}

function SubscriptionSummary() {
  const { context } = useConsole();
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  const entitlements = useResource<any[]>("/api/v1/admin/governance/entitlements");
  const people = listOf(users.data) as TenantUser[];
  const used = countWhere(people, (user) => ["ACTIVE", "INVITED", "PENDING_VERIFICATION"].includes(upper(user.status)));
  const seats = seatUsage(used, licensedSeatLimit(context));
  const features = listOf(entitlements.data);
  const admins = countWhere(
    people,
    (user) => upper(user.role) === "CUSTOMER_ADMIN" && ["ACTIVE", "INVITED"].includes(upper(user.status)),
  );
  return (
    <Layout
      label="Plan and subscription at a glance"
      tiles={
        <>
          <KpiTile
            label="Seats in use"
            value={ready(users) ? seats.used : null}
            detail={seats.limit !== null ? `of ${seats.limit} licensed` : "No seat limit on this plan"}
            tone={seats.limit !== null ? seats.tone : undefined}
            icon={<Users size={18} />}
          />
          {seats.limit !== null ? (
            <KpiTile
              label="Seats free"
              value={ready(users) ? Math.max(0, seats.limit - seats.used) : null}
              detail="Before the plan limit"
              icon={<WalletCards size={18} />}
            />
          ) : (
            <KpiTile
              label="Awaiting activation"
              value={
                ready(users)
                  ? countWhere(people, (user) => ["INVITED", "PENDING_VERIFICATION"].includes(upper(user.status)))
                  : null
              }
              detail="Invited users take a seat once active"
              icon={<WalletCards size={18} />}
            />
          )}
          <KpiTile
            label="Features enabled"
            value={ready(entitlements) ? countWhere(features, (row) => row.enabled) : null}
            detail={`of ${features.length} in the plan`}
            icon={<BadgeCheck size={18} />}
          />
          <KpiTile
            label="Customer administrators"
            value={ready(users) ? admins : null}
            detail="Active or invited"
            tone={ready(users) ? (admins >= 2 ? "good" : "warning") : undefined}
            icon={<KeyRound size={18} />}
          />
        </>
      }
    />
  );
}

function SecuritySummary() {
  const summary = useResource<any>("/api/v1/admin/security-summary");
  const audit = useResource<any[]>("/api/v1/admin/audit-history");
  const trends = useResource<Trends>(TRENDS);
  const days = trends.data?.days ?? 30;
  const signIns = toPoints(trends.data?.sign_ins, "sign_ins");
  const events = toPoints(trends.data?.audit_events, "events", "refused");
  const refused = listOf(audit.data).filter((row) => /DENIED|FAILED/.test(upper(row.action)));
  return (
    <Layout
      label="Security at a glance"
      tiles={
        <>
          <KpiTile
            label="Sign-ins"
            value={ready(trends) ? sum(signIns.map((point) => point.primary)) : null}
            detail={`Last ${days} days`}
            icon={<LogIn size={18} />}
            series={signIns.map((point) => point.primary)}
            seriesLabel={`Sign-ins per day, last ${days} days`}
          />
          <KpiTile
            label="Refused actions"
            value={ready(trends) ? sum(events.map((point) => point.secondary ?? 0)) : null}
            detail={`Denied or failed · last ${days} days`}
            icon={<Ban size={18} />}
            series={events.map((point) => point.secondary ?? 0)}
            seriesLabel={`Refused actions per day, last ${days} days`}
            goodWhenUp={false}
          />
          <KpiTile
            label="Security events"
            value={ready(summary) ? (summary.data?.metrics?.security_events ?? 0) : null}
            detail="In the latest 200 audit events"
            tone={ready(summary) ? (summary.data?.metrics?.security_events ? "serious" : "good") : undefined}
            icon={<ShieldAlert size={18} />}
          />
          <KpiTile
            label="Policy denials"
            value={ready(summary) ? (summary.data?.metrics?.policy_denials ?? 0) : null}
            detail="Requests the server refused"
            icon={<ShieldCheck size={18} />}
          />
        </>
      }
      charts={
        <>
          <Panel eyebrow={`Last ${days} days`} title="Sign-ins" source={trends}>
            <TrendChart data={signIns} primaryLabel="sign-ins" unit="sign-ins" />
          </Panel>
          <Panel eyebrow={`Last ${days} days`} title="Audit events" source={trends}>
            <TrendChart data={events} primaryLabel="events" secondaryLabel="refused" unit="audit events" />
          </Panel>
          <Bars
            eyebrow="Latest 200 events"
            title="Refused actions by type"
            items={slicesBy(refused, (row) => row.action)}
            state={audit.state}
            empty="No refused actions. Denied or failed attempts appear here."
          />
        </>
      }
    />
  );
}

function NotificationsSummary() {
  const preferences = useResource<any>("/api/v1/admin/notifications/preferences");
  const contacts = listOf(preferences.data?.recipients);
  const policy = listOf(preferences.data?.policies)[0];
  const thresholds = listOf(policy?.thresholds) as number[];
  return (
    <Layout
      label="Notifications at a glance"
      tiles={
        <>
          <KpiTile
            label="Contacts"
            value={ready(preferences) ? contacts.length : null}
            detail={`${countWhere(contacts, isActive)} active`}
            icon={<Mail size={18} />}
          />
          <KpiTile
            label="Reminders"
            value={ready(preferences) ? thresholds.length : null}
            detail={thresholds.length ? `${thresholds.join(", ")} days before renewal` : "Default schedule"}
            icon={<Timer size={18} />}
          />
          <KpiTile
            label="First reminder"
            value={ready(preferences) && thresholds.length ? Math.max(...thresholds) : null}
            suffix=" days"
            detail="Before the subscription ends"
            icon={<FileClock size={18} />}
          />
          <KpiTile
            label="Recipient groups"
            value={ready(preferences) ? listOf(policy?.recipient_types).length : null}
            detail={listOf(policy?.recipient_types).map(titleCase).join(", ") || "Customer administrators"}
            icon={<Users size={18} />}
          />
        </>
      }
      charts={
        <>
          <Bars
            eyebrow="Contacts"
            title="Contacts by type"
            items={slicesBy(contacts, (row) => row.recipient_type)}
            state={preferences.state}
            empty="Add billing or business contacts."
          />
          <Bars
            eyebrow="Contacts"
            title="Contacts by status"
            items={slicesBy(contacts, (row) => row.status)}
            state={preferences.state}
            empty="Contacts appear here."
          />
        </>
      }
    />
  );
}

function AuditSummary() {
  const audit = useResource<any[]>("/api/v1/admin/audit-history");
  const retention = useResource<any>("/api/v1/admin/retention-status");
  const trends = useResource<Trends>(TRENDS);
  const days = trends.data?.days ?? 30;
  const events = toPoints(trends.data?.audit_events, "events", "refused");
  const rows = listOf(audit.data);
  return (
    <Layout
      label="Audit at a glance"
      tiles={
        <>
          <KpiTile
            label="Audit events"
            value={ready(trends) ? sum(events.map((point) => point.primary)) : null}
            detail={`Last ${days} days`}
            icon={<FileClock size={18} />}
            series={events.map((point) => point.primary)}
            seriesLabel={`Audit events per day, last ${days} days`}
          />
          <KpiTile
            label="Refused actions"
            value={ready(trends) ? sum(events.map((point) => point.secondary ?? 0)) : null}
            detail={`Denied or failed · last ${days} days`}
            icon={<Ban size={18} />}
            series={events.map((point) => point.secondary ?? 0)}
            seriesLabel={`Refused actions per day, last ${days} days`}
            goodWhenUp={false}
          />
          <KpiTile
            label="Kinds of action"
            value={ready(audit) ? new Set(rows.map((row) => row.action)).size : null}
            detail="In the latest 200 events"
            icon={<ListChecks size={18} />}
          />
          <KpiTile
            label="Events kept"
            value={ready(retention) ? Number(retention.data?.total_events ?? 0) : null}
            detail={retention.data?.policy ?? "Retention policy"}
            tone={ready(retention) ? (upper(retention.data?.status) === "HEALTHY" ? "good" : "serious") : undefined}
            icon={<ShieldCheck size={18} />}
          />
        </>
      }
      charts={
        <>
          <Panel eyebrow={`Last ${days} days`} title="Audit events" source={trends}>
            <TrendChart data={events} primaryLabel="events" secondaryLabel="refused" unit="audit events" />
          </Panel>
          <Bars
            eyebrow="Latest 200 events"
            title="Most frequent actions"
            items={slicesBy(rows, (row) => row.action)}
            state={audit.state}
            empty="Administrative actions appear here."
          />
          <Bars
            eyebrow="Latest 200 events"
            title="Events by object"
            items={slicesBy(rows, (row) => row.entity_type)}
            state={audit.state}
            empty="Administrative actions appear here."
          />
        </>
      }
    />
  );
}

function OrganizationSummary() {
  const products = useResource<any[]>("/api/v1/admin/catalog/products");
  const trends = useResource<Trends>(TRENDS);
  const rows = listOf(products.data);
  const investigations = (trends.data?.investigations_by_status ?? []).map((row) => ({
    key: row.label,
    label: titleCase(row.label),
    count: row.count,
    tone: "neutral" as const,
  }));
  return (
    <Layout
      label="Organization at a glance"
      tiles={
        <>
          <KpiTile
            label="Products"
            value={ready(products) ? rows.length : null}
            detail={`${countWhere(rows, (row) => upper(row.lifecycle_status) === "ACTIVE")} active`}
            icon={<Boxes size={18} />}
          />
          <KpiTile
            label="Product versions"
            value={ready(products) ? sum(rows.map((row) => Number(row.version_count ?? 0))) : null}
            detail="Across all products"
            icon={<GitBranch size={18} />}
          />
          <KpiTile
            label="Product families"
            value={ready(products) ? new Set(rows.map((row) => row.product_family).filter(Boolean)).size : null}
            detail="Groups of products"
            icon={<Building2 size={18} />}
          />
          <KpiTile
            label="Investigations"
            value={ready(trends) ? sum(investigations.map((row) => row.count)) : null}
            detail="Opened by your team"
            icon={<FileSearch size={18} />}
          />
        </>
      }
      charts={
        <>
          <Bars
            eyebrow="Products"
            title="Products by lifecycle"
            items={slicesBy(rows, (row) => row.lifecycle_status)}
            state={products.state}
            empty="Products appear here."
          />
          <Bars
            eyebrow="Products"
            title="Products by family"
            items={slicesBy(
              rows,
              (row) => row.product_family,
              (value) => value,
            )}
            state={products.state}
            empty="Products appear here."
          />
          <Bars
            eyebrow="Quality work"
            title="Investigations by status"
            items={investigations}
            state={trends.state}
            empty="Investigations your team opens are counted here."
          />
        </>
      }
    />
  );
}

const SUMMARIES: Partial<Record<Section, () => ReactNode>> = {
  Users: UsersSummary,
  "Roles & Access": AccessSummary,
  Integrations: IntegrationsSummary,
  "Data Mapping": DataMappingSummary,
  "Plan & Subscription": SubscriptionSummary,
  Security: SecuritySummary,
  Notifications: NotificationsSummary,
  Audit: AuditSummary,
  Organization: OrganizationSummary,
};

/** The page's visual summary (the Dashboard is one already). */
export function SectionSummary({ section }: { section: Section }) {
  const Summary = SUMMARIES[section];
  return Summary ? <Summary /> : null;
}
