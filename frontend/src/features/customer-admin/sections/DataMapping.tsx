import { useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { useConsole } from "../context";
import { Drawer, SearchBox, Table, Tabs, formatDate, listOf, matches, send, useResource } from "../shared";
import { LifecycleBadge } from "./Access";
import { MappingCheckResult, MappingWizard } from "../../mapping/MappingWizard";
import type { MappingCheck } from "../../mapping/mappingModel";

const TABS = ["Mappings", "Field mappings"] as const;
type Tab = (typeof TABS)[number];

// Release transitions the server allows (see /release-action): only offer the ones valid for the current status.
const RELEASE_ACTIONS = [
  { action: "REQUEST_APPROVAL", label: "Request approval", from: ["DRAFT", "VALIDATION", "READY_FOR_APPROVAL"] },
  // Approval must come from a different administrator than the one who requested it (the server enforces this).
  { action: "APPROVE", label: "Approve", from: ["READY_FOR_APPROVAL"] },
  { action: "PROMOTE", label: "Release", from: ["APPROVED"] },
  { action: "ROLLBACK", label: "Roll back", from: ["RELEASED", "ACTIVE"] },
] as const;

export function DataMappingSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Mappings",
  );
  return (
    <>
      <p className="ca-lede">
        Your mappings translate your systems' fields into MDARIX. They stay separate from the platform's master
        mappings, and every release is approved and audited.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Data mapping sections" />
      {active === "Mappings" ? <Mappings /> : <FieldMappings />}
    </>
  );
}

function Mappings() {
  const { notify } = useConsole();
  const mappings = useResource<any[]>("/api/v1/admin/configuration/mappings");
  const [selected, setSelected] = useState<any | null>(null);
  const [creating, setCreating] = useState(false);
  return (
    <>
      <Panel
        eyebrow="Data mapping"
        title="Mappings"
        state={mappings.state}
        error={mappings.error}
        action={
          <button type="button" className="ac-primary" onClick={() => setCreating(true)}>
            <Plus size={16} aria-hidden="true" /> New mapping
          </button>
        }
      >
        <Table
          caption="Mappings"
          rows={listOf(mappings.data)}
          rowKey={(row) => row.id}
          empty={{ title: "No mappings yet", detail: "Create a mapping for each source object you connect." }}
          columns={[
            { key: "code", label: "Mapping", render: (row) => <strong>{row.code}</strong> },
            {
              key: "flow",
              label: "Source → MDARIX",
              render: (row) => `${row.source_system ?? "—"} → ${row.target_entity ?? "—"}`,
            },
            {
              key: "rules",
              label: "Field rules",
              numeric: true,
              render: (row) => Object.keys(row.mapping_rules ?? {}).filter((key) => key !== "_configuration").length,
            },
            { key: "version", label: "Version", render: (row) => row.version },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
            {
              key: "open",
              label: "",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => setSelected(row)}>
                  Release &amp; history
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {creating && (
        <MappingWizard
          onClose={() => setCreating(false)}
          onSaved={(code) => {
            setCreating(false);
            notify(`Mapping ${code} saved as a draft. Open it to request approval.`);
            mappings.reload();
          }}
        />
      )}
      {selected && (
        <ReleaseDrawer
          mapping={selected}
          onClose={() => setSelected(null)}
          onChanged={() => {
            mappings.reload();
            setSelected(null);
          }}
        />
      )}
    </>
  );
}

function ReleaseDrawer({ mapping, onClose, onChanged }: { mapping: any; onClose: () => void; onChanged: () => void }) {
  const { confirm } = useConsole();
  const release = useResource<any>(`/api/v1/admin/configuration/mappings/${mapping.id}/release`);
  const check = useResource<MappingCheck>(`/api/v1/admin/configuration/mappings/${mapping.id}/check`);
  const status = String(release.data?.status ?? mapping.status ?? "").toUpperCase();
  const available = RELEASE_ACTIONS.filter((option) => (option.from as readonly string[]).includes(status));
  return (
    <Drawer title={`${mapping.code} · ${mapping.version}`} onClose={onClose}>
      {check.data && <MappingCheckResult result={check.data} />}
      <dl className="ca-facts">
        <div>
          <dt>Status</dt>
          <dd>
            <LifecycleBadge status={status} />
          </dd>
        </div>
        <div>
          <dt>Flow</dt>
          <dd>
            {mapping.source_system} → {mapping.target_entity}
          </dd>
        </div>
        <div>
          <dt>Validation</dt>
          <dd>
            {release.data?.validation ? (
              <ToneBadge
                tone={release.data.validation.status === "PASS" ? "good" : "warning"}
                label={`${titleCase(release.data.validation.status)} · ${release.data.validation.rule_count} rules`}
              />
            ) : (
              "—"
            )}
          </dd>
        </div>
      </dl>
      <section className="ca-drawer-section">
        <h3>Release</h3>
        {available.length ? (
          <div className="ca-action-row">
            {available.map((option) => (
              <button
                type="button"
                key={option.action}
                className={option.action === "ROLLBACK" ? "ca-danger-outline" : "ac-secondary"}
                onClick={() =>
                  confirm({
                    title: `${option.label}: ${mapping.code} ${mapping.version}?`,
                    body:
                      option.action === "PROMOTE"
                        ? "This version becomes the one used for your incoming data."
                        : option.action === "ROLLBACK"
                          ? "This version stops being used and is marked superseded."
                          : "An approver reviews this version before it can be released.",
                    confirmLabel: option.label,
                    danger: option.action === "ROLLBACK",
                    reason: { label: "Reason (kept in the audit trail)", min: 10 },
                    done: `${option.label} recorded for ${mapping.code}.`,
                    run: async (reason) => {
                      await send(`/api/v1/admin/configuration/mappings/${mapping.id}/release-action`, "POST", {
                        action: option.action,
                        reason,
                        expected_status: status,
                      });
                      onChanged();
                    },
                  })
                }
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : (
          <p className="ac-muted">No release step is available from the {titleCase(status || "current")} status.</p>
        )}
      </section>
      <section className="ca-drawer-section">
        <h3>History</h3>
        {listOf(release.data?.audit).length ? (
          <ul className="ca-timeline">
            {listOf(release.data?.audit).map((event, index) => (
              <li key={index}>
                <strong>{titleCase(event.action ?? "Event")}</strong>
                <small>
                  {formatDate(event.created_at)}
                  {event.details?.reason ? ` · ${event.details.reason}` : ""}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">{release.state === "loading" ? "Loading…" : "No release history yet."}</p>
        )}
      </section>
    </Drawer>
  );
}

function FieldMappings() {
  const fields = useResource<any[]>("/api/v1/admin/configuration/data-mappings");
  const [query, setQuery] = useState("");
  const rows = useMemo(() => listOf(fields.data).filter((row) => matches(row, query)), [fields.data, query]);
  return (
    <Panel eyebrow="Data mapping" title="Field mappings" state={fields.state} error={fields.error}>
      <div className="ca-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search source or MDARIX field" />
        <span className="ac-muted">{rows.length} fields</span>
      </div>
      <Table
        caption="Field mappings"
        rows={rows.slice(0, 200)}
        rowKey={(row, index) => `${row.mapping_id}-${row.source_field}-${index}`}
        empty={{ title: "No field mappings", detail: "Field rules appear once a mapping has them." }}
        columns={[
          { key: "mapping", label: "Mapping", render: (row) => row.mapping_code },
          {
            key: "source",
            label: "Your field",
            render: (row) => (
              <span className="ca-person">
                <strong>{row.source_field}</strong>
                <small>
                  {row.source_system} · {row.source_table}
                </small>
              </span>
            ),
          },
          {
            key: "target",
            label: "MDARIX field",
            render: (row) => (
              <span className="ca-person">
                <strong>{row.target_field}</strong>
                <small>{row.target_table}</small>
              </span>
            ),
          },
          { key: "transform", label: "Transform", render: (row) => titleCase(row.transform ?? "DIRECT") },
          { key: "required", label: "Required", render: (row) => (row.required ? "Yes" : "No") },
          { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
        ]}
      />
    </Panel>
  );
}
