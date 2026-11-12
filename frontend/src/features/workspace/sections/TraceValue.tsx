import { useState } from "react";
import "./decide.css";
import { Panel } from "../../admin/console/charts";
import { Drawer, formatDate, useResource } from "../../customer-admin/shared";
import { REPORTS } from "../authorityReports";
import { useTrace } from "../workspaceContext";

type TraceEvent = {
  action: string;
  by: string;
  at: string;
  reason: string | null;
  values: { before: Record<string, unknown>; after: Record<string, unknown> } | null;
};

export type ValueTrace = {
  field: { id: string; number: string; label: string; value: string | null; status_label: string };
  origin: { type: string; ref: string | null; label: string; id: string | null } | null;
  imports: {
    import_ref: string;
    line: number;
    mapping_version: string;
    file_name: string | null;
    imported_by: string | null;
    imported_at: string;
  }[];
  field_changes: { field: string; before: string | null; after: string | null; source: string; at: string }[];
  record_events: TraceEvent[];
  entered_on_report: TraceEvent[];
  snapshot: {
    version: number;
    state: string;
    requested_by: string;
    requested_at: string;
    approved_by: string | null;
    approved_at: string | null;
    sha256: string;
    frozen_value: string | null;
  } | null;
};

const words = (action: string) => action.toLowerCase().replace(/_/g, " ");
const shown = (values: Record<string, unknown>) =>
  Object.entries(values)
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${value ?? "—"}`)
    .join("; ");

function Events({ items, empty }: { items: TraceEvent[]; empty: string }) {
  if (!items.length) return <p className="ac-muted">{empty}</p>;
  return (
    <ul className="tr-list">
      {items.map((item, index) => (
        <li key={`${item.at}-${index}`}>
          <strong>{words(item.action)}</strong> · {item.by} · {formatDate(item.at)}
          {item.values && (
            <span className="tr-values">
              {shown(item.values.before) || "—"} → {shown(item.values.after) || "—"}
            </span>
          )}
          {item.reason && <span className="tr-values">Why: {item.reason}</span>}
        </li>
      ))}
    </ul>
  );
}

/** B6a G20: what the Trace link shows, in order: the record the value comes from and the import row that brought it,
 * who entered or changed it and when, and the snapshot it is frozen in. Read only. */
export function TraceBody({ data }: { data: ValueTrace }) {
  const { origin, snapshot } = data;
  return (
    <div className="tr-body">
      <section>
        <h3>1. Where it comes from</h3>
        <p>
          {origin ? `${origin.label}${origin.ref ? `: ${origin.ref}` : ""}` : "Entered on this report by a person."}
        </p>
        {data.imports.length > 0 ? (
          <ul className="tr-list">
            {data.imports.map((item) => (
              <li key={`${item.import_ref}-${item.line}`}>
                Imported from <strong>{item.file_name ?? "a file"}</strong>, row {item.line}
                {item.imported_by ? ` · by ${item.imported_by}` : ""} · {formatDate(item.imported_at)}
                <span className="tr-values">Mapping version {item.mapping_version}</span>
              </li>
            ))}
          </ul>
        ) : (
          origin && <p className="ac-muted">No import brought this record: it was entered in MDARIX.</p>
        )}
      </section>
      <section>
        <h3>2. Who entered or changed it, and when</h3>
        {data.entered_on_report.length > 0 && <Events items={data.entered_on_report} empty="" />}
        {data.field_changes.length > 0 && (
          <ul className="tr-list">
            {data.field_changes.map((item, index) => (
              <li key={`${item.at}-${index}`}>
                <strong>{item.field.replace(/_/g, " ")}</strong> changed by a re-upload · {formatDate(item.at)}
                <span className="tr-values">
                  {item.before ?? "—"} → {item.after ?? "—"}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Events items={data.record_events} empty="No change recorded on the record since it came in." />
      </section>
      <section>
        <h3>3. Frozen in</h3>
        {snapshot ? (
          <p>
            Version {snapshot.version},{" "}
            {snapshot.approved_by
              ? `approved by ${snapshot.approved_by} · ${formatDate(snapshot.approved_at)}`
              : `waiting for approval (sent by ${snapshot.requested_by} · ${formatDate(snapshot.requested_at)})`}
            <span className="tr-values">As frozen: {snapshot.frozen_value ?? "—"}</span>
            <span className="tr-values tr-hash">SHA-256 {snapshot.sha256}</span>
          </p>
        ) : (
          <p className="ac-muted">Not frozen yet: sending it for approval freezes it.</p>
        )}
      </section>
    </div>
  );
}

function TraceDrawer({
  reportId,
  fieldId,
  title,
  onClose,
}: {
  reportId: string;
  fieldId: string;
  title: string;
  onClose: () => void;
}) {
  const resource = useResource<ValueTrace>(`${REPORTS}/${reportId}/trace/${encodeURIComponent(fieldId)}`);
  return (
    <Drawer title={`Trace: ${title}`} onClose={onClose}>
      <Panel title="Where this value comes from" source={resource}>
        {resource.data && <TraceBody data={resource.data} />}
      </Panel>
    </Drawer>
  );
}

/** The small "Trace" link beside a report value (hidden while MDARIX_B6_TRACE is off). */
export function TraceLink({ reportId, fieldId, title }: { reportId: string; fieldId: string; title: string }) {
  const on = useTrace();
  const [open, setOpen] = useState(false);
  if (!on) return null;
  return (
    <>
      <button type="button" className="ac-link tr-link" aria-label={`Trace ${title}`} onClick={() => setOpen(true)}>
        Trace
      </button>
      {open && <TraceDrawer reportId={reportId} fieldId={fieldId} title={title} onClose={() => setOpen(false)} />}
    </>
  );
}
