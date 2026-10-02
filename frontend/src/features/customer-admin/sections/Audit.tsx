import { useMemo, useState } from "react";
import { Download, FileArchive } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { SearchBox, Table, formatDate, listOf, matches, useResource } from "../shared";

export function AuditSection() {
  const [entity, setEntity] = useState("");
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(50);
  const users = useResource<any[]>("/api/v1/admin/identity/users");
  const actorName = useMemo(() => {
    const names = new Map(listOf(users.data).map((user) => [String(user.id), user.display_name ?? user.email]));
    return (ref: unknown) => names.get(String(ref)) ?? String(ref ?? "—");
  }, [users.data]);
  const path = `/api/v1/admin/audit-history${entity ? `?entity_type=${encodeURIComponent(entity)}` : ""}`;
  const audit = useResource<any[]>(path);
  const all = useResource<any[]>("/api/v1/admin/audit-history");
  const entityTypes = useMemo(
    () =>
      [
        ...new Set(
          listOf(all.data)
            .map((row) => row.entity_type)
            .filter(Boolean),
        ),
      ].sort(),
    [all.data],
  );
  const rows = useMemo(() => listOf(audit.data).filter((row) => matches(row, query)), [audit.data, query]);
  const scope = entity ? `&entity_type=${encodeURIComponent(entity)}` : "";

  return (
    <Panel
      eyebrow="Audit"
      title="Administrative audit trail"
      state={audit.state}
      error={audit.error}
      action={
        <span className="ca-row-actions">
          <a className="ac-secondary" href={`/api/v1/admin/audit-history/export?output_format=CSV${scope}`} download>
            <Download size={15} /> Export CSV
          </a>
          <a
            className="ac-secondary"
            href={`/api/v1/admin/audit-history/evidence-package${entity ? `?entity_type=${encodeURIComponent(entity)}` : ""}`}
            download
          >
            <FileArchive size={15} /> Evidence package
          </a>
        </span>
      }
    >
      <p className="ac-muted">
        Records are immutable and kept for at least 7 years. Exports contain only your organization's events.
      </p>
      <div className="ca-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search action, actor or reason" />
        <label className="ca-inline-select">
          Object
          <select value={entity} onChange={(event) => setEntity(event.target.value)}>
            <option value="">All objects</option>
            {entityTypes.map((type) => (
              <option key={type} value={type}>
                {titleCase(type)}
              </option>
            ))}
          </select>
        </label>
        <span className="ac-muted">{rows.length} events (latest 200)</span>
      </div>
      <Table
        caption="Audit events"
        rows={rows.slice(0, shown)}
        rowKey={(row) => row.id}
        empty={{ title: "No matching events", detail: "Change the search or object filter." }}
        columns={[
          { key: "when", label: "When", render: (row) => formatDate(row.created_at) },
          { key: "action", label: "Action", render: (row) => <strong>{titleCase(row.action ?? "")}</strong> },
          { key: "object", label: "Object", render: (row) => titleCase(row.entity_type ?? "—") },
          {
            key: "actor",
            label: "Actor",
            // Actions by MDARIX staff come labelled by the server instead of naming the person.
            render: (row) => <span className="ca-mono-sm">{row.actor_label ?? actorName(row.actor_ref)}</span>,
          },
          { key: "reason", label: "Reason", render: (row) => row.reason ?? row.details?.reason ?? "—" },
        ]}
      />
      {rows.length > shown && (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={() => setShown((value) => value + 50)}>
            Show more ({rows.length - shown} remaining)
          </button>
        </div>
      )}
    </Panel>
  );
}
