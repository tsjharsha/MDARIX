import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, ListChecks, Upload } from "lucide-react";
import { Empty, Panel, StatTile } from "../../admin/console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { formatDateTime, formatDay } from "../../../app/dates";
import { useCan } from "../workspaceContext";
import { countOf, formatCount } from "./common";
import { EscalateButton } from "./Triage";

/*
 * What an Excel or CSV import did (0.10.56, the MVP's R14, R16 and R17 on the trial's import path): each run's
 * data-quality report (rows read, written, set aside, whether they balance), the rows it set aside with their reasons
 * (personal details stored as placeholders), and, on a record, the import, file and row it came from. G2a's reference
 * data beside it: a complaint's IMDRF codes and a product's UDI-DI and GMDN.
 */

export const IMPORT_RUNS_PATH = "/api/v1/data/import/runs";
/** Where the reports sit on a page, for the links after an import. */
export const IMPORT_REPORTS_ID = "import-reports";

export type QualityReport = {
  rows_read: number;
  rows_accepted: number;
  rows_quarantined: number;
  /** Rows that updated a record already there; null for a products file. */
  rows_changed: number | null;
  rows_new: number | null;
  balanced: boolean;
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
  line: number;
  row: Record<string, string>;
  problems: string[];
  harm_words: string[];
  suggests_harm: boolean;
  status: string;
};
type Quarantine = { counts: { open: number; reprocessed: number }; items: SetAsideRow[] };

const ENTITY_TITLE: Record<string, string> = { products: "Products", lots: "Lots", complaints: "Complaints" };
/** "Complaints" for a template, else the template's own name with its first letter capital. */
export const entityTitle = (entity: string) =>
  ENTITY_TITLE[entity] ?? `${entity.charAt(0).toUpperCase()}${entity.slice(1).replace(/_/g, " ")}`;

/** "Sample complaints export.xlsx" or, for an import that sent no name, "Complaints file". */
export const fileTitle = (run: Pick<ImportRun, "file_name" | "entity">) =>
  run.file_name || `${entityTitle(run.entity)} file`;

export type Check = { label: string; ok: boolean; detail: string };

/** The checks a run's report answers, in plain words (exported for its test). */
export function runChecks(run: Pick<ImportRun, "report" | "masked_values">): Check[] {
  const { report } = run;
  const written =
    report.rows_new === null || report.rows_changed === null
      ? countOf(report.rows_accepted, "row")
      : `${formatCount(report.rows_new)} new, ${formatCount(report.rows_changed)} updated`;
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
        ? `${countOf(report.rows_quarantined, "row")} set aside with ${report.rows_quarantined === 1 ? "its reason" : "their reasons"}: fix them in your file and import it again.`
        : "No row was set aside.",
    },
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
          detail={
            report.rows_new === null || report.rows_changed === null
              ? "Rows saved"
              : `${formatCount(report.rows_new)} new, ${formatCount(report.rows_changed)} updated`
          }
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
          <table className="ac-table">
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
                  <td>{item.field.replace(/_/g, " ")}</td>
                  <td>{item.before ?? "—"}</td>
                  <td>{item.after ?? "—"}</td>
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

function SetAsideRows({ source }: { source: ReturnType<typeof useResource<Quarantine>> }) {
  const rows = source.data?.items ?? [];
  if (source.state === "error")
    return <p className="ac-muted">{source.error ?? "The rows set aside could not be read."}</p>;
  if (!source.data) return <p className="ac-muted">Reading the rows set aside…</p>;
  // Identifiers first (complaint_id, product_id), then the other columns.
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row.row)))].sort(
    (a, b) => Number(!a.endsWith("_id")) - Number(!b.endsWith("_id")) || a.localeCompare(b),
  );
  const reasons = reasonsByColumn(rows);
  return (
    <div className="uw-import-aside">
      <h3 className="uw-trial-subhead">
        <ListChecks size={15} aria-hidden="true" /> Rows set aside ({formatCount(rows.length)})
      </h3>
      <p className="ac-muted">
        Reasons: {reasons.map(([column, count]) => `${column} (${countOf(count, "row")})`).join(", ")}. Rows that
        suggest harm come first. Personal details are kept only as placeholders such as [PERSON]. Fix these rows in your
        file and import it again: rows already in are updated, not added twice.
      </p>
      <div className="ac-table-wrap">
        <table className="ac-table">
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
              <tr key={row.id}>
                <td>
                  {row.line}
                  {row.suggests_harm ? (
                    <small className="uw-flag-critical" title={`Suggests harm: ${row.harm_words.join(", ")}`}>
                      Suggests harm: on the triage list
                    </small>
                  ) : (
                    <EscalateButton kind="QUARANTINE" id={row.id} label="Triage" />
                  )}
                </td>
                <td>
                  <ul className="uw-trial-issues">
                    {row.problems.map((problem) => (
                      <li key={problem}>{problem}</li>
                    ))}
                  </ul>
                </td>
                {columns.map((column) => (
                  <td key={column}>{row.row[column] || "—"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
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

/** The IMDRF codes a complaint's problem code maps to (approved links only), beside the problem code. */
export function ImdrfCodes({ problemCode }: { problemCode: string | null }) {
  const links = useResource<{ links: Record<string, ImdrfLink[]> }>(
    problemCode ? `/api/v1/regulatory-reference/imdrf/links?${new URLSearchParams({ code: problemCode })}` : null,
  );
  if (!problemCode) return null;
  const found = links.data?.links[problemCode] ?? [];
  return (
    <p className="uw-imdrf">
      Problem code <code>{problemCode}</code>
      {found.length ? (
        <>
          {" "}
          · IMDRF Annex {found[0].annex}:{" "}
          {found.map((link, index) => (
            <span key={`${link.annex}${link.code}`} title={`IMDRF release ${link.release}`}>
              {index ? "; " : ""}
              {imdrfText(link)}
            </span>
          ))}
        </>
      ) : links.data ? (
        " · no IMDRF code mapped yet"
      ) : null}
    </p>
  );
}

type ProductProfile = {
  product_id: string;
  udi_di: string | null;
  gmdn_code: string | null;
  gmdn_term: string | null;
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

/** Products with their regulatory identity (G2a): UDI-DI and GMDN, set here by people who may change records. */
export function ProductIdentityPanel({
  products,
  onOpenReport,
}: {
  products: { id: string; name: string; product_identifier: string }[];
  onOpenReport?: (importRef: string) => void;
}) {
  return (
    <Panel title="Products: UDI-DI and GMDN" eyebrow="Regulatory identity" id="product-identity">
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

function ProductIdentity({
  product,
  onOpenReport,
}: {
  product: { id: string; name: string; product_identifier: string };
  onOpenReport?: (importRef: string) => void;
}) {
  const canEdit = useCan("records.write");
  const profile = useResource<ProductProfile>(
    `/api/v1/regulatory-reference/products/${encodeURIComponent(product.id)}`,
  );
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ udi_di: "", gmdn_code: "", gmdn_term: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const start = () => {
    const data = profile.data;
    setForm({ udi_di: data?.udi_di ?? "", gmdn_code: data?.gmdn_code ?? "", gmdn_term: data?.gmdn_term ?? "" });
    setError("");
    setEditing(true);
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/regulatory-reference/products/${encodeURIComponent(product.id)}/identity`, "PUT", form);
      setEditing(false);
      profile.reload();
    } catch (failure) {
      setError(errorText(failure, "The identity was not saved."));
    } finally {
      setBusy(false);
    }
  };
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
              : "Reading…"}
        </span>
        {canEdit && profile.data && !editing && (
          <button type="button" className="ac-secondary" onClick={start}>
            Edit
          </button>
        )}
      </div>
      {editing && (
        <form className="uw-identity-form" onSubmit={save}>
          <label className="ca-field">
            UDI-DI
            <input value={form.udi_di} maxLength={80} onChange={(e) => setForm({ ...form, udi_di: e.target.value })} />
          </label>
          <label className="ca-field">
            GMDN code (5 digits)
            <input
              value={form.gmdn_code}
              maxLength={10}
              inputMode="numeric"
              onChange={(e) => setForm({ ...form, gmdn_code: e.target.value })}
            />
          </label>
          <label className="ca-field">
            GMDN term
            <input
              value={form.gmdn_term}
              maxLength={300}
              onChange={(e) => setForm({ ...form, gmdn_term: e.target.value })}
            />
          </label>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy}>
              {busy ? "Saving…" : "Save"}
            </button>
            <button type="button" className="ac-secondary" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
          {error && (
            <p className="uw-trial-message is-bad" role="alert">
              {error}
            </p>
          )}
        </form>
      )}
      <RecordOrigin entity="products" recordId={product.id} onOpenReport={onOpenReport} />
    </li>
  );
}
