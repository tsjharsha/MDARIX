import { useEffect, useState } from "react";
import { CheckCircle2, Download, Upload } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { SortableHeader, useSortedRows } from "../../../app/tableSort";
import { useResource, errorText } from "../../customer-admin/shared";
import { Panel } from "../../admin/console/charts";
import { useCan, useWorkspace } from "../workspaceContext";

/*
 * CSV import into the organization's own records. The same validated import serves free trials (their own routes
 * and limits, Getting started) and every other organization (/api/v1/data/import): the whole file is checked first,
 * nothing is saved unless every row passes, and each import is audited on the server.
 */

export type ImportTemplate = {
  entity: string;
  title: string;
  required: string[];
  optional: string[];
  download: string;
};
type CheckReport = {
  entity: string;
  rows: number;
  new_records: number;
  error_count: number;
  issues: { row: number | null; column: string | null; message: string }[];
  ready: boolean;
  preview: Record<string, string>[];
};

export type DateFormat = "ISO" | "DMY" | "MDY";
export const DATE_FORMATS: [DateFormat, string][] = [
  ["ISO", "YYYY-MM-DD (2026-03-04)"],
  ["DMY", "DD/MM/YYYY (04/03/2026)"],
  ["MDY", "MM/DD/YYYY (03/04/2026)"],
];

/** The import address for one template: `/check` only checks; the plain address imports. */
export function importUrl(base: string, entity: string, mode: "check" | "import", dateFormat: DateFormat) {
  const path = `${base}/${encodeURIComponent(entity)}${mode === "check" ? "/check" : ""}`;
  return dateFormat === "ISO" ? path : `${path}?date_format=${dateFormat}`;
}

/** "2 MB" for a file limit in bytes. */
export function readableSize(bytes: number) {
  return bytes >= 1024 * 1024 ? `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

/** The templates in loading order, as one readable phrase ("Products and versions, Lots and batches and 3 more"). */
export function templateSummary(templates: Pick<ImportTemplate, "title">[], shown = 3) {
  const titles = templates.map((item) => item.title.toLowerCase());
  if (!titles.length) return "";
  if (titles.length <= shown)
    return titles.length === 1 ? titles[0] : `${titles.slice(0, -1).join(", ")} and ${titles[titles.length - 1]}`;
  return `${titles.slice(0, shown).join(", ")} and ${titles.length - shown} more`;
}

export function ImportPanel({
  templates,
  basePath,
  fileLimitBytes,
  onImported,
  id = "data-import",
  eyebrow = "Bring your own data",
}: {
  templates: ImportTemplate[];
  /** /api/v1/data/import for every organization; /api/v1/trial/imports for the free trial's own limits. */
  basePath: string;
  fileLimitBytes?: number;
  onImported: () => void;
  id?: string;
  eyebrow?: string;
}) {
  const [entity, setEntity] = useState("products");
  const [file, setFile] = useState<File | null>(null);
  const [dateFormat, setDateFormat] = useState<DateFormat>("ISO");
  const canImport = useCan("records.write");
  const [report, setReport] = useState<CheckReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const template = templates.find((item) => item.entity === entity) ?? templates[0];
  const limit = fileLimitBytes ?? 2 * 1024 * 1024;

  useEffect(() => {
    setFile(null);
    setReport(null);
    setMessage(null);
  }, [entity, dateFormat]);

  const send = async (mode: "check" | "import") => {
    if (!file || !template) return null;
    if (file.size > limit) {
      setMessage({
        tone: "bad",
        text: `Files can be up to ${readableSize(limit)}. Split the file and import it in parts.`,
      });
      return null;
    }
    // The file goes as it is (bytes): the server reads its encoding and its separator (comma, semicolon or tab).
    return requestJson<any>(importUrl(basePath, template.entity, mode, dateFormat), {
      method: "POST",
      body: file,
      headers: { "Content-Type": "text/csv" },
      timeoutMs: 60_000,
    });
  };
  const check = async () => {
    setBusy(true);
    setMessage(null);
    try {
      setReport(await send("check"));
    } catch (error) {
      setMessage({ tone: "bad", text: errorText(error, "The file could not be checked.") });
    } finally {
      setBusy(false);
    }
  };
  const runImport = async () => {
    setBusy(true);
    try {
      const result = await send("import");
      if (result) {
        setMessage({
          tone: "good",
          text: `Imported ${template?.title.toLowerCase()}: ${result.created ?? 0} new, ${result.updated ?? 0} updated.`,
        });
        setReport(null);
        setFile(null);
        onImported();
      }
    } catch (error) {
      setMessage({ tone: "bad", text: errorText(error, "The import failed; nothing was saved.") });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id={id} className="ac-panel uw-trial-import" aria-labelledby={`${id}-title`}>
      <header className="ac-panel-head">
        <div>
          <p className="ac-eyebrow">{eyebrow}</p>
          <h2 id={`${id}-title`}>Upload a CSV file</h2>
        </div>
      </header>
      <p className="uw-trial-note">
        Load the templates in the order shown: products first, then lots, then complaints, then the others that refer to
        them. Remove patient and personal details first. Only template columns are accepted, and a file with any problem
        imports nothing. Comma, semicolon and tab separated files are all read; save them as CSV UTF-8.
      </p>
      <div className="ac-tabs uw-import-templates" role="group" aria-label="Template">
        {templates.map((item, index) => (
          <button
            key={item.entity}
            type="button"
            aria-pressed={template?.entity === item.entity}
            className={template?.entity === item.entity ? "selected" : ""}
            disabled={busy}
            onClick={() => setEntity(item.entity)}
          >
            {index + 1}. {item.title}
          </button>
        ))}
      </div>
      {template && (
        <div className="uw-trial-template">
          <div>
            <strong>Required:</strong> {template.required.join(", ")}
            <br />
            <strong>Optional:</strong> {template.optional.join(", ") || "none"}
          </div>
          <a className="ac-secondary" href={template.download} download>
            <Download size={15} aria-hidden="true" /> Download {template.entity}.csv
          </a>
        </div>
      )}
      <div className="uw-trial-upload">
        <label className="ca-field uw-import-dates">
          Dates in the file
          <select
            value={dateFormat}
            disabled={busy}
            onChange={(event) => setDateFormat(event.target.value as DateFormat)}
          >
            {DATE_FORMATS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="ac-secondary">
          <Upload size={15} aria-hidden="true" /> {file ? file.name : "Choose a CSV file"}
          <input
            type="file"
            accept=".csv,.txt,text/csv"
            aria-label={`Choose a ${template?.entity ?? "data"} CSV file`}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setReport(null);
              setMessage(null);
            }}
          />
        </label>
        {canImport ? (
          <button type="button" className="ac-primary" disabled={!file || busy} onClick={check}>
            {busy && !report ? "Checking…" : "Check file"}
          </button>
        ) : (
          <p className="ac-muted" role="note">
            View only: your role cannot import data.
          </p>
        )}
      </div>
      {message && (
        <p className={`uw-trial-message is-${message.tone}`} role="status">
          {message.text}
        </p>
      )}
      {report && (
        <div className="uw-trial-report" role="status">
          {report.ready ? (
            <p className="uw-trial-message is-good">
              <CheckCircle2 size={16} aria-hidden="true" /> {report.rows} rows are ready to import ({report.new_records}{" "}
              new records).
            </p>
          ) : (
            <>
              <p className="uw-trial-message is-bad">
                {report.error_count} problem{report.error_count === 1 ? "" : "s"} found. Nothing has been saved. Fix the
                file and check it again.
              </p>
              <ul className="uw-trial-issues">
                {report.issues.map((issue, index) => (
                  <li key={index}>
                    {issue.row ? `Row ${issue.row}` : "File"}
                    {issue.column ? ` · ${issue.column}` : ""}: {issue.message}
                  </li>
                ))}
              </ul>
            </>
          )}
          {report.preview.length > 0 && <FilePreviewTable rows={report.preview} />}
          {report.ready && canImport && (
            <button type="button" className="ac-primary" disabled={busy} onClick={runImport}>
              <Upload size={15} aria-hidden="true" /> {busy ? "Importing…" : `Import ${report.rows} rows`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

type Templates = { row_limit: number | null; file_limit_bytes: number; templates: ImportTemplate[] };

/** "Import data": the organization's CSV import, for everyone whose role may change records. */
export function ImportDataSection() {
  const { work } = useWorkspace();
  const templates = useResource<Templates>("/api/v1/data/import/templates");
  return (
    <>
      <p className="ca-lede">
        Bring records from your quality, product and supplier systems into MDARIX as CSV files. Each file is checked in
        full and nothing is saved unless every row passes. Every import is recorded in the audit trail.
      </p>
      {templates.state !== "ready" || !templates.data ? (
        <Panel title="Import templates" eyebrow="Import data" source={templates}>
          {null}
        </Panel>
      ) : (
        <>
          {templates.data.row_limit ? (
            <p className="ac-note">
              Up to {templates.data.row_limit.toLocaleString()} rows and {readableSize(templates.data.file_limit_bytes)}{" "}
              per file.
            </p>
          ) : null}
          <ImportPanel
            templates={templates.data.templates}
            basePath="/api/v1/data/import"
            fileLimitBytes={templates.data.file_limit_bytes}
            onImported={work.refreshProducts}
            eyebrow="Import data"
          />
        </>
      )}
    </>
  );
}

/** The first rows of the checked file, as they will be imported; the headings sort the rows shown. */
function FilePreviewTable({ rows }: { rows: Record<string, string>[] }) {
  const columns = Object.keys(rows[0] ?? {});
  const { sorted, sort, toggle } = useSortedRows(rows, (row, key) => row[key]);
  return (
    <div className="ac-table-wrap">
      <table className="ac-table">
        <caption className="ca-sr-only">First rows of the file</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <SortableHeader key={column} label={column} sortKey={column} sort={sort} onSort={toggle} />
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{row[column] || "—"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
