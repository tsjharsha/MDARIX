import { useState } from "react";
import { Archive, Download, Globe2, KeyRound, LifeBuoy, LockKeyhole, ShieldCheck } from "lucide-react";
import { BarList, Panel, StatTile } from "../console/charts";
import type { Slice } from "../console/dashboardModel";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  errorText,
  formatDate,
  listOf,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { displayCode, titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { Intro, Pager, TenantCell, TenantPicker } from "./common";
import { DialogBehaviour } from "../../shared/DialogBehaviour";
import { formatDay } from "../../../app/dates";
import { sortParams, useServerSort } from "../../../app/tableSort";
import { PersonCell } from "./common";

type Notify = (text: string, tone?: "good" | "critical") => void;

/** An audit action in words ("SOD_DENIED" -> "Segregation of duties denied"). */
const actionLabel = (action: string) => titleCase(action).replace(/^Sod\b/, "Segregation of duties");

type Posture = {
  isolation: {
    tenant_tables: number;
    protected: number;
    unprotected: string[];
    excluded_by_design: string[];
    unexpected: string[];
  };
  sign_in: { active_accounts: number; mfa_required: number; mfa_enrolled: number };
  support_access: Record<string, number>;
  residency: Array<{ region: string; tenants: number }>;
  denied_or_failed_30_days: Array<{ action: string; count: number }>;
  retention: {
    audit_events: number;
    oldest_event_at: string | null;
    earliest_release_at: string | null;
    policy: string;
  };
};

export function SecurityArea({ section, onMessage }: { section: string; onMessage: Notify }) {
  if (section === "Audit trail") return <AuditTrail />;
  if (section === "Support access") return <SupportAccess onMessage={onMessage} />;
  if (section === "Retention") return <Retention />;
  return <Overview />;
}

const usePosture = () => useResource<Posture>("/api/v1/platform-admin/console/security");

/** Isolation, sign-in protection, support access and data residency, measured from the live database. */
function Overview() {
  const posture = usePosture();
  const data = posture.data;
  const isolated = data ? data.isolation.unexpected.length === 0 : null;
  const active = (data?.support_access.ACTIVE ?? 0) + (data?.support_access.APPROVED ?? 0);
  const regions: Slice[] = (data?.residency ?? []).map((row) => ({
    key: row.region,
    label: row.region === "UNSPECIFIED" ? "Not specified" : row.region,
    count: row.tenants,
    tone: row.region === "UNSPECIFIED" ? "warning" : "neutral",
  }));
  return (
    <div className="ac-grid">
      <section className="ac-stats ar-stats-4" aria-label="Security at a glance">
        <StatTile
          label="Tenant isolation"
          value={data ? (isolated ? "Protected" : "Needs attention") : null}
          detail={
            data
              ? isolated
                ? `Each tenant sees only its own data (${data.isolation.protected} of ${data.isolation.tenant_tables} tables separate tenants; the rest are shared by design)`
                : "Some tenant data is not protected: see Tenant isolation below"
              : "Checking"
          }
          icon={<LockKeyhole size={18} />}
          tone={isolated === null ? undefined : isolated ? "good" : "critical"}
        />
        <StatTile
          label="Two-step sign-in"
          value={data ? `${data.sign_in.mfa_enrolled} / ${data.sign_in.active_accounts}` : null}
          detail="Active accounts enrolled"
          icon={<KeyRound size={18} />}
          tone={data ? (data.sign_in.mfa_enrolled < data.sign_in.mfa_required ? "warning" : "neutral") : undefined}
        />
        <StatTile
          label="Support access"
          value={data ? active : null}
          detail={`${data?.support_access.PENDING ?? 0} waiting for approval`}
          icon={<LifeBuoy size={18} />}
          tone={data?.support_access.PENDING ? "warning" : "good"}
        />
        <StatTile
          label="Data regions"
          value={data ? data.residency.length : null}
          detail="Where tenant data is kept"
          icon={<Globe2 size={18} />}
        />
      </section>
      <div className="ac-grid two">
        <Panel
          eyebrow="Data separation between tenants"
          title="Tenant isolation"
          state={posture.state}
          error={posture.error}
        >
          {data && (
            <>
              <Intro>
                {data.isolation.protected} of the {data.isolation.tenant_tables} places where data is stored only ever
                show a tenant its own records. The others hold the platform&apos;s own shared information and are kept
                apart on purpose.
              </Intro>
              {data.isolation.unexpected.length > 0 && (
                <p className="ca-inline-error" role="alert">
                  Not protected: {data.isolation.unexpected.join(", ")}
                </p>
              )}
              <details className="ar-technical">
                <summary>Technical detail: platform tables (excluded by design)</summary>
                <ul className="ar-chips">
                  {data.isolation.excluded_by_design.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              </details>
            </>
          )}
        </Panel>
        <Panel eyebrow="Data residency" title="Tenants by data region" state={posture.state} error={posture.error}>
          {regions.length ? <BarList items={regions} colour="series" /> : <p className="ac-muted">No tenants.</p>}
        </Panel>
      </div>
      <Panel eyebrow="Last 30 days" title="Refused or failed actions" state={posture.state} error={posture.error}>
        <Intro>Actions the platform refused (for example an approval by someone without authority).</Intro>
        <Table
          caption="Refused or failed actions"
          rows={data?.denied_or_failed_30_days ?? []}
          rowKey={(row) => row.action}
          empty={{ title: "None", detail: "Nothing was refused in the last 30 days." }}
          columns={[
            { key: "action", label: "What", render: (row) => actionLabel(row.action) },
            { key: "count", label: "Times", numeric: true, render: (row) => row.count },
          ]}
        />
      </Panel>
    </div>
  );
}

type AuditRow = {
  id: string;
  at: string;
  action: string;
  entity_type: string;
  actor?: string | null;
  actor_business_id?: string | null;
  reason?: string | null;
  tenant_name?: string | null;
  tenant_key?: string | null;
  customer_name?: string | null;
};

/** Columns the server can order every page by (backend platform_console.py platform_audit). */
const AUDIT_SORT_KEYS = [
  "when",
  "tenant",
  "who",
  "what",
  "why",
  "at",
  "tenant_name",
  "actor",
  "action",
  "entity_type",
  "reason",
  "source_ip",
] as const;

/** Who did what, where and why, across every tenant. Record contents are never shown. */
function AuditTrail() {
  const [query, setQuery] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [attention, setAttention] = useState(false);
  const [page, setPage] = useState(1);
  const { sort, onSort } = useServerSort(() => setPage(1));
  const params = new URLSearchParams({ page: String(page), page_size: "25", ...sortParams(sort) });
  if (query.trim()) params.set("q", query.trim());
  if (tenantId) params.set("tenant_id", tenantId);
  if (attention) params.set("attention", "true");
  const audit = useResource<{ items: AuditRow[]; total: number; pages: number }>(
    `/api/v1/platform-admin/console/audit?${params}`,
  );
  const filter = (apply: () => void) => {
    apply();
    setPage(1);
  };
  return (
    <Panel
      eyebrow="All tenants"
      title="Audit trail"
      source={audit}
      action={
        <span className="cc-actions">
          <a
            className="ac-secondary"
            href="/api/v1/admin/audit-history/export?output_format=CSV"
            title="The MDARIX platform tenant's own audit trail"
          >
            <Download size={16} aria-hidden="true" /> Export platform audit (CSV)
          </a>
          <a
            className="ac-secondary"
            href="/api/v1/stage3/compliance-report?output_format=PDF"
            title="Compliance report of the MDARIX platform tenant"
          >
            <Download size={16} aria-hidden="true" /> Platform evidence package (PDF)
          </a>
        </span>
      }
    >
      <Intro>
        Every change is recorded with who made it and why. Record contents are not shown here. The exports cover the
        MDARIX platform tenant.
      </Intro>
      <div className="cc-toolbar">
        <SearchBox value={query} onChange={(value) => filter(() => setQuery(value))} label="Search action or record" />
        <TenantPicker
          value={tenantId}
          onChange={(value) => filter(() => setTenantId(value))}
          allLabel="All tenants"
          inline
        />
        <div className="ca-chips" role="group" aria-label="Show events">
          <button
            type="button"
            className={attention ? "" : "selected"}
            onClick={() => filter(() => setAttention(false))}
          >
            Everything
          </button>
          <button
            type="button"
            className={attention ? "selected" : ""}
            onClick={() => filter(() => setAttention(true))}
          >
            Refusals, suspensions and revocations
          </button>
        </div>
      </div>
      <Table
        caption="Audit trail"
        rows={audit.data?.items ?? []}
        rowKey={(row) => row.id}
        serverSort={{ sort, onSort, keys: AUDIT_SORT_KEYS }}
        empty={{ title: "No events", detail: "No event matches these filters." }}
        columns={[
          { key: "when", fields: ["at"], label: "When", render: (row) => formatDate(row.at) },
          {
            key: "tenant",
            fields: ["tenant_name", "tenant_key", "customer_name", "tenant_business_id", "tenant_id"],
            label: "Tenant",
            render: (row) => <TenantCell row={row} />,
          },
          {
            key: "who",
            fields: ["actor", "actor_business_id"],
            label: "Who",
            render: (row) => <PersonCell name={row.actor} businessId={row.actor_business_id} none="System" />,
          },
          {
            key: "what",
            fields: ["action", "entity_type"],
            label: "What",
            render: (row) => (
              <span className="cc-stack">
                <strong>{actionLabel(row.action)}</strong>
                <small>{displayCode(row.entity_type)}</small>
              </span>
            ),
          },
          { key: "why", fields: ["reason"], label: "Reason", render: (row) => row.reason ?? "—" },
        ]}
      />
      <Pager page={page} pages={audit.data?.pages ?? 1} total={audit.data?.total ?? 0} noun="event" onPage={setPage} />
    </Panel>
  );
}

type Grant = {
  id: string;
  person?: string | null;
  platform_user_business_id?: string | null;
  requested_by?: string | null;
  tenant_name?: string | null;
  tenant_key?: string | null;
  customer_name?: string | null;
  reason: string;
  status: string;
  areas?: Array<{ code: string; label: string }>;
  write?: boolean;
  starts_at?: string | null;
  expires_at?: string | null;
  approved_by?: string | null;
  customer_decided_by?: string | null;
  customer_decision_reason?: string | null;
  can_approve: boolean;
  can_revoke: boolean;
};

export type Area = { code: string; label: string };

/** Where a request stands: waiting for MDARIX, waiting for the customer, then the customer's decision. */
const GRANT_STATUS: Record<string, string> = {
  PENDING: "Waiting for MDARIX approval",
  AWAITING_CUSTOMER: "Waiting for the customer",
  APPROVED: "Active (customer approved)",
  DENIED: "Denied by the customer",
  REVOKED: "Revoked",
  EXPIRED: "Ended",
};

const areaShortNames = (areas?: Area[]) => (areas ?? []).map((area) => area.label.split(":")[0].trim()).join(", ");

const PLATFORM_ROLES = ["PLATFORM_ADMIN", "MDARIX_ADMINISTRATOR", "ADMINISTRATOR", "ADMIN"];
const DECISION = { label: "Reason (kept in the audit trail)", min: 10 };

/**
 * Time-limited access to part of a customer's data, for one platform colleague. A second platform administrator
 * approves it for MDARIX; then the customer's own administrators decide. Without their approval nothing opens.
 */
function SupportAccess({ onMessage }: { onMessage: Notify }) {
  const grants = useResource<{ items: Grant[]; areas: Area[] }>("/api/v1/platform-admin/console/support-access");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [requesting, setRequesting] = useState(false);
  const rows = grants.data?.items ?? [];
  return (
    <Panel
      eyebrow="Customer support"
      title="Support access"
      source={grants}
      action={
        <button type="button" className="ac-primary" onClick={() => setRequesting(true)}>
          <LifeBuoy size={16} aria-hidden="true" /> Request access
        </button>
      }
    >
      <Intro>
        A customer's data is theirs. Support access names the areas you need, is read-only unless changes are asked for,
        lasts at most 24 hours, and opens only after a second platform administrator approves it for MDARIX and then one
        of the customer's administrators approves it. Every use is recorded in the customer's audit trail.
      </Intro>
      <Table
        caption="Support access"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{ title: "No support access", detail: "Requests and their approvals appear here." }}
        columns={[
          {
            key: "tenant",
            fields: ["tenant_name", "tenant_key", "customer_name", "tenant_business_id", "tenant_id"],
            label: "Tenant",
            render: (row) => <TenantCell row={row} />,
          },
          {
            key: "person",
            fields: ["person", "platform_user_business_id", "platform_user_id"],
            label: "For",
            render: (row) => <PersonCell name={row.person} businessId={row.platform_user_business_id} />,
          },
          {
            key: "access",
            fields: ["areas", "write"],
            label: "Access",
            render: (row) => (
              <span className="cc-stack">
                <strong>{areaShortNames(row.areas) || "No area named"}</strong>
                <small>{row.write ? "Read and change" : "Read only"}</small>
              </span>
            ),
          },
          { key: "why", label: "Reason", render: (row) => row.reason },
          {
            key: "window",
            fields: ["starts_at", "expires_at"],
            label: "Access period",
            render: (row) => (
              <span className="cc-stack">
                <strong>{formatDate(row.starts_at)}</strong>
                <small>until {formatDate(row.expires_at)}</small>
              </span>
            ),
          },
          {
            key: "status",
            label: "Status",
            render: (row) => (
              <span className="cc-stack">
                <StatusBadge status={row.status} />
                <small>{GRANT_STATUS[row.status] ?? row.status}</small>
                {row.approved_by && <small>For MDARIX: {row.approved_by}</small>}
                {row.customer_decided_by && <small>Customer: {row.customer_decided_by}</small>}
              </span>
            ),
          },
          {
            key: "actions",
            label: "",
            render: (row) => (
              <span className="cc-actions">
                {row.can_approve && (
                  <button
                    type="button"
                    className="ac-link"
                    onClick={() =>
                      setConfirm({
                        title: `Approve for MDARIX: support access to ${row.tenant_name ?? "this tenant"}?`,
                        body: `The request goes to the customer's administrators, who decide. Nothing opens before they approve. You cannot approve a request you made or one for yourself.`,
                        confirmLabel: "Approve for MDARIX",
                        reason: DECISION,
                        run: (reason) =>
                          send(`/api/v1/platform-admin/support-access/${row.id}/approve`, "POST", { reason }),
                        done: "Approved for MDARIX. The customer's administrators have been asked.",
                      })
                    }
                  >
                    Approve for MDARIX
                  </button>
                )}
                {row.can_revoke && (
                  <button
                    type="button"
                    className="ac-link cc-danger-link"
                    onClick={() =>
                      setConfirm({
                        title: `Revoke support access to ${row.tenant_name ?? "this tenant"}?`,
                        body: "The access ends immediately.",
                        confirmLabel: "Revoke",
                        danger: true,
                        reason: DECISION,
                        run: (reason) =>
                          send(`/api/v1/platform-admin/support-access/${row.id}/revoke`, "POST", { reason }),
                        done: "Support access revoked.",
                      })
                    }
                  >
                    Revoke
                  </button>
                )}
              </span>
            ),
          },
        ]}
      />
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          onMessage(message);
          grants.reload();
        }}
      />
      {requesting && (
        <RequestAccess
          areas={grants.data?.areas ?? []}
          onClose={() => setRequesting(false)}
          onRequested={() => {
            setRequesting(false);
            onMessage(
              "Support access requested. A second platform administrator approves it for MDARIX, then the customer decides.",
            );
            grants.reload();
          }}
        />
      )}
    </Panel>
  );
}

const DURATIONS = [
  [1, "1 hour"],
  [4, "4 hours"],
  [8, "8 hours"],
  [24, "24 hours"],
] as const;

/** What a shortcut fills in for the request (Customers & Tenants › Trials › Request support access). */
export type RequestAccessDraft = {
  tenant_id?: string;
  platform_user_id?: string;
  areas?: string[];
  reason?: string;
  hours?: number;
};

/** The request form: one organization, one platform colleague, the areas, read-only unless changes are asked for. */
export function RequestAccess({
  areas,
  onClose,
  onRequested,
  initial,
}: {
  areas: Area[];
  onClose: () => void;
  onRequested: () => void;
  initial?: RequestAccessDraft;
}) {
  const users = useResource<any[]>("/api/v1/admin/identity/users");
  const people = listOf(users.data).filter(
    (user) =>
      PLATFORM_ROLES.includes(
        String(user.role ?? "")
          .toUpperCase()
          .replace(/ /g, "_"),
      ) && String(user.status ?? "").toUpperCase() === "ACTIVE",
  );
  const [form, setForm] = useState({
    tenant_id: initial?.tenant_id ?? "",
    platform_user_id: initial?.platform_user_id ?? "",
    hours: initial?.hours ?? 4,
    reason: initial?.reason ?? "",
    areas: initial?.areas ?? ([] as string[]),
    write: false,
  });
  const toggleArea = (code: string) =>
    setForm((current) => ({
      ...current,
      areas: current.areas.includes(code) ? current.areas.filter((item) => item !== code) : [...current.areas, code],
    }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.tenant_id) return setError("Choose the tenant.");
    if (!form.areas.length) return setError("Choose what you need to see: at least one area.");
    setBusy(true);
    setError("");
    const starts = new Date();
    const expires = new Date(starts.getTime() + form.hours * 3_600_000);
    try {
      await send("/api/v1/platform-admin/support-access", "POST", {
        tenant_id: form.tenant_id,
        platform_user_id: form.platform_user_id,
        scope: { areas: form.areas, write: form.write },
        reason: form.reason.trim(),
        starts_at: starts.toISOString(),
        expires_at: expires.toISOString(),
      });
      onRequested();
    } catch (reason) {
      setError(errorText(reason, "The request was not created."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="ar-request-access" onSubmit={submit}>
        <p className="ac-eyebrow">Support access</p>
        <h2 id="ar-request-access">Request access</h2>
        <p>
          Access to part of one customer's data, starting now. A second platform administrator approves it for MDARIX,
          then the customer's administrators decide.
        </p>
        <TenantPicker value={form.tenant_id} onChange={(tenant_id) => setForm({ ...form, tenant_id })} />
        <label className="ca-field">
          For
          <select
            required
            value={form.platform_user_id}
            onChange={(event) => setForm({ ...form, platform_user_id: event.target.value })}
          >
            <option value="">
              {users.state === "loading" ? "Loading people…" : "Choose a platform administrator"}
            </option>
            {people.map((user) => (
              <option key={user.id} value={user.id}>
                {user.display_name || user.email} ({user.email})
              </option>
            ))}
          </select>
        </label>
        <fieldset className="ca-field">
          <legend>What you need (only these areas open)</legend>
          {areas.map((area) => (
            <label key={area.code} className="ca-check">
              <input type="checkbox" checked={form.areas.includes(area.code)} onChange={() => toggleArea(area.code)} />
              {area.label}
            </label>
          ))}
          <label className="ca-check">
            <input
              type="checkbox"
              checked={form.write}
              onChange={(event) => setForm({ ...form, write: event.target.checked })}
            />
            Also allow changes (otherwise read-only)
          </label>
        </fieldset>
        <label className="ca-field">
          For how long
          <select value={form.hours} onChange={(event) => setForm({ ...form, hours: Number(event.target.value) })}>
            {DURATIONS.map(([hours, label]) => (
              <option key={hours} value={hours}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Reason (kept in the audit trail)
          <input
            required
            minLength={10}
            value={form.reason}
            onChange={(event) => setForm({ ...form, reason: event.target.value })}
            placeholder="e.g. Ticket 1234: customer cannot see their products"
          />
        </label>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy}>
            {busy ? "Requesting…" : "Request access"}
          </button>
        </div>
      </form>
    </div>
  );
}

/** How long audit records are kept, and how much is held. */
function Retention() {
  const posture = usePosture();
  const retention = posture.data?.retention;
  return (
    <div className="ac-grid">
      <section className="ac-stats ar-stats-3" aria-label="Retention">
        <StatTile
          label="Audit events kept"
          value={retention ? retention.audit_events : null}
          detail="All tenants"
          icon={<Archive size={18} />}
        />
        <StatTile
          label="Oldest event"
          value={retention?.oldest_event_at ? formatDay(retention.oldest_event_at) : null}
          detail="Earliest record held"
          icon={<ShieldCheck size={18} />}
        />
        <StatTile
          label="Earliest date records may be deleted"
          value={retention?.earliest_release_at ? formatDay(retention.earliest_release_at) : null}
          detail="Nothing may be deleted before this"
          icon={<LockKeyhole size={18} />}
        />
      </section>
      <Panel eyebrow="Policy" title="Retention" state={posture.state} error={posture.error}>
        <Intro>{retention?.policy}</Intro>
        <p className="ac-muted">
          Audit events cannot be edited or deleted. Removing data at the end of retention is a controlled process, not a
          button.
        </p>
      </Panel>
    </div>
  );
}
