import { useMemo, useState } from "react";
import { ArrowRight, Pencil, Plus } from "lucide-react";
import { Panel, StatTile } from "../console/charts";
import {
  ConfirmDialog,
  Drawer,
  SearchBox,
  Table,
  errorText,
  formatDate,
  listOf,
  matches,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { MappingCheckResult, MappingWizard } from "../../mapping/MappingWizard";
import type { MappingCheck } from "../../mapping/mappingModel";
import { requestJson } from "../../../app/apiClient";
import { Intro, TenantPicker } from "./common";
import { RELEASE_STEPS, changePolicyLabel, mappingRuleCount, nextReleaseAction, releaseStageOf } from "./dataModel";
import { DialogBehaviour } from "../../shared/DialogBehaviour";

type Notify = (text: string, tone?: "good" | "critical") => void;

export function DataConfiguration({ section, onMessage }: { section: string; onMessage: Notify }) {
  if (section === "Mappings") return <Mappings onMessage={onMessage} />;
  if (section === "Releases") return <Releases onMessage={onMessage} />;
  if (section === "Rules & reference data") return <RulesAndReferenceData />;
  if (section === "Customer configuration") return <CustomerConfiguration onMessage={onMessage} />;
  return <DataModel />;
}

type Entity = { entity_id: string; business_id: string; entity_name: string; status?: string };
type CanonicalField = {
  field_name: string;
  field_label?: string;
  data_type: string;
  required: boolean;
  mapping_allowed: boolean;
  system_managed?: boolean;
  override_policy?: string | null;
  reference_entity?: string | null;
  data_classification?: string | null;
};

const useEntities = () => useResource<Entity[]>("/api/v1/admin/mapping/canonical/entities");
const useFields = (entityId: string) =>
  useResource<CanonicalField[]>(
    entityId ? `/api/v1/admin/mapping/canonical/entities/${encodeURIComponent(entityId)}/fields` : null,
  );

/** The MDARIX records customer data is mapped into, their fields, and how they link to each other. */
function DataModel() {
  const entities = useEntities();
  const rows = listOf(entities.data) as Entity[];
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const entityId = selected || rows[0]?.entity_id || "";
  const fields = useFields(entityId);
  const fieldRows = listOf(fields.data) as CanonicalField[];
  const chosen = rows.find((row) => row.entity_id === entityId);
  const links = [...new Set(fieldRows.map((field) => field.reference_entity).filter(Boolean))] as string[];
  const nameOf = (code: string) => rows.find((row) => row.entity_id === code)?.entity_name ?? titleCase(code);
  return (
    <div className="ac-grid two ar-wide-right">
      <Panel eyebrow="MDARIX records" title="Data model" state={entities.state} error={entities.error}>
        <Intro>
          The records every customer&apos;s data is mapped into. Choose one to see its fields and the records it links
          to.
        </Intro>
        <SearchBox value={query} onChange={setQuery} label="Search records" />
        <ul className="ar-pick-list" aria-label="Records">
          {rows
            .filter((row) => matches(row, query))
            .map((row) => (
              <li key={row.entity_id}>
                <button
                  type="button"
                  className={row.entity_id === entityId ? "selected" : ""}
                  aria-current={row.entity_id === entityId ? "true" : undefined}
                  onClick={() => setSelected(row.entity_id)}
                >
                  <strong>{row.entity_name}</strong>
                  <small>{row.business_id}</small>
                </button>
              </li>
            ))}
        </ul>
      </Panel>
      <Panel
        eyebrow={chosen ? `${fieldRows.length} fields` : "Fields"}
        title={chosen?.entity_name ?? "Fields"}
        state={entityId ? fields.state : "ready"}
        error={fields.error}
      >
        {links.length > 0 && (
          <p className="ar-links">
            Links to:{" "}
            {links.map((code) => (
              <button key={code} type="button" className="ac-link" onClick={() => setSelected(code)}>
                {nameOf(code)}
              </button>
            ))}
          </p>
        )}
        <Table
          caption="Fields"
          rows={fieldRows}
          rowKey={(row) => row.field_name}
          empty={{ title: "No fields", detail: "This record has no fields yet." }}
          columns={[
            {
              key: "field",
              label: "Field",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.field_label ?? titleCase(row.field_name)}</strong>
                  <small>{row.field_name}</small>
                </span>
              ),
            },
            {
              key: "type",
              label: "Type",
              render: (row) =>
                row.reference_entity ? `Link to ${nameOf(row.reference_entity)}` : titleCase(row.data_type),
            },
            { key: "required", label: "Required", render: (row) => (row.required ? "Yes" : "No") },
            {
              key: "mapped",
              label: "Filled from customer data",
              render: (row) => (row.mapping_allowed ? "Yes" : row.system_managed ? "No (set by MDARIX)" : "No"),
            },
            { key: "change", label: "Who may change it", render: (row) => changePolicyLabel(row.override_policy) },
            {
              key: "sensitivity",
              label: "Sensitivity",
              render: (row) => titleCase(row.data_classification ?? "—"),
            },
          ]}
        />
      </Panel>
    </div>
  );
}

type Mapping = {
  id: string;
  code: string;
  source_system: string;
  target_entity: string;
  version: string;
  status: string;
  mapping_rules?: unknown;
};

const STATUS_FILTERS = ["", "DRAFT", "READY_FOR_APPROVAL", "APPROVED", "RELEASED", "SUPERSEDED"];

/** Every source-to-MDARIX mapping: open one to see its fields, check it, or start a new one. */
function Mappings({ onMessage }: { onMessage: Notify }) {
  // Whose mappings: the platform's own tenant (""), or a customer tenant the MDARIX team prepares drafts for.
  const [tenantSearch, setTenantSearch] = useState("");
  const [tenant, setTenant] = useState<{ id: string; name: string } | null>(null);
  const tenants = useResource<{ items: any[] }>(
    `/api/v1/platform-admin/tenants?${new URLSearchParams(tenantSearch.trim() ? { q: tenantSearch.trim() } : {})}`,
  );
  const base = tenant ? `/api/v1/platform-admin/tenants/${tenant.id}/mappings` : "/api/v1/admin/configuration/mappings";
  const mappings = useResource<Mapping[]>(base);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<Mapping | null>(null);
  const [creating, setCreating] = useState(false);
  const rows = (listOf(mappings.data) as Mapping[]).filter(
    (row) => matches(row, query) && (!status || String(row.status).toUpperCase() === status),
  );
  return (
    <Panel
      eyebrow="Source system → MDARIX"
      title="Mappings"
      state={mappings.state}
      error={mappings.error}
      action={
        <button type="button" className="ac-primary" onClick={() => setCreating(true)}>
          <Plus size={16} aria-hidden="true" /> New mapping
        </button>
      }
    >
      <Intro>
        A mapping says which field of a customer&apos;s system (for example TrackWise) fills which MDARIX field. New
        mappings start as drafts and go live through Releases.
      </Intro>
      <div className="cc-toolbar">
        <SearchBox value={tenantSearch} onChange={setTenantSearch} label="Find a customer tenant" />
        <select
          aria-label="Whose mappings"
          value={tenant?.id ?? ""}
          onChange={(event) => {
            const row = listOf(tenants.data?.items).find(
              (item) => String(item.id ?? item.tenant_id) === event.target.value,
            );
            setTenant(
              row ? { id: String(row.id ?? row.tenant_id), name: String(row.display_name ?? row.tenant_key) } : null,
            );
          }}
        >
          <option value="">MDARIX platform tenant (yours)</option>
          {listOf(tenants.data?.items).map((row) => (
            <option key={String(row.id ?? row.tenant_id)} value={String(row.id ?? row.tenant_id)}>
              {String(row.display_name ?? row.tenant_key)}
              {row.customer_name ? ` · ${row.customer_name}` : ""}
            </option>
          ))}
        </select>
      </div>
      {tenant && (
        <p className="ac-note">
          Preparing drafts for {tenant.name}. Their own Customer Administrators request approval, approve (a second
          administrator) and release them, so the customer decides what imports into their data.
        </p>
      )}
      <div className="cc-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search mapping, system or record" />
        <select aria-label="Status" value={status} onChange={(event) => setStatus(event.target.value)}>
          {STATUS_FILTERS.map((value) => (
            <option key={value} value={value}>
              {value ? titleCase(value) : "All statuses"}
            </option>
          ))}
        </select>
      </div>
      <Table
        caption="Mappings"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{ title: "No mappings", detail: "Start one with New mapping." }}
        columns={[
          {
            key: "mapping",
            fields: ["code", "version"],
            label: "Mapping",
            render: (row) =>
              tenant ? (
                <span className="cc-stack">
                  <strong>{row.code}</strong>
                  <small>Version {row.version}</small>
                </span>
              ) : (
                <button type="button" className="ac-link cc-stack" onClick={() => setOpen(row)}>
                  <strong>{row.code}</strong>
                  <small>Version {row.version}</small>
                </button>
              ),
          },
          {
            key: "route",
            fields: ["source_system", "target_entity"],
            label: "From → to",
            render: (row) => (
              <span className="ar-route">
                {titleCase(row.source_system)} <ArrowRight size={14} aria-hidden="true" />{" "}
                {titleCase(row.target_entity)}
              </span>
            ),
          },
          {
            key: "fields",
            fields: ["mapping_rules"],
            label: "Fields",
            numeric: true,
            render: (row) => mappingRuleCount(row.mapping_rules),
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
        ]}
      />
      {open && <MappingDetail mapping={open} onClose={() => setOpen(null)} />}
      {creating && (
        <MappingWizard
          savePath={base}
          onClose={() => setCreating(false)}
          onSaved={(code) => {
            setCreating(false);
            onMessage(
              tenant
                ? `Mapping ${code} saved as a draft for ${tenant.name}. Their administrators release it.`
                : `Mapping ${code} saved as a draft. Request approval for it under Releases.`,
            );
            mappings.reload();
          }}
        />
      )}
    </Panel>
  );
}

type FieldRow = {
  mapping_id: string;
  source_table?: string;
  source_field: string;
  target_table?: string;
  target_field: string;
  transform?: string;
  required?: boolean;
};

/** One mapping: its fields, a check against the MDARIX data model, and its version history. */
function MappingDetail({ mapping, onClose }: { mapping: Mapping; onClose: () => void }) {
  const fields = useResource<FieldRow[]>("/api/v1/admin/configuration/data-mappings");
  const versions = useResource<any[]>(
    `/api/v1/admin/configuration/mappings/${encodeURIComponent(mapping.code)}/versions`,
  );
  const [check, setCheck] = useState<MappingCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const rows = (listOf(fields.data) as FieldRow[]).filter(
    (row) => row.mapping_id === mapping.id && row.target_field !== "Not configured",
  );
  const runCheck = async () => {
    setChecking(true);
    setCheckError("");
    try {
      setCheck(await requestJson<MappingCheck>(`/api/v1/admin/configuration/mappings/${mapping.id}/check`));
    } catch (reason) {
      setCheckError(errorText(reason, "The mapping could not be checked."));
    } finally {
      setChecking(false);
    }
  };
  return (
    <Drawer title={mapping.code} onClose={onClose}>
      <div className="ar-drawer-body">
        <p className="ar-route">
          {titleCase(mapping.source_system)} <ArrowRight size={14} aria-hidden="true" />{" "}
          {titleCase(mapping.target_entity)}
          <span>
            · Version {mapping.version} · <StatusBadge status={mapping.status} />
          </span>
        </p>
        <h3 className="ar-subhead">Fields</h3>
        <Table
          caption="Mapped fields"
          rows={rows}
          rowKey={(row, index) => `${row.source_field}-${row.target_field}-${index}`}
          empty={{ title: "No fields mapped", detail: "This mapping has no field rules yet." }}
          columns={[
            {
              key: "from",
              label: "Customer field",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.source_field}</strong>
                  {row.source_table && row.source_table !== "Not configured" && <small>{row.source_table}</small>}
                </span>
              ),
            },
            {
              key: "to",
              label: "MDARIX field",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.target_field}</strong>
                  {row.target_table && <small>{row.target_table}</small>}
                </span>
              ),
            },
            { key: "how", label: "How", render: (row) => titleCase(row.transform ?? "Direct copy") },
          ]}
        />
        <div className="ar-check">
          <button type="button" className="ac-secondary" onClick={runCheck} disabled={checking}>
            {checking ? "Checking…" : "Check mapping"}
          </button>
        </div>
        {checkError && (
          <p className="ca-inline-error" role="alert">
            {checkError}
          </p>
        )}
        {check && <MappingCheckResult result={check} />}
        <h3 className="ar-subhead">Versions</h3>
        <Table
          caption="Versions"
          rows={listOf(versions.data)}
          rowKey={(row, index) => String(row.id ?? index)}
          empty={{ title: "One version", detail: "No other version of this mapping exists." }}
          columns={[
            { key: "version", label: "Version", render: (row) => row.version },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
            { key: "updated", label: "Changed", render: (row) => formatDate(row.updated_at ?? row.created_at) },
          ]}
        />
      </div>
    </Drawer>
  );
}

/** Mappings move draft → approval → approved → released; each step is one button, with a reason for the record. */
function Releases({ onMessage }: { onMessage: Notify }) {
  const mappings = useResource<Mapping[]>("/api/v1/admin/configuration/mappings");
  const users = useResource<any[]>("/api/v1/admin/identity/users");
  const [stage, setStage] = useState("");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [open, setOpen] = useState<Mapping | null>(null);
  const all = listOf(mappings.data) as Mapping[];
  const counts = useMemo(() => {
    const found: Record<string, number> = {};
    all.forEach((row) => {
      const key = releaseStageOf(row.status);
      if (key) found[key] = (found[key] ?? 0) + 1;
    });
    return found;
  }, [all]);
  const rows = stage ? all.filter((row) => releaseStageOf(row.status) === stage) : all;
  const names = useMemo(
    () => new Map(listOf(users.data).map((user) => [String(user.id), user.display_name || user.email])),
    [users.data],
  );
  const act = (row: Mapping) => {
    const next = nextReleaseAction(row.status);
    if (!next) return;
    setConfirm({
      title: `${next.label}: ${row.code}?`,
      body: next.explain,
      confirmLabel: next.label,
      danger: next.action === "ROLLBACK",
      reason: { label: "Reason (kept in the audit trail)", min: 10 },
      run: (reason) =>
        send(`/api/v1/admin/configuration/mappings/${row.id}/release-action`, "POST", {
          action: next.action,
          reason,
          expected_status: String(row.status).toUpperCase(),
        }),
      done: `${row.code}: ${next.done}`,
    });
  };
  return (
    <div className="ac-grid">
      <section className="ar-pipeline" aria-label="Release stages">
        {RELEASE_STEPS.map((step, index) => (
          <button
            key={step.key}
            type="button"
            className={stage === step.key ? "selected" : ""}
            onClick={() => setStage(stage === step.key ? "" : step.key)}
            aria-pressed={stage === step.key}
          >
            <small>{index + 1}</small>
            <strong>{counts[step.key] ?? 0}</strong>
            <span>{step.label}</span>
          </button>
        ))}
      </section>
      <Panel eyebrow="Configuration releases" title="Releases" state={mappings.state} error={mappings.error}>
        <Intro>
          A mapping goes live only after someone requests approval and a different administrator approves it. Releasing
          replaces nothing silently: a released version can be rolled back.
        </Intro>
        <Table
          caption="Releases"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "Nothing here", detail: stage ? "Choose another stage." : "No mapping yet." }}
          columns={[
            {
              key: "mapping",
              label: "Mapping",
              render: (row) => (
                <button type="button" className="ac-link cc-stack" onClick={() => setOpen(row)}>
                  <strong>{row.code}</strong>
                  <small>
                    {titleCase(row.source_system)} → {titleCase(row.target_entity)} · {row.version}
                  </small>
                </button>
              ),
            },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
            {
              key: "next",
              label: "Next step",
              render: (row) => {
                const next = nextReleaseAction(row.status);
                return next ? (
                  <button
                    type="button"
                    className={next.action === "ROLLBACK" ? "ac-link cc-danger-link" : "ac-link"}
                    onClick={() => act(row)}
                  >
                    {next.label}
                  </button>
                ) : (
                  <span className="ac-muted">None</span>
                );
              },
            },
          ]}
        />
      </Panel>
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          onMessage(message);
          mappings.reload();
        }}
      />
      {open && <ReleaseHistory mapping={open} names={names} onClose={() => setOpen(null)} />}
    </div>
  );
}

function ReleaseHistory({
  mapping,
  names,
  onClose,
}: {
  mapping: Mapping;
  names: Map<string, string>;
  onClose: () => void;
}) {
  const detail = useResource<any>(`/api/v1/admin/configuration/mappings/${mapping.id}/release`);
  const data = detail.data;
  return (
    <Drawer title={`${mapping.code} · release`} onClose={onClose}>
      <div className="ar-drawer-body">
        {detail.state === "error" && (
          <p className="ca-inline-error" role="alert">
            {detail.error}
          </p>
        )}
        {data && (
          <>
            <dl className="cc-details">
              <div>
                <dt>Status</dt>
                <dd>
                  <StatusBadge status={data.status} />
                </dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{data.version}</dd>
              </div>
              <div>
                <dt>Field rules</dt>
                <dd>{data.validation?.rule_count ?? 0}</dd>
              </div>
              <div>
                <dt>Affects</dt>
                <dd>
                  {listOf(data.dependencies)
                    .map((item: string) => titleCase(item))
                    .join(" and ") || "—"}
                </dd>
              </div>
            </dl>
            <h3 className="ar-subhead">History</h3>
            <Table
              caption="Release history"
              rows={listOf(data.audit)}
              rowKey={(row, index) => `${row.action}-${index}`}
              empty={{ title: "No history yet", detail: "Steps appear here as they happen." }}
              columns={[
                { key: "when", label: "When", render: (row) => formatDate(row.created_at) },
                { key: "who", label: "Who", render: (row) => names.get(String(row.actor)) ?? "Administrator" },
                {
                  key: "what",
                  label: "What",
                  render: (row) => titleCase(String(row.action).replace(/^MAPPING_(RELEASE_)?/, "")),
                },
                { key: "why", label: "Reason", render: (row) => row.details?.reason ?? "—" },
              ]}
            />
          </>
        )}
      </div>
    </Drawer>
  );
}

const REFERENCE_VIEWS = [
  "Transformations",
  "Validation rules",
  "Data-quality rules",
  "Lookup rules",
  "Value sets",
  "Countries",
  "Units",
  "Time zones",
  "Jurisdictions",
  "Customer change policies",
] as const;
type ReferenceView = (typeof REFERENCE_VIEWS)[number];

/** The rules and controlled values mappings and checks rely on. Read-only: master data changes go through a release. */
function RulesAndReferenceData() {
  const [view, setView] = useState<ReferenceView>("Transformations");
  const reference = useResource<any>("/api/v1/platform-admin/reference-data");
  const transforms = useResource<any[]>("/api/v1/admin/mapping/transforms");
  const rules = useResource<any[]>("/api/v1/admin/mapping/validation-rules");
  const policies = useResource<any[]>("/api/v1/admin/mapping/override-policies");
  const [valueSet, setValueSet] = useState("");
  const values = useResource<any>(
    valueSet ? `/api/v1/platform-admin/reference-data/value-sets/${encodeURIComponent(valueSet)}` : null,
  );
  const ref = reference.data ?? {};
  const yes = (value: unknown) => (value ? "Yes" : "No");
  const body = (() => {
    switch (view) {
      case "Transformations":
        return (
          <Table
            caption="Transformations"
            rows={listOf(transforms.data)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No transformation is defined." }}
            columns={[
              { key: "name", label: "Transformation", render: (row) => <strong>{row.label}</strong> },
              { key: "category", label: "Kind", render: (row) => titleCase(row.category ?? "—") },
              { key: "override", label: "Customer may adjust", render: (row) => yes(row.customer_override_allowed) },
              { key: "version", label: "Version", render: (row) => row.version },
            ]}
          />
        );
      case "Validation rules":
        return (
          <Table
            caption="Validation rules"
            rows={listOf(rules.data)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No validation rule is defined." }}
            columns={[
              { key: "name", label: "Rule", render: (row) => <strong>{row.label}</strong> },
              { key: "type", label: "Checks", render: (row) => titleCase(row.rule_type) },
              { key: "severity", label: "Severity", render: (row) => titleCase(row.severity) },
              { key: "blocking", label: "Stops a release", render: (row) => yes(row.blocking) },
            ]}
          />
        );
      case "Data-quality rules":
        return (
          <Table
            caption="Data-quality rules"
            rows={listOf(ref.data_quality_rules)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No data-quality rule is defined." }}
            columns={[
              {
                key: "rule",
                label: "Rule",
                render: (row) => (
                  <span className="cc-stack">
                    <strong>{row.description}</strong>
                    <small>{row.code}</small>
                  </span>
                ),
              },
              { key: "record", label: "Record", render: (row) => row.entity ?? "—" },
              { key: "type", label: "Kind", render: (row) => titleCase(row.type) },
              { key: "severity", label: "Severity", render: (row) => titleCase(row.severity) },
              { key: "blocking", label: "Blocks", render: (row) => yes(row.blocking) },
            ]}
          />
        );
      case "Lookup rules":
        return (
          <Table
            caption="Lookup rules"
            rows={listOf(ref.reference_resolution_rules)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No lookup rule is defined." }}
            columns={[
              { key: "record", label: "Finds a", render: (row) => <strong>{row.entity ?? row.code}</strong> },
              { key: "by", label: "By", render: (row) => listOf(row.lookup_fields).map(titleCase).join(", ") },
              { key: "match", label: "Match", render: (row) => titleCase(row.match) },
              { key: "ambiguous", label: "If several match", render: (row) => titleCase(row.if_ambiguous) },
              { key: "missing", label: "If none matches", render: (row) => titleCase(row.if_not_found) },
            ]}
          />
        );
      case "Value sets":
        return (
          <div className="ac-grid two">
            <Table
              caption="Value sets"
              rows={listOf(ref.value_sets)}
              rowKey={(row) => row.code}
              empty={{ title: "None", detail: "No value set is defined." }}
              columns={[
                {
                  key: "name",
                  label: "Value set",
                  render: (row) => (
                    <button
                      type="button"
                      className={`ac-link cc-stack${row.code === valueSet ? " ar-selected" : ""}`}
                      onClick={() => setValueSet(row.code)}
                    >
                      <strong>{row.name}</strong>
                      <small>{row.domain}</small>
                    </button>
                  ),
                },
                { key: "values", label: "Values", numeric: true, render: (row) => row.values },
              ]}
            />
            {valueSet ? (
              <Table
                caption="Values"
                rows={listOf(values.data?.items)}
                rowKey={(row) => row.code}
                empty={{ title: "No values", detail: "This set is empty." }}
                columns={[
                  { key: "label", label: "Value", render: (row) => <strong>{row.label}</strong> },
                  { key: "code", label: "Code", render: (row) => <code>{row.code}</code> },
                ]}
              />
            ) : (
              <p className="ac-muted">Choose a value set to see its values.</p>
            )}
          </div>
        );
      case "Countries":
        return (
          <Table
            caption="Countries"
            rows={listOf(ref.countries)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No country is defined." }}
            columns={[
              { key: "name", label: "Country", render: (row) => <strong>{row.name}</strong> },
              { key: "code", label: "Codes", render: (row) => `${row.code} · ${row.code3}` },
              { key: "group", label: "Region", render: (row) => row.region_group ?? "—" },
              { key: "regions", label: "States / regions", numeric: true, render: (row) => row.regions },
            ]}
          />
        );
      case "Units":
        return (
          <Table
            caption="Units"
            rows={listOf(ref.units)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No unit is defined." }}
            columns={[
              { key: "name", label: "Unit", render: (row) => <strong>{row.name}</strong> },
              { key: "code", label: "Symbol", render: (row) => <code>{row.code}</code> },
              { key: "dimension", label: "Measures", render: (row) => row.dimension ?? "—" },
            ]}
          />
        );
      case "Time zones":
        return (
          <Table
            caption="Time zones"
            rows={listOf(ref.timezones)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No time zone is defined." }}
            columns={[
              { key: "name", label: "Time zone", render: (row) => <strong>{row.name}</strong> },
              { key: "code", label: "Identifier", render: (row) => <code>{row.code}</code> },
            ]}
          />
        );
      case "Jurisdictions":
        return (
          <Table
            caption="Jurisdictions"
            rows={listOf(ref.jurisdictions)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No jurisdiction is defined." }}
            columns={[
              { key: "name", label: "Jurisdiction", render: (row) => <strong>{row.name}</strong> },
              { key: "type", label: "Level", render: (row) => titleCase(row.type) },
            ]}
          />
        );
      default:
        return (
          <Table
            caption="Customer change policies"
            rows={listOf(policies.data)}
            rowKey={(row) => row.code}
            empty={{ title: "None", detail: "No policy is defined." }}
            columns={[
              { key: "name", label: "Policy", render: (row) => <strong>{row.label}</strong> },
              {
                key: "may",
                label: "Customer may change",
                render: (row) =>
                  [
                    row.can_edit_source && "source field",
                    row.can_edit_target && "MDARIX field",
                    row.can_edit_transform && "transformation",
                    row.can_edit_validation && "validation",
                    row.can_edit_enum_mapping && "value mapping",
                  ]
                    .filter(Boolean)
                    .join(", ") || "Nothing",
              },
              { key: "approval", label: "Needs approval", render: (row) => yes(row.requires_approval) },
            ]}
          />
        );
    }
  })();
  return (
    <Panel
      eyebrow="Master data · read-only"
      title="Rules & reference data"
      state={reference.state}
      error={reference.error}
    >
      <Intro>
        The rules and controlled values that mappings and data checks use. They change only through a controlled
        release, so they are shown here without edit buttons.
      </Intro>
      <div className="ca-chips" role="group" aria-label="Show">
        {REFERENCE_VIEWS.map((item) => (
          <button key={item} type="button" className={view === item ? "selected" : ""} onClick={() => setView(item)}>
            {item}
          </button>
        ))}
      </div>
      {body}
    </Panel>
  );
}

type ProductConfiguration = {
  tenant: { id: string; tenant_key: string; name: string; status: string };
  products: Array<{
    id: string;
    identifier: string;
    name: string;
    status: string;
    family?: string | null;
    description?: string | null;
    manufacturer?: string | null;
  }>;
  versions: Array<{ id: string; product_id: string; identifier: string; status: string; release_timestamp?: string }>;
  connectors: Array<{ id: string; code: string; connector_type: string; version: string; status: string }>;
  mapping_versions: Array<{ id: string; master_mapping_id: string; version: string; status: string }>;
};

type ProductDialog =
  | { kind: "product" }
  | { kind: "edit"; product: ProductConfiguration["products"][number] }
  | { kind: "version"; product: ProductConfiguration["products"][number] };

/** One tenant's products and versions, connections and mapping versions, chosen by name. */
function CustomerConfiguration({ onMessage }: { onMessage: Notify }) {
  const [tenantId, setTenantId] = useState("");
  const config = useResource<ProductConfiguration>(
    tenantId ? `/api/v1/platform/product-configuration/${tenantId}` : null,
  );
  const [dialog, setDialog] = useState<ProductDialog | null>(null);
  const data = config.data;
  const versionsOf = (productId: string) => (data?.versions ?? []).filter((item) => item.product_id === productId);
  return (
    <div className="ac-grid">
      <Panel eyebrow="One tenant" title="Customer configuration">
        <Intro>Choose a tenant to see and maintain its products and versions, connections and mapping versions.</Intro>
        <TenantPicker value={tenantId} onChange={setTenantId} />
      </Panel>
      {tenantId && (
        <>
          <section className="ac-stats ar-stats-4" aria-label="Configuration at a glance">
            <StatTile
              label="Products"
              value={data ? data.products.length : null}
              detail="In this tenant"
              icon={<Plus size={18} />}
            />
            <StatTile
              label="Product versions"
              value={data ? data.versions.length : null}
              detail="All products"
              icon={<Plus size={18} />}
            />
            <StatTile
              label="Connections"
              value={data ? data.connectors.length : null}
              detail="Source systems"
              icon={<ArrowRight size={18} />}
            />
            <StatTile
              label="Mapping versions"
              value={data ? data.mapping_versions.length : null}
              detail="Tenant-specific mappings"
              icon={<ArrowRight size={18} />}
            />
          </section>
          <Panel
            eyebrow={data?.tenant.name ?? "Tenant"}
            title="Products"
            state={config.state}
            error={config.error}
            action={
              <button type="button" className="ac-primary" onClick={() => setDialog({ kind: "product" })}>
                <Plus size={16} aria-hidden="true" /> Add product
              </button>
            }
          >
            <Table
              caption="Products"
              rows={data?.products ?? []}
              rowKey={(row) => row.id}
              empty={{ title: "No products", detail: "Add the tenant's first product." }}
              columns={[
                {
                  key: "product",
                  label: "Product",
                  render: (row) => (
                    <span className="cc-stack">
                      <strong>{row.name}</strong>
                      <small>
                        {row.identifier}
                        {row.family ? ` · ${row.family}` : ""}
                      </small>
                    </span>
                  ),
                },
                {
                  key: "versions",
                  label: "Versions",
                  render: (row) =>
                    versionsOf(row.id)
                      .map((item) => item.identifier)
                      .join(", ") || "—",
                },
                { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
                {
                  key: "actions",
                  label: "",
                  render: (row) => (
                    <span className="cc-actions">
                      <button
                        type="button"
                        className="ac-link"
                        onClick={() => setDialog({ kind: "edit", product: row })}
                      >
                        <Pencil size={14} aria-hidden="true" /> Edit
                      </button>
                      <button
                        type="button"
                        className="ac-link"
                        onClick={() => setDialog({ kind: "version", product: row })}
                      >
                        <Plus size={14} aria-hidden="true" /> Add version
                      </button>
                    </span>
                  ),
                },
              ]}
            />
          </Panel>
          <div className="ac-grid two">
            <Panel eyebrow="Source systems" title="Connections" state={config.state} error={config.error}>
              <Table
                caption="Connections"
                rows={data?.connectors ?? []}
                rowKey={(row) => row.id}
                empty={{ title: "No connections", detail: "This tenant has no source system connected." }}
                columns={[
                  {
                    key: "connection",
                    label: "Connection",
                    render: (row) => (
                      <span className="cc-stack">
                        <strong>{row.code}</strong>
                        <small>
                          {row.connector_type} · {row.version}
                        </small>
                      </span>
                    ),
                  },
                  { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
                ]}
              />
            </Panel>
            <Panel eyebrow="Tenant-specific" title="Mapping versions" state={config.state} error={config.error}>
              <Table
                caption="Mapping versions"
                rows={data?.mapping_versions ?? []}
                rowKey={(row) => row.id}
                empty={{ title: "None", detail: "This tenant uses the standard mappings." }}
                columns={[
                  { key: "version", label: "Version", render: (row) => <strong>{row.version}</strong> },
                  { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
                ]}
              />
            </Panel>
          </div>
        </>
      )}
      {dialog && data && (
        <ProductForm
          tenantId={tenantId}
          dialog={dialog}
          onClose={() => setDialog(null)}
          onSaved={(message) => {
            setDialog(null);
            onMessage(message);
            config.reload();
          }}
        />
      )}
    </div>
  );
}

function ProductForm({
  tenantId,
  dialog,
  onClose,
  onSaved,
}: {
  tenantId: string;
  dialog: ProductDialog;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const product = dialog.kind === "product" ? null : dialog.product;
  const [form, setForm] = useState({
    identifier: "",
    name: product?.name ?? "",
    family: product?.family ?? "",
    manufacturer: product?.manufacturer ?? "",
    description: product?.description ?? "",
    status: product?.status ?? "active",
    version: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: event.target.value });
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (dialog.kind === "product") {
        await send("/api/v1/platform/product-configuration/products", "POST", {
          tenant_id: tenantId,
          product_identifier: form.identifier.trim(),
          name: form.name.trim(),
          product_family: form.family.trim() || null,
          manufacturer_context: form.manufacturer.trim() || null,
          description: form.description.trim() || null,
        });
        onSaved(`Product ${form.name.trim()} added.`);
      } else if (dialog.kind === "edit") {
        await send(`/api/v1/platform/product-configuration/${tenantId}/products/${dialog.product.id}`, "PATCH", {
          name: form.name.trim(),
          product_family: form.family.trim() || null,
          manufacturer_context: form.manufacturer.trim() || null,
          description: form.description.trim() || null,
          lifecycle_status: form.status,
        });
        onSaved(`Product ${form.name.trim()} updated.`);
      } else {
        await send("/api/v1/platform/product-configuration/product-versions", "POST", {
          tenant_id: tenantId,
          product_id: dialog.product.id,
          version_identifier: form.version.trim(),
          description: form.description.trim() || null,
        });
        onSaved(`Version ${form.version.trim()} added to ${dialog.product.name}.`);
      }
    } catch (reason) {
      setError(errorText(reason, "The change was not saved."));
      setBusy(false);
    }
  };
  const title =
    dialog.kind === "product" ? "Add product" : dialog.kind === "edit" ? `Edit ${dialog.product.name}` : "Add version";
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="ar-product-form" onSubmit={submit}>
        <p className="ac-eyebrow">Customer configuration</p>
        <h2 id="ar-product-form">{title}</h2>
        {dialog.kind === "version" ? (
          <>
            <p>A new version of {dialog.product.name}.</p>
            <label className="ca-field">
              Version
              <input required value={form.version} onChange={set("version")} placeholder="e.g. 2.1" />
            </label>
          </>
        ) : (
          <>
            {dialog.kind === "product" ? (
              <label className="ca-field">
                Product identifier
                <input required value={form.identifier} onChange={set("identifier")} placeholder="e.g. PUMP-200" />
              </label>
            ) : (
              <p className="ac-muted">Identifier {dialog.product.identifier} (cannot change)</p>
            )}
            <label className="ca-field">
              Name
              <input required value={form.name} onChange={set("name")} />
            </label>
            <div className="cc-two-fields">
              <label className="ca-field">
                Product family
                <input value={form.family} onChange={set("family")} />
              </label>
              <label className="ca-field">
                Manufacturer
                <input value={form.manufacturer} onChange={set("manufacturer")} />
              </label>
            </div>
            {dialog.kind === "edit" && (
              <label className="ca-field">
                Status
                <select value={form.status} onChange={set("status")}>
                  <option value="active">Active</option>
                  <option value="retired">Retired</option>
                  <option value="archived">Archived</option>
                </select>
              </label>
            )}
          </>
        )}
        <label className="ca-field">
          Description
          <input value={form.description} onChange={set("description")} />
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
            {busy ? "Saving…" : dialog.kind === "edit" ? "Save changes" : title}
          </button>
        </div>
      </form>
    </div>
  );
}
