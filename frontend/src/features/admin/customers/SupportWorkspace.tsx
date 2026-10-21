import { useState, type ReactNode } from "react";
import { ArrowLeft, Download, Eye, LockKeyhole } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../console/charts";
import {
  ConfirmDialog,
  Table,
  Tabs,
  formatDate,
  send,
  useResource,
  type Column,
  type Confirmation,
  type Resource,
} from "../../customer-admin/shared";
import { Pager } from "../areas/common";
import { roleLabel } from "../../../app/roles";
import { titleCase } from "./model";

export const workspacePath = (tenantId: string) => `/api/v1/platform-admin/tenants/${tenantId}/support-workspace`;
export const exportsPath = (tenantId: string) => `/api/v1/platform-admin/tenants/${tenantId}/exports`;

type Area = { code: string; label: string };
export type WorkspaceSection = { key: string; title: string; area: string; open: boolean };
export type WorkspaceSummary = {
  tenant: { id: string; name: string; tenant_key: string; business_id?: string | null; is_trial: boolean };
  grant: {
    id: string;
    areas: Area[];
    write: boolean;
    starts_at?: string | null;
    expires_at?: string | null;
    approved_by?: string | null;
    approved_at?: string | null;
    person?: string | null;
  } | null;
  read_only: boolean;
  sections: WorkspaceSection[];
  export: { open: boolean };
  story: Array<{ code: string; title: string; tried: boolean }> | null;
};
type Page<T> = { items: T[]; total?: number; page?: number; pages?: number };
type Row = Record<string, any>;
type TenantExport = {
  id: string;
  business_id?: string | null;
  status: string;
  reason?: string | null;
  size_bytes?: number | null;
  created_at?: string | null;
  completed_at?: string | null;
  expires_at?: string | null;
};

/** The banner every page of the workspace carries: who granted the access, until when, and that it is read-only. */
export function bannerText(summary: Pick<WorkspaceSummary, "grant">): string {
  const grant = summary.grant;
  if (!grant) return "No active support access. Request it from Customers & Tenants › Trials.";
  return `MDARIX support, read-only, access granted by ${grant.approved_by ?? "the customer"} until ${formatDate(grant.expires_at)}.`;
}

/** A record type as words ("SupportAccessGrant" -> "Support access grant"). */
export const recordType = (value: unknown) =>
  String(value ?? "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/^./, (first) => first.toUpperCase());
// Import counts grouped the en-US way ("4,993"), as the import result says them (DEV-025).
const count = (value: unknown) => Number(value).toLocaleString("en-US");
const yesNo = (value: unknown) => (value === true ? "Yes" : value === false ? "No" : "—");
const short = (value: unknown, length = 140) => {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length - 1)}…` : text || "—";
};
const recordCell = (row: Row) => (
  <span className="cc-stack">
    <strong>{row.identifier ?? "—"}</strong>
    {row.business_id && <small>{row.business_id}</small>}
  </span>
);

/** The columns of each page, by its key (backend/app/support_workspace.py answers these fields and no others). */
const COLUMNS: Record<string, Column<Row>[]> = {
  complaints: [
    { key: "complaint", label: "Complaint", render: recordCell },
    { key: "received", label: "Received", render: (row) => formatDate(row.received_at) },
    { key: "product", label: "Product", render: (row) => row.product ?? "—" },
    {
      key: "kind",
      label: "Severity and type",
      render: (row) => (
        <span className="cc-stack">
          <strong>{row.severity ? titleCase(row.severity) : "—"}</strong>
          <small>{row.type ? titleCase(row.type) : ""}</small>
        </span>
      ),
    },
    { key: "status", label: "Status", render: (row) => titleCase(row.status ?? "—") },
    { key: "description", label: "Description", render: (row) => short(row.description) },
  ],
  investigations: [
    { key: "case", label: "Case", render: recordCell },
    { key: "question", label: "Question", render: (row) => short(row.question, 120) },
    { key: "product", label: "Product", render: (row) => row.product ?? "—" },
    { key: "state", label: "State", render: (row) => titleCase(row.state ?? "—") },
    { key: "priority", label: "Priority", render: (row) => titleCase(row.priority ?? "—") },
    { key: "owner", label: "Owner", render: (row) => row.owner ?? "—" },
    { key: "opened", label: "Opened", render: (row) => formatDate(row.opened_at) },
  ],
  decisions: [
    { key: "decision", label: "Decision", render: recordCell },
    { key: "case", label: "Case", render: (row) => row.investigation ?? "—" },
    { key: "outcome", label: "Outcome", render: (row) => titleCase(row.outcome ?? "—") },
    { key: "status", label: "Status", render: (row) => titleCase(row.status ?? "—") },
    { key: "by", label: "Decided by", render: (row) => row.decided_by ?? "—" },
    { key: "at", label: "When", render: (row) => formatDate(row.decided_at) },
  ],
  imports: [
    { key: "at", label: "When", render: (row) => formatDate(row.at) },
    { key: "who", label: "Who", render: (row) => row.who ?? "—" },
    { key: "what", label: "Records", render: (row) => titleCase(row.entity ?? "—") },
    {
      key: "rows",
      label: "Rows",
      numeric: true,
      render: (row) => (
        <span className="cc-stack">
          <strong>{row.rows === undefined || row.rows === null ? "—" : count(row.rows)}</strong>
          <small>
            {count(row.created ?? 0)} added · {count(row.updated ?? 0)} updated
            {row.set_aside ? ` · ${count(row.set_aside)} set aside` : ""}
          </small>
        </span>
      ),
    },
  ],
  team: [
    {
      key: "name",
      label: "Person",
      render: (row) => (
        <span className="cc-stack">
          <strong>{row.name || row.email}</strong>
          <small>{row.email}</small>
        </span>
      ),
    },
    { key: "role", label: "Role", render: (row) => (row.is_owner ? "Trial owner" : roleLabel(row.role)) },
    { key: "status", label: "Status", render: (row) => titleCase(row.status ?? "—") },
    { key: "mfa", label: "Uses an authenticator", render: (row) => yesNo(row.uses_authenticator) },
    { key: "joined", label: "Joined", render: (row) => formatDate(row.joined_at) },
  ],
  audit: [
    { key: "at", label: "When", render: (row) => formatDate(row.at) },
    { key: "who", label: "Who", render: (row) => row.who ?? "System" },
    {
      key: "what",
      label: "What",
      render: (row) => (
        <span className="cc-stack">
          <strong>{titleCase(row.action ?? "")}</strong>
          <small>{row.support ? `Support access: ${row.support_what ?? "used"}` : recordType(row.entity_type)}</small>
        </span>
      ),
    },
    { key: "why", label: "Reason", render: (row) => row.reason ?? "—" },
  ],
};

/**
 * Platform Admin's read-only view of one organization (a free trial, typically) under the support access its owner
 * approved. The server decides everything shown: only the granted areas answer, nothing here can change the
 * organization's data, and every page read is written to its audit trail (backend/app/support_workspace.py).
 */
export function SupportWorkspace({
  tenantId,
  backLabel = "All trials",
  onBack,
  onMessage,
}: {
  tenantId: string;
  backLabel?: string;
  onBack: () => void;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const summary = useResource<WorkspaceSummary>(workspacePath(tenantId));
  const open = (summary.data?.sections ?? []).filter((section) => section.open);
  const [chosen, setChosen] = useState<string | null>(null);
  const active = open.find((section) => section.key === chosen) ?? open[0] ?? null;
  return (
    <SupportWorkspaceView
      summary={summary}
      backLabel={backLabel}
      onBack={onBack}
      active={active?.key ?? null}
      onSection={setChosen}
    >
      {active && <SectionPage key={active.key} tenantId={tenantId} section={active} />}
      {summary.data?.export.open && <ExportPanel tenantId={tenantId} onMessage={onMessage} />}
    </SupportWorkspaceView>
  );
}

/** The workspace for one answer of its summary (separate from the requests, so it renders on its own in tests). */
export function SupportWorkspaceView({
  summary,
  backLabel,
  onBack,
  active,
  onSection,
  children,
}: {
  summary: Resource<WorkspaceSummary>;
  backLabel: string;
  onBack: () => void;
  active: string | null;
  onSection: (key: string) => void;
  children?: ReactNode;
}) {
  const data = summary.data;
  const open = (data?.sections ?? []).filter((section) => section.open);
  const closed = (data?.sections ?? []).filter((section) => !section.open);
  return (
    <div className="cc-page cc-support-workspace">
      <div className="cc-page-head">
        <button type="button" className="ac-link" onClick={onBack}>
          <ArrowLeft size={14} aria-hidden="true" /> {backLabel}
        </button>
      </div>
      <div className="cc-title">
        <div>
          <p className="ac-eyebrow">Read-only workspace</p>
          <h2>{data?.tenant.name ?? "Organization"}</h2>
          {data && <p className="ac-muted">{data.tenant.tenant_key}</p>}
        </div>
      </div>
      {data && (
        <div className={`cc-support-banner${data.grant ? "" : " is-closed"}`} role="status">
          {data.grant ? <Eye size={18} aria-hidden="true" /> : <LockKeyhole size={18} aria-hidden="true" />}
          <div>
            <strong>{bannerText(data)}</strong>
            <small>
              {data.grant
                ? "You can read the areas below and nothing else. Nothing here can be changed. Every page you open is recorded in the organization's audit trail."
                : "The organization's data opens only after its owner approves a request."}
            </small>
          </div>
        </div>
      )}
      {summary.state !== "ready" && !data && (
        <Panel title="Read-only workspace" source={summary}>
          <p className="ac-muted">Loading…</p>
        </Panel>
      )}
      {data && open.length > 0 && (
        <Tabs
          tabs={open.map((section) => section.title)}
          active={open.find((section) => section.key === active)?.title ?? open[0].title}
          onChange={(title) => onSection(open.find((section) => section.title === title)?.key ?? open[0].key)}
          label="Read-only workspace"
        >
          {children}
        </Tabs>
      )}
      {data && open.length === 0 && children}
      {data && closed.length > 0 && data.grant && (
        <p className="ac-note">Not granted, so not shown: {closed.map((section) => section.title).join(", ")}.</p>
      )}
      {data?.story && (
        <Panel eyebrow="The trial's story" title="Chapters tried">
          <ul className="cc-support-story">
            {data.story.map((chapter) => (
              <li key={chapter.code}>
                <ToneBadge tone={chapter.tried ? "good" : "neutral"} label={chapter.tried ? "Tried" : "Not yet"} />
                {chapter.title}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function SectionPage({ tenantId, section }: { tenantId: string; section: WorkspaceSection }) {
  const [pages, setPages] = useState<Record<string, number>>({});
  const page = pages[section.key] ?? 1;
  const paged = section.key !== "team";
  const resource = useResource<Page<Row>>(`${workspacePath(tenantId)}/${section.key}${paged ? `?page=${page}` : ""}`);
  return (
    <SectionView
      section={section}
      resource={resource}
      onPage={(next) => setPages((current) => ({ ...current, [section.key]: next }))}
    />
  );
}

export function SectionView({
  section,
  resource,
  onPage,
}: {
  section: WorkspaceSection;
  resource: Resource<Page<Row>>;
  onPage: (page: number) => void;
}) {
  const data = resource.data;
  return (
    <Panel eyebrow="Read only" title={section.title} source={resource}>
      <Table<Row>
        caption={section.title}
        rows={data?.items ?? []}
        rowKey={(row) => String(row.id)}
        empty={{ title: `No ${section.title.toLowerCase()}`, detail: "Nothing has been recorded here yet." }}
        columns={COLUMNS[section.key] ?? []}
      />
      {data?.pages !== undefined && (
        <Pager
          page={data.page ?? 1}
          pages={data.pages ?? 1}
          total={data.total ?? data.items.length}
          noun="record"
          onPage={onPage}
        />
      )}
    </Panel>
  );
}

const megabytes = (bytes?: number | null) => (bytes ? `${(bytes / 1_048_576).toFixed(1)} MB` : "—");

/** The organization's full export, under a Full export grant: prepared in the background, then downloaded. */
function ExportPanel({
  tenantId,
  onMessage,
}: {
  tenantId: string;
  onMessage: (text: string, tone?: "good" | "critical") => void;
}) {
  const exports = useResource<{ exports: TenantExport[] }>(exportsPath(tenantId));
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  return (
    <ExportView
      exports={exports}
      tenantId={tenantId}
      onExport={() =>
        setConfirm({
          title: "Prepare a full export?",
          body: "A copy of every record of the organization, without passwords, authenticator secrets or other credentials. It is recorded in the organization's audit trail, and can be downloaded for 7 days while the access lasts.",
          confirmLabel: "Prepare export",
          reason: { label: "Reason (kept in the organization's audit trail)", min: 10 },
          mfaCode: true,
          done: "The export is being prepared. It appears below when it is ready.",
          run: async (reason, _password, _acknowledged, mfaCode) => {
            await send(exportsPath(tenantId), "POST", { reason, mfa_code: mfaCode || undefined });
            exports.reload();
          },
        })
      }
    >
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          onMessage(text);
        }}
      />
    </ExportView>
  );
}

export function ExportView({
  exports,
  tenantId,
  onExport,
  children,
}: {
  exports: Resource<{ exports: TenantExport[] }>;
  tenantId: string;
  onExport: () => void;
  children?: ReactNode;
}) {
  const rows = exports.data?.exports ?? [];
  return (
    <Panel
      eyebrow="Full export"
      title="Export the organization's data"
      source={exports}
      action={
        <button type="button" className="ac-primary" onClick={onExport}>
          <Download size={16} aria-hidden="true" /> Export data
        </button>
      }
    >
      <p className="ac-muted">
        The same export the organization's own administrators make: every record, as JSON Lines and readable CSV files,
        with a manifest. Credentials are never included.
      </p>
      {rows.length ? (
        <Table<TenantExport>
          caption="Exports"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "", detail: "" }}
          columns={[
            { key: "when", label: "Asked for", render: (row) => formatDate(row.created_at) },
            { key: "status", label: "Status", render: (row) => titleCase(row.status) },
            { key: "size", label: "Size", numeric: true, render: (row) => megabytes(row.size_bytes) },
            { key: "why", label: "Reason", render: (row) => row.reason ?? "—" },
            {
              key: "download",
              label: "",
              render: (row) =>
                row.status === "READY" ? (
                  <a className="ac-link" href={`${exportsPath(tenantId)}/${row.id}/download`}>
                    Download
                  </a>
                ) : null,
            },
          ]}
        />
      ) : (
        <Empty title="No export yet" detail="Prepare one with Export data." />
      )}
      {children}
    </Panel>
  );
}
