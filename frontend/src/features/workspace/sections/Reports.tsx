import { PracticeApproval } from "./PracticeApproval";
import { useContext, useEffect, useState } from "react";
import { marketLabel, versionWords } from "../../../app/labels";
import { CheckCircle2, ClipboardList, Download, FileText, Send, ShieldCheck, Undo2 } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { WorkspaceContext, useCan, useNavigation, useTabParam } from "../workspaceContext";
import { communicationsTab } from "../communications";
import { AlsoKnownAs, countOf, DecideAndSign, shortPrint } from "./common";
import { ComplaintNextStep } from "./ComplaintNextStep";
import { DeadlineChip, StateChip } from "../../../app/chips";
import { Hero, InlineError } from "./boardParts";
import { CodePicker } from "./CodePicker";
import {
  OUTCOME_LABELS,
  REASON_MIN,
  askNote,
  REPORTS,
  RESULT_LABELS,
  deadlineDue,
  deadlineText,
  fieldTone,
  fileIn,
  nowLocal,
  stateTone,
  stepIndex,
  submissionBody,
  submissionProblem,
  isMissing,
  reportPlace,
  worksheetMeter,
  filledCounts,
  summaryLine,
  type ReportDetail,
  type ReportList,
  type ReportListItem,
  type Submission,
  type SubmissionForm,
  type WorksheetField,
} from "../authorityReports";

/** The regulatory rule: review or approval rights may prepare, approve and record (the server's rule). */
export function useCanReport() {
  const review = useCan("regulatory.review");
  const approve = useCan("regulatory.approve");
  return review || approve;
}

const PATH = ["Triage", "Market assessment", "Worksheet", "Second-person approval", "Marked submitted"];

/**
 * Complaints › Reports: every report a market assessment says is owed (reportable, or pending with a provisional
 * deadline), with the US Form FDA 3500A and India MvPI worksheets in the authority's field order, the second person's
 * approval of the snapshot, and the complete submission record. Prepared by MDARIX, submitted by the customer.
 */
export function Reports({ complaintId }: { complaintId?: string | null }) {
  const list = useResource<ReportList>(complaintId ? `${REPORTS}?complaint_id=${complaintId}` : REPORTS);
  // The report whose panel is open is part of the address (Reports?report=<id>): Back closes it, refresh keeps it.
  const [open, setOpen] = useTabParam("report");
  const [error, setError] = useState("");
  const canWrite = useCanReport();
  const workspace = useContext(WorkspaceContext);
  // The new navigation opens a report on its own page in the Reports tab (0.10.75, C3); classic keeps the panel.
  const fresh = useNavigation() === "new";
  const show = (id: string) =>
    fresh && workspace ? workspace.open(reportPlace(id).section, reportPlace(id).tab) : setOpen(id);
  // A link to one report (an approval task, a Home item: 0.10.76) opens its own page on the new navigation.
  useEffect(() => {
    if (fresh && workspace && open) workspace.open(reportPlace(open).section, reportPlace(open).tab);
  }, [fresh, workspace, open]);
  const items = list.data?.items ?? [];
  const waiting = items.filter(
    (item) => !["ACCEPTED", "COMPLETE", "SUBMITTED_NO_ACK", "FOLLOW_UP_DUE"].includes(item.state),
  );
  const start = async (item: ReportListItem) => {
    setError("");
    try {
      const made = await send<ReportDetail>(REPORTS, "POST", { complaint_id: item.complaint_id, market: item.market });
      list.reload();
      show(made.id);
    } catch (reason) {
      setError(errorText(reason, "The worksheet was not started."));
    }
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={waiting.some((item) => item.overdue) ? "critical" : waiting.length ? "warning" : "good"}
        icon={<ClipboardList size={28} />}
        eyebrow="Reports"
        title={
          list.data
            ? waiting.length
              ? `${countOf(waiting.length, "report")} to finish`
              : "No report waits"
            : "Authority reports"
        }
        detail="From a market assessment to a report ready to file: the worksheet in the authority's field order, a second person's approval, and the submission you record after entering it in the authority's route."
      />
      <ol className="uw-rp-path" aria-label="The path of a report">
        {PATH.map((step, index) => (
          <li key={step}>
            <span aria-hidden="true">{index + 1}</span> {step}
          </li>
        ))}
      </ol>
      <Panel
        eyebrow="Obligations"
        title={complaintId ? "This complaint's reports" : "Nearest deadline first"}
        source={list}
      >
        {list.data && (
          <p className="uw-ma-starter" role="note">
            <Send size={15} aria-hidden="true" /> Forms:{" "}
            {list.data.forms.map((form) => `${marketLabel(form.market)}: ${versionWords(form.version)}`).join("; ")}.
          </p>
        )}
        <InlineError text={error} />
        {items.length ? (
          <ul className="uw-cr-list">
            {items.map((item) => (
              <li key={item.id ?? `${item.complaint_id}-${item.market}`} className="uw-cr-card">
                <span className={`uw-cr-rail tone-${stateTone(item.state, item.overdue)}`} aria-hidden="true" />
                <div className="uw-cr-body">
                  <div className="uw-cr-head">
                    <strong className="uw-cr-id">{item.complaint_ref}</strong>
                    <span className="uw-cr-meta">
                      {item.complaint_identifier !== item.complaint_ref ? `${item.complaint_identifier} · ` : ""}
                      {item.market_label}
                      {item.form_title ? ` · ${item.form_title}` : ""}
                      {item.kind === "RESPONSE" ? " · response to a request" : ""}
                      {item.sample ? " · sample" : ""}
                    </span>
                    <StateChip label={item.state_label} />
                    {deadlineDue(item, item.state) && (
                      <DeadlineChip item={deadlineDue(item, item.state)!} prefix="Report" />
                    )}
                  </div>
                  <q className="uw-cr-text uw-cr-clip">{item.description}</q>
                  <p className="uw-cr-meta">
                    <span className={`uw-clock tone-${item.overdue ? "critical" : "neutral"}`}>
                      {deadlineText(item, item.state)}
                    </span>
                    {item.assessment ? ` · Assessment: ${item.assessment}` : ""} · Next: {item.next_step}
                  </p>
                  <div className="ca-action-row">
                    {item.id ? (
                      <button type="button" className="ac-secondary" onClick={() => show(item.id!)}>
                        Open the worksheet
                      </button>
                    ) : item.can_start && canWrite ? (
                      <button type="button" className="ac-primary" onClick={() => void start(item)}>
                        Start the worksheet
                      </button>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <Empty
            title="No report is owed yet"
            detail="A market assessed reportable, or pending information, lists its report here with its deadline."
            action={
              workspace && (
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() => workspace.open("Complaints", "Reportability")}
                >
                  Assess a complaint per market
                </button>
              )
            }
          />
        )}
        {list.data && <p className="ac-muted">{list.data.starter_mark}</p>}
      </Panel>
      {open && !fresh && (
        <ReportDrawer
          id={open}
          onOpen={setOpen}
          onClose={() => {
            setOpen(null);
            list.reload();
          }}
        />
      )}
    </div>
  );
}

/** One report: its lifecycle, the worksheet, the snapshots and the complete submission record. */
export function ReportDrawer({
  id,
  onOpen,
  onClose,
}: {
  id: string;
  onOpen: (id: string) => void;
  onClose: () => void;
}) {
  const resource = useResource<ReportDetail>(`${REPORTS}/${id}`);
  const [shown, setShown] = useState<ReportDetail | null>(null);
  const detail = shown?.id === id ? shown : resource.data;
  const canWrite = useCanReport();
  const changed = (next: ReportDetail) => setShown(next);
  if (!detail) {
    return (
      <Drawer title="Report" onClose={onClose}>
        <p className="ac-muted">
          {resource.error ? errorText(resource.error, "The report could not be read.") : "Reading…"}
        </p>
      </Drawer>
    );
  }
  const step = stepIndex(detail.state);
  return (
    <Drawer title={`${detail.form.title}: ${detail.complaint.ref}`} onClose={onClose}>
      <div className="uw-dp uw-rp">
        <AlsoKnownAs id={detail.complaint.business_id} shown={detail.complaint.ref} />
        <div className="uw-cr-decision">
          <StateChip label={detail.state_label} />
          {deadlineDue(detail.deadline, detail.state) && (
            <DeadlineChip item={deadlineDue(detail.deadline, detail.state)!} prefix="Report" />
          )}
          <span className="uw-cr-meta">{deadlineText(detail.deadline, detail.state)}</span>
          <span className="uw-cr-meta">
            {versionWords(detail.form.version)} · {detail.market_label}
            {detail.complaint.sample ? " · sample" : ""}
          </span>
        </div>
        <ol className="uw-rp-steps" aria-label="Where this report is">
          {detail.steps.map((item, index) => (
            <li key={item.state} className={index < step ? "done" : index === step ? "current" : ""}>
              {index < step ? (
                <CheckCircle2 size={14} aria-hidden="true" />
              ) : (
                <span aria-hidden="true">{index + 1}</span>
              )}{" "}
              {item.label}
            </li>
          ))}
        </ol>
        <section className="ca-drawer-section" aria-label="Next step">
          <h3>Next: {detail.next_step}</h3>
          {detail.request && (
            <p>
              <strong>The authority asked</strong> ({detail.request.received_on}): {detail.request.text}
            </p>
          )}
          {detail.parent_id && (
            <button type="button" className="ac-link" onClick={() => onOpen(detail.parent_id!)}>
              Open the report this responds to
            </button>
          )}
          {canWrite && <NextStep detail={detail} onChanged={changed} onOpen={onOpen} />}
        </section>
        <section className="ca-drawer-section" aria-label="The case behind it">
          <h3>Drafted from</h3>
          <p className="uw-cr-meta">
            Complaint {detail.complaint.ref} ({detail.complaint.product_name ?? "no product"}{" "}
            {detail.complaint.version ?? ""}), aware {detail.complaint.aware_date ?? "—"}
            {detail.assessment
              ? ` · ${detail.market} conclusion: ${detail.assessment.conclusion ? `${detail.assessment.conclusion.toLowerCase().replace("_", " ")}, signed by ${detail.assessment.signed_by} ${formatDate(detail.assessment.signed_at)}` : "not signed yet (pending)"}`
              : ""}
            {detail.assessment?.report_type_label ? ` · ${detail.assessment.report_type_label}` : ""}
            {detail.case ? ` · ${detail.case}` : ""}
          </p>
          <CommunicationsLink complaintId={detail.complaint.id} />
        </section>
        <Downloads detail={detail} />
        <Worksheet detail={detail} onChanged={changed} canWrite={canWrite} />
        <SubmissionRecord detail={detail} />
        {detail.responses.length > 0 && (
          <section className="ca-drawer-section" aria-label="Responses to requests">
            <h3>Requests for information</h3>
            <ul>
              {detail.responses.map((row) => (
                <li key={row.id}>
                  {row.request_text} · due {row.due_on} · {row.state_label}{" "}
                  <button type="button" className="ac-link" onClick={() => onOpen(row.id)}>
                    Open
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        <p className="ac-muted">
          {detail.starter_mark} Field order: {detail.form.source_document}.
        </p>
        <ComplaintNextStep
          complaintId={detail.complaint.id}
          here="Reports"
          refreshKey={`${detail.state}.${detail.snapshots.length}.${detail.submissions.length}`}
        />
      </div>
    </Drawer>
  );
}

export function useAction(onChanged: (detail: ReportDetail) => void, failure: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path: string, method: "POST" | "PUT", body?: unknown) => {
    setBusy(true);
    setError("");
    try {
      onChanged(await send<ReportDetail>(path, method, body));
      return true;
    } catch (reason) {
      setError(errorText(reason, failure));
      return false;
    } finally {
      setBusy(false);
    }
  };
  const fail = (reason: unknown) => setError(errorText(reason, failure));
  return { busy, error, run, fail };
}

function NextStep({
  detail,
  onChanged,
  onOpen,
}: {
  detail: ReportDetail;
  onChanged: (detail: ReportDetail) => void;
  onOpen: (id: string) => void;
}) {
  const action = useAction(onChanged, "That step was not recorded.");
  const base = `${REPORTS}/${detail.id}`;
  if (detail.editable) {
    return (
      <>
        {detail.pending_snapshot ? (
          <Approval detail={detail} onChanged={onChanged} />
        ) : (
          <p className="ac-muted">
            Check each field. Missing fields never block a timely initial report. {askNote(detail.approval)}
          </p>
        )}
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-primary"
            disabled={action.busy}
            onClick={() => void action.run(`${base}/snapshots`, "POST")}
          >
            <ShieldCheck size={15} aria-hidden="true" />{" "}
            {detail.pending_snapshot ? "Freeze the worksheet again" : "Ask for approval"}
          </button>
        </div>
        <InlineError text={action.error} />
      </>
    );
  }
  if (detail.state === "APPROVED") return <RecordSubmission detail={detail} onChanged={onChanged} />;
  if (detail.state === "SUBMITTED_PENDING" && detail.submissions[0])
    return <RecordEvidence detail={detail} attempt={detail.submissions[0]} onChanged={onChanged} />;
  if (["ACCEPTED", "SUBMITTED_NO_ACK", "FOLLOW_UP_DUE"].includes(detail.state))
    return <AfterAcceptance detail={detail} onChanged={onChanged} onOpen={onOpen} />;
  return null;
}

export function Approval({ detail, onChanged }: { detail: ReportDetail; onChanged: (detail: ReportDetail) => void }) {
  const snapshot = detail.pending_snapshot!;
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const action = useAction(onChanged, "The snapshot was not approved.");
  const standing = detail.approval;
  const waiting = (
    <>
      <strong>Snapshot {snapshot.version}</strong> frozen by {snapshot.requested_by} {formatDate(snapshot.requested_at)}
      , waiting for a second person.
    </>
  );
  // Who approves is told before any password: someone who may not approve never sees the form (J13).
  if (standing && !standing.may_approve)
    return (
      <div className="uw-rp-approval" role="note" aria-label="Who approves the snapshot">
        <p>{waiting}</p>
        <p>{standing.message}</p>
      </div>
    );
  return (
    <form
      className="uw-rp-approval"
      aria-label="Approve the snapshot"
      onSubmit={(event) => {
        event.preventDefault();
        void action.run(`${REPORTS}/${detail.id}/snapshots/${snapshot.id}/approve`, "POST", {
          password,
          mfa_code: code || null,
        });
      }}
    >
      {standing?.same_person ? (
        <>
          <p>{waiting}</p>
          <p className="ac-message tone-warning">{standing.message}</p>
        </>
      ) : (
        <p>
          {waiting} Not allowed to approve: {detail.cannot_approve.join(", ")} (the preparer and the signer of the
          market conclusion).
        </p>
      )}
      <div className="ca-form-grid">
        <DecideAndSign
          signs={`Approval of snapshot ${snapshot.version} of the ${detail.form.title} for ${detail.complaint.ref}, as frozen.`}
          restsOn={[
            `${filledCounts(detail.counts).fromRecords} fields filled from your records, ${detail.counts.MUST_HAVE ?? 0} still to enter; fingerprint ${shortPrint(snapshot.content_fingerprint)}.`,
            detail.assessment
              ? `The ${detail.market_label} conclusion: ${String(detail.assessment.conclusion ?? "")
                  .toLowerCase()
                  .replace("_", " ")}, version ${detail.assessment.version}, signed by ${detail.assessment.signed_by}.`
              : null,
            `${detail.form.title}, ${detail.form.version}.`,
          ]}
        />
        <label className="ca-field">
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
        </label>
      </div>
      <p className="ac-muted">
        Your approval covers this snapshot exactly as frozen (checksum {snapshot.content_fingerprint.slice(0, 12)}…). It
        is what is submitted.
      </p>
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={action.busy || !password}>
          {action.busy ? "Approving…" : "Approve the snapshot"}
        </button>
        <PracticeApproval shown={standing?.same_person} />
      </div>
      <InlineError text={action.error} />
    </form>
  );
}

const EMPTY_SUBMISSION: SubmissionForm = {
  route: "",
  submittedAt: "",
  note: "",
  reference: "",
  matches: true,
  differences: [],
};

export function RecordSubmission({
  detail,
  onChanged,
  quiet = false,
}: {
  detail: ReportDetail;
  onChanged: (detail: ReportDetail) => void;
  /** Its button is secondary where the page's one main button is elsewhere (the report page's Generate the PDF). */
  quiet?: boolean;
}) {
  const [form, setForm] = useState<SubmissionForm>({
    ...EMPTY_SUBMISSION,
    route: detail.routes[0]?.code ?? "",
    submittedAt: nowLocal(),
  });
  const [file, setFile] = useState<File | null>(null);
  const [reopenReason, setReopenReason] = useState("");
  const action = useAction(onChanged, "The submission was not recorded.");
  const problem = submissionProblem(form, !!file);
  const set = (patch: Partial<SubmissionForm>) => setForm((current) => ({ ...current, ...patch }));
  return (
    <>
      <form
        className="ca-form-grid"
        aria-label="Record the submission"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            const attached = file ? await fileIn(file) : null;
            await action.run(`${REPORTS}/${detail.id}/submissions`, "POST", submissionBody(form, attached));
          } catch (reason) {
            action.fail(reason);
          }
        }}
      >
        <p className="ac-muted ca-wide">
          Enter the approved snapshot in the authority's route yourself, then record it here at once.
        </p>
        <DecideAndSign />
        <label className="ca-field">
          Route
          <select value={form.route} onChange={(event) => set({ route: event.target.value })}>
            {detail.routes.map((route) => (
              <option key={route.code} value={route.code}>
                {route.label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Submitted at
          <input
            type="datetime-local"
            value={form.submittedAt}
            onChange={(event) => set({ submittedAt: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Authority's reference (if you have it)
          <input value={form.reference} maxLength={120} onChange={(event) => set({ reference: event.target.value })} />
        </label>
        <label className="ca-field">
          Submitted content: the portal's copy or export
          <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        </label>
        <label className="ca-field ca-wide">
          Or a note describing it
          <textarea rows={2} value={form.note} onChange={(event) => set({ note: event.target.value })} />
        </label>
        <label className="ca-check ca-wide">
          <input
            type="checkbox"
            checked={form.matches}
            onChange={(event) => set({ matches: event.target.checked, differences: [] })}
          />{" "}
          The submitted content matches the approved snapshot
        </label>
        {!form.matches && (
          <div className="ca-wide">
            {form.differences.map((item, index) => (
              <div key={index} className="ca-form-grid">
                <label className="ca-field">
                  Field
                  <input
                    value={item.field}
                    onChange={(event) =>
                      set({
                        differences: form.differences.map((row, at) =>
                          at === index ? { ...row, field: event.target.value } : row,
                        ),
                      })
                    }
                  />
                </label>
                <label className="ca-field">
                  Difference
                  <select
                    value={item.classification}
                    onChange={(event) =>
                      set({
                        differences: form.differences.map((row, at) =>
                          at === index
                            ? { ...row, classification: event.target.value as "MATERIAL" | "NON_MATERIAL" }
                            : row,
                        ),
                      })
                    }
                  >
                    <option value="NON_MATERIAL">Not material</option>
                    <option value="MATERIAL">Material</option>
                  </select>
                </label>
                <label className="ca-field">
                  Reason
                  <input
                    value={item.reason}
                    onChange={(event) =>
                      set({
                        differences: form.differences.map((row, at) =>
                          at === index ? { ...row, reason: event.target.value } : row,
                        ),
                      })
                    }
                  />
                </label>
              </div>
            ))}
            <button
              type="button"
              className="ac-link"
              onClick={() =>
                set({ differences: [...form.differences, { field: "", classification: "NON_MATERIAL", reason: "" }] })
              }
            >
              Add a difference
            </button>
          </div>
        )}
        {problem && <p className="uw-hint ca-wide">{problem}</p>}
        <div className="ca-action-row ca-wide">
          <button type="submit" className={quiet ? "ac-secondary" : "ac-primary"} disabled={action.busy || !!problem}>
            <Send size={15} aria-hidden="true" /> {action.busy ? "Recording…" : "Mark as submitted"}
          </button>
        </div>
        <InlineError text={action.error} />
      </form>
      <details className="uw-rp-reopen">
        <summary>Found something to correct before submitting?</summary>
        <label className="ca-field">
          Why you reopen the draft
          <input value={reopenReason} onChange={(event) => setReopenReason(event.target.value)} />
        </label>
        <button
          type="button"
          className="ac-secondary"
          disabled={action.busy || reopenReason.trim().length < REASON_MIN}
          onClick={() => void action.run(`${REPORTS}/${detail.id}/reopen`, "POST", { reason: reopenReason })}
        >
          <Undo2 size={15} aria-hidden="true" /> Reopen the draft (needs a new approval)
        </button>
      </details>
    </>
  );
}

export function RecordEvidence({
  detail,
  attempt,
  onChanged,
}: {
  detail: ReportDetail;
  attempt: Submission;
  onChanged: (detail: ReportDetail) => void;
}) {
  const route = detail.routes.find((item) => item.code === attempt.route);
  const kinds = (route?.evidence ?? []).filter((item) => item.kind !== "SUBMITTED_CONTENT");
  const [kind, setKind] = useState(kinds[0]?.kind ?? "");
  const outcomes = kinds.find((item) => item.kind === kind)?.outcomes ?? [];
  const [outcome, setOutcome] = useState(outcomes[0] ?? "");
  const [at, setAt] = useState(nowLocal());
  const [note, setNote] = useState("");
  const [reference, setReference] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const action = useAction(onChanged, "The evidence was not recorded.");
  const chosen = outcomes.includes(outcome) ? outcome : (outcomes[0] ?? "");
  return (
    <form
      className="ca-form-grid"
      aria-label="Record the evidence"
      onSubmit={async (event) => {
        event.preventDefault();
        try {
          const attached = file ? await fileIn(file) : null;
          await action.run(`${REPORTS}/${detail.id}/submissions/${attempt.id}/evidence`, "POST", {
            kind,
            outcome: chosen,
            received_at: new Date(at).toISOString(),
            note,
            authority_reference: reference,
            file: attached,
          });
        } catch (reason) {
          action.fail(reason);
        }
      }}
    >
      <p className="ac-muted ca-wide">
        Attempt {attempt.attempt}, {attempt.route_label}, submitted {formatDate(attempt.submitted_at)}. A receipt is not
        acceptance: the report stays "acceptance pending" until the acceptance evidence is recorded.
        {attempt.follow_up ? ` Check for acceptance by ${formatDate(attempt.follow_up.at)}.` : ""}
      </p>
      <label className="ca-field">
        Evidence
        <select value={kind} onChange={(event) => setKind(event.target.value)}>
          {kinds.map((item) => (
            <option key={item.kind} value={item.kind}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        It says
        <select value={chosen} onChange={(event) => setOutcome(event.target.value)}>
          {outcomes.map((item) => (
            <option key={item} value={item}>
              {OUTCOME_LABELS[item]}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Arrived at
        <input type="datetime-local" value={at} onChange={(event) => setAt(event.target.value)} />
      </label>
      <label className="ca-field">
        Reference (if it carries one)
        <input value={reference} maxLength={120} onChange={(event) => setReference(event.target.value)} />
      </label>
      <label className="ca-field">
        The file
        <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      </label>
      <label className="ca-field">
        Or a note
        <input value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <div className="ca-action-row ca-wide">
        <button type="submit" className="ac-primary" disabled={action.busy || !kind || (!note.trim() && !file)}>
          Record the evidence
        </button>
      </div>
      <InlineError text={action.error} />
    </form>
  );
}

export function AfterAcceptance({
  detail,
  onChanged,
  onOpen,
}: {
  detail: ReportDetail;
  onChanged: (detail: ReportDetail) => void;
  onOpen: (id: string) => void;
}) {
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [request, setRequest] = useState({ text: "", received: "", due: "" });
  // The obligation is met; completing it is optional. On the new navigation the drawer's one main button is the
  // complaint's next step below (0.10.70).
  const fresh = useNavigation() === "new";
  const action = useAction(onChanged, "That step was not recorded.");
  const base = `${REPORTS}/${detail.id}`;
  return (
    <div className="uw-rp-after">
      <label className="ca-field">
        Note (why it is complete, or what is due)
        <input value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button
          type="button"
          className={fresh ? "ac-secondary" : "ac-primary"}
          disabled={action.busy || note.trim().length < REASON_MIN}
          onClick={() => void action.run(`${base}/complete`, "POST", { reason: note })}
        >
          Complete the obligation
        </button>
        {detail.state !== "FOLLOW_UP_DUE" && (
          <>
            <input
              type="date"
              aria-label="Follow-up due on"
              value={due}
              onChange={(event) => setDue(event.target.value)}
            />
            <button
              type="button"
              className="ac-secondary"
              disabled={action.busy || !due || note.trim().length < REASON_MIN}
              onClick={() => void action.run(`${base}/follow-up`, "POST", { due_on: due, note })}
            >
              A follow-up is due
            </button>
          </>
        )}
      </div>
      {detail.kind === "INITIAL" && (
        <details>
          <summary>The authority asked for more information</summary>
          <div className="ca-form-grid">
            <label className="ca-field ca-wide">
              What it asked
              <textarea
                rows={2}
                value={request.text}
                onChange={(event) => setRequest({ ...request, text: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Received on
              <input
                type="date"
                value={request.received}
                onChange={(event) => setRequest({ ...request, received: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Response due on
              <input
                type="date"
                value={request.due}
                onChange={(event) => setRequest({ ...request, due: event.target.value })}
              />
            </label>
          </div>
          <button
            type="button"
            className="ac-secondary"
            disabled={action.busy || request.text.trim().length < REASON_MIN || !request.received || !request.due}
            onClick={async () => {
              try {
                const made = await send<ReportDetail>(`${base}/requests`, "POST", {
                  request_text: request.text,
                  received_on: request.received,
                  due_on: request.due,
                });
                onOpen(made.id);
              } catch (reason) {
                action.fail(reason);
              }
            }}
          >
            Create the response obligation
          </button>
        </details>
      )}
      <InlineError text={action.error} />
    </div>
  );
}

function Downloads({ detail }: { detail: ReportDetail }) {
  const canExport = useCan("data.export");
  // The new navigation generates the PDF once the report is approved (0.10.75, C3): no working-draft download.
  const fresh = useNavigation() === "new";
  const [error, setError] = useState("");
  if (!canExport) return null;
  const approved = detail.snapshots.find((row) => row.state === "APPROVED");
  const get = async (kind: "pdf" | "docx", snapshot?: string) => {
    setError("");
    try {
      await downloadFile(`${REPORTS}/${detail.id}/worksheet.${kind}${snapshot ? `?snapshot=${snapshot}` : ""}`, {
        fallbackName: `mdarix-${detail.form.code.toLowerCase()}-${detail.complaint.ref}.${kind}`,
      });
    } catch (reason) {
      setError(errorText(reason, "The file could not be downloaded."));
    }
  };
  return (
    <div className="ca-action-row uw-doc-downloads">
      {!fresh && (
        <>
          <button type="button" className="ac-secondary" onClick={() => void get("pdf")}>
            <Download size={15} aria-hidden="true" /> PDF (working draft)
          </button>
          <button type="button" className="ac-secondary" onClick={() => void get("docx")}>
            <Download size={15} aria-hidden="true" /> DOCX
          </button>
        </>
      )}
      {approved && (
        <button type="button" className="ac-secondary" onClick={() => void get("pdf", approved.id)}>
          <FileText size={15} aria-hidden="true" /> Approved snapshot {approved.version} (PDF)
        </button>
      )}
      <InlineError text={error} />
    </div>
  );
}

function Worksheet({
  detail,
  onChanged,
  canWrite,
}: {
  detail: ReportDetail;
  onChanged: (detail: ReportDetail) => void;
  canWrite: boolean;
}) {
  // Wow screen 5: a sticky meter of the fields filled from your records, and "show only missing".
  const [onlyMissing, setOnlyMissing] = useState(false);
  const meter = worksheetMeter(detail.sections);
  const shown = (fields: WorksheetField[]) => (onlyMissing ? fields.filter(isMissing) : fields);
  return (
    <section className="ca-drawer-section" aria-label="The worksheet">
      <h3>The worksheet, in the authority's field order</h3>
      <div className="uw-rp-meter" role="group" aria-label="How much of the worksheet your records filled">
        <span className="uw-rp-meter-text">
          <strong>
            {meter.fromRecords} of {meter.total} fields filled from your records
          </strong>
          {meter.missing ? ` · ${meter.missing} still to enter before submission` : " · nothing missing"}
        </span>
        <span className="uw-rp-meter-bar" aria-hidden="true">
          <span style={{ width: `${meter.total ? (100 * meter.fromRecords) / meter.total : 0}%` }} />
          <span className="is-entered" style={{ width: `${meter.total ? (100 * meter.entered) / meter.total : 0}%` }} />
        </span>
        <label className="ca-check">
          <input type="checkbox" checked={onlyMissing} onChange={(event) => setOnlyMissing(event.target.checked)} />
          Show only missing
        </label>
      </div>
      <p className="uw-cr-meta">{summaryLine(detail.counts)}</p>
      {detail.sections
        .filter((section) => !onlyMissing || shown(section.fields).length > 0)
        .map((section) => (
          <details key={section.code} className="uw-rp-section" open={section.fields.length > 0}>
            <summary>
              {section.title}
              {section.fields.length ? ` (${shown(section.fields).length})` : ""}
            </summary>
            {section.note && <p className="ac-muted">{section.note}</p>}
            {section.fields.length > 0 && (
              <ul className="uw-rp-fields">
                {shown(section.fields).map((item) => (
                  <FieldRow
                    key={item.id}
                    detail={detail}
                    item={item}
                    onChanged={onChanged}
                    canEdit={canWrite && detail.editable}
                  />
                ))}
              </ul>
            )}
          </details>
        ))}
    </section>
  );
}

/** Who settled a code and how: "Confirmed by Asha Quality 3 Nov 2026", "Changed by …; suggested A0908 …". */
export function codeMeta(item: Pick<WorksheetField, "status" | "by" | "at" | "suggested">): string {
  if (!item.by) return "";
  const how = { CONFIRMED: "Confirmed", CHANGED: "Changed" }[item.status] ?? "Chosen";
  const was = item.status === "CHANGED" && item.suggested ? `; suggested ${item.suggested}` : "";
  return `${how} by ${item.by} ${formatDate(item.at)}${was}`;
}

/**
 * A code field on the new navigation (0.10.77, C5): what the approved mapping suggests waits for the regulatory
 * manager, who confirms it or changes it in the code picker; the report records which, who and when. Nothing is
 * filed unconfirmed: a suggestion counts as missing and is never frozen into a snapshot.
 */
function CodeFieldRow({
  detail,
  item,
  onChanged,
  canEdit,
}: {
  detail: ReportDetail;
  item: WorksheetField;
  onChanged: (detail: ReportDetail) => void;
  canEdit: boolean;
}) {
  const [picking, setPicking] = useState(false);
  const action = useAction(onChanged, "The code was not saved.");
  const path = `${REPORTS}/${detail.id}/fields/${item.id}`;
  const settled = ["CONFIRMED", "CHANGED", "ENTERED"].includes(item.status);
  return (
    <li className={item.status === "SUGGESTED" ? "uw-rp-field is-suggested" : "uw-rp-field"}>
      <div className="uw-rp-field-head">
        <span className="uw-rp-number">{item.number}</span>
        <span className="uw-rp-label">{item.label}</span>
        <ToneBadge tone={fieldTone(item.status)} label={item.status_label} />
      </div>
      {item.status === "SUGGESTED" ? (
        <p className="uw-rp-value uw-rp-suggestion">
          <span className="ac-muted">Suggested: </span>
          {item.suggestion}
        </p>
      ) : (
        <p className={item.value ? "uw-rp-value" : "uw-rp-value empty"}>{item.value ?? "—"}</p>
      )}
      <p className="uw-cr-meta">
        {item.status === "SUGGESTED"
          ? `From your approved mapping${item.source?.ref ? `: ${item.source.ref}` : ""}. You confirm or change it; it is not filed until you do.`
          : codeMeta(item)}
        {item.note ? ` ${item.note}` : ""}
      </p>
      {canEdit && !picking && (
        <div className="ca-action-row">
          {item.status === "SUGGESTED" && (
            <button
              type="button"
              className="ac-secondary"
              disabled={action.busy}
              onClick={() => void action.run(path, "PUT", { confirmed: true })}
            >
              Confirm
            </button>
          )}
          <button type="button" className="ac-link" onClick={() => setPicking(true)}>
            {item.status === "SUGGESTED" || settled ? "Change" : "Choose a code"}
          </button>
          {settled && (
            <button
              type="button"
              className="ac-link"
              disabled={action.busy}
              onClick={() => void action.run(path, "PUT", { clear: true })}
            >
              Undo
            </button>
          )}
        </div>
      )}
      {picking && (
        <CodePicker
          annex={item.code_annex!}
          label={`${item.number} ${item.label}`.trim()}
          busy={action.busy}
          onCancel={() => setPicking(false)}
          onChoose={async (code) => {
            if (await action.run(path, "PUT", { codes: [code.code] })) setPicking(false);
          }}
        />
      )}
      <InlineError text={action.error} />
    </li>
  );
}

const FIELD_HINTS: Record<string, string> = {
  DATE_RANGE: "YYYY-MM-DD, or YYYY-MM-DD to YYYY-MM-DD",
  LIST_CODE: "A code of the published list",
};

export function FieldRow({
  detail,
  item,
  onChanged,
  canEdit,
}: {
  detail: ReportDetail;
  item: WorksheetField;
  onChanged: (detail: ReportDetail) => void;
  canEdit: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(item.status === "ENTERED" ? (item.value ?? "") : "");
  const action = useAction(onChanged, "The field was not saved.");
  const path = `${REPORTS}/${detail.id}/fields/${item.id}`;
  const editable = canEdit && item.editable !== false;
  // A code field takes only codes from the picker, on either navigation (0.10.81, F6).
  if (item.code_annex) return <CodeFieldRow detail={detail} item={item} onChanged={onChanged} canEdit={editable} />;
  return (
    <li className="uw-rp-field">
      <div className="uw-rp-field-head">
        <span className="uw-rp-number">{item.number}</span>
        <span className="uw-rp-label">{item.label}</span>
        <ToneBadge tone={fieldTone(item.status)} label={item.status_label} />
      </div>
      <p className={item.value ? "uw-rp-value" : "uw-rp-value empty"}>{item.value ?? "—"}</p>
      <p className="uw-cr-meta">
        {item.source
          ? `From ${item.source.label.replace(/^(The|An|A) /, (word) => word.toLowerCase())}${item.source.ref ? `: ${item.source.ref}` : ""}`
          : ""}
        {item.by
          ? `${item.source ? " · " : ""}${item.status === "CONFIRMED" ? "Confirmed" : "Entered"} by ${item.by} ${formatDate(item.at)}`
          : ""}
        {item.note ? ` ${item.note}` : ""}
      </p>
      {item.problem && <InlineError text={`${item.problem}: it counts as missing until it is corrected.`} />}
      {editable && !editing && (
        <div className="ca-action-row">
          <button type="button" className="ac-link" onClick={() => setEditing(true)}>
            {item.status === "ENTERED" ? "Change" : "Enter a value"}
          </button>
          {item.status === "FROM_RECORD" && (
            <button
              type="button"
              className="ac-link"
              disabled={action.busy}
              onClick={() => void action.run(path, "PUT", { confirmed: true })}
            >
              Confirm against the source
            </button>
          )}
          {(item.status === "ENTERED" || item.status === "CONFIRMED") && (
            <button
              type="button"
              className="ac-link"
              disabled={action.busy}
              onClick={() => void action.run(path, "PUT", { clear: true })}
            >
              Undo
            </button>
          )}
        </div>
      )}
      {editing && (
        <form
          className="uw-rp-edit"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await action.run(path, "PUT", { value })) setEditing(false);
          }}
        >
          {item.options?.length ? (
            <select
              aria-label={`${item.number} ${item.label}`.trim()}
              value={value}
              onChange={(event) => setValue(event.target.value)}
            >
              <option value="">Choose…</option>
              {item.options.map((choice) => (
                <option key={choice} value={choice}>
                  {choice}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label={`${item.number} ${item.label}`.trim()}
              // A date field takes a date (0.10.81, F6); a range or a list's code says its form.
              type={item.kind === "DATE" ? "date" : "text"}
              placeholder={FIELD_HINTS[item.kind ?? ""]}
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          )}
          <button type="submit" className="ac-secondary" disabled={action.busy || !value.trim()}>
            Save
          </button>
          <button type="button" className="ac-link" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      )}
      <InlineError text={action.error} />
    </li>
  );
}

export function SubmissionRecord({ detail }: { detail: ReportDetail }) {
  if (!detail.snapshots.length && !detail.submissions.length) return null;
  const file = (attempt: Submission, evidence: { id: string; file_name: string | null }) =>
    void downloadFile(`${REPORTS}/${detail.id}/submissions/${attempt.id}/evidence/${evidence.id}/file`, {
      fallbackName: evidence.file_name ?? "evidence",
    });
  return (
    <section className="ca-drawer-section" aria-label="The complete submission record">
      <h3>The complete submission record</h3>
      <ul className="uw-rp-record">
        {detail.submissions.map((attempt) => (
          <li key={attempt.id}>
            <p>
              <strong>Attempt {attempt.attempt}</strong> · {attempt.route_label} · submitted{" "}
              {formatDate(attempt.submitted_at)} · recorded by {attempt.recorded_by}{" "}
              <ToneBadge
                tone={attempt.result === "ACCEPTED" ? "good" : attempt.result === "REJECTED" ? "critical" : "warning"}
                label={RESULT_LABELS[attempt.result]}
              />
              {attempt.late && <ToneBadge tone="critical" label="Late" />}
            </p>
            <p className="uw-cr-meta">
              {attempt.authority_reference ? `Reference ${attempt.authority_reference} · ` : ""}
              {attempt.differences.length
                ? `Differences: ${attempt.differences.map((item) => `${item.field} (${item.classification.toLowerCase().replace("_", " ")}: ${item.reason})`).join("; ")}`
                : "Matches the approved snapshot"}
            </p>
            <ul>
              {attempt.evidence.map((item) => (
                <li key={item.id}>
                  {formatDate(item.received_at)} · {item.kind_label} · {OUTCOME_LABELS[item.outcome]}
                  {item.note ? `: ${item.note}` : ""}
                  {item.file_name && (
                    <>
                      {" "}
                      <button type="button" className="ac-link" onClick={() => file(attempt, item)}>
                        {item.file_name}
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </li>
        ))}
        {detail.snapshots.map((row) => (
          <li key={row.id}>
            Snapshot {row.version} · {row.state.toLowerCase()} · frozen by {row.requested_by}{" "}
            {formatDate(row.requested_at)}
            {row.approved_by ? ` · approved by ${row.approved_by} ${formatDate(row.approved_at)}` : ""}
            {row.same_person ? " · same person (trial practice)" : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The complaint's communications log: the questions to the reporter or others behind the report (T-G30). */
function CommunicationsLink({ complaintId }: { complaintId: string }) {
  const workspace = useContext(WorkspaceContext);
  return (
    <button
      type="button"
      className="ac-link"
      disabled={!workspace}
      onClick={() => workspace?.open("Complaints", communicationsTab(complaintId))}
    >
      Open the complaint's communications log
    </button>
  );
}
