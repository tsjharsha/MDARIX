import { Download } from "lucide-react";
import type { ReportDetail } from "../authorityReports";

type MirDetail = Pick<ReportDetail, "mir"> & {
  form?: Pick<ReportDetail["form"], "code">;
  routes?: ReportDetail["routes"];
};

/** B8 step 17: the GB report (MHRA's GB MIR 7.2.1, MORE only) and a Northern Ireland incident (the EU form in MORE). */
const isGb = (detail: MirDetail) => detail.form?.code === "GB_MIR";
const toMore = (detail: MirDetail) => isGb(detail) || !!detail.routes?.some((route) => route.code === "MHRA_MORE_EU");

/** B8 step 8: what an EU or GB report's MIR file still needs before Send for approval (blocks, parts, schema errors). */
export function MirNeeds({ detail }: { detail: MirDetail & Pick<ReportDetail, "stage"> }) {
  const needs = [...(detail.mir?.missing ?? []), ...(detail.mir?.errors ?? [])];
  if (!detail.mir || detail.mir.snapshot || !needs.length || detail.stage === "APPROVED") return null;
  return (
    <div className="ac-muted" id="rp-mir-needs">
      <p>
        Send for approval checks the MIR file against {isGb(detail) ? "MHRA's GB schema" : "the Commission's schema"}.
        <strong>
          {needs.length} {needs.length === 1 ? "field" : "fields"} left
        </strong>
        .
      </p>
      {/* The schema's own keys stay in a fold: the count is what a reader needs first (F-M6). */}
      <details className="uw-more">
        <summary>Show {needs.length === 1 ? "it" : "them"}</summary>
        <ul>
          {needs.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}

/** B8 steps 8-11, 17: after approval, the MIR XML beside the PDF, both made at approval (no generate step). */
export function MirFiles({ detail, onXml }: { detail: MirDetail; onXml: () => void }) {
  if (!detail.mir?.snapshot) return null; // no XML before approval, nor for a report approved before B8 (its PDF)
  const sha = (
    <>
      The files were made when the report was approved; the approval covers the XML (SHA-256{" "}
      <code>{detail.mir.sha256?.slice(0, 12)}…</code>).
    </>
  );
  return (
    <>
      <button type="button" className="ac-secondary" onClick={onXml}>
        <Download size={15} aria-hidden="true" /> Download XML ({isGb(detail) ? "GB MIR 7.2.1" : "MIR 7.3.1"})
      </button>
      {toMore(detail) ? (
        <p className="ac-note">
          {sha} MDARIX never submits: upload the XML in MHRA's MORE, the only route MHRA takes, and record the
          submission here. The PDF is your record copy.
          {!isGb(detail) &&
            " Northern Ireland: which EU MIR version MORE takes is to confirm with MHRA before your first upload."}
        </p>
      ) : (
        <p className="ac-note">
          {sha} MDARIX never submits: you send them to the national competent authority and record the submission here.
          Import the XML into the official MIR PDF if your authority asks for it.
        </p>
      )}
    </>
  );
}
