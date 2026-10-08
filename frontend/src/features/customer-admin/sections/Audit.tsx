import { useMemo, useState } from "react";
import { Download, FileArchive, ShieldCheck } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { Panel } from "../../admin/console/charts";
import { SearchBox, Table, formatDate, listOf, matches, useResource } from "../shared";
import { hideUuid, safeText } from "../../../app/displayId";
import { plural, readable } from "../labels";

export function AuditSection() {
  const [entity, setEntity] = useState("");
  const [query, setQuery] = useState("");
  const users = useResource<any[]>("/api/v1/admin/identity/users");
  const names = useMemo(
    () => new Map<string, string>(listOf(users.data).map((user) => [String(user.id), user.display_name ?? user.email])),
    [users.data],
  );
  // Who acted, as people know them: the server's label (MDARIX staff), the person's name, their User ID, and never
  // the UUID of someone no longer listed.
  const actorName = (row: any) =>
    safeText(row.actor_label) ??
    names.get(String(row.actor_ref)) ??
    safeText(row.actor_business_id) ??
    (row.actor_ref ? hideUuid(row.actor_ref, "Former user") : "System");
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
            <Download size={15} /> Download CSV
          </a>
          <a
            className="ac-secondary"
            href={`/api/v1/admin/audit-history/evidence-package${entity ? `?entity_type=${encodeURIComponent(entity)}` : ""}`}
            download
            title="A zip of these events with proof that they have not been changed, for auditors and inspectors"
          >
            <FileArchive size={15} /> Evidence package
          </a>
        </span>
      }
    >
      <p className="ac-muted">
        Events cannot be changed or deleted and are kept for at least 7 years. Any tampering is detected; use the check
        below to confirm. Downloads contain only your organization&apos;s events.
      </p>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={verify} disabled={integrity.state === "checking"}>
          <ShieldCheck size={15} aria-hidden="true" />{" "}
          {integrity.state === "checking" ? "Checking…" : "Check the audit trail is intact"}
        </button>
        <span role="status" className={integrity.result && !integrity.result.valid ? "ca-inline-error" : "ac-muted"}>
          {integrity.state === "done" && integrity.result
            ? integrity.result.valid
              ? `All ${plural(integrity.result.checked, "event")} checked: nothing has been changed.`
              : `The trail does not verify from event #${integrity.result.first_broken_seq}. Contact MDARIX support.`
            : integrity.state === "error"
              ? integrity.error
              : ""}
        </span>
      </div>
      <div className="ca-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search action, person or reason" />
        <label className="ca-inline-select">
          Record type
          <select value={entity} onChange={(event) => setEntity(event.target.value)}>
            <option value="">All record types</option>
            {entityTypes.map((type) => (
              <option key={type} value={type}>
                {readable(type)}
              </option>
            ))}
          </select>
        </label>
        <span className="ac-muted">{plural(rows.length, "event")} (from the latest 200)</span>
      </div>
      <Table
        caption="Audit events"
        rows={rows}
        rowKey={(row) => row.id}
        pageSize={50}
        pageNoun="event"
        empty={{ title: "No matching events", detail: "Change the search or the record type." }}
        columns={[
          { key: "when", fields: ["created_at"], label: "When", render: (row) => formatDate(row.created_at) },
          { key: "action", label: "Action", render: (row) => <strong>{readable(row.action)}</strong> },
          { key: "object", label: "Record type", render: (row) => readable(row.entity_type) },
          {
            key: "actor",
            label: "Who",
            fields: ["actor_label", "actor_business_id", "actor_ref"],
            sortValue: actorName,
            render: actorName,
          },
          { key: "reason", label: "Reason", render: (row) => row.reason ?? row.details?.reason ?? "—" },
        ]}
      />
    </Panel>
  );
}
