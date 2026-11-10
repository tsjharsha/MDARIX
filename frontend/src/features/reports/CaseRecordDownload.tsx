import { useState } from "react";
import { AlertTriangle, Download } from "lucide-react";
import { describeError } from "../../app/apiClient";
import { useCan } from "../workspace/workspaceContext";
import { downloadFile } from "./download";
import { recordPath, type RecordFormat } from "./reportModel";
import "./reports.css";

const FORMATS: Array<[RecordFormat, string]> = [
  ["pdf", "PDF"],
  ["csv", "CSV"],
  ["json", "JSON"],
];

/**
 * "Download case record": everything recorded about one investigation (its fields, complaints, evidence with
 * provenance, hypotheses, decisions and signatures, audit events) as PDF, CSV or JSON. An export, so only roles with
 * the export permission see it; the server checks the permission and audits every download.
 */
export function CaseRecordDownload({ investigationId, label }: { investigationId: string; label?: string }) {
  const canExport = useCan("data.export");
  const [busy, setBusy] = useState<RecordFormat | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  if (!canExport || !investigationId) return null;
  const download = async (format: RecordFormat) => {
    setBusy(format);
    setResult(null);
    try {
      const name = await downloadFile(recordPath(investigationId, format), {
        fallbackName: `${label || "investigation"}-record.${format}`,
      });
      setResult({ ok: true, text: `Investigation record downloaded as ${name}.` });
    } catch (reason) {
      setResult({ ok: false, text: describeError(reason, "The investigation record could not be downloaded.") });
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="rp-record" role="group" aria-label="Download investigation record">
      <span>Download investigation record</span>
      {FORMATS.map(([format, name]) => (
        <button
          key={format}
          type="button"
          className="ac-secondary"
          disabled={busy !== null}
          onClick={() => void download(format)}
          aria-label={`Download investigation record as ${name}`}
        >
          <Download size={14} aria-hidden="true" /> {busy === format ? "Preparing…" : name}
        </button>
      ))}
      {result &&
        (result.ok ? (
          <p className="ca-inline-ok" role="status">
            {result.text}
          </p>
        ) : (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {result.text}
          </p>
        ))}
    </div>
  );
}
