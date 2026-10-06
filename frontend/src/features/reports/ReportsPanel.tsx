import { useState } from "react";
import { AlertTriangle, Download, Eye } from "lucide-react";
import { describeError, requestJson } from "../../app/apiClient";
import { Empty, Panel } from "../admin/console/charts";
import { Drawer, Table, formatDate, useResource } from "../customer-admin/shared";
import { useCan } from "../workspace/workspaceContext";
import { SortableHeader, useSortedRows } from "../../app/tableSort";
import { downloadFile } from "./download";
import {
  cellText,
  previewSections,
  reportFallbackName,
  reportPath,
  type CatalogReport,
  type FileFormat,
} from "./reportModel";
import "./reports.css";

type ReportDocument = {
  report_type: string;
  title: string;
  generated_at?: string;
  data_cut_off?: string;
  report_version?: string;
  context?: Record<string, unknown>;
  limitations?: string[];
};

/**
 * The organization's governed reports, built from its own records: shown on screen (JSON) or downloaded as CSV or
 * PDF. Generating one is an export (the server requires the export permission and audits every generation), so
 * roles without it see the catalog only. A failure names the reference the server logged it under.
 */
export function ReportsPanel() {
  const catalog = useResource<{ reports: CatalogReport[] }>("/api/v1/reports/catalog");
  const canExport = useCan("data.export");
  const [busy, setBusy] = useState("");
  const [failure, setFailure] = useState<{ report: string; text: string } | null>(null);
  const [done, setDone] = useState("");
  const [preview, setPreview] = useState<ReportDocument | null>(null);

  const run = async (report: CatalogReport, format: "JSON" | FileFormat) => {
    setBusy(`${report.code}:${format}`);
    setFailure(null);
    setDone("");
    try {
      if (format === "JSON")
        setPreview(
          await requestJson<ReportDocument>(reportPath(report.code, "JSON"), { method: "POST", timeoutMs: 120_000 }),
        );
      else {
        const name = await downloadFile(reportPath(report.code, format), {
          method: "POST",
          fallbackName: reportFallbackName(report.code, format),
        });
        setDone(`${report.label} downloaded as ${name}.`);
      }
    } catch (reason) {
      setFailure({ report: report.label, text: describeError(reason, "The report could not be generated.") });
    } finally {
      setBusy("");
    }
  };

  const action = (report: CatalogReport, format: "JSON" | FileFormat) => {
    const key = `${report.code}:${format}`;
    return (
      <button
        type="button"
        className="ac-link"
        disabled={!!busy}
        onClick={() => void run(report, format)}
        aria-label={`${format === "JSON" ? "Preview" : `Download ${format} of`} ${report.label}`}
      >
        {format === "JSON" ? <Eye size={14} aria-hidden="true" /> : <Download size={14} aria-hidden="true" />}{" "}
        {busy === key ? "Preparing…" : format === "JSON" ? "Preview" : format}
      </button>
    );
  };

  return (
    <>
      <Panel eyebrow="Your organization's records" title="Reports" source={catalog}>
        <p className="ac-muted">
          Each report is built from your organization's own records at the moment you generate it, with its data
          cut-off. Reports summarize records; they do not establish causality or replace human approval. Every
          generation is recorded in the audit trail.
        </p>
        {!canExport && (
          <p className="ac-note" role="note">
            Your role can see which reports exist but not generate them: reports are exports of your organization's
            data. Ask an administrator if you need one.
          </p>
        )}
        <Table
          caption="Reports"
          rows={catalog.data?.reports ?? []}
          rowKey={(row) => row.code}
          empty={{ title: "No reports available", detail: "The report catalog is empty." }}
          columns={[
            { key: "label", label: "Report", render: (row) => <strong>{row.label}</strong> },
            ...(canExport
              ? [
                  {
                    key: "actions",
                    label: "",
                    render: (row: CatalogReport) => (
                      <span className="rp-actions">
                        {action(row, "JSON")}
                        {row.formats.includes("CSV") && action(row, "CSV")}
                        {row.formats.includes("PDF") && action(row, "PDF")}
                      </span>
                    ),
                  },
                ]
              : []),
          ]}
        />
        {failure && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {failure.report}: {failure.text}
          </p>
        )}
        {done && (
          <p className="ca-inline-ok" role="status">
            {done}
          </p>
        )}
      </Panel>
      {preview && <ReportPreview report={preview} onClose={() => setPreview(null)} />}
    </>
  );
}

function ReportPreview({ report, onClose }: { report: ReportDocument; onClose: () => void }) {
  const sections = previewSections(report.context);
  return (
    <Drawer title={report.title} onClose={onClose}>
      <dl className="ca-facts">
        <div>
          <dt>Data cut-off</dt>
          <dd>{formatDate(report.data_cut_off)}</dd>
        </div>
        <div>
          <dt>Generated</dt>
          <dd>{formatDate(report.generated_at)}</dd>
        </div>
        <div>
          <dt>Report version</dt>
          <dd>{report.report_version ?? "—"}</dd>
        </div>
      </dl>
      <p className="ac-note">
        Human review required. The preview shows the first rows of each part; the CSV and PDF hold everything.
      </p>
      {!sections.length && <Empty title="No content" detail="This report has no records for your organization yet." />}
      {sections.map((section) => (
        <section className="ca-drawer-section" key={section.key}>
          <h3>{section.label}</h3>
          {section.kind === "empty" && <p className="ac-muted">No records.</p>}
          {section.kind === "value" && <p>{section.value}</p>}
          {section.kind === "facts" && (
            <dl className="ca-facts">
              {section.facts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          )}
          {section.kind === "table" && (
            <>
              <PreviewTable label={section.label} columns={section.columns} rows={section.rows} />
              {section.total > section.rows.length && (
                <p className="ac-muted">
                  First {section.rows.length} of {section.total}.
                </p>
              )}
            </>
          )}
        </section>
      ))}
      {!!report.limitations?.length && (
        <ul className="ac-muted">
          {report.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </Drawer>
  );
}

/** One table of a report preview; its headings sort the rows shown. */
function PreviewTable({
  label,
  columns,
  rows,
}: {
  label: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
}) {
  const { sorted, sort, toggle } = useSortedRows(rows, (row, key) => {
    const value = row[key];
    return value !== null && typeof value === "object" ? cellText(value) : value;
  });
  return (
    <div className="ac-table-wrap">
      <table className="ac-table">
        <caption className="ca-sr-only">{label}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <SortableHeader
                key={column}
                label={column === "business_id" ? "ID" : column.replace(/_business_id$/, " ID").replace(/_/g, " ")}
                sortKey={column}
                sort={sort}
                onSort={toggle}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{cellText(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
