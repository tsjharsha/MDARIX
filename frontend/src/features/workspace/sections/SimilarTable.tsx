import { useState } from "react";
import { ToneBadge } from "../../admin/console/charts";
import {
  REPORTS,
  SIMILAR_COUNTS,
  SIMILAR_PERIODS,
  fieldTone,
  similarRows,
  type ReportDetail,
  type SimilarRow,
  type WorksheetField,
} from "../authorityReports";
import { InlineError } from "./boardParts";
import { useAction } from "./Reports";

/** The table's cells: periods N to N-3 down, dates and the six counts across; inputs while ``edit`` is given. */
export function SimilarGrid({
  rows,
  edit,
}: {
  rows: SimilarRow[];
  edit?: ((index: number, key: string, text: string) => void) | null;
}) {
  const cell = (index: number, key: string, label: string, value: string | number | undefined, type: string) =>
    edit ? (
      <input
        aria-label={`Period ${SIMILAR_PERIODS[index]}: ${label}`}
        type={type}
        min={type === "number" ? 0 : undefined}
        step={type === "number" ? 1 : undefined}
        value={value ?? ""}
        onChange={(event) => edit(index, key, event.target.value)}
      />
    ) : (
      (value ?? "—")
    );
  return (
    <div className="uw-rp-table-wrap">
      <table className="uw-rp-table">
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th scope="col">Start</th>
            <th scope="col">End</th>
            {SIMILAR_COUNTS.map(([key, label]) => (
              <th scope="col" key={key}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={SIMILAR_PERIODS[index]}>
              <th scope="row">{SIMILAR_PERIODS[index]}</th>
              <td>{cell(index, "start", "start", row.start, "date")}</td>
              <td>{cell(index, "end", "end", row.end, "date")}</td>
              {SIMILAR_COUNTS.map(([key, label]) => (
                <td key={key}>{cell(index, key, label, row[key], "number")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * B8 step 10: the MIR's 4.3.3c similar incidents as a table (one entry). Every number is a person's (B8-D7): MDARIX
 * holds no distribution data, so nothing is counted or suggested here.
 */
export function SimilarTableRow({
  detail,
  item,
  onChanged,
  canEdit,
}: {
  detail: ReportDetail;
  item: WorksheetField;
  onChanged: (detail: ReportDetail) => void;
  canEdit: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState(() => similarRows(item.value));
  const action = useAction(onChanged, "The table was not saved.");
  const path = `${REPORTS}/${detail.id}/fields/${item.id}`;
  const set = (index: number, key: string, text: string) =>
    setRows(
      rows.map((row, at) =>
        at !== index
          ? row
          : { ...row, [key]: key === "start" || key === "end" ? text : text === "" ? undefined : Number(text) },
      ),
    );
  return (
    <li className="uw-rp-field">
      <div className="uw-rp-field-head">
        <span className="uw-rp-number">{item.number}</span>
        <span className="uw-rp-label">{item.label}</span>
        <ToneBadge tone={fieldTone(item.status)} label={item.status_label} />
      </div>
      <p className="uw-cr-meta">
        Every number is yours: MDARIX holds no distribution data. Enter 0 where you found none, for each period and
        region.
      </p>
      {(item.value || editing) && (
        <SimilarGrid rows={editing ? rows : similarRows(item.value)} edit={editing ? set : null} />
      )}
      {!item.value && !editing && <p className="uw-rp-value empty">—</p>}
      {item.problem && <InlineError text={`${item.problem}: it counts as missing until it is corrected.`} />}
      {canEdit && item.editable !== false && !editing && (
        <div className="ca-action-row">
          <button type="button" className="ac-link" onClick={() => setEditing(true)}>
            {item.value ? "Change the table" : "Enter the table"}
          </button>
        </div>
      )}
      {editing && (
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-secondary"
            disabled={action.busy}
            onClick={async () => {
              if (await action.run(path, "PUT", { value: JSON.stringify(rows) })) setEditing(false);
            }}
          >
            Save the table
          </button>
          <button type="button" className="ac-link" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
      )}
      <InlineError text={action.error} />
    </li>
  );
}
