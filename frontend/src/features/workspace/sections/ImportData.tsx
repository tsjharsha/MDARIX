import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, Upload } from "lucide-react";
import { ApiError, requestJson } from "../../../app/apiClient";
import { SortableHeader, useSortedRows } from "../../../app/tableSort";
import { useResource, errorText } from "../../customer-admin/shared";
import { Panel } from "../../admin/console/charts";
import { useCan, useFeatureSet, useIsTrial, useWorkspace } from "../workspaceContext";
import { TRIAL_SET_ASIDE_NOTE } from "./ImportReports";
import { importTemplatesFor } from "../../../app/featureSet";
import { countOf, formatCount } from "./common";
import { IMPORT_REPORTS_ID, ImportReportsPanel, ProductIdentityPanel, previewValue } from "./ImportReports";

/*
 * Excel and CSV import into the organization's own records: one upload panel and one server path
 * (/api/v1/data/import) for free trials (Getting started) and every other organization (Import data), with the same
 * limits, checks, quarantine and data-quality report (stage 4). The whole file is checked first and each import is
 * audited on the server. By default nothing is saved unless every row passes; the uploader may choose to
 * import the rows that pass (the others come back as a rejects file to fix) and to have personal data in the text
 * replaced by placeholders such as [PERSON] instead of refused.
 */

/** How long the page waits for a check or an import: a trial's full allowance (5,000 rows) takes the server minutes. */
export const IMPORT_TIMEOUT_MS = 10 * 60_000;

/** What to say when an import fails. A timeout is not a failure the server reported: the import may have finished. */
export function importFailureText(error: unknown): string {
  if (error instanceof ApiError && error.code === "TIMEOUT")
    return (
      "MDARIX is taking longer than expected, so the page stopped waiting. The import may still finish: check your " +
      "complaints in a few minutes before importing again. Importing the same file again updates its rows; it does " +
      "not add them twice."
    );
  return errorText(error, "The import failed; nothing was saved.");
}

/** What to say when a check is refused. A file without a single data row is a problem of the file, said plainly as
 * the other problems are (no support reference: nothing went wrong on the server, DEV-018). */
export function checkFailureText(error: unknown): string {
  if (error instanceof ApiError && error.code === "IMPORT_FILE_EMPTY") return error.message;
  return errorText(error, "The file could not be checked.");
}

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
  /** The rows that add a record: what a free trial's row allowance counts (one row in the file is one row). */
  new_rows?: number;
  /** The free trial's row allowance, or null for a workspace without one. */
  row_limit?: number | null;
  error_count: number;
  /** Each problem with its row (the file's own row number), its template column and that column's name in the
   * file ("Death (Y/N)"). */
  issues: { row: number | null; column: string | null; header?: string | null; message: string }[];
  ready: boolean;
  preview: Record<string, string>[];
  rows_to_import?: number;
  rejected_rows?: number;
  masked_values?: number;
  /** The rows set aside, with their problems (only when problem rows are skipped); never stored on the server. */
  rejects_csv?: string;
  /** How the export was read: its headers read under a template name, the columns left out (never stored), notes
   * (an encoding, a workbook sheet) and what a complaints file adds besides its complaints (a free trial). */
  columns?: { header: string; column: string }[];
  ignored_columns?: string[];
  /** A second column for a field already read ("Complaint Received Date" beside "Date of Complaint"). */
  duplicate_columns?: { header: string; column: string; kept: string }[];
  notes?: string[];
  also_creates?: Record<string, number>;
  /** The workbook sheet read and its other visible sheets; the date order used; for a complaints file without a
   * date column, the columns that may hold it (J4-J6). */
  sheet?: string | null;
  sheets?: string[];
  date_format_used?: string;
  needs_date_column?: boolean;
  date_column_choices?: string[];
};

const CREATES: [string, string, string][] = [
  ["products", "product", "products"],
  ["versions", "version", "versions"],
  ["lots", "lot", "lots"],
];

/** "1 product and 2 lots": what a complaints file adds besides its complaints, or "" when nothing. */
export function alsoCreatesText(creates: Record<string, number> | null | undefined): string {
  const parts = CREATES.filter(([key]) => (creates?.[key] ?? 0) > 0).map(([key, one, many]) =>
    countOf(creates?.[key] ?? 0, one, many),
  );
  if (!parts.length) return "";
  return parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * What a ready check says: the rows to import and, in a free trial, how many of them count toward its row allowance
 * (the products, versions and lots a complaints file names are added with it but are not rows); elsewhere, the new
 * records (exported for its test).
 */
export function readyText(
  report: Pick<
    CheckReport,
    "rows" | "rows_to_import" | "new_records" | "new_rows" | "row_limit" | "masked_values" | "also_creates"
  >,
): string {
  const rows = countOf(report.rows_to_import ?? report.rows, "row");
  const masked = report.masked_values
    ? `; personal data will be replaced in ${countOf(report.masked_values, "value")}`
    : "";
  const also = alsoCreatesText(report.also_creates);
  if (report.row_limit)
    return `${rows} ready to import (${countOf(report.new_rows ?? 0, "new row")} of your ${formatCount(report.row_limit)})${masked}${
      also ? `; the complaints also add ${also} they name, which do not count as rows` : ""
    }.`;
  return `${rows} ready to import (${countOf(report.new_records, "new record")})${masked}${
    also ? `, including ${also} the complaints name` : ""
  }.`;
}

export type ImportResult = {
  created?: number;
  updated?: number;
  /** The products, versions and lots a free trial's complaints file added (counted in ``created`` too). */
  also_created?: Record<string, number>;
  rejected_rows?: number;
  masked_values?: number;
  /** "FINDING": signals from these complaints are being found after the answer (they show within seconds). */
  signals?: string;
  /** The import run, whose data-quality report (rows read, written, set aside) the reports below show. */
  import_ref?: string;
};

/** What the import result adds while its signals are being found. */
export const FINDING_SIGNALS_TEXT =
  "MDARIX is now finding signals in these complaints: they show in Signals in a moment.";

/**
 * "Imported complaints: 4 new, 0 updated, and 2 products and 3 lots they name." (exported for its test). Every count
 * is grouped the en-US way, "4,993 updated" (DEV-025).
 */
export function importedText(title: string, result: ImportResult): string {
  const also = alsoCreatesText(result.also_created);
  const added = Object.values(result.also_created ?? {}).reduce((sum, count) => sum + count, 0);
  const notes = [
    also ? `and ${also} they name` : "",
    result.rejected_rows ? `${countOf(result.rejected_rows, "row")} set aside to fix` : "",
    result.masked_values ? `personal data replaced in ${countOf(result.masked_values, "value")}` : "",
  ].filter(Boolean);
  const [first, ...rest] = notes;
  return `Imported ${title.toLowerCase()}: ${formatCount((result.created ?? 0) - added)} new, ${formatCount(result.updated ?? 0)} updated${
    first ? `${also ? ", " : "; "}${first}` : ""
  }${rest.length ? `; ${rest.join("; ")}` : ""}.${result.signals === "FINDING" ? ` ${FINDING_SIGNALS_TEXT}` : ""}`;
}

/** What to do with rows that have a problem, and with personal data in the text. */
export type ImportOptions = { skipProblems: boolean; maskPersonal: boolean };
export const NO_OPTIONS: ImportOptions = { skipProblems: false, maskPersonal: false };

/** "AUTO": the server finds the order of day and month from the file, else the organization's usual one (J4). */
export type DateFormat = "AUTO" | "ISO" | "DMY" | "MDY";
export type DateOrder = "DMY" | "MDY";
export const DATE_ORDER_LABELS: Record<string, string> = { DMY: "DD/MM/YYYY", MDY: "MM/DD/YYYY", ISO: "YYYY-MM-DD" };
/** The "Dates in the file" choices, "find it from the file" first with the organization's usual order named. */
export function dateFormatChoices(usual: DateOrder = "DMY"): [DateFormat, string][] {
  return [
    ["AUTO", `From the file, else ${DATE_ORDER_LABELS[usual]}`],
    ["DMY", "DD/MM/YYYY (04/03/2026)"],
    ["MDY", "MM/DD/YYYY (03/04/2026)"],
    ["ISO", "YYYY-MM-DD (2026-03-04)"],
  ];
}
/** How the file writes numbers: only "1,250" and "1.250" read differently in the two (J41). */
export type NumberFormat = "GROUP" | "DECIMAL_COMMA";
export const NUMBER_FORMATS: [NumberFormat, string][] = [
  ["GROUP", "1,250.00 or 1,25,000"],
  ["DECIMAL_COMMA", "1.250,00"],
];
/** The choices about the file itself: the workbook sheet, the number format, the column that holds the date. */
export type FileChoices = { sheet?: string | null; numberFormat?: NumberFormat; dateColumn?: string | null };
/** The date column choice for a complaints file that has none: each complaint is dated the import day. */
export const NO_DATE_COLUMN = "none";

/** The import address for one template: `/check` only checks; the plain address imports. */
export function importUrl(
  base: string,
  entity: string,
  mode: "check" | "import",
  dateFormat: DateFormat,
  options: ImportOptions = NO_OPTIONS,
  fileName?: string,
  choices: FileChoices = {},
) {
  const path = `${base}/${encodeURIComponent(entity)}${mode === "check" ? "/check" : ""}`;
  const query = new URLSearchParams();
  if (dateFormat !== "ISO") query.set("date_format", dateFormat);
  if (options.skipProblems) query.set("on_problems", "skip");
  if (options.maskPersonal) query.set("personal_data", "mask");
  if (choices.numberFormat && choices.numberFormat !== "GROUP") query.set("number_format", choices.numberFormat);
  if (choices.sheet) query.set("sheet", choices.sheet);
  if (choices.dateColumn) query.set("date_column", choices.dateColumn);
  // The file's name, for the import's data-quality report (only with the import itself).
  if (mode === "import" && fileName) query.set("file_name", fileName.slice(0, 255));
  const search = query.toString();
  return search ? `${path}?${search}` : path;
}

/** Save the rows set aside as a CSV file the person can fix and import again. A byte-order mark goes first, so Excel
 * reads it as UTF-8 and "Cathéter" stays "Cathéter" (J42). */
export function downloadRejects(csv: string, entity: string) {
  const url = URL.createObjectURL(new Blob([CSV_BOM, csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `mdarix-${entity}-rows-to-fix.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
export const CSV_BOM = "﻿";

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

/** "Row 5 · Death (Y/N): ..." a problem as the file names it: its row and its own column name. */
export function issueText(issue: CheckReport["issues"][number]) {
  const where = issue.row ? `Row ${issue.row}` : "File";
  const column = issue.header || issue.column;
  return `${where}${column ? ` · ${column}` : ""}: ${issue.message}`;
}

/** The one upload path (stage 4): every screen posts here, with the same limits, checks, quarantine and report. */
export const IMPORT_PATH = "/api/v1/data/import";

/** The templates and limits of this organization's imports (GET /api/v1/data/import/templates). */
export type ImportSetup = {
  row_limit: number | null;
  file_limit_bytes: number;
  /** A free trial may start from one complaints export: the products, versions and lots it names are added. */
  creates_references?: boolean;
  /** The organization's usual date order and number format (DD/MM/YYYY and "1,25,000" in India). */
  usual?: { date_order: DateOrder; number_format: NumberFormat };
  templates: ImportTemplate[];
};

/**
 * "Upload your export": the one upload screen, the same on Getting started and Import data (stage 4). It reads this
 * organization's templates and limits itself (``setup`` only replaces them in a test).
 */
export function ImportPanel({
  onImported,
  id = "data-import",
  eyebrow = "Bring your own data",
  onReport,
  setup: given,
}: {
  /** After an import: what it imported, and of which template. */
  onImported: (result: ImportResult, entity: string) => void;
  id?: string;
  eyebrow?: string;
  /** Opens the data-quality report of the import just done (shown below the panel). */
  onReport?: (importRef: string) => void;
  setup?: ImportSetup;
}) {
  const fetched = useResource<ImportSetup>(given ? null : `${IMPORT_PATH}/templates`);
  const setup = given ?? fetched.data;
  if (!setup)
    return (
      <Panel title="Upload your export" eyebrow={eyebrow} source={fetched}>
        {null}
      </Panel>
    );
  return <ImportForm setup={setup} onImported={onImported} id={id} eyebrow={eyebrow} onReport={onReport} />;
}

function ImportForm({
  setup,
  onImported,
  id,
  eyebrow,
  onReport,
}: {
  setup: ImportSetup;
  onImported: (result: ImportResult, entity: string) => void;
  id: string;
  eyebrow: string;
  onReport?: (importRef: string) => void;
}) {
  const templates = setup.templates;
  // Where a complaints export alone is enough (a free trial), the panel opens on it, until the person chooses another.
  const complaintsAlone = !!setup.creates_references && templates.some((item) => item.entity === "complaints");
  const [entity, setEntity] = useState(complaintsAlone ? "complaints" : "products");
  const trial = useIsTrial();
  // Under the MVP feature set the data types its screens read come first (in a trial, distribution too); the others are
  // offered on request.
  const { core, more } = importTemplatesFor(templates, useFeatureSet());
  const [showMore, setShowMore] = useState(false);
  const shown = showMore ? [...core, ...more] : core;
  const [file, setFile] = useState<File | null>(null);
  const [dateFormat, setDateFormat] = useState<DateFormat>("AUTO");
  const [numberFormat, setNumberFormat] = useState<NumberFormat>(setup.usual?.number_format ?? "GROUP");
  const [sheet, setSheet] = useState<string | null>(null);
  const [dateColumn, setDateColumn] = useState<string | null>(null);
  const [options, setOptions] = useState<ImportOptions>(NO_OPTIONS);
  // The rows set aside by the last import, kept to download after the report is cleared.
  const [rejects, setRejects] = useState<{ csv: string; rows: number } | null>(null);
  // The last import's run, whose data-quality report is one click away.
  const [lastRun, setLastRun] = useState<string | null>(null);
  const canImport = useCan("records.write");
  const [report, setReport] = useState<CheckReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  // Whether this file was checked: a new choice about it then checks the same file again, without picking it again.
  const [checked, setChecked] = useState(false);
  const template = templates.find((item) => item.entity === entity) ?? templates[0];
  const limit = setup.file_limit_bytes;
  const choices: FileChoices = { sheet, numberFormat, dateColumn };

  const send = async (mode: "check" | "import") => {
    if (!file || !template) return null;
    if (file.size > limit) {
      setMessage({
        tone: "bad",
        text: `Files can be up to ${readableSize(limit)}. Split the file and import it in parts.`,
      });
      return null;
    }
    // The file goes as it is (bytes): the server reads an Excel workbook, or text in its encoding and separator.
    return requestJson<any>(importUrl(IMPORT_PATH, template.entity, mode, dateFormat, options, file.name, choices), {
      method: "POST",
      body: file,
      headers: { "Content-Type": isWorkbook(file) ? XLSX_TYPE : "text/csv" },
      timeoutMs: IMPORT_TIMEOUT_MS,
    });
  };
  const check = async () => {
    setBusy(true);
    setMessage(null);
    setChecked(true);
    try {
      setReport(await send("check"));
    } catch (error) {
      setReport(null);
      setMessage({ tone: "bad", text: checkFailureText(error) });
    } finally {
      setBusy(false);
    }
  };
  // A choice about the file (its dates, numbers, sheet, date column, or what to do with problems) checks the same file
  // again (J4); a new template forgets the sheet and date column chosen for the last one.
  const choiceKey = JSON.stringify([entity, dateFormat, numberFormat, sheet, dateColumn, options]);
  const lastChoice = useRef(choiceKey);
  useEffect(() => {
    if (lastChoice.current === choiceKey) return;
    lastChoice.current = choiceKey;
    setRejects(null);
    if (file && checked) void check();
    else setReport(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs when a choice changes, with that render's check
  }, [choiceKey]);
  const chooseTemplate = (next: string) => {
    setEntity(next);
    setSheet(null);
    setDateColumn(null);
    setLastRun(null);
    setMessage(null);
  };
  const runImport = async () => {
    setBusy(true);
    try {
      const result = await send("import");
      if (result) {
        setMessage({ tone: "good", text: importedText(template?.title ?? "data", result) });
        setRejects(result.rejects_csv ? { csv: result.rejects_csv, rows: result.rejected_rows ?? 0 } : null);
        setLastRun(result.import_ref ?? null);
        setReport(null);
        setFile(null);
        setChecked(false);
        onImported(result, template.entity);
      }
    } catch (error) {
      setMessage({ tone: "bad", text: importFailureText(error) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id={id} className="ac-panel uw-trial-import" aria-labelledby={`${id}-title`}>
      <header className="ac-panel-head">
        <div>
          <p className="ac-eyebrow">{eyebrow}</p>
          <h2 id={`${id}-title`}>Upload your export</h2>
        </div>
      </header>
      <p className="uw-trial-note">
        Upload the export as it comes from your quality system, as an Excel workbook or a CSV file: MDARIX finds the
        column names (below a title too), reads them (Complaint No., Date of Complaint, Batch/Lot No. and the like) and
        lists the columns it does not use, without storing them.{" "}
        {complaintsAlone
          ? "A complaints export alone is enough to start: the products and lots it names are added. Load products and lots too for versions and per-unit trends."
          : "Load products first, then lots, then complaints, then the others that refer to them."}{" "}
        By default a file with any problem imports nothing; below you can choose to import the rows that pass and get
        the others back, and to replace personal details instead of refusing them.
      </p>
      {setup.row_limit ? (
        <p className="uw-trial-note">
          Up to {formatCount(setup.row_limit)} rows and {readableSize(setup.file_limit_bytes)} per file.
        </p>
      ) : null}
      {trial && <p className="uw-trial-note">{TRIAL_SET_ASIDE_NOTE}</p>}
      <div className="ac-tabs uw-import-templates" role="group" aria-label="Template">
        {shown.map((item, index) => (
          <button
            key={item.entity}
            type="button"
            aria-pressed={template?.entity === item.entity}
            className={template?.entity === item.entity ? "selected" : ""}
            disabled={busy}
            onClick={() => chooseTemplate(item.entity)}
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
            if (showMore && more.some((item) => item.entity === entity)) chooseTemplate(core[0]?.entity ?? "products");
            setShowMore((value) => !value);
          }}
        >
          {showMore
            ? `Show only the first ${core.length} data types`
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
            {dateFormatChoices(setup.usual?.date_order).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field uw-import-dates">
          Numbers in the file
          <select
            value={numberFormat}
            disabled={busy}
            onChange={(event) => setNumberFormat(event.target.value as NumberFormat)}
          >
            {NUMBER_FORMATS.map(([value, label]) => (
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
            <option value="skip">Import the rows that pass; set the rest aside to fix</option>
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
          <Upload size={15} aria-hidden="true" /> {file ? file.name : "Choose a file (Excel or CSV)"}
          <input
            type="file"
            accept={`.xlsx,.csv,.txt,text/csv,${XLSX_TYPE}`}
            aria-label={`Choose a ${template?.entity ?? "data"} file (Excel or CSV)`}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setReport(null);
              setMessage(null);
              setSheet(null);
              setDateColumn(null);
              setChecked(false);
              // The same file can be chosen again after it is fixed: the input forgets it (J4).
              event.target.value = "";
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
      {(rejects || (lastRun && onReport)) && !report && (
        <div className="ca-action-row">
          {lastRun && onReport && (
            <button type="button" className="ac-primary" onClick={() => onReport(lastRun)}>
              <CheckCircle2 size={15} aria-hidden="true" /> See its data-quality report
            </button>
          )}
          {rejects && (
            <button
              type="button"
              className="ac-secondary"
              onClick={() => downloadRejects(rejects.csv, template.entity)}
            >
              <Download size={15} aria-hidden="true" /> Download the {countOf(rejects.rows, "row")} to fix
            </button>
          )}
        </div>
      )}
      {report && (
        <div className="uw-trial-report" role="status">
          <HowItWasRead report={report} />
          <FileQuestions
            report={report}
            busy={busy}
            sheet={sheet}
            onSheet={setSheet}
            dateColumn={dateColumn}
            onDateColumn={setDateColumn}
          />
          {report.ready ? (
            <>
              <p className="uw-trial-message is-good">
                <CheckCircle2 size={16} aria-hidden="true" /> {readyText(report)}
              </p>
              {!!report.rejected_rows && (
                <>
                  <p className="uw-trial-message is-bad">
                    {countOf(report.rejected_rows, "row")} will be set aside and not imported. After the import you can
                    fix each one in its data-quality report below, or download them, fix them and import that file
                    again.
                  </p>
                  <ul className="uw-trial-issues">
                    {report.issues.map((issue, index) => (
                      <li key={index}>{issueText(issue)}</li>
                    ))}
                  </ul>
                </>
              )}
            </>
          ) : (
            <>
              <p className="uw-trial-message is-bad">
                {countOf(report.error_count, "problem")} found. Nothing has been saved. Fix the file, or change a choice
                above, and check it again.
              </p>
              <ul className="uw-trial-issues">
                {report.issues.map((issue, index) => (
                  <li key={index}>{issueText(issue)}</li>
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

/** What the check asks about the file: which workbook sheet to read, and for a complaints file without a date
 * column, which column holds the date (J5, J6). Each answer checks the same file again. */
export function FileQuestions({
  report,
  busy,
  sheet,
  onSheet,
  dateColumn,
  onDateColumn,
}: {
  report: Pick<CheckReport, "sheet" | "sheets" | "needs_date_column" | "date_column_choices">;
  busy: boolean;
  sheet: string | null;
  onSheet: (sheet: string) => void;
  dateColumn: string | null;
  onDateColumn: (column: string) => void;
}) {
  const sheets = report.sheets ?? [];
  if (sheets.length < 2 && !report.needs_date_column) return null;
  return (
    <div className="uw-trial-upload">
      {sheets.length > 1 && (
        <label className="ca-field uw-import-dates">
          Sheet to read
          <select value={sheet ?? report.sheet ?? ""} disabled={busy} onChange={(event) => onSheet(event.target.value)}>
            {sheets.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}
      {report.needs_date_column && (
        <label className="ca-field uw-import-dates">
          Which column holds the date each complaint was received?
          <select value={dateColumn ?? ""} disabled={busy} onChange={(event) => onDateColumn(event.target.value)}>
            <option value="" disabled>
              Choose a column
            </option>
            {(report.date_column_choices ?? []).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
            <option value={NO_DATE_COLUMN}>None: date each complaint the day it is imported</option>
          </select>
        </label>
      )}
    </div>
  );
}

const XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const isWorkbook = (file: File) => file.type === XLSX_TYPE || file.name.toLowerCase().endsWith(".xlsx");

/** How the server read the export: notes, the headers read under a template name, and the columns not used. */
export function HowItWasRead({
  report,
}: {
  report: Pick<CheckReport, "columns" | "ignored_columns" | "duplicate_columns" | "notes">;
}) {
  const mapped = report.columns ?? [];
  const same = new Map((report.duplicate_columns ?? []).map((item) => [item.header, item.kept]));
  const ignored = (report.ignored_columns ?? []).map((header) =>
    same.has(header) ? `${header} (the same as ${same.get(header)})` : header,
  );
  const notes = report.notes ?? [];
  if (!mapped.length && !ignored.length && !notes.length) return null;
  return (
    <div className="uw-import-read">
      {notes.map((note) => (
        <p key={note} className="ac-muted">
          {note}
        </p>
      ))}
      {mapped.length > 0 && (
        <p>
          <b>Read your columns as:</b>{" "}
          {mapped.map((item, index) => (
            <span key={item.header}>
              {index ? ", " : ""}
              {item.header} → <code>{item.column}</code>
            </span>
          ))}
        </p>
      )}
      {ignored.length > 0 && (
        <p>
          <b>Not used (not stored):</b> {ignored.join(", ")}
        </p>
      )}
    </div>
  );
}

/** The import run a link names (``report=<import_ref>``, from a record's origin), if any. */
export const reportFocus = (focus?: string) => (focus?.startsWith("report=") ? focus.slice("report=".length) : null);

/** Shows one import's data-quality report: chosen and scrolled to (Getting started › Your data, Import data). */
export function useReportChoice(focus?: string) {
  const [selected, setSelected] = useState<string | null>(() => reportFocus(focus));
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    const named = reportFocus(focus);
    if (named) {
      setSelected(named);
      // After the reports are drawn.
      window.setTimeout(() => document.getElementById(IMPORT_REPORTS_ID)?.scrollIntoView({ behavior: "smooth" }), 300);
    }
  }, [focus]);
  const show = (importRef: string) => {
    setSelected(importRef);
    document.getElementById(IMPORT_REPORTS_ID)?.scrollIntoView({ behavior: "smooth" });
  };
  const imported = (importRef?: string) => {
    if (importRef) setSelected(importRef);
    setRefreshKey((key) => key + 1);
  };
  return { selected, setSelected, show, imported, refreshKey };
}

/** "Import data": the organization's import, for everyone whose role may change records: the same upload panel as
 * Getting started (one upload path, stage 4). */
export function ImportDataSection({ focus }: { focus?: string } = {}) {
  const { work } = useWorkspace();
  const reports = useReportChoice(focus);
  return (
    <>
      <ImportPanel
        onImported={(result) => {
          work.refreshProducts();
          reports.imported(result.import_ref);
        }}
        onReport={reports.show}
        eyebrow="Import data"
      />
      <ImportReportsPanel selected={reports.selected} onSelect={reports.setSelected} refreshKey={reports.refreshKey} />
      <ProductIdentityPanel products={work.products} onOpenReport={reports.show} />
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
                <td key={column}>{previewValue(row[column])}</td>
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
