import { useRef, useState } from "react";
import { MASKING_SUMMARY, aiAcknowledgement, aiSettingsPayload, providerLabel } from "../../customer-admin/aiSettings";
import { ArrowLeft, Globe2, Lock, PauseCircle, PlayCircle, Plus, Unlock } from "lucide-react";
import { Panel, ToneBadge } from "../console/charts";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  Tabs,
  errorText,
  formatDate,
  idColumn,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { displayId, referenceId } from "../../../app/displayId";
import { CustomerAdmins } from "./CustomerAdmins";
import { lifecycleAction, titleCase } from "./model";
import { StatusBadge } from "./StatusBadge";
import { DialogBehaviour } from "../../shared/DialogBehaviour";
import {
  WAIVER_MIN,
  exportAfterSuspension,
  handBackReady,
  legalHoldError,
  legalHoldRequest,
  purgeOutcome,
  purgeRequest,
  type DataExport,
  type HandBack,
  type LegalHold,
  type PurgeResult,
} from "./dataGovernance";

/** Every tenant (customer workspace). Opening a row shows the tenant's page. */
export function TenantDirectory({ onOpen }: { onOpen: (tenantId: string) => void }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page) });
  if (query.trim()) params.set("q", query.trim());
  if (status) params.set("status", status);
  const tenants = useResource<{ items: any[]; total: number; pages: number }>(
    `/api/v1/platform-admin/tenants?${params}`,
  );
  const pages = tenants.data?.pages ?? 1;
  return (
    <Panel eyebrow="Tenants" title="Tenant directory" source={tenants}>
      <div className="cc-toolbar">
        <SearchBox
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
          label="Search tenant name or ID"
        />
        <select
          aria-label="Tenant status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="PROVISIONED">Provisioned</option>
        </select>
      </div>
      <Table
        caption="Tenants"
        rows={tenants.data?.items ?? []}
        rowKey={(row) => row.id}
        empty={{ title: "No matching tenants", detail: "Change the search or status filter." }}
        columns={[
          idColumn("Tenant ID", "tenant_key"),
          {
            key: "tenant",
            fields: ["name", "tenant_key", "tenant_identifier"],
            label: "Tenant",
            render: (row) => (
              <button type="button" className="ac-link cc-stack" onClick={() => onOpen(row.id)}>
                <strong>{row.name}</strong>
                {row.tenant_key && <small>{row.tenant_key}</small>}
              </button>
            ),
          },
          {
            key: "customer",
            fields: ["customer_name", "customer_business_id", "customer_identifier", "customer_id"],
            label: "Customer",
            render: (row) => (
              <span className="cc-stack">
                <strong>{row.customer_name ?? "—"}</strong>
                <small>{referenceId(row, "customer", row.customer_identifier)}</small>
              </span>
            ),
          },
          {
            key: "region",
            fields: ["residency_region", "region"],
            label: "Data region",
            render: (row) => row.residency_region ?? row.region ?? "—",
          },
          {
            key: "plan",
            fields: ["plan_name", "plan_code"],
            label: "Plan",
            render: (row) => row.plan_name ?? row.plan_code ?? "—",
          },
          {
            key: "environments",
            fields: ["environment_count"],
            label: "Environments",
            numeric: true,
            render: (row) => row.environment_count ?? 0,
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
      <div className="cc-pager">
        <span>{tenants.data?.total ?? 0} tenants</span>
        <button type="button" className="ac-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button type="button" className="ac-secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
    </Panel>
  );
}

const SECTIONS = [
  "Overview",
  "Administrators",
  "Environments",
  "Domain & identity",
  "AI processing",
  "Data",
  "Activity",
] as const;
type Section = (typeof SECTIONS)[number];

export function TenantPage({
  tenantId,
  onBack,
  onOpenCustomer,
  onMessage,
}: {
  tenantId: string;
  onBack: () => void;
  onOpenCustomer?: (customerId: string) => void;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const record = useResource<{ tenant: any; environments: any[]; identity_providers: any[] }>(
    `/api/v1/platform-admin/tenants/${tenantId}`,
  );
  const [section, setSection] = useState<Section>("Overview");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const tenant = record.data?.tenant;
  const next = lifecycleAction(tenant?.status);
  const name = tenant?.display_name ?? tenant?.tenant_key ?? "Tenant";
  const changeStanding = () =>
    next &&
    setConfirm({
      title: next === "SUSPENDED" ? `Suspend ${name}?` : `Reactivate ${name}?`,
      body:
        next === "SUSPENDED"
          ? "Nobody in this tenant can sign in until it is reactivated. Its data is kept."
          : "The tenant becomes active again and its users can sign in.",
      confirmLabel: next === "SUSPENDED" ? "Suspend tenant" : "Reactivate tenant",
      danger: next === "SUSPENDED",
      reason: { label: "Reason (kept in the audit trail)", min: 5 },
      password: true,
      run: (reason, password) =>
        send(`/api/v1/platform-admin/tenants/${tenantId}/lifecycle`, "POST", {
          status: next,
          reason,
          password,
          lock_version: tenant?.lock_version,
        }),
      done: next === "SUSPENDED" ? `${name} is suspended.` : `${name} is active again.`,
    });
  return (
    <div className="cc-page">
      <div className="cc-page-head">
        <button type="button" className="ac-link" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden="true" /> Back
        </button>
        <div className="cc-title">
          <div>
            <p className="ac-eyebrow">Tenant · {tenant ? displayId(tenant, "tenant_key") : "…"}</p>
            <h2>{name}</h2>
            {tenant?.customer_name && (
              <p className="ac-muted">
                Belongs to{" "}
                {onOpenCustomer && tenant.customer_id ? (
                  <button type="button" className="ac-link" onClick={() => onOpenCustomer(tenant.customer_id)}>
                    {tenant.customer_name}
                  </button>
                ) : (
                  <strong>{tenant.customer_name}</strong>
                )}{" "}
                ({referenceId(tenant, "customer", tenant.customer_identifier)})
              </p>
            )}
          </div>
          <span className="cc-actions">
            <StatusBadge status={tenant?.status} />
            {next && (
              <button
                type="button"
                className={next === "SUSPENDED" ? "ca-danger" : "ac-primary"}
                onClick={changeStanding}
              >
                {next === "SUSPENDED" ? (
                  <PauseCircle size={16} aria-hidden="true" />
                ) : (
                  <PlayCircle size={16} aria-hidden="true" />
                )}{" "}
                {next === "SUSPENDED" ? "Suspend tenant" : "Reactivate tenant"}
              </button>
            )}
          </span>
        </div>
      </div>
      {record.state === "error" && (
        <p className="ca-inline-error" role="alert">
          {record.error ?? "The tenant could not be loaded."}
        </p>
      )}
      <Tabs tabs={SECTIONS} active={section} onChange={setSection} label="Tenant sections">
        {tenant && section === "Overview" && (
          <>
            <TenantOverview tenant={tenant} />
            <LegalHoldPanel tenantId={tenantId} name={name} onMessage={onMessage} />
          </>
        )}
        {tenant && section === "Administrators" && (
          <CustomerAdmins
            tenantId={tenantId}
            tenants={[{ id: tenantId, tenant_key: tenant.tenant_key, display_name: tenant.display_name }]}
            onMessage={onMessage}
          />
        )}
        {tenant && section === "Environments" && (
          <Environments
            tenantId={tenantId}
            rows={record.data?.environments ?? []}
            defaultRegion={tenant.residency_region ?? tenant.primary_region ?? ""}
            onChanged={(message) => {
              onMessage(message);
              record.reload();
            }}
          />
        )}
        {tenant && section === "Domain & identity" && (
          <DomainIdentity tenantId={tenantId} providers={record.data?.identity_providers ?? []} onMessage={onMessage} />
        )}
        {tenant && section === "AI processing" && (
          <TenantAiSettings tenantId={tenantId} name={name} onMessage={onMessage} />
        )}
        {tenant && section === "Data" && (
          <TenantData
            tenantId={tenantId}
            tenantKey={tenant.tenant_key}
            status={tenant.status}
            suspendedAt={tenant.suspended_at ?? null}
            name={name}
            onMessage={onMessage}
            onChanged={() => record.reload()}
          />
        )}
        {tenant && section === "Activity" && <TenantActivity tenantId={tenantId} />}
        <ConfirmDialog
          request={confirm}
          onClose={() => setConfirm(null)}
          onDone={(message) => {
            setConfirm(null);
            onMessage(message);
            record.reload();
          }}
        />
      </Tabs>
    </div>
  );
}

const TENANT_DETAILS: Array<[string, string]> = [
  ["Tenant ID", "business_id"],
  ["Tenant key", "tenant_key"],
  ["Deployment", "deployment_model"],
  ["Primary region", "primary_region"],
  ["Data residency", "residency_region"],
  ["Database region", "database_region"],
  ["Storage region", "storage_region"],
  ["AI processing region", "ai_processing_region"],
  ["Backup region", "backup_region"],
];

function TenantOverview({ tenant }: { tenant: any }) {
  return (
    <Panel eyebrow="Workspace" title="Tenant details">
      <dl className="cc-details">
        {TENANT_DETAILS.map(([label, key]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{key === "business_id" ? displayId(tenant, "tenant_identifier") : tenant[key] || "—"}</dd>
          </div>
        ))}
        <div>
          <dt>Cross-border processing</dt>
          <dd>{tenant.cross_border_processing_allowed ? "Allowed" : "Not allowed"}</dd>
        </div>
        <div>
          <dt>Activated</dt>
          <dd>{formatDate(tenant.activated_at)}</dd>
        </div>
      </dl>
    </Panel>
  );
}

type AiSettings = {
  ai_processing_allowed: boolean;
  monthly_token_budget: number;
  budget_is_default: boolean;
  tokens_used: number;
  requests: number;
  refused: number;
  month: string;
  models: { provider: string; model: string }[];
  provider_name: string | null;
  masking: boolean;
};

/** Whether the tenant's content may go to an AI model, its monthly token allowance, and this month's use. */
function TenantAiSettings({
  tenantId,
  name,
  onMessage,
}: {
  tenantId: string;
  name: string;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const url = `/api/v1/platform-admin/tenants/${tenantId}/ai-settings`;
  const settings = useResource<AiSettings>(url);
  const [budget, setBudget] = useState("");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const data = settings.data;
  const on = data?.ai_processing_allowed ?? false;
  const ask = (body: Record<string, unknown>, title: string, effect: string, done: string) =>
    setConfirm({
      title,
      body: effect,
      confirmLabel: "Save",
      reason: { label: "Reason (kept in the audit trail)", min: 5 },
      run: (reason) => send(url, "PUT", { ...body, reason }),
      done,
    });
  // Turning AI on needs the acknowledgement, given here on the customer's instruction (the API refuses it otherwise).
  const switchAi = () =>
    setConfirm({
      title: on ? `Turn AI off for ${name}?` : `Turn AI on for ${name}?`,
      body: on
        ? "Nothing from this tenant is sent to an AI model; its features answer from rules."
        : `This tenant's AI features will send the records an answer needs to ${providerLabel(data?.provider_name)}. ${MASKING_SUMMARY}`,
      confirmLabel: on ? "Turn AI off" : "Turn AI on",
      reason: { label: "Reason (kept in the audit trail)", min: 5 },
      ...(on ? {} : { acknowledge: aiAcknowledgement(data?.provider_name, name) }),
      run: (reason, _password, acknowledged) => send(url, "PUT", aiSettingsPayload(!on, reason, acknowledged)),
      done: on ? `AI processing is off for ${name}.` : `AI processing is on for ${name}.`,
    });
  return (
    <>
      <Panel eyebrow="AI processing" title={`AI for ${name}`} source={settings}>
        {data && (
          <dl className="cc-details">
            <div>
              <dt>AI processing</dt>
              <dd>{on ? "On" : "Off: rule-based answers only"}</dd>
            </div>
            <div>
              <dt>Tokens used this month</dt>
              <dd>
                {data.tokens_used.toLocaleString()} of {data.monthly_token_budget.toLocaleString()}
                {data.budget_is_default ? " (server default)" : ""}
              </dd>
            </div>
            <div>
              <dt>AI requests this month</dt>
              <dd>
                {data.requests.toLocaleString()} · {data.refused.toLocaleString()} answered from rules instead
              </dd>
            </div>
            <div>
              <dt>Model in use</dt>
              <dd>
                {data.models.length ? data.models.map((item) => item.provider).join(", ") : "None configured"}
                {data.provider_name ? ` · provider: ${data.provider_name}` : ""}
              </dd>
            </div>
          </dl>
        )}
        <div className="ca-action-row">
          <button type="button" className={on ? "ca-danger" : "ac-primary"} disabled={!data} onClick={switchAi}>
            {on ? "Turn AI off" : "Turn AI on"}
          </button>
        </div>
        <form
          className="ca-form"
          onSubmit={(event) => {
            event.preventDefault();
            const value = Number(budget);
            if (!Number.isInteger(value) || value < 0) return onMessage("Enter a whole number of tokens.", "critical");
            ask(
              { monthly_token_budget: value },
              "Change the monthly AI allowance?",
              `${name} may use up to ${value.toLocaleString()} tokens a month; after that its features answer from rules.`,
              "Monthly AI allowance saved.",
            );
          }}
        >
          <div className="ca-form-grid">
            <label className="ca-field">
              Monthly token allowance
              <input
                type="number"
                min={0}
                step={1000}
                inputMode="numeric"
                required
                placeholder={data ? String(data.monthly_token_budget) : ""}
                value={budget}
                onChange={(event) => setBudget(event.target.value)}
              />
            </label>
          </div>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={!data}>
              Save allowance
            </button>
            {data && !data.budget_is_default && (
              <button
                type="button"
                className="ac-secondary"
                onClick={() =>
                  ask(
                    { use_default_budget: true },
                    "Use the standard allowance?",
                    "The tenant goes back to the server's standard monthly allowance.",
                    "Standard allowance restored.",
                  )
                }
              >
                Use standard allowance
              </button>
            )}
          </div>
        </form>
      </Panel>
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          setBudget("");
          onMessage(message);
          settings.reload();
        }}
      />
    </>
  );
}

const legalHoldPath = (tenantId: string) => `/api/v1/platform-admin/tenants/${tenantId}/legal-hold`;

/**
 * The organization's legal hold: while it is set nothing of the organization can be deleted (the server refuses a
 * purge and records the attempt). Setting, updating and releasing it each need a reason and an MFA-verified session.
 */
function LegalHoldPanel({
  tenantId,
  name,
  onMessage,
}: {
  tenantId: string;
  name: string;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const hold = useResource<LegalHold>(legalHoldPath(tenantId));
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const on = !!hold.data?.legal_hold;
  const change = (next: boolean, update = false) =>
    setConfirm({
      title: next
        ? update
          ? `Update the legal hold on ${name}?`
          : `Place ${name} under a legal hold?`
        : `Release the legal hold on ${name}?`,
      body: next
        ? "While the hold is set, none of this organization's data can be deleted, including at the end of its contract. Record who asked for it, their reference and its scope."
        : "Its data can be deleted again under the normal rules. Record who authorized the release.",
      confirmLabel: next ? (update ? "Update hold" : "Place legal hold") : "Release hold",
      danger: !next,
      reason: {
        label: next ? "Who asked, their reference and the scope" : "Who authorized the release, and why",
        min: 10,
      },
      run: async (reason) => {
        try {
          await send(legalHoldPath(tenantId), "PUT", legalHoldRequest(next, reason));
        } catch (error) {
          throw new Error(legalHoldError(error));
        }
      },
      done: next ? `${name} is under a legal hold.` : `The legal hold on ${name} is released.`,
    });
  return (
    <Panel eyebrow="Data retention" title="Legal hold" source={hold}>
      {hold.data && (
        <>
          <dl className="cc-details">
            <div>
              <dt>Status</dt>
              <dd>
                {on ? (
                  <ToneBadge tone="serious" label="On hold: nothing can be deleted" />
                ) : (
                  <ToneBadge tone="neutral" label="No legal hold" />
                )}
              </dd>
            </div>
            {on && (
              <>
                <div>
                  <dt>Reason</dt>
                  <dd>{hold.data.legal_hold_reason || "—"}</dd>
                </div>
                <div>
                  <dt>Set</dt>
                  <dd>{formatDate(hold.data.legal_hold_set_at)}</dd>
                </div>
                <div>
                  <dt>Set by (account)</dt>
                  <dd>
                    <code>{hold.data.legal_hold_set_by || "—"}</code>
                  </dd>
                </div>
              </>
            )}
          </dl>
          <div className="ca-action-row">
            {on ? (
              <>
                <button type="button" className="ac-secondary" onClick={() => change(true, true)}>
                  <Lock size={15} aria-hidden="true" /> Update reason
                </button>
                <button type="button" className="ca-danger" onClick={() => change(false)}>
                  <Unlock size={15} aria-hidden="true" /> Release hold
                </button>
              </>
            ) : (
              <button type="button" className="ac-primary" onClick={() => change(true)}>
                <Lock size={15} aria-hidden="true" /> Place legal hold
              </button>
            )}
          </div>
          <p className="ac-muted">Changing the hold needs a session that passed multi-factor authentication.</p>
        </>
      )}
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          onMessage(message);
          hold.reload();
        }}
      />
    </Panel>
  );
}

/** Export everything the tenant stored (to hand it back), and delete it at the end of a contract or on request. */
function TenantData({
  tenantId,
  tenantKey,
  status,
  suspendedAt,
  name,
  onMessage,
  onChanged,
}: {
  tenantId: string;
  tenantKey: string;
  status: string;
  suspendedAt: string | null;
  name: string;
  onMessage: (text: string, tone?: "good" | "critical") => void;
  onChanged: () => void;
}) {
  const base = `/api/v1/platform-admin/tenants/${tenantId}`;
  const exports = useResource<{ exports: DataExport[] }>(`${base}/exports`);
  const hold = useResource<LegalHold>(legalHoldPath(tenantId));
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [typedKey, setTypedKey] = useState("");
  const [handBack, setHandBack] = useState<HandBack>({ kind: "export" });
  const [outcome, setOutcome] = useState<{ tone: "good" | "warning"; text: string } | null>(null);
  const purgeResult = useRef<PurgeResult | null>(null);
  const rows = exports.data?.exports ?? [];
  const busy = rows.some((row) => row.status === "QUEUED" || row.status === "RUNNING");
  const upper = String(status).toUpperCase();
  const resuming = upper === "PURGING";
  const deletable = ["SUSPENDED", "TERMINATED", "PURGING"].includes(upper);
  const onHold = !!hold.data?.legal_hold;
  const available = exportAfterSuspension(rows, suspendedAt);
  // A purge left PURGING already recorded its hand-back; resuming it asks only for the confirmation.
  const answered = resuming || handBackReady(handBack, available);
  const startPurge = () =>
    setConfirm({
      title: resuming ? `Finish deleting ${name}'s data?` : `Delete all of ${name}'s data?`,
      body: resuming
        ? "The records are already deleted; this retries removing the stored files and any dedicated database."
        : handBack.kind === "export"
          ? `Everything this organization stored is deleted for good and the organization is archived. The export completed ${formatDate(available?.completed_at)} is recorded as the data handed back.`
          : "Everything this organization stored is deleted for good and the organization is archived. No export is handed back; your waiver reason is kept in the deletion record.",
      confirmLabel: resuming ? "Finish deletion" : "Delete all data",
      danger: true,
      reason: { label: "Reason (for example the customer's written request)", min: 10 },
      password: true,
      run: async (reason, password) => {
        purgeResult.current = await send<PurgeResult>(
          `${base}/purge`,
          "POST",
          purgeRequest(reason, password, typedKey, resuming ? null : handBack),
        );
      },
      done: "",
    });
  return (
    <>
      <Panel eyebrow="Data" title="Exports" source={exports}>
        <p className="ac-muted">
          A zip of every record, the audit trail and every stored file (no passwords or secrets), kept for 7 days.
        </p>
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-primary"
            disabled={busy}
            onClick={() =>
              setConfirm({
                title: `Prepare a full export of ${name}?`,
                body: "The export is prepared in the background; refresh this page to download it.",
                confirmLabel: "Prepare export",
                reason: { label: "Reason (kept in the audit trail)", min: 10 },
                run: (reason) => send(`${base}/exports`, "POST", { reason }),
                done: "The export is being prepared.",
              })
            }
          >
            {busy ? "Export in progress…" : "Prepare export"}
          </button>
          <button type="button" className="ac-secondary" onClick={() => exports.reload()}>
            Refresh
          </button>
        </div>
        <Table
          caption="Exports"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "No exports", detail: "Prepare one to hand the data back to the customer." }}
          columns={[
            idColumn("Export ID"),
            { key: "requested", label: "Requested", render: (row) => formatDate(row.created_at) },
            { key: "status", label: "Status", render: (row) => titleCase(row.status) },
            {
              key: "contents",
              label: "Contents",
              render: (row) =>
                row.summary ? `${row.summary.rows.toLocaleString()} records · ${row.summary.files} files` : "—",
            },
            {
              key: "download",
              label: "Download",
              render: (row) =>
                row.status === "READY" ? (
                  <a className="ac-link" href={`${base}/exports/${row.id}/download`} download>
                    Download zip
                  </a>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </Panel>
      <Panel eyebrow="Danger zone" title="Delete all of this organization's data">
        <p>
          Deletes every record, the audit trail and every stored file, pseudonymizes the people and archives the
          organization. Contract history is kept. This cannot be undone.
        </p>
        {outcome && (
          <div className={`ac-message tone-${outcome.tone === "good" ? "good" : "warning"}`} role="status">
            {outcome.text}
          </div>
        )}
        {onHold ? (
          <p className="ca-inline-error" role="note">
            <Lock size={15} aria-hidden="true" /> This organization is under a legal hold: nothing can be deleted until
            the hold is released (Overview).
          </p>
        ) : deletable ? (
          <form
            className="ca-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (typedKey.trim() !== tenantKey) return onMessage("Type the organization key exactly.", "critical");
              if (!answered)
                return onMessage("Choose the export to hand back, or record why there is none.", "critical");
              startPurge();
            }}
          >
            {resuming ? (
              <p className="ac-note">
                A previous deletion did not finish: the records are deleted but stored files (or a dedicated database)
                remain. Finishing it retries their removal; scripts/complete_tenant_purge.py does the same.
              </p>
            ) : (
              <fieldset className="ca-fieldset">
                <legend>Step 1 · The customer's data is handed back first</legend>
                <label className="ca-check">
                  <input
                    type="radio"
                    name="hand-back"
                    checked={handBack.kind === "export"}
                    disabled={!available}
                    onChange={() => setHandBack({ kind: "export" })}
                  />
                  {available
                    ? `Use the export completed ${formatDate(available.completed_at)}${
                        available.summary ? ` (${available.summary.rows.toLocaleString()} records)` : ""
                      }, prepared after the suspension`
                    : "No export completed after the suspension yet: prepare one above, or waive it below"}
                </label>
                <label className="ca-check">
                  <input
                    type="radio"
                    name="hand-back"
                    checked={handBack.kind === "waiver"}
                    onChange={() => setHandBack({ kind: "waiver", reason: "" })}
                  />
                  No export: record why the data is not being returned
                </label>
                {handBack.kind === "waiver" && (
                  <label className="ca-field">
                    Why no export is handed back (for example the customer declined in writing)
                    <textarea
                      rows={2}
                      minLength={WAIVER_MIN}
                      maxLength={1000}
                      value={handBack.reason}
                      onChange={(event) => setHandBack({ kind: "waiver", reason: event.target.value })}
                      placeholder={`At least ${WAIVER_MIN} characters`}
                    />
                  </label>
                )}
                <p className="ac-muted">Free trials are deleted without a hand-back; either choice is accepted.</p>
              </fieldset>
            )}
            <label className="ca-field">
              {resuming ? "" : "Step 2 · "}Type the organization key <strong>{tenantKey}</strong> to confirm
              <input value={typedKey} onChange={(event) => setTypedKey(event.target.value)} autoComplete="off" />
            </label>
            <div className="ca-action-row">
              <button type="submit" className="ca-danger" disabled={busy || typedKey.trim() !== tenantKey || !answered}>
                {resuming ? "Finish deletion" : "Delete all data"}
              </button>
            </div>
          </form>
        ) : (
          <p className="ac-muted">Suspend or terminate the organization first.</p>
        )}
      </Panel>
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          const purged = purgeResult.current;
          purgeResult.current = null;
          setConfirm(null);
          setTypedKey("");
          if (purged) {
            const result = purgeOutcome(name, purged);
            setOutcome(result);
            onMessage(result.text, result.tone === "good" ? "good" : "critical");
          } else onMessage(message);
          exports.reload();
          onChanged();
        }}
      />
    </>
  );
}

const ENVIRONMENT_TYPES = ["PRODUCTION", "SANDBOX", "VALIDATION", "UAT", "DEMO"];

function Environments({
  tenantId,
  rows,
  defaultRegion,
  onChanged,
}: {
  tenantId: string;
  rows: any[];
  defaultRegion: string;
  onChanged: (message: string) => void;
}) {
  const used = new Set(rows.map((row) => String(row.environment_type).toUpperCase()));
  const free = ENVIRONMENT_TYPES.filter((type) => !used.has(type));
  const [adding, setAdding] = useState(false);
  return (
    <Panel
      eyebrow="One of each type per tenant"
      title="Environments"
      action={
        <button
          type="button"
          className="ac-primary"
          onClick={() => setAdding(true)}
          disabled={!free.length}
          title={free.length ? undefined : "Every environment type already exists"}
        >
          <Plus size={16} aria-hidden="true" /> Add environment
        </button>
      }
    >
      <Table
        caption="Environments"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{ title: "No environments", detail: "Add the tenant's first environment." }}
        columns={[
          {
            key: "name",
            label: "Environment",
            render: (row) => (
              <span className="cc-stack">
                <strong>{row.environment_identifier}</strong>
                <small>{titleCase(row.environment_type)}</small>
              </span>
            ),
          },
          { key: "region", label: "Region", render: (row) => row.region ?? "—" },
          { key: "residency", label: "Data residency", render: (row) => row.residency_region ?? "—" },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
      {adding && (
        <AddEnvironment
          tenantId={tenantId}
          types={free}
          defaultRegion={defaultRegion}
          onClose={() => setAdding(false)}
          onAdded={(message) => {
            setAdding(false);
            onChanged(message);
          }}
        />
      )}
    </Panel>
  );
}

function AddEnvironment({
  tenantId,
  types,
  defaultRegion,
  onClose,
  onAdded,
}: {
  tenantId: string;
  types: string[];
  defaultRegion: string;
  onClose: () => void;
  onAdded: (message: string) => void;
}) {
  const [form, setForm] = useState({
    environment_type: types[0] ?? "",
    environment_identifier: "",
    region: defaultRegion,
    residency_region: defaultRegion,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/platform-admin/tenants/${tenantId}/environments`, "POST", {
        ...form,
        environment_identifier: form.environment_identifier.trim(),
      });
      onAdded(`${titleCase(form.environment_type)} environment ${form.environment_identifier.trim()} added (draft).`);
    } catch (reason) {
      setError(errorText(reason, "The environment was not added."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="cc-add-env" onSubmit={submit}>
        <p className="ac-eyebrow">Environments</p>
        <h2 id="cc-add-env">Add environment</h2>
        <label className="ca-field">
          Type
          <select
            value={form.environment_type}
            onChange={(event) => setForm({ ...form, environment_type: event.target.value })}
          >
            {types.map((type) => (
              <option key={type} value={type}>
                {titleCase(type)}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Name
          <input
            required
            pattern="[A-Za-z0-9][A-Za-z0-9_.\-]*"
            title="Letters, numbers, dots, dashes or underscores"
            value={form.environment_identifier}
            onChange={(event) => setForm({ ...form, environment_identifier: event.target.value })}
            placeholder="e.g. acme-uat"
          />
        </label>
        <div className="cc-two-fields">
          <label className="ca-field">
            Region
            <input
              required
              value={form.region}
              onChange={(event) => setForm({ ...form, region: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Data residency
            <input
              required
              value={form.residency_region}
              onChange={(event) => setForm({ ...form, residency_region: event.target.value })}
            />
          </label>
        </div>
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !form.environment_type}>
            {busy ? "Adding…" : "Add environment"}
          </button>
        </div>
      </form>
    </div>
  );
}

// Why a domain check stayed PENDING, in words (codes from POST .../domain-verifications).
const PROOF_ERRORS: Record<string, string> = {
  PROOF_MISMATCH: "the file was found but does not contain this token",
  PROOF_NOT_FOUND: "the file was not found at that address",
  PROOF_UNREACHABLE: "the domain could not be reached over HTTPS",
  PROOF_DESTINATION_BLOCKED: "the domain points to an address MDARIX does not connect to",
  PROOF_REDIRECT_NOT_FOLLOWED: "the address redirects elsewhere; publish the file at the exact address",
  PROOF_TOO_LARGE: "the file is larger than a verification file can be",
  CHALLENGE_EXPIRED: "the token has expired; get a new one",
};

/** The result of a domain check, in one sentence: verified, or still pending and why. */
export function domainCheckMessage(domain: string, result: { status?: string; last_error?: string | null }): string {
  if (String(result.status ?? "").toUpperCase() === "VERIFIED") return `Domain ${domain} is verified.`;
  const code = result.last_error ?? "";
  const why = PROOF_ERRORS[code] ?? (code.startsWith("PROOF_HTTP_") ? `the site answered HTTP ${code.slice(11)}` : "");
  return `Domain ${domain} is not verified yet${why ? `: ${why}` : ""}.`;
}

function DomainIdentity({
  tenantId,
  providers,
  onMessage,
}: {
  tenantId: string;
  providers: any[];
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const [domain, setDomain] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [issued, setIssued] = useState<{
    token: string;
    proofUrl?: string;
    instructions?: string;
    expiresAt?: string;
  } | null>(null);
  const [pending, setPending] = useState<{ text: string; checkedAt?: string } | null>(null);
  const url = `/api/v1/platform-admin/tenants/${tenantId}/domain-verifications`;
  // Step 1: a token is issued once (only its hash is kept); the customer publishes it on their own web site.
  const getToken = async () => {
    if (!domain.trim()) return setError("Enter the domain first.");
    setBusy(true);
    setError("");
    setPending(null);
    try {
      const result = await send<any>(url, "POST", { domain: domain.trim(), verification_method: "FILE" });
      setIssued({
        token: String(result.verification_token ?? ""),
        proofUrl: result.proof_url,
        instructions: result.instructions,
        expiresAt: result.expires_at,
      });
      setToken(String(result.verification_token ?? ""));
    } catch (reason) {
      setError(errorText(reason, "A verification token could not be issued."));
    } finally {
      setBusy(false);
    }
  };
  // Step 2: MDARIX fetches https://<domain>/.well-known/mdarix-verify.txt and compares it with the token.
  const verify = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setPending(null);
    try {
      const result = await send<any>(url, "POST", {
        domain: domain.trim(),
        verification_method: "FILE",
        verification_token: token.trim(),
      });
      const text = domainCheckMessage(domain.trim(), result);
      if (String(result.status ?? "").toUpperCase() === "VERIFIED") {
        onMessage(text);
        setDomain("");
        setToken("");
        setIssued(null);
      } else setPending({ text, checkedAt: result.last_checked_at ?? undefined });
    } catch (reason) {
      setError(errorText(reason, "The domain was not verified."));
    } finally {
      setBusy(false);
    }
  };
  const proofUrl = domain.trim() ? `https://${domain.trim()}/.well-known/mdarix-verify.txt` : "";
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Sign-in" title="Identity providers">
        <Table
          caption="Identity providers"
          rows={providers}
          rowKey={(row) => row.id}
          empty={{ title: "Password sign-in", detail: "No single sign-on provider is configured for this tenant." }}
          columns={[
            { key: "type", label: "Provider", render: (row) => titleCase(row.provider_type) },
            { key: "mode", label: "Sign-in mode", render: (row) => titleCase(row.login_mode) },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ]}
        />
      </Panel>
      <Panel eyebrow="Ownership" title="Verify a domain">
        <form className="cc-form" onSubmit={verify}>
          <label className="ca-field">
            Domain
            <input
              required
              value={domain}
              onChange={(event) => setDomain(event.target.value)}
              placeholder="example.com"
            />
          </label>
          <p className="ac-muted">
            1. Get a token. 2. The customer publishes it, on one line, at{" "}
            <code>{proofUrl || "https://<domain>/.well-known/mdarix-verify.txt"}</code>. 3. Verify.
          </p>
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" disabled={busy || !domain.trim()} onClick={getToken}>
              Get a token
            </button>
          </div>
          {issued && (
            <div className="ac-message tone-good" role="status">
              <span>
                Token (shown once): <code>{issued.token}</code>
                {issued.instructions ? ` ${issued.instructions}` : ""}
                {issued.expiresAt ? ` Valid until ${formatDate(issued.expiresAt)}.` : ""}
              </span>
            </div>
          )}
          <label className="ca-field">
            Verification token
            <input
              required
              minLength={8}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder={`Published at ${proofUrl || "https://<domain>/.well-known/mdarix-verify.txt"}`}
            />
          </label>
          {pending && (
            <p className="ca-inline-error" role="status">
              {pending.text}
              {pending.checkedAt ? ` Checked ${formatDate(pending.checkedAt)}.` : ""}
            </p>
          )}
          {error && (
            <p className="ca-inline-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="ac-primary" disabled={busy}>
            <Globe2 size={16} aria-hidden="true" /> {busy ? "Working…" : "Verify domain"}
          </button>
        </form>
      </Panel>
    </div>
  );
}

function TenantActivity({ tenantId }: { tenantId: string }) {
  const activity = useResource<{ items: any[] }>(`/api/v1/platform-admin/tenants/${tenantId}/tabs/Activity`);
  return (
    <Panel eyebrow="Audit trail" title="Recent activity" source={activity}>
      <Table
        caption="Recent tenant activity"
        rows={activity.data?.items ?? []}
        rowKey={(row) => row.id}
        empty={{ title: "No activity yet", detail: "Changes to this tenant appear here." }}
        columns={[
          { key: "when", label: "When", render: (row) => formatDate(row.created_at) },
          { key: "action", label: "What happened", render: (row) => titleCase(row.action) },
          { key: "reason", label: "Reason", render: (row) => row.details?.reason ?? "—" },
        ]}
      />
    </Panel>
  );
}
