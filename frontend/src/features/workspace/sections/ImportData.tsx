import { useEffect, useState } from "react";
import { CheckCircle2, Download, Upload } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { SortableHeader, useSortedRows } from "../../../app/tableSort";
import { useResource, errorText } from "../../customer-admin/shared";
import { Panel } from "../../admin/console/charts";
import { useCan, useFeatureSet, useWorkspace } from "../workspaceContext";
import { importTemplatesFor } from "../../../app/featureSet";
import { countOf } from "./common";

/*
 * CSV import into the organization's own records. The same validated import serves free trials (their own routes
 * and limits, Getting started) and every other organization (/api/v1/data/import): the whole file is checked first and
 * each import is audited on the server. By default nothing is saved unless every row passes; the uploader may choose to
 * import the rows that pass (the others come back as a rejects file to fix) and to have personal data in the text
 * replaced by placeholders such as [PERSON] instead of refused.
 */

export type ImportTemplate = {
  entity: string;
  title: string;
  required: string[];
  optional: string[];
  /** What the columns that change MDARIX's findings are for (lot quantity, awareness date, harm flags, ...). */
  help?: Record<string, string>;
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
  rows_to_import?: number;
  rejected_rows?: number;
  masked_values?: number;
  /** The rows set aside, with their problems (only when problem rows are skipped); never stored on the server. */
  rejects_csv?: string;
};

/** What to do with rows that have a problem, and with personal data in the text. */
export type ImportOptions = { skipProblems: boolean; maskPersonal: boolean };
export const NO_OPTIONS: ImportOptions = { skipProblems: false, maskPersonal: false };

export type DateFormat = "ISO" | "DMY" | "MDY";
export const DATE_FORMATS: [DateFormat, string][] = [
  ["ISO", "YYYY-MM-DD (2026-03-04)"],
  ["DMY", "DD/MM/YYYY (04/03/2026)"],
  ["MDY", "MM/DD/YYYY (03/04/2026)"],
];

/** The import address for one template: `/check` only checks; the plain address imports. */
export function importUrl(
  base: string,
  entity: string,
  mode: "check" | "import",
  dateFormat: DateFormat,
  options: ImportOptions = NO_OPTIONS,
) {
  const path = `${base}/${encodeURIComponent(entity)}${mode === "check" ? "/check" : ""}`;
  const query = new URLSearchParams();
  if (dateFormat !== "ISO") query.set("date_format", dateFormat);
  if (options.skipProblems) query.set("on_problems", "skip");
  if (options.maskPersonal) query.set("personal_data", "mask");
  const search = query.toString();
  return search ? `${path}?${search}` : path;
}

/** Save the rows set aside as a CSV file the person can fix and import again. */
export function downloadRejects(csv: string, entity: string) {
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `mdarix-${entity}-rows-to-fix.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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
  // Under the MVP feature set the six data types its screens read come first; the others are offered on request.
  const { core, more } = importTemplatesFor(templates, useFeatureSet());
  const [showMore, setShowMore] = useState(false);
  const shown = showMore ? [...core, ...more] : core;
  const [file, setFile] = useState<File | null>(null);
  const [dateFormat, setDateFormat] = useState<DateFormat>("ISO");
  const [options, setOptions] = useState<ImportOptions>(NO_OPTIONS);
  // The rows set aside by the last import, kept to download after the report is cleared.
  const [rejects, setRejects] = useState<{ csv: string; rows: number } | null>(null);
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
    setRejects(null);
  }, [entity, dateFormat]);
  // A new choice needs a new check of the same file.
  useEffect(() => {
    setReport(null);
    setRejects(null);
  }, [options]);

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
    return requestJson<any>(importUrl(basePath, template.entity, mode, dateFormat, options), {
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
        const notes = [
          result.rejected_rows ? `${countOf(result.rejected_rows, "row")} set aside to fix` : "",
          result.masked_values ? `personal data replaced in ${countOf(result.masked_values, "value")}` : "",
        ].filter(Boolean);
        setMessage({
          tone: "good",
          text: `Imported ${template?.title.toLowerCase()}: ${result.created ?? 0} new, ${result.updated ?? 0} updated${
            notes.length ? `; ${notes.join("; ")}` : ""
          }.`,
        });
        setRejects(result.rejects_csv ? { csv: result.rejects_csv, rows: result.rejected_rows ?? 0 } : null);
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
        them. Only template columns are accepted. By default a file with any problem imports nothing; below you can
        choose to import the rows that pass and get the others back, and to replace personal details instead of refusing
        them. Comma, semicolon and tab separated files are all read; save them as CSV UTF-8.
      </p>
      <div className="ac-tabs uw-import-templates" role="group" aria-label="Template">
        {shown.map((item, index) => (
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
      {more.length > 0 && (
        <button
          type="button"
          className="ac-link uw-import-more"
          aria-expanded={showMore}
          disabled={busy}
          onClick={() => {
            // Hiding the extra types while one is chosen goes back to the first template.
            if (showMore && more.some((item) => item.entity === entity)) setEntity(core[0]?.entity ?? "products");
            setShowMore((value) => !value);
          }}
        >
          {showMore
            ? "Show only the six data types the checks read"
            : `Show ${more.length} more data types for deeper investigations (components, suppliers, changes…)`}
        </button>
      )}
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
      {template && <ColumnGuide template={template} />}
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
        <label className="ca-field uw-import-dates">
          Rows with problems
          <select
            value={options.skipProblems ? "skip" : "refuse"}
            disabled={busy}
            onChange={(event) => setOptions({ ...options, skipProblems: event.target.value === "skip" })}
          >
            <option value="refuse">Import nothing until the file is fixed</option>
            <option value="skip">Import the rows that pass; give me the rest to fix</option>
          </select>
        </label>
        <label className="ca-field uw-import-dates">
          Personal details in the text
          <select
            value={options.maskPersonal ? "mask" : "refuse"}
            disabled={busy}
            onChange={(event) => setOptions({ ...options, maskPersonal: event.target.value === "mask" })}
          >
            <option value="refuse">Refuse them: I remove them first</option>
            <option value="mask">Replace them with [PERSON], [PHONE] and similar</option>
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
      {rejects && !report && (
        <button type="button" className="ac-secondary" onClick={() => downloadRejects(rejects.csv, template.entity)}>
          <Download size={15} aria-hidden="true" /> Download the {countOf(rejects.rows, "row")} to fix
        </button>
      )}
      {report && (
        <div className="uw-trial-report" role="status">
          {report.ready ? (
            <>
              <p className="uw-trial-message is-good">
                <CheckCircle2 size={16} aria-hidden="true" /> {countOf(report.rows_to_import ?? report.rows, "row")}{" "}
                ready to import ({countOf(report.new_records, "new record")})
                {report.masked_values
                  ? `; personal data will be replaced in ${countOf(report.masked_values, "value")}`
                  : ""}
                .
              </p>
              {!!report.rejected_rows && (
                <>
                  <p className="uw-trial-message is-bad">
                    {countOf(report.rejected_rows, "row")} will be set aside and not imported. Download them, fix them
                    and import that file again.
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
            </>
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
          {report.rejects_csv && (
            <button
              type="button"
              className="ac-secondary"
              onClick={() => downloadRejects(report.rejects_csv ?? "", report.entity)}
            >
              <Download size={15} aria-hidden="true" /> Download the {countOf(report.rejected_rows ?? 0, "row")} to fix
            </button>
          )}
          {report.preview.length > 0 && <FilePreviewTable rows={report.preview} />}
          {report.ready && canImport && (
            <button type="button" className="ac-primary" disabled={busy} onClick={runImport}>
              <Upload size={15} aria-hidden="true" />{" "}
              {busy ? "Importing…" : `Import ${countOf(report.rows_to_import ?? report.rows, "row")}`}
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

/**
 * What the template's key columns are for, beside the template. For lots, a callout first: a quantity on every lot
 * turns the trend check from per calendar day into per unit in the field (exported for its test).
 */
export function ColumnGuide({ template }: { template: ImportTemplate }) {
  const entries = Object.entries(template.help ?? {});
  if (!entries.length) return null;
  const perUnit = template.entity === "lots" && Boolean(template.help?.quantity);
  return (
    <div className="uw-import-guide">
      {perUnit && (
        <p className="uw-import-callout" role="note">
          <strong>Per-unit trends from day one:</strong> add <code>quantity</code> (devices released) and{" "}
          <code>manufacture_date</code> to every lot. The trend check then counts complaints per unit in the field, so a
          version shipped in growing numbers is not mistaken for a rising trend. Lots already loaded can be updated by
          uploading them again with the quantity.
        </p>
      )}
      <details open={perUnit}>
        <summary>What the key columns do</summary>
        <dl>
          {entries.map(([column, text]) => (
            <div key={column}>
              <dt>
                <code>{column}</code>
              </dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}
