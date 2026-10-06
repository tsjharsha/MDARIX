import { useMemo, useState } from "react";
import { Download, FileArchive, ShieldCheck } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
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
  const [integrity, setIntegrity] = useState<{
    state: "idle" | "checking" | "done" | "error";
    result?: { valid: boolean; checked: number; first_broken_seq: number | null; last_hash: string | null };
    error?: string;
  }>({ state: "idle" });
  const verify = async () => {
    setIntegrity({ state: "checking" });
    try {
      setIntegrity({ state: "done", result: await requestJson("/api/v1/admin/audit-chain", { timeoutMs: 60000 }) });
    } catch (error) {
      setIntegrity({ state: "error", error: error instanceof Error ? error.message : "The check could not run." });
    }
  };

  return (
    <Panel
      eyebrow="Audit"
      title="Administrative audit trail"
      source={audit}
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
        Records are immutable and kept for at least 7 years. Each event is linked to the one before it by a hash, so any
        change to history is detected. Exports contain only your organization&apos;s events.
      </p>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={verify} disabled={integrity.state === "checking"}>
          <ShieldCheck size={15} aria-hidden="true" />{" "}
          {integrity.state === "checking" ? "Verifying…" : "Verify audit trail integrity"}
        </button>
        <span role="status" className={integrity.result && !integrity.result.valid ? "ca-inline-error" : "ac-muted"}>
          {integrity.state === "done" && integrity.result
            ? integrity.result.valid
              ? `All ${integrity.result.checked.toLocaleString()} events verified: the trail is intact.`
              : `The trail does not verify from event #${integrity.result.first_broken_seq}. Contact MDARIX support.`
            : integrity.state === "error"
              ? integrity.error
              : ""}
        </span>
      </div>
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
