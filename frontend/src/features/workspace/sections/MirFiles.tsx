import { Download } from "lucide-react";
import type { ReportDetail } from "../authorityReports";

/** B8 step 8: what an EU report's MIR file still needs before Send for approval (blocks, parts, schema errors). */
export function MirNeeds({ detail }: { detail: Pick<ReportDetail, "mir" | "stage"> }) {
  const needs = [...(detail.mir?.missing ?? []), ...(detail.mir?.errors ?? [])];
  if (!detail.mir || detail.mir.snapshot || !needs.length || detail.stage === "APPROVED") return null;
  return (
    <div className="ac-muted" id="rp-mir-needs">
      <p>Send for approval checks the MIR file against the Commission's schema. It still needs:</p>
      <ul>
        {needs.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/** B8 steps 8-11: after approval, the MIR XML beside the PDF, both made at approval (no generate step). */
export function MirFiles({ detail, onXml }: { detail: Pick<ReportDetail, "mir">; onXml: () => void }) {
  if (!detail.mir?.snapshot) return null; // no XML before approval, nor for a report approved before B8 (its PDF)
  return (
    <>
      <button type="button" className="ac-secondary" onClick={onXml}>
        <Download size={15} aria-hidden="true" /> Download XML (MIR 7.3.1)
      </button>
      <p className="ac-note">
        The files were made when the report was approved; the approval covers the XML (SHA-256{" "}
        <code>{detail.mir.sha256?.slice(0, 12)}…</code>). MDARIX never submits: you send them to the national competent
        authority and record the submission here. Import the XML into the official MIR PDF if your authority asks for
        it.
      </p>
    </>
  );
}
