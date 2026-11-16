import { Fragment, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, ListChecks, Upload } from "lucide-react";
import { Empty, Panel, StatTile } from "../../admin/console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { formatDateTime, formatDay, isDateOnly } from "../../../app/dates";
import { useCan, useIsTrial, type BusinessPermission } from "../workspaceContext";
import { countOf, formatCount } from "./common";
import { marketLabel } from "../../../app/labels";
import { EscalateButton } from "./Triage";
import { ProblemCodeOf } from "./ProblemCode";

/*
 * What an Excel or CSV import did (0.10.56, the MVP's R14, R16 and R17 on the trial's import path): each run's
 * data-quality report (rows read, written, set aside, whether they balance), the rows it set aside with their reasons
 * (personal details stored as placeholders), and, on a record, the import, file and row it came from. G2a's reference
 * data beside it: a complaint's IMDRF codes and a product's UDI-DI and GMDN.
 */

/** A value as the review screens show it: every date in one format, "14 Aug 2026" (J42). */
export const previewValue = (value: string | undefined) => (isDateOnly(value) ? formatDay(value) : value || "—");

export const IMPORT_RUNS_PATH = "/api/v1/data/import/runs";
/** Where the reports sit on a page, for the links after an import. */
export const IMPORT_REPORTS_ID = "import-reports";

export type QualityReport = {
  rows_read: number;
  rows_accepted: number;
  rows_quarantined: number;
  /** Rows that changed a field of a record already there; null for a products file. */
  rows_changed: number | null;
  rows_new: number | null;
  /** Rows of records already there, as the file has them (0.10.62; absent from older runs). */
  rows_unchanged?: number | null;
  balanced: boolean;
  /** The file's columns MDARIX did not use, by their names in the file (0.10.65; absent from older runs). */
  columns_not_used?: string[];
  /** A distribution file: the lots whose units shipped now exceed the units they released (flagged, not refused). */
  flags?: { lot_id: string; released: number; shipped: number; message: string }[];
  /** A complaints file (0.10.81): accepted rows that contradict themselves or lack a fact a reporting step needs. */
  row_flags?: { row: number; complaint_id: string | null; message: string }[];
};
export type ImportRun = {
  import_ref: string;
  entity: string;
  file_name: string | null;
  imported_at: string;
  imported_by: string | null;
  mapping_version: string | null;
  masked_values: number;
  sample: boolean;
  report: QualityReport;
};
export type SetAsideRow = {
  id: string;
  /** The file's template: only a complaints row can be a complaint to triage. */
  entity?: string;
  line: number;
  row: Record<string, string>;
  problems: string[];
  harm_words: string[];
  suggests_harm: boolean;
  status: string;
};
type Quarantine = { counts: { open: number; reprocessed: number; dismissed?: number }; items: SetAsideRow[] };

const ENTITY_TITLE: Record<string, string> = { products: "Products", lots: "Lots", complaints: "Complaints" };
/** "Complaints" for a template, else the template's own name with its first letter capital. */
export const entityTitle = (entity: string) =>
  ENTITY_TITLE[entity] ?? `${entity.charAt(0).toUpperCase()}${entity.slice(1).replace(/_/g, " ")}`;

/** "Sample complaints export.xlsx" or, for an import that sent no name, "Complaints file". */
export const fileTitle = (run: Pick<ImportRun, "file_name" | "entity">) =>
  run.file_name || `${entityTitle(run.entity)} file`;

export type Check = { label: string; ok: boolean; detail: string };

/** "2 new, 1 updated, 7 unchanged": updated counts only rows that changed a field; null for a products file. */
export function writtenSplit(report: QualityReport): string | null {
  if (report.rows_new === null || report.rows_changed === null) return null;
  const unchanged = report.rows_unchanged ? `, ${formatCount(report.rows_unchanged)} unchanged` : "";
  return `${formatCount(report.rows_new)} new, ${formatCount(report.rows_changed)} updated${unchanged}`;
}

/** The checks a run's report answers, in plain words (exported for its test). */
export function runChecks(run: Pick<ImportRun, "report" | "masked_values">): Check[] {
  const { report } = run;
  const written = writtenSplit(report) ?? countOf(report.rows_accepted, "row");
  return [
    {
      label: "Every row accounted for",
      ok: report.balanced,
      detail: report.balanced
        ? `${countOf(report.rows_read, "row")} read: ${formatCount(report.rows_accepted)} written and ${formatCount(report.rows_quarantined)} set aside.`
        : `${countOf(report.rows_read, "row")} read, but only ${formatCount(report.rows_accepted + report.rows_quarantined)} written or set aside. Ask us to look at this import.`,
    },
    { label: "Rows written", ok: true, detail: `${written}.` },
    {
      label: "Rows that passed every check",
      ok: report.rows_quarantined === 0,
      detail: report.rows_quarantined
        ? `${countOf(report.rows_quarantined, "row")} set aside with ${report.rows_quarantined === 1 ? "its reason" : "their reasons"}: fix each one below and process it again, or dismiss it with a reason.`
        : "No row was set aside.",
    },
    ...(report.columns_not_used
      ? [
          {
            label: "Columns not used",
            ok: true,
            detail: report.columns_not_used.length
              ? `${report.columns_not_used.join(", ")}: not stored.`
              : "Every column of the file was used.",
          },
        ]
      : []),
    ...(report.flags
      ? [
          {
            label: "Units shipped within units released",
            ok: report.flags.length === 0,
            detail: report.flags.length
              ? `${countOf(report.flags.length, "lot")} shipped more units than released: ${report.flags.map((flag) => flag.message).join(" ")}`
              : "No lot shipped more units than it released.",
          },
        ]
      : []),
    ...(report.row_flags
      ? [
          {
            label: "Rows to check",
            ok: report.row_flags.length === 0,
            detail: report.row_flags.length
              ? report.row_flags
                  .map(
                    (flag) => `Row ${flag.row}${flag.complaint_id ? ` (${flag.complaint_id})` : ""}: ${flag.message}`,
                  )
                  .join(" ")
              : "No row contradicts itself or lacks a country or awareness date.",
          },
        ]
      : []),
    ...(run.masked_values
      ? [
          {
            label: "Personal details replaced",
            ok: true,
            detail: `Replaced with placeholders such as [PERSON] in ${countOf(run.masked_values, "value")}.`,
          },
        ]
      : []),
  ];
}

/** The set-aside rows' reasons by column, most frequent first: [["description", 2], ["event_date", 1]]. */
export function reasonsByColumn(rows: Pick<SetAsideRow, "problems">[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const row of rows)
    for (const column of new Set(row.problems.map((problem) => problem.split(":")[0].trim() || "row")))
      counts.set(column, (counts.get(column) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/**
 * The data-quality reports of the latest imports: one chosen (the newest unless ``selected`` names another), with
 * its rows set aside. Shown below the import panel (Getting started › Your data, Import data).
 */
export function ImportReportsPanel({
  selected,
  onSelect,
  refreshKey = 0,
}: {
  selected: string | null;
  onSelect: (importRef: string) => void;
  /** Changes after an import, so the list is read again. */
  refreshKey?: number;
}) {
  const runs = useResource<{ runs: ImportRun[] }>(IMPORT_RUNS_PATH);
  const reload = runs.reload;
  useEffect(() => {
    if (refreshKey) reload();
  }, [refreshKey, reload]);
  const list = runs.data?.runs ?? [];
  const run = list.find((item) => item.import_ref === selected) ?? list[0];
  return (
    <Panel
      id={IMPORT_REPORTS_ID}
      className="uw-anchor"
      title="Data-quality reports"
      eyebrow="Your imports"
      source={runs}
    >
      {!list.length ? (
        <Empty
          title="No import yet"
          detail="After each import, its report shows here: rows read, written and set aside, and why."
        />
      ) : (
        <>
          {list.length > 1 && (
            <div className="ac-tabs uw-import-runs" role="group" aria-label="Import">
              {list.map((item) => (
                <button
                  key={item.import_ref}
                  type="button"
                  aria-pressed={item.import_ref === run?.import_ref}
                  className={item.import_ref === run?.import_ref ? "selected" : ""}
                  onClick={() => onSelect(item.import_ref)}
                >
                  {fileTitle(item)} · {formatDay(item.imported_at)}
                </button>
              ))}
            </div>
          )}
          {run && <ImportRunReport key={run.import_ref} run={run} />}
        </>
      )}
    </Panel>
  );
}

/** One run's report: the counts, the checks and the rows set aside. */
export function ImportRunReport({ run }: { run: ImportRun }) {
  const { report } = run;
  const aside = useResource<Quarantine>(
    report.rows_quarantined
      ? `/api/v1/data/import/quarantine?${new URLSearchParams({ import_ref: run.import_ref })}`
      : null,
  );
  return (
    <div className="uw-import-run">
      <p className="uw-import-run-head">
        <FileSpreadsheet size={16} aria-hidden="true" /> <strong>{fileTitle(run)}</strong> ·{" "}
        {entityTitle(run.entity).toLowerCase()} · imported {formatDateTime(run.imported_at)}
        {run.imported_by ? ` by ${run.imported_by}` : ""}
        {run.sample ? " · sample data" : ""}
      </p>
      <div className="uw-trial-stats">
        <StatTile
          label="Rows read"
          value={formatCount(report.rows_read)}
          detail="Data rows in the file"
          icon={<Upload size={18} />}
        />
        <StatTile
          label="Written"
          value={formatCount(report.rows_accepted)}
          detail={writtenSplit(report) ?? "Rows saved"}
          icon={<CheckCircle2 size={18} />}
          tone="good"
        />
        <StatTile
          label="Set aside"
          value={formatCount(report.rows_quarantined)}
          detail={report.rows_quarantined ? "Listed below with the reasons" : "None"}
          icon={<AlertTriangle size={18} />}
          tone={report.rows_quarantined ? "warning" : "good"}
        />
      </div>
      <ul className="uw-import-checks" aria-label="Checks">
        {runChecks(run).map((check) => (
          <li key={check.label} className={check.ok ? "is-ok" : "is-bad"}>
            {check.ok ? <CheckCircle2 size={15} aria-hidden="true" /> : <AlertTriangle size={15} aria-hidden="true" />}
            <span>
              <strong>{check.label}:</strong> {check.detail}
            </span>
          </li>
        ))}
      </ul>
      {report.rows_quarantined > 0 && <SetAsideRows source={aside} />}
      {!!report.rows_changed && <FieldChanges importRef={run.import_ref} />}
    </div>
  );
}

type FieldChange = { record_key: string; field: string; before: string | null; after: string | null };

/** The fields this run changed on records already there: a re-upload keeps their history (T-G20). */
function FieldChanges({ importRef }: { importRef: string }) {
  const changes = useResource<{ items: FieldChange[] }>(
    `/api/v1/intake/changes?${new URLSearchParams({ import_ref: importRef })}`,
  );
  const items = changes.data?.items ?? [];
  if (!changes.data) return null;
  return (
    <div className="uw-import-aside">
      <h3 className="uw-trial-subhead">
        <ListChecks size={15} aria-hidden="true" /> Field changes ({formatCount(items.length)})
      </h3>
      {items.length ? (
        <div className="ac-table-wrap">
          <table className="ac-table ms-cards">
            <caption className="ca-sr-only">Fields this import changed</caption>
            <thead>
              <tr>
                <th scope="col">Record</th>
                <th scope="col">Field</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${item.record_key}-${item.field}-${index}`}>
                  <td>{item.record_key}</td>
                  <td data-label="Field">{item.field.replace(/_/g, " ")}</td>
                  <td data-label="Before">{item.before ?? "—"}</td>
                  <td data-label="After">{item.after ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="ac-muted">The updated rows changed no field.</p>
      )}
    </div>
  );
}

/** The privacy line of a trial's set-aside rows (true since 0.10.62: every free-text value is masked when stored). */
export const TRIAL_SET_ASIDE_NOTE =
  "In a free trial, rows set aside on import are kept with personal details masked so you can review and fix them, and are deleted with the trial.";

/** The columns a set-aside row's reasons name, which the fix form offers; every column of the row when they name
 * none (exported for its test). */
export function fixColumns(row: Pick<SetAsideRow, "row" | "problems">): string[] {
  const named = [...new Set(row.problems.map((problem) => problem.split(":")[0].trim()))].filter(
    (column) => column in row.row,
  );
  return named.length ? named : Object.keys(row.row);
}

/** "1 still open · 2 processed again · 1 dismissed", or "" before any row was closed (exported for its test). */
export function asideCounts(counts: Quarantine["counts"] | undefined): string {
  if (!counts || (!counts.reprocessed && !counts.dismissed)) return "";
  return `${formatCount(counts.open)} still open · ${formatCount(counts.reprocessed)} processed again · ${formatCount(counts.dismissed ?? 0)} dismissed`;
}

function SetAsideRows({ source }: { source: ReturnType<typeof useResource<Quarantine>> }) {
  const trial = useIsTrial();
  const canFix = useCan("records.write");
  const [acting, setActing] = useState<{ id: string; mode: "fix" | "dismiss" } | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const rows = source.data?.items ?? [];
  if (source.state === "error")
    return <p className="ac-muted">{source.error ?? "The rows set aside could not be read."}</p>;
  if (!source.data) return <p className="ac-muted">Reading the rows set aside…</p>;
  // Identifiers first (complaint_id, product_id), then the other columns.
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row.row)))].sort(
    (a, b) => Number(!a.endsWith("_id")) - Number(!b.endsWith("_id")) || a.localeCompare(b),
  );
  const reasons = reasonsByColumn(rows);
  const counts = asideCounts(source.data.counts);
  const finished = (text: string) => {
    setActing(null);
    setDone(text);
    source.reload();
  };
  return (
    <div className="uw-import-aside">
      <h3 className="uw-trial-subhead">
        <ListChecks size={15} aria-hidden="true" /> Rows set aside ({formatCount(rows.length)})
      </h3>
      {done && (
        <p className="uw-trial-message is-good" role="status">
          {done}
        </p>
      )}
      {counts && <p className="ac-muted">{counts}</p>}
      {!rows.length ? (
        <p className="ac-muted">Every row this import set aside has been processed again or dismissed.</p>
      ) : (
        <>
          <p className="ac-muted">
            Reasons: {reasons.map(([column, count]) => `${column} (${countOf(count, "row")})`).join(", ")}. Rows that
            suggest harm come first. Personal details are kept only as placeholders such as [PERSON]. Fix a row here and
            process it again, or dismiss it with a reason. A row also closes when its record comes in with a later
            import of your fixed file.
          </p>
          {trial && <p className="ac-muted">{TRIAL_SET_ASIDE_NOTE}</p>}
          <div className="ac-table-wrap">
            <table className="ac-table ms-cards">
              <caption className="ca-sr-only">Rows set aside, with their reasons</caption>
              <thead>
                <tr>
                  <th scope="col">Row</th>
                  <th scope="col">Reasons</th>
                  {columns.map((column) => (
                    <th key={column} scope="col">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <Fragment key={row.id}>
                    <tr>
                      <td>
                        {row.line}
                        {row.suggests_harm ? (
                          <small className="uw-flag-critical" title={`Suggests harm: ${row.harm_words.join(", ")}`}>
                            Suggests harm: on the triage list
                          </small>
                        ) : !row.entity || row.entity === "complaints" ? (
                          <EscalateButton kind="QUARANTINE" id={row.id} label="Triage" />
                        ) : null}
                        {canFix && (
                          <span className="uw-aside-actions">
                            <button
                              type="button"
                              className="ac-link"
                              aria-expanded={acting?.id === row.id && acting.mode === "fix"}
                              onClick={() => setActing({ id: row.id, mode: "fix" })}
                            >
                              Fix and process again
                            </button>
                            <button
                              type="button"
                              className="ac-link"
                              aria-expanded={acting?.id === row.id && acting.mode === "dismiss"}
                              onClick={() => setActing({ id: row.id, mode: "dismiss" })}
                            >
                              Dismiss
                            </button>
                          </span>
                        )}
                      </td>
                      <td data-label="Reasons">
                        <ul className="uw-trial-issues">
                          {row.problems.map((problem) => (
                            <li key={problem}>{problem}</li>
                          ))}
                        </ul>
                      </td>
                      {columns.map((column) => (
                        <td key={column} data-label={column}>
                          {previewValue(row.row[column])}
                        </td>
                      ))}
                    </tr>
                    {acting?.id === row.id && (
                      <tr>
                        <td colSpan={columns.length + 2} data-label="">
                          <SetAsideAction
                            row={row}
                            mode={acting.mode}
                            onCancel={() => setActing(null)}
                            onDone={finished}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/** Fix the fields a set-aside row's reasons name and process it again through the same checks, or dismiss it with a
 * reason (J11). What is still wrong is said beside the row, and the row stays set aside. */
function SetAsideAction({
  row,
  mode,
  onCancel,
  onDone,
}: {
  row: SetAsideRow;
  mode: "fix" | "dismiss";
  onCancel: () => void;
  onDone: (text: string) => void;
}) {
  const columns = fixColumns(row);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(columns.map((column) => [column, row.row[column] ?? ""])),
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = row.row.complaint_id || row.row[Object.keys(row.row)[0]] || `Row ${row.line}`;
  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (mode === "fix") {
        await send(`/api/v1/data/import/quarantine/${row.id}/reprocess`, "POST", { row: values });
        onDone(`Row ${row.line} (${label}) was processed again and is in your records.`);
      } else {
        await send(`/api/v1/data/import/quarantine/${row.id}/dismiss`, "POST", { reason });
        onDone(`Row ${row.line} (${label}) was dismissed: ${reason.trim()}`);
      }
    } catch (failure) {
      setError(errorText(failure, mode === "fix" ? "The row could not be processed again." : "Not dismissed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="uw-import-fix"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {mode === "fix" ? (
        <>
          <p className="ac-muted">
            Correct what the reasons name; the row's other values stay as stored (personal details as placeholders).
          </p>
          {columns.map((column) => (
            <label key={column} className="ca-field">
              {column}
              <input
                type={column.endsWith("_date") ? "date" : "text"}
                value={values[column] ?? ""}
                onChange={(event) => setValues({ ...values, [column]: event.target.value })}
              />
            </label>
          ))}
        </>
      ) : (
        <label className="ca-field">
          Why is this row dismissed? (kept with the row; personal details are masked)
          <textarea value={reason} rows={2} maxLength={500} onChange={(event) => setReason(event.target.value)} />
        </label>
      )}
      {error && (
        <p className="uw-trial-message is-bad" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button
          type="submit"
          className="ac-primary"
          disabled={busy || (mode === "dismiss" && reason.trim().length < 3)}
        >
          {busy ? "Saving…" : mode === "fix" ? "Process again" : "Dismiss the row"}
        </button>
        <button type="button" className="ac-secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

type Origin = {
  source_system: string | null;
  imports: {
    import_ref: string;
    line: number;
    file_name: string | null;
    imported_at: string;
    imported_by: string | null;
    has_report: boolean;
  }[];
};

/** "Row 14 of Sample complaints export.xlsx, imported 31 Oct 2026 by MDARIX sample author" (exported for its test). */
export function originText(item: Origin["imports"][number], entity: string) {
  const file = item.file_name || `a ${entityTitle(entity).toLowerCase()} file`;
  return `Row ${item.line} of ${file}, imported ${formatDateTime(item.imported_at)}${item.imported_by ? ` by ${item.imported_by}` : ""}`;
}

/**
 * Where this record came from (R16): the import, the file and the row, newest first, with a link to that import's
 * data-quality report. Hidden from people whose role may not read imports.
 */
export function RecordOrigin({
  entity,
  recordId,
  onOpenReport,
}: {
  entity: "complaints" | "products" | "lots";
  recordId: string;
  onOpenReport?: (importRef: string) => void;
}) {
  const allowed = useCan("records.write");
  const origin = useResource<Origin>(
    allowed ? `/api/v1/data/import/origin/${entity}/${encodeURIComponent(recordId)}` : null,
  );
  if (!allowed || !origin.data) return null;
  const imports = origin.data.imports;
  return (
    <div className="uw-origin">
      <strong>Where this record came from</strong>
      {imports.length ? (
        <ul>
          {imports.slice(0, 3).map((item) => (
            <li key={`${item.import_ref}-${item.line}`}>
              {originText(item, entity)}.{" "}
              {item.has_report && onOpenReport && (
                <button type="button" className="ac-link" onClick={() => onOpenReport(item.import_ref)}>
                  Data-quality report
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">
          {origin.data.source_system === "MDARIX_SAMPLE"
            ? "Sample data, added when the trial started."
            : "Not from an import that recorded its rows: added in MDARIX, named by a complaints file, or imported before imports kept each row's origin."}
        </p>
      )}
    </div>
  );
}

type ImdrfLink = { release: string; annex: string; code: string; term: string | null };

/** "A16 Protective measures problem": an IMDRF code and its term once the release is loaded (exported for its test). */
export const imdrfText = (link: ImdrfLink) => (link.term ? `${link.code} ${link.term}` : link.code);

/** A complaint's problem code: its IMDRF term first, the customer's own code as the "your code" detail (0.10.70). */
export function ImdrfCodes({ problemCode }: { problemCode: string | null }) {
  if (!problemCode) return null;
  return (
    <p className="uw-imdrf">
      Problem: <ProblemCodeOf code={problemCode} />
    </p>
  );
}

type Registration = {
  id: string;
  market: string;
  registration_type: string;
  registration_number: string;
  product_code: string | null;
  product_code_name?: string | null;
  body_name: string | null;
  body_number: string | null;
  risk_class: string | null;
};

type ProductProfile = {
  product_id: string;
  udi_di: string | null;
  basic_udi_di?: string | null;
  gmdn_code: string | null;
  gmdn_term: string | null;
  emdn_code?: string | null;
  emdn_term?: string | null;
  registrations?: Registration[];
};

/** "UDI-DI 04000000030010 · GMDN 13215 General-purpose infusion pump", or what is missing (exported for its test). A
 * sample product carries a GMDN term without a code: it shows "sample" in place of the number. */
export function identityText(profile: Pick<ProductProfile, "udi_di" | "gmdn_code" | "gmdn_term">, sample = false) {
  const udi = profile.udi_di ? `UDI-DI ${profile.udi_di}` : "No UDI-DI";
  const gmdn = profile.gmdn_code
    ? `GMDN ${[profile.gmdn_code, profile.gmdn_term].filter(Boolean).join(" ")}`
    : profile.gmdn_term
      ? `GMDN ${sample ? "sample" : "code not set"} ${profile.gmdn_term}`
      : "no GMDN term";
  return `${udi} · ${gmdn}`;
}

/** The EU identity line (0.10.77): "Basic UDI-DI … · EMDN Z12030101 Infusion pumps", or "" when neither is set. */
export function euIdentityText(profile: Pick<ProductProfile, "basic_udi_di" | "emdn_code" | "emdn_term">) {
  return [
    profile.basic_udi_di ? `Basic UDI-DI ${profile.basic_udi_di}` : "",
    profile.emdn_code ? `EMDN ${[profile.emdn_code, profile.emdn_term].filter(Boolean).join(" ")}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/** The registration kinds and risk classes each market knows (as the server checks them, regulatory_reference.py;
 * the classes are a starter, for your consultant to confirm). */
export const REGISTRATION_TYPES: Record<string, readonly string[]> = {
  US: ["510K", "PMA", "DE_NOVO", "EXEMPT"],
  EU: ["CE"],
  NI: ["CE", "UKNI"],
  GB: ["UKCA", "CE"],
  CA: ["MDL"],
  IN: ["CDSCO_LICENCE"],
  AU: ["ARTG"],
};
const EU_CLASSES = ["I", "IIa", "IIb", "III", "A", "B", "C", "D"];
export const RISK_CLASSES: Record<string, readonly string[]> = {
  US: ["I", "II", "III"],
  EU: EU_CLASSES,
  NI: EU_CLASSES,
  GB: EU_CLASSES,
  CA: ["I", "II", "III", "IV"],
  IN: ["A", "B", "C", "D"],
};
const TYPE_LABELS: Record<string, string> = {
  "510K": "510(k)",
  PMA: "PMA",
  DE_NOVO: "De Novo",
  EXEMPT: "Exempt",
  CE: "CE mark",
  UKNI: "UKNI mark",
  UKCA: "UKCA mark",
  MDL: "Medical device licence",
  CDSCO_LICENCE: "CDSCO licence",
  ARTG: "ARTG entry",
};
const NUMBER_LABELS: Record<string, string> = {
  US: "510(k), PMA or De Novo number",
  CA: "Licence number",
  IN: "CDSCO licence number",
};

/** "US · 510(k) K123456 · FDA product code FRN (Pump, infusion) · Class II" (exported for its test). */
export function registrationText(item: Registration): string {
  return [
    `${item.market} · ${TYPE_LABELS[item.registration_type] ?? item.registration_type} ${item.registration_number}`,
    item.product_code
      ? `FDA product code ${item.product_code}${item.product_code_name ? ` (${item.product_code_name})` : ""}`
      : "",
    item.body_number ? `${item.market === "GB" ? "Approved" : "Notified"} body ${item.body_number}` : "",
    item.risk_class ? `Class ${item.risk_class}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Products with their regulatory identity (G2a; 0.10.77 adds the Basic UDI-DI, the EMDN code and each market's
 * registration with its risk class), set here by people who may change records and by the Regulatory Leader. */
export function ProductIdentityPanel({
  products,
  onOpenReport,
  title = "Products: UDI-DI and GMDN",
}: {
  products: { id: string; name: string; product_identifier: string }[];
  onOpenReport?: (importRef: string) => void;
  title?: string;
}) {
  return (
    <Panel title={title} eyebrow="Regulatory identity" id="product-identity">
      {products.length ? (
        <ul className="uw-identity-list">
          {products.slice(0, 20).map((product) => (
            <ProductIdentity key={product.id} product={product} onOpenReport={onOpenReport} />
          ))}
        </ul>
      ) : (
        <Empty title="No product yet" detail="Products come in with your complaints or products file." />
      )}
    </Panel>
  );
}

/** Who changes a product's identity, its registrations and the responsible parties: whoever changes records, and the
 * Regulatory Leader (regulatory.review, 0.10.79). The server checks the same (regulatory_reference_router.py). */
export const PRODUCT_EDITORS: readonly BusinessPermission[] = ["records.write", "regulatory.review"];
function useCanEditProducts() {
  const write = useCan("records.write");
  const review = useCan("regulatory.review");
  return write || review;
}

const IDENTITY_FIELDS = [
  ["udi_di", "UDI-DI", 80],
  ["basic_udi_di", "Basic UDI-DI (EU)", 120],
  ["gmdn_code", "GMDN code (5 digits, your own)", 10],
  ["gmdn_term", "GMDN term", 300],
  ["emdn_code", "EMDN code", 30],
] as const;
type IdentityForm = Record<(typeof IDENTITY_FIELDS)[number][0], string>;

function ProductIdentity({
  product,
  onOpenReport,
}: {
  product: { id: string; name: string; product_identifier: string };
  onOpenReport?: (importRef: string) => void;
}) {
  const canEdit = useCanEditProducts();
  const path = `/api/v1/regulatory-reference/products/${encodeURIComponent(product.id)}`;
  const profile = useResource<ProductProfile>(path);
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<IdentityForm>({
    udi_di: "",
    basic_udi_di: "",
    gmdn_code: "",
    gmdn_term: "",
    emdn_code: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const start = () => {
    const data = profile.data;
    setForm({
      udi_di: data?.udi_di ?? "",
      basic_udi_di: data?.basic_udi_di ?? "",
      gmdn_code: data?.gmdn_code ?? "",
      gmdn_term: data?.gmdn_term ?? "",
      emdn_code: data?.emdn_code ?? "",
    });
    setError("");
    setEditing(true);
  };
  const run = async (call: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    setError("");
    try {
      await call();
      profile.reload();
      return true;
    } catch (failure) {
      setError(errorText(failure, fallback));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (await run(() => send(`${path}/identity`, "PUT", form), "The identity was not saved.")) setEditing(false);
  };
  const eu = profile.data ? euIdentityText(profile.data) : "";
  return (
    <li>
      <div className="uw-identity-head">
        <span>
          <strong>{product.name}</strong> <span className="ac-muted">{product.product_identifier}</span>
          <br />
          {profile.data
            ? identityText(profile.data, product.product_identifier.startsWith("SAMPLE-"))
            : profile.state === "error"
              ? "Could not be read."
              : "Loading…"}
          {eu && (
            <>
              <br />
              {eu}
            </>
          )}
        </span>
        {canEdit && profile.data && !editing && (
          <button type="button" className="ac-secondary" onClick={start}>
            Edit
          </button>
        )}
      </div>
      {editing && (
        <form className="uw-identity-form" onSubmit={save}>
          {IDENTITY_FIELDS.map(([key, label, max]) => (
            <label key={key} className="ca-field">
              {label}
              <input
                value={form[key]}
                maxLength={max}
                inputMode={key === "gmdn_code" ? "numeric" : undefined}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </label>
          ))}
          <p className="ac-muted">
            GMDN is licensed: MDARIX keeps your own code. The EMDN code is checked against the European Commission's
            list.
          </p>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
            <button type="button" className="ac-secondary" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {profile.data && (
        <div className="uw-identity-regs">
          <strong>Registrations</strong>
          {profile.data.registrations?.length ? (
            <ul>
              {profile.data.registrations.map((item) => (
                <li key={item.id}>
                  <span>{registrationText(item)}</span>
                  {canEdit && (
                    <button
                      type="button"
                      className="ac-link"
                      disabled={busy}
                      onClick={() =>
                        void run(() => send(`${path}/registrations/${item.id}`, "DELETE"), "It was not removed.")
                      }
                    >
                      Remove
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="ac-muted">
              None yet: each market's registration, its FDA product code or notified body, and its risk class fill the
              report forms.
            </p>
          )}
          {canEdit && !adding && (
            <button type="button" className="ac-link" onClick={() => setAdding(true)}>
              Add a registration
            </button>
          )}
          {adding && (
            <RegistrationForm
              busy={busy}
              onCancel={() => setAdding(false)}
              onSave={async (body) => {
                if (await run(() => send(`${path}/registrations`, "POST", body), "The registration was not added."))
                  setAdding(false);
              }}
            />
          )}
        </div>
      )}
      {error && (
        <p className="uw-trial-message is-bad" role="alert">
          {error}
        </p>
      )}
      <RecordOrigin entity="products" recordId={product.id} onOpenReport={onOpenReport} />
    </li>
  );
}

function RegistrationForm({
  busy,
  onSave,
  onCancel,
}: {
  busy: boolean;
  onSave: (body: Record<string, string>) => void;
  onCancel: () => void;
}) {
  const [market, setMarket] = useState("US");
  const [form, setForm] = useState({
    registration_type: "510K",
    registration_number: "",
    product_code: "",
    body_name: "",
    body_number: "",
    risk_class: "",
  });
  const classes = RISK_CLASSES[market] ?? [];
  const body = market === "EU" || market === "NI" || market === "GB";
  return (
    <form
      className="uw-identity-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({ market, ...form });
      }}
    >
      <label className="ca-field">
        Market
        <select
          value={market}
          onChange={(event) => {
            setMarket(event.target.value);
            setForm({ ...form, registration_type: REGISTRATION_TYPES[event.target.value][0], risk_class: "" });
          }}
        >
          {Object.keys(REGISTRATION_TYPES).map((item) => (
            <option key={item} value={item}>
              {marketLabel(item)}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Kind
        <select
          value={form.registration_type}
          onChange={(event) => setForm({ ...form, registration_type: event.target.value })}
        >
          {REGISTRATION_TYPES[market].map((item) => (
            <option key={item} value={item}>
              {TYPE_LABELS[item] ?? item}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        {NUMBER_LABELS[market] ?? "Registration or certificate number"}
        <input
          value={form.registration_number}
          maxLength={120}
          onChange={(event) => setForm({ ...form, registration_number: event.target.value })}
        />
      </label>
      {market === "US" && (
        <label className="ca-field">
          FDA product code (3 letters)
          <input
            value={form.product_code}
            maxLength={3}
            onChange={(event) => setForm({ ...form, product_code: event.target.value })}
          />
        </label>
      )}
      {body && (
        <>
          <label className="ca-field">
            {market === "GB" ? "Approved body" : "Notified body"}
            <input
              value={form.body_name}
              maxLength={200}
              onChange={(event) => setForm({ ...form, body_name: event.target.value })}
            />
          </label>
          <label className="ca-field">
            {market === "GB" ? "Approved body number" : "Notified body number"}
            <input
              value={form.body_number}
              maxLength={20}
              onChange={(event) => setForm({ ...form, body_number: event.target.value })}
            />
          </label>
        </>
      )}
      {classes.length > 0 && (
        <label className="ca-field">
          Risk class in this market
          <select value={form.risk_class} onChange={(event) => setForm({ ...form, risk_class: event.target.value })}>
            <option value="">Not set</option>
            {classes.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="ac-muted">Risk classes: starter list, for your consultant to confirm.</p>
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={busy || !form.registration_number.trim()}>
          Add
        </button>
        <button type="button" className="ac-secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

type Party = {
  id: string;
  market: string;
  role: string;
  organisation: string;
  address: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  srn: string | null;
  // B8 (tr29): the parts the EU and GB MIR XML needs.
  street?: string | null;
  city?: string | null;
  postcode?: string | null;
  country_code?: string | null;
  contact_first_name?: string | null;
  contact_last_name?: string | null;
};
const PARTS = ["street", "city", "postcode", "country_code", "contact_first_name", "contact_last_name"] as const;

/** What the MIR XML reads for a party, or the parts still to enter (B8 step 6). */
export function partsLine(item: Party): string {
  const missing = PARTS.filter((key) => !item[key]);
  return missing.length
    ? `MIR address and contact parts to enter (${missing.length} of ${PARTS.length})`
    : `${item.street}, ${item.postcode} ${item.city}, ${item.country_code} · ${item.contact_first_name} ${item.contact_last_name}`;
}
const ROLE_LABELS: Record<string, string> = {
  MANUFACTURER: "Manufacturer",
  IMPORTER: "Importer",
  AUTHORISED_REPRESENTATIVE: "Authorised representative",
  UK_RESPONSIBLE_PERSON: "UK Responsible Person",
  SPONSOR: "Sponsor",
  LICENCE_HOLDER: "Licence holder",
};

/** The organization's responsible party per market and role, with its SRN (0.10.77): the reports' manufacturer,
 * authorised representative and importer fields. */
export function ResponsibleParties() {
  const canEdit = useCanEditProducts();
  const list = useResource<{ parties: Party[] }>("/api/v1/regulatory-reference/responsible-parties");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({
    market: "EU",
    role: "MANUFACTURER",
    organisation: "",
    srn: "",
    address: "",
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    street: "",
    city: "",
    postcode: "",
    country_code: "",
    contact_first_name: "",
    contact_last_name: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send("/api/v1/regulatory-reference/responsible-parties", "PUT", form);
      setAdding(false);
      list.reload();
    } catch (failure) {
      setError(errorText(failure, "The responsible party was not saved."));
    } finally {
      setBusy(false);
    }
  };
  const field = (key: keyof typeof form, label: string, max: number) => (
    <label className="ca-field">
      {label}
      <input value={form[key]} maxLength={max} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </label>
  );
  return (
    <Panel title="Responsible parties and SRN" eyebrow="Your organization" source={list}>
      {list.data?.parties.length ? (
        <ul className="uw-identity-list">
          {list.data.parties.map((item) => (
            <li key={item.id}>
              <strong>
                {marketLabel(item.market)} · {ROLE_LABELS[item.role] ?? item.role}
              </strong>{" "}
              {item.organisation}
              {item.srn ? ` · SRN ${item.srn}` : ""}
              <br />
              <span className="ac-muted">{partsLine(item)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">
          None yet. The manufacturer and, outside the EU, the authorised representative fill the EU report's 1.3.
        </p>
      )}
      {canEdit && !adding && (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={() => setAdding(true)}>
            Set a responsible party
          </button>
        </div>
      )}
      {adding && (
        <form className="uw-identity-form" onSubmit={save}>
          <label className="ca-field">
            Market
            <select value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value })}>
              {Object.keys(REGISTRATION_TYPES).map((item) => (
                <option key={item} value={item}>
                  {marketLabel(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {Object.entries(ROLE_LABELS).map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {field("organisation", "Organization", 200)}
          {field("srn", "Single registration number (SRN, EUDAMED)", 40)}
          {field("address", "Address", 2000)}
          {field("contact_name", "Contact", 200)}
          {field("contact_email", "Contact e-mail", 254)}
          {field("contact_phone", "Contact phone", 40)}
          <p className="ac-muted">The EU and GB MIR files take the address and contact in parts:</p>
          {field("street", "Street and number", 500)}
          {field("postcode", "Postcode", 20)}
          {field("city", "City", 120)}
          {field("country_code", "Country (two-letter code, e.g. FR; XI for Northern Ireland)", 2)}
          {field("contact_first_name", "Contact's first name", 100)}
          {field("contact_last_name", "Contact's last name", 100)}
          <p className="ac-muted">Setting a market and role again replaces it.</p>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !form.organisation.trim()}>
              Save
            </button>
            <button type="button" className="ac-secondary" disabled={busy} onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="uw-trial-message is-bad" role="alert">
          {error}
        </p>
      )}
    </Panel>
  );
}
