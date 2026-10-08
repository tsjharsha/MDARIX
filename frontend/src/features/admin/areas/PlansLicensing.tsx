import { useMemo, useState } from "react";
import { AlarmClock, CalendarClock, CalendarX2, CheckCircle2, Mail } from "lucide-react";
import { Empty, Panel, StatTile } from "../console/charts";
import {
  Drawer,
  SearchBox,
  Table,
  errorText,
  formatDate,
  idColumn,
  referenceIdColumn,
  send,
  useResource,
  type Resource,
} from "../../customer-admin/shared";
import { ChangeSubscription } from "../customers/CustomerPage";
import { titleCase } from "../customers/model";
import { featureLabel } from "../onboardingModel";
import { StatusBadge } from "../customers/StatusBadge";
import { Intro, Pager, TenantCell, TenantPicker } from "./common";
import { parseThresholds, previewTemplate, templateVariables } from "./sections";
import { formatDay } from "../../../app/dates";
import { safeText } from "../../../app/displayId";
import { sortParams, useServerSort } from "../../../app/tableSort";

type Notify = (text: string, tone?: "good" | "critical") => void;

export function PlansLicensing({ section, onMessage }: { section: string; onMessage: Notify }) {
  if (section === "Subscriptions") return <Subscriptions onMessage={onMessage} />;
  if (section === "Renewals") return <Renewals />;
  if (section === "Reminders") return <Reminders onMessage={onMessage} />;
  return <Plans />;
}

type Plan = {
  id: string;
  business_id?: string | null;
  code: string;
  name: string;
  description?: string | null;
  status?: string;
  version?: string;
  capabilities?: Record<string, boolean>;
  limits?: Record<string, unknown>;
};

const LIMIT_LABELS: Record<string, string> = {
  licensed_users_limit: "Licensed users",
  customer_admin_limit: "Customer administrators",
  connector_limit: "Connections",
  trial_days: "Trial length (days)",
  upload_row_limit: "Rows per upload",
};

/** Each plan with what it includes (features) and allows (limits): the entitlements, in one place. */
function Plans() {
  const plans = useResource<Plan[]>("/api/v1/platform-admin/plans");
  const rows = Array.isArray(plans.data) ? plans.data : [];
  return (
    <Panel eyebrow="Catalog" title="Plans" state={plans.state} error={plans.error}>
      <Intro>
        A plan sets what a tenant can use (features) and how much (limits). Every tenant has one plan; change it from
        Subscriptions.
      </Intro>
      {rows.length ? (
        <div className="ar-cards">
          {rows.map((plan) => {
            const features = Object.entries(plan.capabilities ?? {}).filter(([, enabled]) => enabled);
            const limits = Object.entries(plan.limits ?? {}).filter(([, value]) => value !== null && value !== "");
            return (
              <article key={plan.id} className="ar-card">
                <header>
                  <span className="cc-stack">
                    <strong>{plan.name}</strong>
                    {safeText(plan.business_id) && <small>{safeText(plan.business_id)}</small>}
                  </span>
                  <StatusBadge status={plan.status} />
                </header>
                {plan.description && <p className="ac-muted">{plan.description}</p>}
                <h4>Includes</h4>
                {features.length ? (
                  <ul className="ar-chips">
                    {features.map(([feature]) => (
                      <li key={feature}>{featureLabel(feature)}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="ac-muted">No features listed.</p>
                )}
                <h4>Limits</h4>
                {limits.length ? (
                  <dl className="ar-limits">
                    {limits.map(([key, value]) => (
                      <div key={key}>
                        <dt>{LIMIT_LABELS[key] ?? titleCase(key)}</dt>
                        <dd>{String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <p className="ac-muted">No limits set.</p>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <Empty title="No plans yet" detail="Plans appear here once they are set up for the platform." />
      )}
    </Panel>
  );
}

type TenantRow = {
  id: string;
  business_id?: string | null;
  name?: string | null;
  tenant_key?: string | null;
  plan_code?: string | null;
  plan_name?: string | null;
  license_start?: string | null;
  expires_at?: string | null;
  seat_usage?: number | null;
  status?: string | null;
};

/** Columns the server can order every page by (backend platform_customers.py _subscription_sort_columns). */
const SUBSCRIPTION_SORT_KEYS = [
  "business_id",
  "tenant",
  "plan",
  "period",
  "seats",
  "status",
  "tenant_key",
  "plan_name",
  "plan_code",
  "license_start",
  "expires_at",
  "seat_usage",
  "created_at",
] as const;

/** Every tenant's plan and license period, with Change subscription on each row. */
function Subscriptions({ onMessage }: { onMessage: Notify }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [changing, setChanging] = useState<TenantRow | null>(null);
  const [limiting, setLimiting] = useState<TenantRow | null>(null);
  const { sort, onSort } = useServerSort(() => setPage(1));
  const params = new URLSearchParams({ page: String(page), page_size: "25", sort: "name", ...sortParams(sort) });
  if (query.trim()) params.set("q", query.trim());
  const tenants = useResource<{ items: TenantRow[]; total: number; pages: number }>(
    `/api/v1/platform-admin/customers?${params}`,
  );
  return (
    <Panel eyebrow="Licenses" title="Subscriptions" state={tenants.state} error={tenants.error}>
      <Intro>Each tenant has its own plan and license period. The previous subscription stays in the history.</Intro>
      <div className="cc-toolbar">
        <SearchBox
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
          label="Search customer, tenant or ID"
        />
      </div>
      <Table
        caption="Subscriptions"
        rows={tenants.data?.items ?? []}
        rowKey={(row) => row.id}
        serverSort={{ sort, onSort, keys: SUBSCRIPTION_SORT_KEYS }}
        empty={{ title: "No matching tenants", detail: "Change the search." }}
        columns={[
          idColumn("Tenant ID", "tenant_key"),
          {
            key: "tenant",
            fields: ["name"],
            label: "Tenant",
            render: (row) => <strong>{row.name ?? "—"}</strong>,
          },
          {
            key: "plan",
            fields: ["plan_name", "plan_code"],
            label: "Plan",
            render: (row) => row.plan_name ?? row.plan_code ?? "Not assigned",
          },
          {
            key: "period",
            fields: ["license_start", "expires_at"],
            label: "License period",
            render: (row) =>
              row.expires_at
                ? `${row.license_start ? formatDay(row.license_start) : "—"} – ${formatDay(row.expires_at)}`
                : "No end date",
          },
          { key: "seats", fields: ["seat_usage"], label: "Users", numeric: true, render: (row) => row.seat_usage ?? 0 },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          {
            key: "change",
            label: "",
            render: (row) => (
              <span className="ca-action-row">
                <button type="button" className="ac-link" onClick={() => setChanging(row)}>
                  Change plan
                </button>
                <button type="button" className="ac-link" onClick={() => setLimiting(row)}>
                  Edit limits
                </button>
              </span>
            ),
          },
        ]}
      />
      <Pager
        page={page}
        pages={tenants.data?.pages ?? 1}
        total={tenants.data?.total ?? 0}
        noun="tenant"
        onPage={setPage}
      />
      {limiting && (
        <TenantLimits
          tenant={limiting}
          onClose={() => setLimiting(null)}
          onSaved={() => {
            setLimiting(null);
            onMessage(`${limiting.name ?? "Tenant"}: limits updated.`);
            tenants.reload();
          }}
        />
      )}
      {changing && (
        <ChangeSubscription
          tenants={[{ id: changing.id, tenant_key: changing.tenant_key, display_name: changing.name }]}
          currentPlans={changing.plan_code ? [changing.plan_code] : []}
          onClose={() => setChanging(null)}
          onChanged={(message) => {
            setChanging(null);
            onMessage(`${changing.name ?? "Tenant"}: ${message}`);
            tenants.reload();
          }}
        />
      )}
    </Panel>
  );
}

const TENANT_LIMITS = [
  { key: "licensed_users_limit", usage: "licensed_users", label: "Licensed users" },
  { key: "customer_admin_limit", usage: "customer_admins", label: "Customer administrators" },
  { key: "connector_limit", usage: "connectors", label: "Connections" },
] as const;

/** One tenant's own limits (its plan's other customers are not affected); never below what it already uses. */
function TenantLimits({ tenant, onClose, onSaved }: { tenant: TenantRow; onClose: () => void; onSaved: () => void }) {
  const usage = useResource<{ usage: Record<string, number>; limits: Record<string, unknown> }>(
    `/api/v1/platform-admin/customers/${tenant.id}/usage`,
  );
  const [values, setValues] = useState<Record<string, string>>({});
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current = (key: string) => {
    const value = usage.data?.limits?.[key];
    return typeof value === "number" ? String(value) : "";
  };
  const changed = Object.fromEntries(
    TENANT_LIMITS.filter(({ key }) => (values[key] ?? current(key)) !== current(key) && values[key] !== "").map(
      ({ key }) => [key, Number(values[key])],
    ),
  );
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/platform-admin/customers/${tenant.id}/limits`, "PUT", { ...changed, reason: reason.trim() });
      onSaved();
    } catch (failure) {
      setError(errorText(failure, "The limits were not changed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Limits for ${tenant.name ?? tenant.tenant_key}`} onClose={onClose}>
      <Intro>These limits belong to this tenant only. A limit cannot go below what the tenant already uses.</Intro>
      {usage.state === "ready" &&
        TENANT_LIMITS.map(({ key, usage: used, label }) => (
          <label className="ca-field" key={key}>
            {label} · {usage.data?.usage?.[used] ?? 0} in use
            <input
              type="number"
              min={key === "connector_limit" ? 0 : 1}
              value={values[key] ?? current(key)}
              onChange={(event) => setValues({ ...values, [key]: event.target.value })}
            />
          </label>
        ))}
      <label className="ca-field">
        Reason (kept in the tenant&apos;s audit trail)
        <textarea rows={2} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          disabled={busy || reason.trim().length < 10 || !Object.keys(changed).length}
          onClick={() => void save()}
        >
          Save limits
        </button>
      </div>
    </Drawer>
  );
}

type Renewal = {
  subscription_id: string;
  subscription_business_id?: string | null;
  tenant_business_id?: string | null;
  tenant_name?: string | null;
  tenant_key?: string | null;
  customer_name?: string | null;
  plan_name?: string | null;
  status: string;
  expires_at?: string | null;
  days_remaining: number | null;
  reminders_queued: number;
};

// Each license is in exactly one period; a license without an end date is in none of the date periods.
const WINDOWS = [
  { key: "expired", label: "Ended", test: (days: number | null) => days !== null && days < 0 },
  { key: "7", label: "Within 7 days", test: (days: number | null) => days !== null && days >= 0 && days <= 7 },
  { key: "30", label: "Within 30 days", test: (days: number | null) => days !== null && days > 7 && days <= 30 },
  { key: "later", label: "Later than 30 days", test: (days: number | null) => days !== null && days > 30 },
  { key: "none", label: "No end date", test: (days: number | null) => days === null },
] as const;

const dayCount = (days: number) => `${days} day${days === 1 ? "" : "s"}`;
/** "in 3 days", "today", "1 day ago". */
const endsIn = (days: number | null) =>
  days === null ? "" : days === 0 ? "today" : days < 0 ? `${dayCount(-days)} ago` : `in ${dayCount(days)}`;

/** Licenses by how soon they end, so renewals are handled before access stops. */
function Renewals() {
  const renewals = useResource<{ items: Renewal[] }>("/api/v1/platform-admin/console/renewals");
  const [period, setPeriod] = useState<string>("");
  const rows = renewals.data?.items ?? [];
  const count = (key: string) =>
    rows.filter((row) => WINDOWS.find((item) => item.key === key)!.test(row.days_remaining ?? null)).length;
  const shown = period
    ? rows.filter((row) => WINDOWS.find((item) => item.key === period)!.test(row.days_remaining ?? null))
    : rows;
  return (
    <div className="ac-grid">
      <section className="ac-stats ar-stats-4" aria-label="Licenses by end date">
        <StatTile
          label="Ended"
          value={renewals.data ? count("expired") : null}
          detail="Past the end date: renew or close"
          icon={<CalendarX2 size={18} />}
          tone={count("expired") ? "critical" : "good"}
          onOpen={() => setPeriod("expired")}
        />
        <StatTile
          label="Within 7 days"
          value={renewals.data ? count("7") : null}
          detail="Renew now"
          icon={<AlarmClock size={18} />}
          tone={count("7") ? "serious" : "good"}
          onOpen={() => setPeriod("7")}
        />
        <StatTile
          label="Within 30 days"
          value={renewals.data ? count("30") : null}
          detail="Plan the renewal"
          icon={<CalendarClock size={18} />}
          tone={count("30") ? "warning" : "good"}
          onOpen={() => setPeriod("30")}
        />
        <StatTile
          label="Later than 30 days"
          value={renewals.data ? count("later") : null}
          detail="Nothing to do yet"
          icon={<CheckCircle2 size={18} />}
          tone="good"
          onOpen={() => setPeriod("later")}
        />
      </section>
      <Panel eyebrow="Renewals" title="Licenses by end date" state={renewals.state} error={renewals.error}>
        <div className="ca-chips" role="group" aria-label="Show licenses">
          <button type="button" className={period === "" ? "selected" : ""} onClick={() => setPeriod("")}>
            All ({rows.length})
          </button>
          {WINDOWS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={period === item.key ? "selected" : ""}
              onClick={() => setPeriod(item.key)}
            >
              {item.label} ({count(item.key)})
            </button>
          ))}
        </div>
        <Table
          caption="Licenses by end date"
          rows={shown}
          rowKey={(row) => row.subscription_id}
          empty={{
            title: "No licenses here",
            detail: rows.length ? "Choose another period." : "Licenses with an end date appear here.",
          }}
          columns={[
            referenceIdColumn("Subscription ID", "subscription"),
            {
              key: "tenant",
              fields: ["tenant_name", "tenant_key", "customer_name", "tenant_business_id", "tenant_id"],
              label: "Tenant",
              render: (row) => <TenantCell row={row} />,
            },
            { key: "plan", fields: ["plan_name"], label: "Plan", render: (row) => row.plan_name ?? "—" },
            {
              key: "ends",
              fields: ["expires_at", "days_remaining"],
              label: "Ends",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.expires_at ? formatDay(row.expires_at) : "—"}</strong>
                  <small>{endsIn(row.days_remaining ?? null)}</small>
                </span>
              ),
            },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "reminders",
              fields: ["reminders_queued"],
              label: "Reminder emails waiting",
              numeric: true,
              render: (row) => row.reminders_queued,
            },
          ]}
        />
      </Panel>
    </div>
  );
}

type ReminderSettings = {
  policy: { name: string; thresholds: number[]; version: string; created_at?: string } | null;
  default_thresholds: number[];
  templates: Array<{
    id: string;
    stage: string;
    version: string;
    subject: string;
    status: string;
    created_at?: string;
  }>;
  template_variables: string[];
};

const STAGES = [
  ["EXPIRING", "Before the license ends"],
  ["GRACE", "During the grace period"],
  ["EXPIRED", "After the license has ended"],
] as const;

const SAMPLE: Record<string, string> = {
  customer_name: "Apex Medical Devices",
  expiry_date: formatDay(Date.now() + 30 * 86_400_000),
  days_remaining: "30",
  activation_link: "https://app.mdarix.example/renew",
};

const nextVersion = (version?: string) => {
  const number = Number(String(version ?? "").replace(/^v/i, ""));
  return Number.isInteger(number) && number > 0 ? `v${number + 1}` : "v1";
};

/** A tenant's reminder schedule and its reminder emails, edited in plain language with a live preview. */
function Reminders({ onMessage }: { onMessage: Notify }) {
  const [tenantId, setTenantId] = useState("");
  const settings = useResource<ReminderSettings>(
    tenantId ? `/api/v1/platform-admin/tenants/${tenantId}/reminder-settings` : null,
  );
  return (
    <div className="ac-grid">
      <Panel eyebrow="Renewal reminders" title="Reminders">
        <Intro>
          Reminders are set per tenant: when they are due before the license ends, and what the email says. Choose the
          tenant first.
        </Intro>
        <TenantPicker value={tenantId} onChange={setTenantId} />
        <p className="ar-notice" role="note">
          <Mail size={16} aria-hidden="true" /> Reminders are emailed on the chosen days to the tenant&apos;s Customer
          Administrators and the contacts in its notification settings. The newest saved email for each stage is the one
          sent; without one, the standard wording is used. Operations, Email &amp; notifications shows whether email is
          configured.
        </p>
      </Panel>
      {tenantId && (
        <div className="ac-grid two" key={tenantId}>
          <Schedule tenantId={tenantId} settings={settings} onMessage={onMessage} />
          <TemplateEditor tenantId={tenantId} settings={settings} onMessage={onMessage} />
        </div>
      )}
    </div>
  );
}

function Schedule({
  tenantId,
  settings,
  onMessage,
}: {
  tenantId: string;
  settings: Resource<ReminderSettings>;
  onMessage: Notify;
}) {
  const current = settings.data?.policy?.thresholds ?? settings.data?.default_thresholds ?? [];
  const [text, setText] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const value = text ?? current.join(", ");
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = parseThresholds(value);
    if (parsed.error) return setError(parsed.error);
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/platform/subscriptions/${tenantId}/reminder-policies`, "POST", {
        name: "Renewal reminders",
        thresholds: parsed.days,
        timezone: "UTC",
        recipient_types: ["CUSTOMER_ADMIN"],
        version: nextVersion(settings.data?.policy?.version),
      });
      onMessage(`Reminder schedule saved: ${parsed.days.join(", ")} days before the license ends.`);
      setText(null);
      settings.reload();
    } catch (reason) {
      setError(errorText(reason, "The schedule was not saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel eyebrow="When" title="Reminder schedule" state={settings.state} error={settings.error}>
      <p>
        {settings.data?.policy ? "This tenant's schedule" : "The default schedule (this tenant has not changed it)"}:
      </p>
      <ul className="ar-chips">
        {current.map((days) => (
          <li key={days}>{days === 0 ? "On the day it ends" : `${days} days before`}</li>
        ))}
      </ul>
      <form className="cc-form" onSubmit={save}>
        <label className="ca-field">
          Days before the license ends
          <input value={value} onChange={(event) => setText(event.target.value)} placeholder="e.g. 90, 45, 14" />
        </label>
        <p className="ac-muted">Sent to the tenant&apos;s Customer Administrators.</p>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="ac-primary" disabled={busy}>
          {busy ? "Saving…" : "Save schedule"}
        </button>
      </form>
    </Panel>
  );
}

function TemplateEditor({
  tenantId,
  settings,
  onMessage,
}: {
  tenantId: string;
  settings: Resource<ReminderSettings>;
  onMessage: Notify;
}) {
  const allowed = settings.data?.template_variables ?? [];
  const [form, setForm] = useState({
    stage: "EXPIRING",
    subject: "Your MDARIX license ends on {{expiry_date}}",
    body: "Hello {{customer_name}},\n\nYour MDARIX license ends in {{days_remaining}} days, on {{expiry_date}}. Contact us to renew.",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const used = useMemo(() => templateVariables(`${form.subject} ${form.body}`), [form]);
  const unknown = used.filter((name) => !allowed.includes(name));
  const insert = (name: string) => setForm({ ...form, body: `${form.body}{{${name}}}` });
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (unknown.length) return setError(`Remove ${unknown.map((name) => `{{${name}}}`).join(", ")}: not available.`);
    setBusy(true);
    setError("");
    const versions = (settings.data?.templates ?? []).filter((item) => item.stage === form.stage);
    try {
      await send(`/api/v1/platform/subscriptions/${tenantId}/email-templates`, "POST", {
        stage: form.stage,
        version: nextVersion(versions[0]?.version),
        subject: form.subject.trim(),
        body: form.body.trim(),
        allowed_variables: used,
      });
      onMessage("Reminder email saved. It is used for the next reminders at this stage.");
      settings.reload();
    } catch (reason) {
      setError(errorText(reason, "The email was not saved."));
    } finally {
      setBusy(false);
    }
  };
  const templates = settings.data?.templates ?? [];
  return (
    <Panel eyebrow="What" title="Reminder email" state={settings.state} error={settings.error}>
      <form className="cc-form" onSubmit={save}>
        <label className="ca-field">
          Sent
          <select value={form.stage} onChange={(event) => setForm({ ...form, stage: event.target.value })}>
            {STAGES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Subject
          <input
            required
            maxLength={255}
            value={form.subject}
            onChange={(event) => setForm({ ...form, subject: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Message
          <textarea
            required
            rows={6}
            value={form.body}
            onChange={(event) => setForm({ ...form, body: event.target.value })}
          />
        </label>
        <div className="ar-insert" role="group" aria-label="Insert a value">
          <span className="ac-muted">Insert:</span>
          {allowed.map((name) => (
            <button key={name} type="button" className="ac-secondary" onClick={() => insert(name)}>
              {titleCase(name)}
            </button>
          ))}
        </div>
        <section className="ar-preview" aria-label="Preview">
          <p className="ac-eyebrow">Preview</p>
          <strong>{previewTemplate(form.subject, SAMPLE)}</strong>
          <p>{previewTemplate(form.body, SAMPLE)}</p>
        </section>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="ac-primary" disabled={busy}>
          {busy ? "Saving…" : "Save email"}
        </button>
      </form>
      {templates.length > 0 && (
        <Table
          caption="Saved reminder emails"
          rows={templates}
          rowKey={(row) => row.id}
          empty={{ title: "None yet", detail: "" }}
          columns={[
            {
              key: "stage",
              label: "Sent",
              render: (row) => STAGES.find(([value]) => value === row.stage)?.[1] ?? row.stage,
            },
            { key: "subject", label: "Subject", render: (row) => row.subject },
            { key: "version", label: "Version", render: (row) => row.version },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "saved", label: "Saved", render: (row) => formatDate(row.created_at) },
          ]}
        />
      )}
    </Panel>
  );
}
