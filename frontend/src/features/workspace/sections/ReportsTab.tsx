import { useState } from "react";
import { Download, FileText, Send } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Table, errorText, notFound, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { marketLabel, versionWords } from "../../../app/labels";
import { DeadlineChip, SampleDates, StateChip } from "../../../app/chips";
import { useB9Canada, useB9India, useCan, useTabParam, useWorkspace } from "../workspaceContext";
import {
  REPORTS,
  REPORT_VIEWS,
  REPORT_VIEW_NAMES,
  askNote,
  byCountry,
  deadlineDue,
  otherCountryOptions,
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
import { ComplaintNextStep } from "./ComplaintNextStep";
import { listTitle } from "./common";
import { StagePath } from "./ComplaintPage";
import { StoryPill } from "./OneStory";
import { runOfReport, useOneStory, useVisited } from "../oneStory";
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
import { STARTER_LABEL } from "../../shared/standards";
import { ApprovingDoc, ConfirmAllCodes, ThingsToGive, signatureLine } from "./ReportBody";
import { FollowUps } from "./FollowUps";
import { MirFiles, MirNeeds } from "./MirFiles";
import { PersonalAtSend, personalBody } from "./PersonalAtSend";
import { OtherReportPage, type AttachedDetail } from "./OtherCountries";

/** What MDARIX does with an authority report, said once where it matters (Release C guardrail 3). */
export const NEVER_SUBMITS =
  "MDARIX prepares each report, gets it approved and records the submission you make through the authority's own " +
  "channel: eMDR for the FDA, EUDAMED or the national authority for the EU, MHRA's portal for Great Britain, Health " +
  "Canada, and MvPI for India. MDARIX never submits to an authority.";

/** How many mandatory fields are still empty. */
const meterMissing = (detail: Pick<ReportDetail, "mandatory">) =>
  (detail.mandatory?.total ?? 0) - (detail.mandatory?.filled ?? 0);

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
  const missing = meterMissing(detail);
  // Sent back for correction: the status the chip and the path say (0.10.92, A7: "Ready for approval" beside
  // "Draft: correction required" and "Created").
  if (detail.state === "CORRECTION_REQUIRED" && detail.stage === "CREATED")
    return {
      title: detail.state_label,
      detail: missing
        ? "Give what is missing, then send it for approval again."
        : "Correct what the authority rejected, then send it for approval again.",
    };
  switch (detail.stage) {
    case "CREATED":
      // The count is said once, on the page (0.10.83, D2.7).
      return {
        title: missing ? "Give what is missing" : "Ready for approval",
        detail: "Send for approval opens when every mandatory field is filled.",
      };
    case "COMPLETE":
      return { title: "Ready for approval", detail: "Every mandatory field is filled." };
    case "APPROVAL":
      return { title: "Sent for approval", detail: "A second person approves it with their password." };
    case "APPROVED":
      return {
        title: "Approved · PDF ready",
        // "MDARIX never submits" is said once, below on the rail (0.10.87).
        detail:
          "The PDF follows the form's field order, with the approval on its last page. Then record your submission.",
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
  const all = (list.data?.items ?? []).filter((row) => !complaintId || row.complaint_id === complaintId);
  // B9b: "Other countries" and each country by name, once the list holds an Other Regulatory Report.
  const [country, setCountry] = useTabParam("country", "replace");
  const countries = otherCountryOptions(all);
  const items = byCountry(all, country ?? "");
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
        {countries.length > 0 && (
          <label className="ca-field">
            Market
            <select value={country ?? ""} onChange={(event) => setCountry(event.target.value || null)}>
              <option value="">Every market</option>
              <option value="OTHER">Other countries</option>
              {countries.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <Panel title={listTitle(view, list.data ? rows.length : undefined)} source={list}>
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
                  <span className="uw-what-text">
                    {row.form_title}
                    {row.follow_up ? ` · Follow-up #${row.follow_up}` : ""}
                  </span>
                </span>
              ),
            },
            {
              key: "status",
              label: "Status",
              // Plain text, as the complaint list's Stage (0.10.85, D3.15).
              render: (row) => row.stage_label ?? row.state_label,
            },
            {
              key: "mandatory",
              label: "Mandatory fields",
              render: (row) => {
                // B9b: no form, so no fields to count: the report is attached.
                if (row.market === "OTHER") return <span className="ac-muted">Attached report, no form</span>;
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
                  <span className="ms-chip is-starter">{STARTER_LABEL}</span>
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

/** "Record the submission" in the rail: open the folded report part that holds the form, bring it into view and put
 * the keyboard on its first field (focus stayed on the rail's button, far from the form). Exported for its test. */
export function openSubmission(part: HTMLElement | null) {
  if (!part) return;
  const folded = part.closest("details");
  if (folded) folded.open = true;
  part.scrollIntoView({ behavior: "smooth" });
  part.querySelector<HTMLElement>("select, input, textarea, button")?.focus({ preventScroll: true });
}

/** One report on its own page: highlights, the status path, the form's fields in order, and the rail. */
export function ReportPage({ id, onBack }: { id: string; onBack: () => void }) {
  const { open, isTrial } = useWorkspace();
  // The ten-step story's pill on its own report (0.10.82, D1.5); the rail's Next step is already the story's step.
  const storyRun = runOfReport(useOneStory(!!isTrial).data, id);
  const resource = useResource<ReportDetail>(`${REPORTS}/${id}`);
  // Story step 5 counts once this report has loaded (0.10.88).
  useVisited({ step: "form", reportId: resource.data?.id }, resource.state === "ready");
  const [shown, setShown] = useState<ReportDetail | null>(null);
  const canWrite = useCanReport();
  const canExport = useCan("data.export");
  const india = useB9India();
  const canada = useB9Canada();
  const detail = shown?.id === id ? shown : resource.data;
  const action = useAction((next) => setShown(next), "That step was not recorded.");
  const [pdfError, setPdfError] = useState("");
  const [personal, setPersonal] = useState<Record<string, string>>({});
  if (!detail)
    return (
      <Panel eyebrow="Report" title="Authority report" source={notFound(resource) ? undefined : resource}>
        {resource.state === "error" && (
          <Empty
            title="This report could not be opened"
            detail={errorText(resource.error, "It is not in your organization.")}
            action={
              <button type="button" className="ac-secondary" onClick={onBack}>
                All reports
              </button>
            }
          />
        )}
      </Panel>
    );
  const changed = (next: ReportDetail) => setShown(next);
  // B9b: an Other Regulatory Report has no form: its own page (attach, Report ID, status, follow-ups).
  if ((detail as unknown as Partial<AttachedDetail>).attached)
    return (
      <OtherReportPage
        detail={detail as unknown as AttachedDetail}
        onBack={onBack}
        onChanged={(next) => setShown(next as unknown as ReportDetail)}
      />
    );
  const mandatory = detail.mandatory ?? { total: 0, filled: 0, missing: [] };
  const meter = meterText(mandatory);
  const missing = mandatory.total - mandatory.filled;
  const next = reportNext(detail);
  // A report sent back for correction, every mandatory field filled, is sent for approval again (0.10.92, A7: its
  // path stays at the first stage, which kept the button shut).
  const resend = detail.state === "CORRECTION_REQUIRED" && detail.stage === "CREATED" && !meterMissing(detail);
  const due = deadlineDue(detail.deadline, detail.state);
  const ref = detail.complaint.ref;
  // A follow-up's files say which one they are: "...-RV-09-follow-up-2.xml" (0.10.96, B3).
  const stem = detail.follow_up ? `${ref}-follow-up-${detail.follow_up}` : ref;
  const approved = detail.approved_snapshot;
  const openReport = (other: string) => open(reportPlace(other).section, reportPlace(other).tab);
  const origin =
    detail.state === "CANCELLED"
      ? `Cancelled: ${detail.cancelled_reason ?? "a later signed conclusion says not reportable"}`
      : detail.follow_up
        ? `Follow-up #${detail.follow_up} of its initial report (21 CFR 803.56).`
        : detail.assessment?.conclusion === "REPORTABLE"
          ? `Created when the ${detail.market_label} conclusion was signed reportable${
              detail.assessment.report_type_label
                ? `: ${detail.assessment.report_type_label[0].toLowerCase()}${detail.assessment.report_type_label.slice(1)}`
                : ""
            }.`
          : "Started while the market was still being assessed.";
  const fetchFile = async (path: string, name: string, failed: string, query = "") => {
    setPdfError("");
    try {
      await downloadFile(`${REPORTS}/${detail.id}/${path}?snapshot=${approved!.id}${query}`, { fallbackName: name });
    } catch (reason) {
      setPdfError(errorText(reason, failed));
    }
  };
  const pdf = () =>
    fetchFile(
      "worksheet.pdf",
      `mdarix-${detail.form.code.toLowerCase()}-${stem}.pdf`,
      "The PDF could not be downloaded.",
    );
  // 0.10.96 (A6): FDA's own fillable form, the second US PDF.
  const official = () =>
    fetchFile(
      "worksheet.pdf",
      `mdarix-fda-3500a-${stem}-official-form.pdf`,
      "The official form could not be downloaded.",
      "&form=official",
    );
  // A US report also as FDA's eMDR file: the blocks it still needs, by their names ("H6 Component code").
  const emdrNeeds = (detail.emdr?.missing ?? []).map((item) => item.split(":")[0]);
  const write = canWrite && detail.state !== "CANCELLED";
  const approving = canWrite && detail.stage === "APPROVAL" && !!detail.approval?.may_approve;
  const approvedBy =
    detail.stage === "APPROVED"
      ? (detail.signatures ?? []).find((item) => /^(approved|practice)/.test(item.meaning))
      : undefined;
  return (
    <div className="uw-cp uw-report-page">
      <div className="uw-topline">
        <nav className="uw-crumbs" aria-label="Where you are">
          <button type="button" className="ac-link" onClick={onBack}>
            Reports
          </button>
          <span aria-hidden="true">›</span>
          <span>
            {detail.form.title} · {ref}
          </span>
        </nav>
        {storyRun && <StoryPill run={storyRun} />}
      </div>
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
            {/* The count of what is missing is the "things to give" head while any is (0.10.87). */}
            {meter.share === 100 && <span className="ms-chip">{meter.text} fields</span>}
            {detail.follow_up ? (
              <span className="ms-chip">Follow-up #{detail.follow_up}</span>
            ) : (
              detail.form.report_kind && <span className="ms-chip">{detail.form.report_kind} report</span>
            )}
            {detail.form.starter && <span className="ms-chip is-starter">{STARTER_LABEL}</span>}
            {(detail.state === "CORRECTION_REQUIRED" || detail.state === "CANCELLED") && (
              <StateChip label={detail.state_label} />
            )}
          </div>
        </div>
        <dl className="uw-hl-fields">
          {/* The market is the eyebrow and the due day the chip (0.10.87). */}
          <div>
            <dt>Form</dt>
            <dd>{versionWords(detail.form.version)}</dd>
          </div>
          <div>
            <dt>Prepared by</dt>
            <dd>{detail.preparers?.join(", ") || "—"}</dd>
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
          {/* 0.10.96 (A7): every suggested code confirmed in one click, over the list of what to give. */}
          {/* 0.10.96 (B3): a submitted US report's chain and "Start follow-up #n"; on a follow-up, what it sends. */}
          <FollowUps detail={detail} canWrite={write} onChanged={changed} onOpen={openReport} />
          {write && <ConfirmAllCodes detail={detail} onChanged={changed} />}
          {write && <ThingsToGive detail={detail} onChanged={changed} canEdit={write} />}
          {/* 0.10.83 (D2.8): the approver reads what they approve, then approves below it. */}
          {approving && (
            <>
              <ApprovingDoc detail={detail} />
              <section className="uw-card uw-card-pad" aria-label="Approve">
                <Approval detail={detail} onChanged={changed} />
              </section>
            </>
          )}
          <details
            className="uw-card uw-rec-main rp-fold"
            open={!approving && (!missing || !write)}
            hidden={approving}
            aria-label="The form's fields"
          >
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
                <section className="uw-rec-part" id="rp-acknowledgement" aria-label="Record the acknowledgement">
                  <h2>Record the acknowledgement</h2>
                  <RecordEvidence detail={detail} attempt={detail.submissions[0]} onChanged={changed} />
                </section>
              )}
              {write && detail.stage === "ACKNOWLEDGED" && detail.state !== "COMPLETE" && (
                <section className="uw-rec-part" aria-label="After acknowledgement">
                  <h2>After acknowledgement</h2>
                  <AfterAcceptance detail={detail} onChanged={changed} onOpen={openReport} />
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
                {/* A starter form's chip says it is a starter (0.10.87). */}
                {!detail.form.starter && detail.starter_mark ? `${detail.starter_mark} ` : ""}Field order:{" "}
                {detail.form.source_document}.
              </p>
            </div>
          </details>
        </div>
        <aside className="uw-rail" aria-label="What to do next">
          <section className="uw-card uw-card-pad uw-rail-next">
            <h2>Next step</h2>
            <b>{next.title}</b>
            <p className="ac-muted">{next.detail}</p>
            {detail.emdr && emdrNeeds.length > 0 && (
              <p className="ac-muted" id="rp-emdr-needs">
                The eMDR XML also needs: {emdrNeeds.join("; ")}.
              </p>
            )}
            <MirNeeds detail={detail} />
            {write && detail.stage === "CREATED" && !resend && (
              <>
                <button type="button" className="ac-secondary" disabled aria-describedby="rp-why-send">
                  <Send size={15} aria-hidden="true" /> Send for approval
                </button>
                <p className="sr-only" id="rp-why-send">
                  Send for approval opens when every mandatory field is filled.
                </p>
              </>
            )}
            {write && (detail.stage === "COMPLETE" || resend) && (
              <>
                <p className="ac-muted">{askNote(detail.approval)}</p>
                <PersonalAtSend detail={detail} values={personal} onChange={setPersonal} />
                <button
                  type="button"
                  className="ac-primary"
                  disabled={action.busy}
                  onClick={() =>
                    void action
                      .run(`${REPORTS}/${detail.id}/snapshots`, "POST", personalBody(personal))
                      .then((ok) => ok && setPersonal({}))
                  }
                >
                  <Send size={15} aria-hidden="true" /> Send for approval
                </button>
              </>
            )}
            {canWrite &&
              detail.stage === "APPROVAL" &&
              (approving ? (
                <p className="ac-muted">Read every value under “What you are approving”, then approve below it.</p>
              ) : (
                <Approval detail={detail} onChanged={changed} />
              ))}
            {approvedBy && (
              <p className="dt-success">
                ✓ {signatureLine(approvedBy)}
                <SampleDates sample={detail.sample} />
              </p>
            )}
            {detail.stage === "APPROVED" && approved && (
              <>
                {canExport ? (
                  <>
                    {/* 0.10.96 (A8): the files are ready at approval, no generate step. */}
                    <button type="button" className="ac-primary" onClick={() => void pdf()}>
                      <FileText size={15} aria-hidden="true" /> Download PDF
                    </button>
                    {detail.emdr && (
                      <>
                        <button
                          type="button"
                          className="ac-secondary"
                          disabled={emdrNeeds.length > 0}
                          aria-describedby={emdrNeeds.length ? "rp-emdr-needs" : undefined}
                          onClick={() =>
                            void fetchFile(
                              "emdr.xml",
                              `mdarix-emdr-${stem}.xml`,
                              "The eMDR XML could not be downloaded.",
                            )
                          }
                        >
                          <Download size={15} aria-hidden="true" /> Download XML
                        </button>
                        <button type="button" className="ac-secondary" onClick={() => void official()}>
                          <FileText size={15} aria-hidden="true" /> Official Form 3500A (PDF)
                        </button>
                        <p className="ac-note">
                          The files were made when the report was approved. MDARIX never submits: you send the XML
                          through your own ESG account or eSubmitter and record the submission here.
                        </p>
                      </>
                    )}
                    <MirFiles
                      detail={detail}
                      onXml={() =>
                        void fetchFile("mir.xml", `mdarix-mir-${stem}.xml`, "The MIR XML could not be downloaded.")
                      }
                    />
                    {/* B9 step 10: Health Canada's own form, once its form file is in place (needed from the owner). */}
                    {canada && detail.canada_chain?.official_form && (
                      <button
                        type="button"
                        className="ac-secondary"
                        onClick={() =>
                          void fetchFile(
                            "worksheet.pdf",
                            `mdarix-hc-mdpr-${stem}-official-form.pdf`,
                            "The official form could not be downloaded.",
                            "&form=official",
                          )
                        }
                      >
                        <FileText size={15} aria-hidden="true" /> Official form HC Pub. 110180 (PDF)
                      </button>
                    )}
                    {/* B9 steps 12-13: India's official MvPI form and the ADRMS entry sheet, from the same snapshot. */}
                    {india && detail.form.code === "MVPI_MDAE" && (
                      <>
                        <button
                          type="button"
                          className="ac-secondary"
                          onClick={() =>
                            void fetchFile(
                              "worksheet.pdf",
                              `mdarix-mvpi-mdae-${stem}-official-form.pdf`,
                              "The official form could not be downloaded.",
                              "&form=official",
                            )
                          }
                        >
                          <FileText size={15} aria-hidden="true" /> Official MvPI form v1.2 (PDF)
                        </button>
                        <button
                          type="button"
                          className="ac-secondary"
                          onClick={() =>
                            void fetchFile(
                              "worksheet.pdf",
                              `mdarix-mvpi-mdae-${stem}-adrms-entry-sheet.pdf`,
                              "The ADRMS entry sheet could not be downloaded.",
                              "&form=adrms",
                            )
                          }
                        >
                          <FileText size={15} aria-hidden="true" /> ADRMS entry sheet (PDF)
                        </button>
                        <p className="ac-note">
                          MDARIX never submits: e-mail the official form to MvPI, or type the sheet's values into ADRMS
                          in its screen order, then record the submission here.
                        </p>
                      </>
                    )}
                  </>
                ) : (
                  <p className="ac-muted">A colleague with export rights downloads the files.</p>
                )}
                {write && (
                  <button
                    type="button"
                    className="ac-secondary"
                    onClick={() => openSubmission(document.getElementById("rp-submission"))}
                  >
                    Record the submission
                  </button>
                )}
              </>
            )}
            {write && detail.stage === "SUBMITTED" && detail.submissions[0] && (
              <button
                type="button"
                className="ac-secondary"
                onClick={() => openSubmission(document.getElementById("rp-acknowledgement"))}
              >
                Record the acknowledgement
              </button>
            )}
            {!canWrite && detail.stage !== "APPROVED" && detail.state !== "CANCELLED" && (
              <p className="ac-muted">You can read this report; a Regulatory Leader or Quality Leader works on it.</p>
            )}
            <InlineError text={action.error || pdfError} />
            {/* B6a navigation review: once nothing more is owed here, the complaint's own next step (as the drawer). */}
            {(detail.state === "COMPLETE" || detail.state === "CANCELLED") && (
              <ComplaintNextStep complaintId={detail.complaint.id} here="Reports" refreshKey={detail.state} />
            )}
          </section>
          <section className="uw-card uw-card-pad uw-rail-signs" aria-label="Who signs">
            <h2>Who signs</h2>
            <ul className="rp-signatures">
              {(detail.signatures ?? []).map((item) => (
                <li key={`${item.meaning}-${item.at}`}>
                  {signatureLine(item)}
                  <SampleDates sample={detail.sample} />
                </li>
              ))}
            </ul>
            <ul className="uw-rail-signers">
              {!detail.signatures?.length &&
                (detail.preparers ?? []).map((person) => (
                  <li key={`p-${person}`} className="ms-chip">
                    Prepared: {person}
                  </li>
                ))}
              {approved?.approved_by
                ? !detail.signatures?.length && <li className="ms-chip">Approved: {approved.approved_by}</li>
                : (detail.approval?.approvers ?? []).map((person) => (
                    <li key={`a-${person}`} className="ms-chip">
                      May approve: {person}
                    </li>
                  ))}
            </ul>
            <p className="ac-note">Never the person who prepared it, nor the signer of the conclusion behind it.</p>
            <p className="uw-never-submits">{NEVER_SUBMITS}</p>
          </section>
        </aside>
      </div>
    </div>
  );
}
