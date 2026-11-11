import { useState } from "react";
import { ChevronRight, FileText, Globe2, PenLine } from "lucide-react";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { formatDay } from "../../../app/dates";
import { DeadlineChip } from "../../../app/chips";
import { useWorkspace } from "../workspaceContext";
import {
  OUTCOME_LABELS,
  REASON_MIN,
  REPORTS,
  deadlineDue,
  fileIn,
  nowLocal,
  reportPlace,
  type DeadlineFields,
  type Evidence,
  type FileIn,
  type ObligationState,
} from "../authorityReports";
import {
  CONCLUSION_LABELS,
  assessmentPath,
  type AssessmentDetail,
  type Market,
  type OtherCountryItem,
  type Suggestion,
} from "../marketAssessment";
import { useCanReport } from "./Reports";
import { InlineError } from "./boardParts";
import { STARTER_LABEL } from "../../shared/standards";

// B9b (OC spec, approved 9 Nov 2026): a country outside the five built-in markets. The person picks the country on the
// Decision trees page, answers the generic starter questions and signs; Reportable creates the "Other Regulatory
// Report", which has no form: the customer attaches the report they made, its Report ID and status, and signs that it
// was submitted (password and authenticator code; no second person, OC-D3). MDARIX never submits. Flat (G-2).

/** GET /api/v1/other-countries (reportability/other_countries.py). */
export type OtherCountries = {
  countries: { code: string; name: string }[];
  not_offered: { code: string; name: string; market: string | null; message: string }[];
  generic_note: string;
  starter_mark: string;
};

/** The picker's countries: those not yet assessed on this complaint. */
export function pickableFor(all: OtherCountries["countries"], detail: Pick<AssessmentDetail, "other_countries">) {
  const taken = new Set((detail.other_countries ?? []).map((item) => item.country));
  return all.filter((item) => !taken.has(item.code));
}

/** The "+ Other country" card: pick a country this tree covers and start its assessment (an empty draft). */
export function OtherCountryPicker({
  detail,
  onStarted,
}: {
  detail: AssessmentDetail;
  onStarted: (key: string) => void;
}) {
  const canDecide = useCanReport();
  const list = useResource<OtherCountries>("/api/v1/other-countries");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const countries = list.data ? pickableFor(list.data.countries, detail) : [];
  const start = async () => {
    setBusy(true);
    setError("");
    try {
      await send(assessmentPath(detail.complaint.id, `OTHER-${code}` as Market), "PUT", { answers: {} });
      onStarted(`OTHER-${code}`);
    } catch (reason) {
      setError(errorText(reason, "The country's assessment was not started."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="uw-card uw-card-pad dt-other" aria-label="Other country">
      <h2>
        <Globe2 size={18} aria-hidden="true" /> A country outside the five built-in markets
      </h2>
      <p className="ac-muted">
        For a country such as Australia, Switzerland or Japan: answer the generic questions and sign the conclusion.
        Reportable creates an Other Regulatory Report, where you attach the report you made in the authority's own
        route. MDARIX never submits.
      </p>
      {list.data && (
        <p className="dt-hint" role="note">
          {list.data.generic_note} <span className="dt-tag is-starter">{STARTER_LABEL}</span>
        </p>
      )}
      {list.state === "error" && <InlineError text={errorText(list.error, "The countries could not be read.")} />}
      {canDecide ? (
        <form
          className="dt-pick"
          onSubmit={(event) => {
            event.preventDefault();
            if (code && !busy) void start();
          }}
        >
          <label>
            <span>Country</span>
            <select value={code} onChange={(event) => setCode(event.target.value)}>
              <option value="">Choose a country</option>
              {countries.map((item) => (
                <option key={item.code} value={item.code}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="ac-primary" disabled={!code || busy}>
            {busy ? "Starting…" : "Assess this country"}
          </button>
        </form>
      ) : (
        <p className="ac-muted">Your role reads the assessments. A Regulatory Leader or Quality Leader starts one.</p>
      )}
      {list.data && list.data.not_offered.length > 0 && (
        <details className="dt-rule">
          <summary>Not in this list</summary>
          <p>
            EU and EEA countries, Great Britain and Northern Ireland, the US, Canada and India have their own trees.
          </p>
          <ul>
            {list.data.not_offered.map((item) => (
              <li key={item.code}>
                {item.name}: {item.message}
              </li>
            ))}
          </ul>
        </details>
      )}
      <InlineError text={error} />
    </section>
  );
}

/** The rail's report card for a country: what Reportable creates, and the report once it exists. */
export function OtherReportCard({
  country,
  outcome,
  signed,
}: {
  country: OtherCountryItem;
  outcome: Suggestion | null;
  signed: boolean;
}) {
  const { open } = useWorkspace();
  if (!outcome) return null;
  const report = signed ? country.report : null;
  return (
    <section className="uw-card uw-card-pad dt-form" aria-label="The report">
      <h2>The report for {country.country_name}</h2>
      {outcome === "NOT_REPORTABLE" ? (
        <p className="ac-muted">No report for {country.country_name}.</p>
      ) : (
        <>
          <p className="dt-form-name">
            <b>Other Regulatory Report</b> <span className="ac-muted">· attached, no form in MDARIX</span>
          </p>
          {report ? (
            <button
              type="button"
              className="ac-primary"
              onClick={() => open(reportPlace(report.id).section, reportPlace(report.id).tab)}
            >
              Open the report ({report.state_label.toLowerCase()}) <ChevronRight size={15} aria-hidden="true" />
            </button>
          ) : (
            <p className="ac-muted">
              Created when you sign {CONCLUSION_LABELS.REPORTABLE.toLowerCase()}: attach the report you made, its Report
              ID and its status there.
            </p>
          )}
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------------------------------- the report's own page

export type AttachedSubmission = {
  id: string;
  attempt: number;
  submitted_at: string;
  report_id: string;
  report_id_pending: boolean;
  result: "PENDING" | "ACCEPTED" | "REJECTED" | "NO_ACK_EXPECTED";
  late: boolean;
  note: string | null;
  recorded_by: string;
  recorded_at: string | null;
  signature_id: string | null;
  evidence: Evidence[];
};

/** GET /api/v1/reports/{id} for an Other Regulatory Report (authority_reports/attached.py ``detail``). */
export type AttachedDetail = DeadlineFields & {
  id: string;
  kind: "INITIAL" | "RESPONSE";
  attached: true;
  follow_up: boolean;
  market: "OTHER";
  country: string;
  country_name: string;
  market_label: string;
  form_title: string;
  banner: string;
  never_submits: string;
  generic_note: string;
  complaint: { id: string; ref: string | null };
  state: ObligationState;
  state_label: string;
  note: string | null;
  due_source: "WINDOW" | "CUSTOMER" | null;
  due_source_label: string | null;
  submissions: AttachedSubmission[];
  evidence_kinds: Record<string, string[]>;
  evidence_labels: Record<string, string>;
  route_label: string;
  parent: { id: string; state_label: string } | null;
  follow_ups: { id: string; number: number; state: ObligationState; state_label: string; due_on: string | null }[];
  can: {
    submit: boolean;
    acknowledge: boolean;
    enter_report_id: boolean;
    set_due_date: boolean;
    follow_up: boolean;
    close: boolean;
  };
};

export type SubmittedForm = {
  submittedAt: string;
  reportId: string;
  notIssued: boolean;
  password: string;
  code: string;
  note: string;
};

/** Why "Submitted" cannot be recorded yet, or null (the server checks it all again, and the signature). */
export function submittedProblem(form: SubmittedForm, hasFile: boolean, now: Date = new Date()): string | null {
  if (!hasFile) return "Attach the report you submitted";
  if (!form.submittedAt) return "Give when it was submitted";
  if (new Date(form.submittedAt) > now) return "The submission time cannot be in the future";
  if (!form.reportId.trim() && !form.notIssued) return "Enter the Report ID, or mark it not issued yet";
  if (!form.password) return "Enter your password to sign";
  return null;
}

export const submittedBody = (form: SubmittedForm, file: FileIn) => ({
  submitted_at: new Date(form.submittedAt).toISOString(),
  report_id: form.notIssued ? "" : form.reportId.trim(),
  not_issued_yet: form.notIssued,
  file,
  note: form.note,
  password: form.password,
  mfa_code: form.code || null,
});

/** An Other Regulatory Report on its own page: the banner, the status and due date, every submission with its files
 * and signature, the acknowledgement, the follow-ups, and Close. */
export function OtherReportPage({
  detail,
  onBack,
  onChanged,
}: {
  detail: AttachedDetail;
  onBack: () => void;
  onChanged: (next: AttachedDetail) => void;
}) {
  const { open } = useWorkspace();
  const canWrite = useCanReport();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path: string, method: "POST" | "PUT", body: unknown, failed: string) => {
    setBusy(true);
    setError("");
    try {
      onChanged(await send<AttachedDetail>(path, method, body));
      return true;
    } catch (reason) {
      setError(errorText(reason, failed));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const openReport = (id: string) => open(reportPlace(id).section, reportPlace(id).tab);
  const due = deadlineDue(detail, detail.state);
  const ref = detail.complaint.ref ?? "this complaint";
  const title = detail.follow_up ? `Follow-up report · ${detail.country_name}` : `Other Regulatory Report`;
  const action = { busy, run };
  return (
    <div className="uw-cp uw-report-page">
      <div className="uw-topline">
        <nav className="uw-crumbs" aria-label="Where you are">
          <button type="button" className="ac-link" onClick={onBack}>
            Reports
          </button>
          <span aria-hidden="true">›</span>
          <span>
            {title} · {ref}
          </span>
        </nav>
      </div>
      <header className="uw-card uw-highlights" aria-label="The report at a glance">
        <div className="uw-hl-top">
          <div className="uw-hl-title">
            <p className="ac-eyebrow">Authority report · {detail.market_label}</p>
            <h1 tabIndex={-1}>{title}</h1>
            <p className="uw-cp-what">
              For{" "}
              <button
                type="button"
                className="ac-link uw-mono"
                onClick={() => open("Complaint", `Summary?ref=${encodeURIComponent(ref)}`)}
              >
                {ref}
              </button>
              {detail.parent && (
                <>
                  {" · follow-up of "}
                  <button type="button" className="ac-link" onClick={() => openReport(detail.parent!.id)}>
                    the first report ({detail.parent.state_label.toLowerCase()})
                  </button>
                </>
              )}
            </p>
          </div>
          <div className="uw-cp-chips">
            <span className="ms-chip">{detail.state_label}</span>
            {due && <DeadlineChip item={due} prefix="Due" />}
          </div>
        </div>
        <dl className="uw-hl-fields">
          <div>
            <dt>Due date</dt>
            <dd>
              {detail.due_on ? formatDay(detail.due_on) : "Not set yet"}
              {detail.due_source_label ? ` · ${detail.due_source_label}` : ""}
            </dd>
          </div>
          <div>
            <dt>Route</dt>
            <dd>{detail.route_label}</dd>
          </div>
        </dl>
        <p className="ac-message tone-neutral" role="note">
          {detail.banner}. {detail.never_submits}
        </p>
        {detail.note && <p className="ac-muted">{detail.note}</p>}
      </header>
      <div className="uw-rec">
        <div className="rp-main">
          {canWrite && detail.can.set_due_date && <DueDateForm detail={detail} action={action} />}
          {canWrite && detail.can.submit && <SubmittedForm detail={detail} action={action} />}
          <Submissions detail={detail} canWrite={canWrite} action={action} />
          {(detail.follow_ups.length > 0 || (canWrite && detail.can.follow_up)) && (
            <FollowUpsPart detail={detail} canWrite={canWrite} action={action} onOpen={openReport} />
          )}
          {canWrite && detail.can.close && <CloseForm detail={detail} action={action} />}
          {!canWrite && <p className="ac-muted">You can read this report; a Regulatory Leader works on it.</p>}
          <InlineError text={error} />
        </div>
        <aside className="uw-rail" aria-label="About this report">
          <section className="uw-card uw-card-pad">
            <h2>No form in MDARIX</h2>
            <p className="ac-muted">
              You prepare the report in the authority's own format and route. Here you keep the copy you sent, its
              Report ID, the authority's acknowledgement and any follow-ups. Every file is scanned and kept; a new file
              never replaces an earlier one.
            </p>
            <p className="ac-note">{detail.generic_note}</p>
          </section>
        </aside>
      </div>
    </div>
  );
}

type Action = {
  busy: boolean;
  run: (path: string, method: "POST" | "PUT", body: unknown, failed: string) => Promise<boolean>;
};

function DueDateForm({ detail, action }: { detail: AttachedDetail; action: Action }) {
  const [day, setDay] = useState(detail.due_on ?? "");
  const [reason, setReason] = useState("");
  const ready = !!day && reason.trim().length >= REASON_MIN && !action.busy;
  return (
    <form
      className="uw-card uw-card-pad ca-form"
      aria-label="The due date"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready)
          void action.run(
            `${REPORTS}/${detail.id}/attached-due-date`,
            "PUT",
            { due_on: day, reason },
            "The due date was not saved.",
          );
      }}
    >
      <h2>The due date</h2>
      <p className="ac-muted">
        No reporting window names {detail.country_name}: enter the date your procedure gives. It is shown as “Due date
        entered by the customer” and counted in Overdue and Due this week.
      </p>
      <div className="ca-form-grid">
        <label className="ca-field">
          Due date
          <input type="date" value={day} onChange={(event) => setDay(event.target.value)} />
        </label>
        <label className="ca-field">
          Where the date comes from (required)
          <input value={reason} maxLength={2000} onChange={(event) => setReason(event.target.value)} />
        </label>
      </div>
      <button type="submit" className="ac-secondary" disabled={!ready}>
        Save the due date
      </button>
    </form>
  );
}

function SubmittedForm({ detail, action }: { detail: AttachedDetail; action: Action }) {
  const [form, setForm] = useState<SubmittedForm>({
    submittedAt: nowLocal(),
    reportId: "",
    notIssued: false,
    password: "",
    code: "",
    note: "",
  });
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const problem = submittedProblem(form, !!file);
  const record = async () => {
    setFileError("");
    let content: FileIn;
    try {
      content = await fileIn(file!);
    } catch (reason) {
      setFileError(errorText(reason, "The file cannot be attached."));
      return;
    }
    const done = await action.run(
      `${REPORTS}/${detail.id}/attached-submission`,
      "POST",
      submittedBody(form, content),
      "The submission was not recorded.",
    );
    if (done) setForm({ ...form, password: "", code: "" });
  };
  return (
    <form
      className="uw-card uw-card-pad ca-form"
      aria-label="Record that it was submitted"
      onSubmit={(event) => {
        event.preventDefault();
        if (!problem && !action.busy) void record();
      }}
    >
      <h2>
        <PenLine size={16} aria-hidden="true" /> Record that it was submitted
      </h2>
      <div className="ca-form-grid">
        <label className="ca-field">
          The report you submitted (scanned; at most 2 MB)
          <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <label className="ca-field">
          Submitted on
          <input
            type="datetime-local"
            value={form.submittedAt}
            max={nowLocal()}
            onChange={(event) => setForm({ ...form, submittedAt: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Report ID from the authority
          <input
            value={form.reportId}
            maxLength={120}
            disabled={form.notIssued}
            onChange={(event) => setForm({ ...form, reportId: event.target.value })}
          />
        </label>
        <label className="ca-check">
          <input
            type="checkbox"
            checked={form.notIssued}
            onChange={(event) => setForm({ ...form, notIssued: event.target.checked })}
          />
          Not issued yet (enter it here once the authority gives it)
        </label>
        <label className="ca-field">
          Note (optional)
          <input
            value={form.note}
            maxLength={2000}
            onChange={(event) => setForm({ ...form, note: event.target.value })}
          />
        </label>
      </div>
      <p className="ac-muted">
        You sign: “I recorded that this report was submitted to the authority of {detail.country_name} on the date
        given, as attached.” The file's SHA-256 is part of what you sign. No second person approves it.
      </p>
      <div className="ca-form-grid">
        <label className="ca-field">
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value })}
          />
        </label>
      </div>
      {problem && <p className="uw-hint">{problem}</p>}
      <button type="submit" className="ac-primary" disabled={!!problem || action.busy}>
        {action.busy ? "Signing…" : "Sign: submitted"}
      </button>
      <InlineError text={fileError} />
    </form>
  );
}

function Submissions({ detail, canWrite, action }: { detail: AttachedDetail; canWrite: boolean; action: Action }) {
  if (!detail.submissions.length) return null;
  const file = (submission: AttachedSubmission, evidence: Evidence) =>
    void downloadFile(`${REPORTS}/${detail.id}/submissions/${submission.id}/evidence/${evidence.id}/file`, {
      fallbackName: evidence.file_name ?? "report",
    });
  return (
    <section className="uw-card uw-card-pad" aria-label="Submissions">
      <h2>Submitted</h2>
      <ul className="uw-rp-record">
        {detail.submissions.map((submission) => (
          <li key={submission.id}>
            <p>
              <strong>Report ID: {submission.report_id}</strong> · submitted {formatDate(submission.submitted_at)} ·
              recorded and signed by {submission.recorded_by}
              {submission.late ? " · after the due date" : ""}
            </p>
            <ul>
              {submission.evidence.map((evidence) => (
                <li key={evidence.id}>
                  {evidence.kind_label} · {OUTCOME_LABELS[evidence.outcome] ?? evidence.outcome}
                  {evidence.file_name && (
                    <>
                      {" · "}
                      <button type="button" className="ac-link" onClick={() => file(submission, evidence)}>
                        <FileText size={14} aria-hidden="true" /> {evidence.file_name}
                      </button>
                    </>
                  )}
                  {evidence.sha256 && <span className="uw-mono ac-muted"> · SHA-256 {evidence.sha256}</span>}
                </li>
              ))}
            </ul>
            {canWrite && detail.can.enter_report_id && submission.report_id_pending && (
              <ReportIdLater detail={detail} submission={submission} action={action} />
            )}
            {canWrite && detail.can.acknowledge && submission === detail.submissions[0] && (
              <Acknowledgement detail={detail} submission={submission} action={action} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ReportIdLater({
  detail,
  submission,
  action,
}: {
  detail: AttachedDetail;
  submission: AttachedSubmission;
  action: Action;
}) {
  const [value, setValue] = useState("");
  return (
    <form
      className="ca-action-row"
      onSubmit={(event) => {
        event.preventDefault();
        if (value.trim() && !action.busy)
          void action.run(
            `${REPORTS}/${detail.id}/attached-report-id`,
            "PUT",
            { submission_id: submission.id, report_id: value },
            "The Report ID was not saved.",
          );
      }}
    >
      <label className="ca-field">
        Report ID, now issued
        <input value={value} maxLength={120} onChange={(event) => setValue(event.target.value)} />
      </label>
      <button type="submit" className="ac-secondary" disabled={!value.trim() || action.busy}>
        Save the Report ID
      </button>
    </form>
  );
}

function Acknowledgement({
  detail,
  submission,
  action,
}: {
  detail: AttachedDetail;
  submission: AttachedSubmission;
  action: Action;
}) {
  const kinds = Object.keys(detail.evidence_kinds).filter((kind) => kind !== "SUBMITTED_CONTENT");
  const [kind, setKind] = useState(kinds.includes("ACCEPTANCE") ? "ACCEPTANCE" : (kinds[0] ?? ""));
  const outcome = detail.evidence_kinds[kind]?.[0] ?? "";
  const [receivedAt, setReceivedAt] = useState(nowLocal());
  const [reference, setReference] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const record = async () => {
    setFileError("");
    let content: FileIn | null = null;
    try {
      content = file ? await fileIn(file) : null;
    } catch (reason) {
      setFileError(errorText(reason, "The file cannot be attached."));
      return;
    }
    await action.run(
      `${REPORTS}/${detail.id}/submissions/${submission.id}/evidence`,
      "POST",
      {
        kind,
        outcome,
        received_at: new Date(receivedAt).toISOString(),
        file: content,
        authority_reference: reference,
      },
      "The authority's answer was not recorded.",
    );
  };
  return (
    <form
      className="ca-form"
      aria-label="The authority's answer"
      onSubmit={(event) => {
        event.preventDefault();
        if (kind && !action.busy) void record();
      }}
    >
      <h3>The authority's answer</h3>
      <div className="ca-form-grid">
        <label className="ca-field">
          What arrived
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            {kinds.map((item) => (
              <option key={item} value={item}>
                {detail.evidence_labels[item] ?? item}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Received on
          <input type="datetime-local" value={receivedAt} onChange={(event) => setReceivedAt(event.target.value)} />
        </label>
        <label className="ca-field">
          The authority's reference (optional)
          <input value={reference} maxLength={240} onChange={(event) => setReference(event.target.value)} />
        </label>
        <label className="ca-field">
          The file (optional)
          <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
      </div>
      <button type="submit" className="ac-secondary" disabled={!kind || action.busy}>
        Record it
      </button>
      <InlineError text={fileError} />
    </form>
  );
}

function FollowUpsPart({
  detail,
  canWrite,
  action,
  onOpen,
}: {
  detail: AttachedDetail;
  canWrite: boolean;
  action: Action;
  onOpen: (id: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  // The new follow-up opens on its own page (its file, Report ID and status are its own).
  const start = () => {
    setError("");
    send<AttachedDetail>(`${REPORTS}/${detail.id}/attached-follow-ups`, "POST", { reason }).then(
      (child) => onOpen(child.id),
      (failure) => setError(errorText(failure, "The follow-up was not created.")),
    );
  };
  return (
    <section className="uw-card uw-card-pad" aria-label="Follow-up reports">
      <h2>Follow-up reports</h2>
      {detail.follow_ups.length ? (
        <ul>
          {detail.follow_ups.map((item) => (
            <li key={item.id}>
              <button type="button" className="ac-link" onClick={() => onOpen(item.id)}>
                Follow-up {item.number}
              </button>{" "}
              · {item.state_label}
              {item.due_on ? ` · due ${formatDay(item.due_on)}` : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">None yet. The authority may ask for more: each follow-up has its own file and ID.</p>
      )}
      {canWrite && detail.can.follow_up && (
        <form
          className="ca-action-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (reason.trim().length >= REASON_MIN && !action.busy) start();
          }}
        >
          <label className="ca-field">
            What the follow-up is for (required)
            <input value={reason} maxLength={2000} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button type="submit" className="ac-secondary" disabled={reason.trim().length < REASON_MIN || action.busy}>
            Start a follow-up report
          </button>
        </form>
      )}
      <InlineError text={error} />
    </section>
  );
}

function CloseForm({ detail, action }: { detail: AttachedDetail; action: Action }) {
  const [reason, setReason] = useState("");
  const acknowledged = detail.state === "ACCEPTED" || detail.state === "FOLLOW_UP_DUE";
  return (
    <form
      className="uw-card uw-card-pad ca-form"
      aria-label="Close the report"
      onSubmit={(event) => {
        event.preventDefault();
        if (reason.trim().length >= REASON_MIN && !action.busy)
          void action.run(`${REPORTS}/${detail.id}/complete`, "POST", { reason }, "The report was not closed.");
      }}
    >
      <h2>Close the report</h2>
      <p className="ac-muted">
        {acknowledged
          ? "Nothing more is owed? Say why, and close it."
          : "No acknowledgement recorded: say why nothing more is expected (for example, the authority sends none)."}
      </p>
      <label className="ca-field">
        Why it is closed (required)
        <input value={reason} maxLength={2000} onChange={(event) => setReason(event.target.value)} />
      </label>
      <button type="submit" className="ac-secondary" disabled={reason.trim().length < REASON_MIN || action.busy}>
        Close
      </button>
    </form>
  );
}
