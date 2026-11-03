import { useState } from "react";
import { FileText, Send } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { Table, errorText, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { marketLabel, versionWords } from "../../../app/labels";
import { DeadlineChip, StateChip } from "../../../app/chips";
import { useCan, useTabParam, useWorkspace } from "../workspaceContext";
import {
  REPORTS,
  REPORT_VIEWS,
  REPORT_VIEW_NAMES,
  askNote,
  deadlineDue,
  deadlineText,
  reportPlace,
  reportsInView,
  type Mandatory,
  type ReportDetail,
  type ReportList,
  type ReportListItem,
  type ReportView,
} from "../authorityReports";
import { InlineError } from "./boardParts";
import { listTitle } from "./common";
import { StagePath } from "./ComplaintPage";
import {
  AfterAcceptance,
  Approval,
  FieldRow,
  RecordEvidence,
  RecordSubmission,
  SubmissionRecord,
  useAction,
  useCanReport,
} from "./Reports";
import { ListViewPicker } from "./Views";
import { ThingsToGive } from "./ReportBody";

/** What MDARIX does with an authority report, said once where it matters (Release C guardrail 3). */
export const NEVER_SUBMITS =
  "MDARIX prepares each report, gets it approved and records the submission you make through the authority's own " +
  "channel: eMDR for the FDA, EUDAMED or the national authority for the EU, MHRA's portal for Great Britain, Health " +
  "Canada, and MvPI for India. MDARIX never submits to an authority.";

/** "18 of 24 mandatory": the meter's words, and its share filled. */
export function meterText(mandatory: Mandatory | undefined): { text: string; share: number } {
  const total = mandatory?.total ?? 0;
  const filled = mandatory?.filled ?? 0;
  return { text: `${filled} of ${total} mandatory`, share: total ? Math.round((100 * filled) / total) : 0 };
}

/** The one main thing to do next on a report, by its place on the status path (the approved design's rail). */
export function reportNext(detail: Pick<ReportDetail, "stage" | "state" | "mandatory" | "state_label">): {
  title: string;
  detail: string;
} {
  const missing = (detail.mandatory?.total ?? 0) - (detail.mandatory?.filled ?? 0);
  const correction = detail.state === "CORRECTION_REQUIRED" ? " A correction is required after a rejection." : "";
  switch (detail.stage) {
    case "CREATED":
      // The count is said once, on the page (0.10.83, D2.7).
      return {
        title: missing ? "Give what is missing" : "Ready for approval",
        detail: `Send for approval opens when every mandatory field is filled.${correction}`,
      };
    case "COMPLETE":
      return { title: "Ready for approval", detail: `Every mandatory field is filled.${correction}` };
    case "APPROVAL":
      return { title: "Sent for approval", detail: "A second person approves it with their password." };
    case "APPROVED":
      return {
        title: "Approved · PDF ready",
        detail:
          "The PDF follows the form's field order, with the approval on its last page. Submit it through the authority's channel, then record the submission.",
      };
    case "SUBMITTED":
      return {
        title: "Submitted by you",
        detail: "Waiting for the authority's acknowledgement. Record it when it arrives.",
      };
    case "ACKNOWLEDGED":
      return { title: "Acknowledged", detail: "Complete it, or record a follow-up or a request for information." };
    default:
      return { title: detail.state_label, detail: "Nothing more is owed for this report." };
  }
}

/**
 * Reports (0.10.75, Release C part C3): authority reports as records. The list has three list views (open, waiting for
 * my approval, submitted this month) with six columns and cards on a phone; a report opens on its own page in the
 * record page's shape (highlights, the status path, the form's fields, and the rail of what to do next). Its address:
 * /app/reports?view=<view>, /app/reports?report=<id>.
 */
export function ReportsSection({ complaintId }: { complaintId?: string | null } = {}) {
  const [reportId, setReport] = useTabParam("report");
  return reportId ? (
    <ReportPage id={reportId} onBack={() => setReport(null)} />
  ) : (
    <ReportListView onOpen={(id) => setReport(id)} complaintId={complaintId} />
  );
}

const EMPTY: Record<ReportView, { title: string; detail: string }> = {
  "Open reports": {
    title: "No report is owed",
    detail: "A report is created when a person signs a US or India conclusion as reportable.",
  },
  "Waiting for my approval": {
    title: "Nothing waits for your approval",
    detail: "A report sent for approval by a colleague comes here and to your Home.",
  },
  "Submitted this month": {
    title: "Nothing submitted this month",
    detail: "A report is listed here once you record its submission.",
  },
};

function ReportListView({ onOpen, complaintId }: { onOpen: (id: string) => void; complaintId?: string | null }) {
  const { open } = useWorkspace();
  const [code, setCode] = useTabParam("view", "replace");
  const view = REPORT_VIEW_NAMES.find((name) => REPORT_VIEWS[name].code === code) ?? "Open reports";
  const list = useResource<ReportList>(REPORTS);
  // One complaint's reports when the list is opened from it (Complaints › Reporting, Authority reports).
  const items = (list.data?.items ?? []).filter((row) => !complaintId || row.complaint_id === complaintId);
  const rows = list.data ? reportsInView(items, view) : [];
  const name = (row: ReportListItem) => `${row.form_title ?? "Report"} for ${row.complaint_ref}`;
  return (
    <>
      <div className="ca-action-row uw-list-actions">
        <ListViewPicker
          mine={REPORT_VIEW_NAMES}
          active={view}
          onChange={(next) => setCode(REPORT_VIEWS[next as ReportView].code)}
          detail={REPORT_VIEWS[view].detail}
        />
      </div>
      <Panel eyebrow="Reports" title={listTitle(view, list.data ? rows.length : undefined)} source={list}>
        <Table
          caption={view}
          rows={rows}
          rowKey={(row) => String(row.id)}
          empty={{
            ...EMPTY[view],
            action: (
              <button type="button" className="ac-secondary" onClick={() => open("Decision trees")}>
                See the decision trees
              </button>
            ),
          }}
          columns={[
            {
              key: "due",
              label: "Due",
              render: (row) => {
                const due = deadlineDue(row, row.state);
                return due ? (
                  <DeadlineChip item={due} />
                ) : (
                  <span className="ac-muted">{deadlineText(row, row.state)}</span>
                );
              },
            },
            {
              key: "report",
              label: "Report",
              render: (row) => (
                <span className="uw-what">
                  <button type="button" className="ac-link" onClick={() => onOpen(String(row.id))}>
                    <strong>{row.complaint_ref}</strong>
                  </button>
                  <span className="uw-what-text">{row.form_title}</span>
                </span>
              ),
            },
            {
              key: "status",
              label: "Status",
              render: (row) => <StateChip label={row.stage_label ?? row.state_label} />,
            },
            {
              key: "mandatory",
              label: "Mandatory fields",
              render: (row) => {
                const meter = meterText(row.mandatory);
                return (
                  <span className="uw-meter-cell">
                    <span className="uw-meter" aria-hidden="true">
                      <i style={{ width: `${meter.share}%` }} />
                    </span>
                    <span>{meter.text}</span>
                  </span>
                );
              },
            },
            { key: "market", label: "Market", render: (row) => row.market_label },
            {
              key: "open",
              label: "",
              render: (row) => (
                <button
                  type="button"
                  className="ac-secondary"
                  aria-label={`Open the ${name(row)}`}
                  onClick={() => onOpen(String(row.id))}
                >
                  Open
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {list.data && (
        <section className="uw-card uw-card-pad uw-forms-card" aria-label="Forms MDARIX prepares">
          <h2>Forms MDARIX prepares</h2>
          <div className="uw-forms">
            {list.data.forms.map((form) => (
              <div key={form.market} className="uw-form-card">
                <b>{marketLabel(form.market)}</b>
                <span>{form.title.replace(/ worksheet$/, "")}</span>
                <span className="ac-muted">{versionWords(form.version)}</span>
                {form.starter ? (
                  <ToneBadge tone="neutral" label="Starter, for your consultant to confirm" />
                ) : (
                  <ToneBadge tone="good" label="In MDARIX today" />
                )}
              </div>
            ))}
          </div>
          <p className="ac-muted">{list.data.starter_mark}</p>
        </section>
      )}
    </>
  );
}

/** One report on its own page: highlights, the status path, the form's fields in order, and the rail. */
export function ReportPage({ id, onBack }: { id: string; onBack: () => void }) {
  const { open } = useWorkspace();
  const resource = useResource<ReportDetail>(`${REPORTS}/${id}`);
  const [shown, setShown] = useState<ReportDetail | null>(null);
  const canWrite = useCanReport();
  const canExport = useCan("data.export");
  const detail = shown?.id === id ? shown : resource.data;
  const action = useAction((next) => setShown(next), "That step was not recorded.");
  const [pdfError, setPdfError] = useState("");
  if (!detail)
    return (
      <Panel eyebrow="Report" title="Authority report" source={resource}>
        {resource.state === "error" && (
          <p className="ac-muted">{errorText(resource.error, "It is not in your organization.")}</p>
        )}
      </Panel>
    );
  const changed = (next: ReportDetail) => setShown(next);
  const mandatory = detail.mandatory ?? { total: 0, filled: 0, missing: [] };
  const meter = meterText(mandatory);
  const missing = mandatory.total - mandatory.filled;
  const next = reportNext(detail);
  const due = deadlineDue(detail.deadline, detail.state);
  const ref = detail.complaint.ref;
  const approved = detail.approved_snapshot;
  const origin =
    detail.state === "CANCELLED"
      ? `Cancelled: ${detail.cancelled_reason ?? "a later signed conclusion says not reportable"}`
      : detail.assessment?.conclusion === "REPORTABLE"
        ? `Created when the ${detail.market_label} conclusion was signed reportable${
            detail.assessment.report_type_label
              ? `: ${detail.assessment.report_type_label[0].toLowerCase()}${detail.assessment.report_type_label.slice(1)}`
              : ""
          }.`
        : "Started while the market was still being assessed.";
  const pdf = async () => {
    setPdfError("");
    try {
      await downloadFile(`${REPORTS}/${detail.id}/worksheet.pdf?snapshot=${approved!.id}`, {
        fallbackName: `mdarix-${detail.form.code.toLowerCase()}-${ref}.pdf`,
      });
    } catch (reason) {
      setPdfError(errorText(reason, "The PDF could not be generated."));
    }
  };
  const write = canWrite && detail.state !== "CANCELLED";
  return (
    <div className="uw-cp uw-report-page">
      <nav className="uw-crumbs" aria-label="Where you are">
        <button type="button" className="ac-link" onClick={onBack}>
          Reports
        </button>
        <span aria-hidden="true">›</span>
        <span>
          {detail.form.title} · {ref}
        </span>
      </nav>
      <header className="uw-card uw-highlights" aria-label="The report at a glance">
        <div className="uw-hl-top">
          <div className="uw-hl-title">
            <p className="ac-eyebrow">Authority report · {detail.market_label}</p>
            <h1 tabIndex={-1}>{detail.form.title}</h1>
            <p className="uw-cp-what">
              For{" "}
              <button
                type="button"
                className="ac-link uw-mono"
                onClick={() => open("Complaint", `Summary?ref=${encodeURIComponent(ref)}`)}
              >
                {ref}
              </button>
              {`. ${origin}`}
            </p>
          </div>
          <div className="uw-cp-chips">
            {due && <DeadlineChip item={due} prefix="Due" />}
            <span className="ms-chip">{meter.text} fields</span>
            {detail.form.report_kind && <span className="ms-chip">{detail.form.report_kind} report</span>}
            {detail.form.starter && <span className="ms-chip">Starter form, for your consultant to confirm</span>}
            {(detail.state === "CORRECTION_REQUIRED" || detail.state === "CANCELLED") && (
              <StateChip label={detail.state_label} />
            )}
          </div>
        </div>
        <dl className="uw-hl-fields">
          <div>
            <dt>Market</dt>
            <dd>{detail.market_label}</dd>
          </div>
          <div>
            <dt>Form</dt>
            <dd>{versionWords(detail.form.version)}</dd>
          </div>
          <div>
            <dt>Prepared by</dt>
            <dd>{detail.preparers?.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt>Due</dt>
            <dd>{deadlineText(detail.deadline, detail.state)}</dd>
          </div>
        </dl>
        {detail.stages && detail.stage && <StagePath stages={detail.stages} />}
        {detail.conclusion_changed && (
          <p className="ac-message tone-warning" role="status">
            {detail.conclusion_changed}
          </p>
        )}
      </header>
      <div className="uw-rec">
        <div className="rp-main">
          {/* 0.10.83 (D2.7): what is missing first, grouped by who knows it; the full report folds away meanwhile. */}
          {write && <ThingsToGive detail={detail} onChanged={changed} canEdit={write} />}
          <details className="uw-card uw-rec-main rp-fold" open={!missing || !write} aria-label="The form's fields">
            <summary className="uw-card-head">
              <h2>The report, in the form's order</h2>
              <span className="ac-muted">
                {missing && write ? "Show" : "Each field says where its value comes from"}
              </span>
            </summary>
            <div className="uw-rec-body">
              {write && detail.stage === "APPROVED" && (
                <section className="uw-rec-part" id="rp-submission" aria-label="Record the submission">
                  <h2>Record the submission</h2>
                  <RecordSubmission detail={detail} onChanged={changed} quiet />
                </section>
              )}
              {write && detail.stage === "SUBMITTED" && detail.submissions[0] && (
                <section className="uw-rec-part" aria-label="Record the acknowledgement">
                  <h2>Record the acknowledgement</h2>
                  <RecordEvidence detail={detail} attempt={detail.submissions[0]} onChanged={changed} />
                </section>
              )}
              {write && detail.stage === "ACKNOWLEDGED" && detail.state !== "COMPLETE" && (
                <section className="uw-rec-part" aria-label="After acknowledgement">
                  <h2>After acknowledgement</h2>
                  <AfterAcceptance
                    detail={detail}
                    onChanged={changed}
                    onOpen={(other) => open(reportPlace(other).section, reportPlace(other).tab)}
                  />
                </section>
              )}
              {detail.sections
                .filter((section) => section.fields.length)
                .map((section) => (
                  <section key={section.code} className="uw-rec-part" aria-label={section.title}>
                    <h2>{section.title}</h2>
                    {section.note && <p className="ac-muted">{section.note}</p>}
                    <ul className="uw-rp-fields">
                      {section.fields.map((item) => (
                        <FieldRow
                          key={item.id}
                          detail={detail}
                          item={item}
                          onChanged={changed}
                          canEdit={write && detail.editable}
                        />
                      ))}
                    </ul>
                  </section>
                ))}
              <SubmissionRecord detail={detail} />
              <p className="ac-note">
                {detail.starter_mark} Field order: {detail.form.source_document}.
              </p>
            </div>
          </details>
        </div>
        <aside className="uw-rail" aria-label="What to do next">
          <section className="uw-card uw-card-pad uw-rail-next">
            <h2>Next step</h2>
            <b>{next.title}</b>
            <p className="ac-muted">{next.detail}</p>
            {write && detail.stage === "CREATED" && (
              <>
                <button type="button" className="ac-secondary" disabled aria-describedby="rp-why-send">
                  <Send size={15} aria-hidden="true" /> Send for approval
                </button>
                <p className="sr-only" id="rp-why-send">
                  Send for approval opens when every mandatory field is filled.
                </p>
              </>
            )}
            {write && detail.stage === "COMPLETE" && (
              <>
                <p className="ac-muted">{askNote(detail.approval)}</p>
                <button
                  type="button"
                  className="ac-primary"
                  disabled={action.busy}
                  onClick={() => void action.run(`${REPORTS}/${detail.id}/snapshots`, "POST")}
                >
                  <Send size={15} aria-hidden="true" /> Send for approval
                </button>
              </>
            )}
            {canWrite && detail.stage === "APPROVAL" && <Approval detail={detail} onChanged={changed} />}
            {detail.stage === "APPROVED" && approved && (
              <>
                {canExport ? (
                  <button type="button" className="ac-primary" onClick={() => void pdf()}>
                    <FileText size={15} aria-hidden="true" /> Generate the PDF
                  </button>
                ) : (
                  <p className="ac-muted">A colleague with export rights generates the PDF.</p>
                )}
                {write && (
                  <button
                    type="button"
                    className="ac-secondary"
                    onClick={() => document.getElementById("rp-submission")?.scrollIntoView({ behavior: "smooth" })}
                  >
                    Record the submission
                  </button>
                )}
              </>
            )}
            {!canWrite && detail.stage !== "APPROVED" && detail.state !== "CANCELLED" && (
              <p className="ac-muted">You can read this report; a Regulatory Leader or Quality Leader works on it.</p>
            )}
            <InlineError text={action.error || pdfError} />
          </section>
          <section className="uw-card uw-card-pad uw-rail-signs" aria-label="Who signs">
            <h2>Who signs</h2>
            <ul className="uw-rail-signers">
              {(detail.preparers ?? []).map((person) => (
                <li key={`p-${person}`} className="ms-chip">
                  Prepared: {person}
                </li>
              ))}
              {approved?.approved_by ? (
                <li className="ms-chip">Approved: {approved.approved_by}</li>
              ) : (
                (detail.approval?.approvers ?? []).map((person) => (
                  <li key={`a-${person}`} className="ms-chip">
                    May approve: {person}
                  </li>
                ))
              )}
            </ul>
            <p className="ac-note">Never the person who prepared it, nor the signer of the conclusion behind it.</p>
            <p className="uw-never-submits">{NEVER_SUBMITS}</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
