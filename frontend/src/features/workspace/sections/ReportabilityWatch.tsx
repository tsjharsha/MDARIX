import { useRef, useState } from "react";
import {
  AlarmClock,
  CheckCircle2,
  FileSearch,
  HelpCircle,
  Hourglass,
  Scale,
  ScanSearch,
  Settings2,
} from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { investigationRequestFor, useCan, useOpenInvestigation, useWorkspace } from "../workspaceContext";
import { recordId, type ComplaintsTab } from "../complaintReview";
import {
  AWARE_SOURCE,
  EMPTY_DECISION,
  REPORT_LIMITS,
  TRIGGER_LABELS,
  WATCH_SHOWS,
  clockText,
  decisionBody,
  decisionForm,
  decisionProblem,
  timelinessOf,
  watchHeadline,
  watchPath,
  watchStateOf,
  type DecisionForm,
  type WatchItem,
  type WatchList,
  type WatchShow,
} from "../reportability";
import { StatusBadge, countOf } from "./common";
import { ChipFilter, Hero, InlineError, Pager, ProductFilter } from "./boardParts";
import { Starters } from "./Starters";
import { REPORTABILITY_STARTERS, starterProblem } from "../starters";

/** Whether the signed-in role may record a reportability decision (the server's rule). */
function useCanDecide() {
  const review = useCan("regulatory.review");
  const approve = useCan("regulatory.approve");
  return review || approve;
}

const todayIso = () => new Date().toISOString().slice(0, 10);

/**
 * Complaints › Reportability: every complaint that reports a death, a serious injury or a malfunction (or a patient
 * whose outcome is unknown), with its reporting clocks against the organization's own windows, most urgent first. A
 * person records the decision; MDARIX keeps the clock and never submits a report.
 */
export function ReportabilityWatch({ onOpenTab }: { onOpenTab: (tab: ComplaintsTab) => void }) {
  const canEditWindows = useCan("regulatory.approve");
  const [show, setShow] = useState<WatchShow>("open");
  const [product, setProduct] = useState("");
  const [page, setPage] = useState(1);
  const [deciding, setDeciding] = useState<WatchItem | null>(null);
  const list = useResource<WatchList>(watchPath(show, product, page));
  const summary = list.data?.summary;
  const headline = watchHeadline(summary);
  const items = list.data?.items ?? [];
  const choose = (next: WatchShow) => {
    setShow(next);
    setPage(1);
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={list.data ? headline.tone : "neutral"}
        icon={<AlarmClock size={28} />}
        eyebrow="Reportability watch"
        title={headline.title}
        detail={headline.detail}
      />
      {summary && !summary.configured && (
        <div className="ac-message tone-critical uw-rw-callout" role="status">
          <Settings2 size={16} aria-hidden="true" />
          <span>
            <strong>No reporting windows yet.</strong> Enter the windows from your procedure (FDA, EU or others) and
            every complaint here gets its due date.
          </span>
          <button type="button" className="ac-secondary" onClick={() => onOpenTab("Reporting windows")}>
            {canEditWindows ? "Enter reporting windows" : "See reporting windows"}
          </button>
        </div>
      )}
      {summary && summary.held_on_second_look > 0 && (
        <div className="ac-message tone-critical uw-rw-callout" role="status">
          <ScanSearch size={16} aria-hidden="true" />
          <span>
            <strong>
              {countOf(summary.held_on_second_look, "cancelled record or inquiry", "cancelled records or inquiries")}
            </strong>{" "}
            {summary.held_on_second_look === 1 ? "reports" : "report"} a death, a serious injury or a malfunction.
            Decide on the second look whether each is a complaint: a confirmed one joins this watch with its clock.
          </span>
          <button type="button" className="ac-secondary" onClick={() => onOpenTab("Second look")}>
            Open the second look
          </button>
        </div>
      )}
      <div className="uw-cr-stats">
        <StatTile
          label="Overdue"
          value={summary ? summary.overdue : null}
          detail="Past the reporting window"
          icon={<AlarmClock size={18} />}
          tone={summary?.overdue ? "critical" : undefined}
          onOpen={() => choose("overdue")}
        />
        <StatTile
          label="Due soon"
          value={summary ? summary.due_soon : null}
          detail="Within days of the window"
          icon={<Hourglass size={18} />}
          tone={summary?.due_soon ? "warning" : undefined}
          onOpen={() => choose("due_soon")}
        />
        <StatTile
          label="Missing answers"
          value={summary ? summary.follow_up : null}
          detail="Follow up before deciding"
          icon={<HelpCircle size={18} />}
          tone={summary?.follow_up ? "warning" : undefined}
          onOpen={() => choose("follow_up")}
        />
        <StatTile
          label="Decided inside the window"
          value={summary ? `${summary.decided_in_window} of ${summary.decided_in_window + summary.decided_late}` : null}
          detail={summary?.decided_late ? `${summary.decided_late} after the window` : "Timeliness of decisions"}
          icon={<CheckCircle2 size={18} />}
          tone={summary?.decided_late ? "serious" : undefined}
          onOpen={() => choose("decided")}
        />
      </div>
      <Panel
        eyebrow="Reportability"
        title={
          show === "decided" ? "Decided complaints, latest first" : "Complaints needing a decision, most urgent first"
        }
        source={list}
      >
        <div className="uw-cr-toolbar">
          <ChipFilter
            label="Which complaints"
            options={WATCH_SHOWS}
            value={show}
            counts={{
              open: summary?.open,
              overdue: summary?.overdue,
              due_soon: summary?.due_soon,
              follow_up: summary?.follow_up,
              decided: summary?.decided,
            }}
            onChange={choose}
          />
          <ProductFilter
            value={product}
            onChange={(value) => {
              setProduct(value);
              setPage(1);
            }}
          />
        </div>
        {list.data?.truncated && (
          <p className="uw-hint">Only the first 20,000 complaints were read. Choose a product to see all of its own.</p>
        )}
        {items.length ? (
          <ul className="uw-cr-list">
            {items.map((item) => (
              <WatchCard key={item.id} item={item} onDecide={() => setDeciding(item)} />
            ))}
          </ul>
        ) : (
          <Empty
            title={show === "decided" ? "No decisions yet" : "Nothing waits for a decision"}
            detail="Complaints reporting a death, a serious injury or a malfunction, or a patient whose outcome is unknown, appear here."
          />
        )}
        <Pager page={page} pages={list.data?.pages ?? 1} onPage={setPage} />
        <p className="ac-note">
          The windows come from your procedure; MDARIX keeps the clock and never decides reportability or submits a
          report. Windows that rest on a judgment (an FDA 5-work-day report, an EU serious public health threat) are
          applied by your reviewer.
        </p>
      </Panel>
      {deciding && <DecisionDrawer item={deciding} onClose={() => setDeciding(null)} onDecided={list.reload} />}
    </div>
  );
}

/** One complaint on the watch (exported for its unit test). */
export function WatchCard({ item, onDecide }: { item: WatchItem; onDecide: () => void }) {
  const canDecide = useCanDecide();
  const openInvestigation = useOpenInvestigation();
  const state = watchStateOf(item.state);
  const request = investigationRequestFor(item);
  const name = recordId(item);
  const timeliness = timelinessOf(item.decision);
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${state.tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{name}</strong>
          <span className="uw-cr-meta">
            {item.product_name ?? "No product"}
            {item.version ? ` · ${item.version}` : ""} · {item.country ?? "Country not recorded"}
          </span>
          <ToneBadge tone={state.tone} label={state.label} />
          <StatusBadge value={item.status} />
        </div>
        {item.state !== "DECIDED" && (
          <div className={`uw-rw-clock tone-${state.tone}`}>
            <strong>{item.binding ? clockText(item.binding) : state.label}</strong>
            {item.binding && (
              <span>
                Due by {formatDay(item.binding.due_date)} · {item.binding.window}
              </span>
            )}
            {item.aware_date && (
              <span>
                Aware {formatDay(item.aware_date)} by the {AWARE_SOURCE[item.aware_source ?? ""] ?? "records"} ·{" "}
                {countOf(item.days_since_aware ?? 0, "day")} ago
              </span>
            )}
          </div>
        )}
        <ul className="uw-cr-chips" aria-label="What it reports">
          {item.triggers.map((trigger) => (
            <li key={trigger} className={`uw-cr-chip tone-${trigger === "MALFUNCTION" ? "serious" : "critical"}`}>
              <ToneIcon tone={trigger === "MALFUNCTION" ? "serious" : "critical"} size={13} /> {TRIGGER_LABELS[trigger]}
            </li>
          ))}
          {item.clocks.slice(1).map((clock) => (
            <li key={clock.window} className="uw-cr-chip">
              Also: {clock.window} · {clockText(clock)}
            </li>
          ))}
        </ul>
        {item.follow_ups.length > 0 && (
          <ul className="uw-rw-followups" aria-label="Missing answers">
            {item.follow_ups.map((flag) => (
              <li key={flag.code}>
                <HelpCircle size={14} aria-hidden="true" /> {flag.label}
              </li>
            ))}
          </ul>
        )}
        {item.description && <p className="uw-cr-text uw-cr-clip-3">{item.description}</p>}
        {item.case && (
          <p className="uw-cr-meta">
            In case {item.case.case.business_id ?? "—"}
            {item.case.review
              ? ` · regulatory review ${item.case.review.business_id ?? ""}: ${
                  item.case.review.status === "COMPLETED"
                    ? (item.case.review.outcome ?? "completed").toLowerCase().replace(/_/g, " ")
                    : item.case.review.status.toLowerCase().replace(/_/g, " ")
                }`
              : " · no regulatory review yet"}
          </p>
        )}
        {item.decision && (
          <div className="uw-cr-decision">
            <ToneBadge
              tone={item.decision.decision === "REPORTED" ? "good" : "neutral"}
              label={
                item.decision.decision === "REPORTED"
                  ? `Reported${item.decision.report_reference ? ` · ${item.decision.report_reference}` : ""}`
                  : "Not reportable"
              }
            />
            {timeliness && <ToneBadge tone={timeliness.tone} label={timeliness.label} />}
            <span className="uw-cr-meta">
              {item.decision.decided_by} · {formatDate(item.decision.decided_at)}
              {item.decision.reported_on ? ` · filed ${formatDay(item.decision.reported_on)}` : ""}
            </span>
            <q>{item.decision.rationale}</q>
          </div>
        )}
        {item.settled_by_case && !item.decision && (
          <p className="uw-cr-meta">Settled by the completed regulatory review of its case.</p>
        )}
      </div>
      <div className="uw-cr-actions">
        {canDecide && (
          <button
            type="button"
            className={item.decision ? "ac-secondary" : "ac-primary"}
            onClick={onDecide}
            aria-label={`${name}: ${item.decision ? "change the reportability decision" : "record the reportability decision"}`}
          >
            <Scale size={15} aria-hidden="true" /> {item.decision ? "Change decision" : "Record decision"}
          </button>
        )}
        {openInvestigation && request && !item.case && (
          <button type="button" className="ac-link" onClick={() => openInvestigation(request)}>
            <FileSearch size={15} aria-hidden="true" /> Open investigation
          </button>
        )}
      </div>
    </li>
  );
}

function DecisionDrawer({ item, onClose, onDecided }: { item: WatchItem; onClose: () => void; onDecided: () => void }) {
  const { notify } = useWorkspace();
  const [form, setForm] = useState<DecisionForm>(() => (item.decision ? decisionForm(item.decision) : EMPTY_DECISION));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = recordId(item);
  // A starter begins the rationale; the person finishes it in their own words (workspace/starters.ts).
  const starters = form.decision ? REPORTABILITY_STARTERS[form.decision] : [];
  const problem = decisionProblem(form, todayIso(), item.aware_date) ?? starterProblem(form.rationale, starters);
  const field = useRef<HTMLTextAreaElement>(null);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/complaints/${encodeURIComponent(item.id)}/reportability`, "POST", decisionBody(form));
      notify(`${name}: reportability decision recorded.`);
      onDecided();
      onClose();
    } catch (failure) {
      setError(errorText(failure, "The decision was not recorded."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={`${name}: reportability decision`} onClose={onClose}>
      <form className="ca-form" onSubmit={submit}>
        <section className="ca-drawer-section">
          <h3>{item.binding ? clockText(item.binding) : watchStateOf(item.state).label}</h3>
          <p>
            {item.triggers.length
              ? `Reports ${item.triggers.map((trigger) => TRIGGER_LABELS[trigger].toLowerCase()).join(", ")}`
              : "A patient was involved"}
            {item.country ? ` in ${item.country}` : ""}
            {item.aware_date ? `; aware ${formatDay(item.aware_date)}` : ""}.
            {item.binding ? ` ${item.binding.window}: due ${formatDay(item.binding.due_date)}.` : ""}
          </p>
          {item.follow_ups.length > 0 && (
            <p className="uw-hint">Missing answers: {item.follow_ups.map((flag) => flag.label).join("; ")}.</p>
          )}
        </section>
        <fieldset className="ca-field uw-rw-choice">
          <legend>Decision</legend>
          <label className="ca-check">
            <input
              type="radio"
              name="decision"
              checked={form.decision === "REPORTED"}
              onChange={() => setForm({ ...form, decision: "REPORTED" })}
            />
            Reported to the authority
          </label>
          <label className="ca-check">
            <input
              type="radio"
              name="decision"
              checked={form.decision === "NOT_REPORTABLE"}
              onChange={() => setForm({ ...form, decision: "NOT_REPORTABLE" })}
            />
            Not reportable
          </label>
        </fieldset>
        {form.decision === "REPORTED" && (
          <div className="ca-form-grid">
            <label className="ca-field">
              Report reference
              <input
                value={form.reference}
                maxLength={REPORT_LIMITS.referenceMax}
                placeholder="e.g. MDR or vigilance report number"
                onChange={(event) => setForm({ ...form, reference: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Filed on
              <input
                type="date"
                value={form.reportedOn}
                max={todayIso()}
                min={item.aware_date ?? undefined}
                onChange={(event) => setForm({ ...form, reportedOn: event.target.value })}
              />
            </label>
          </div>
        )}
        <label className="ca-field">
          Rationale
          <textarea
            ref={field}
            rows={4}
            maxLength={REPORT_LIMITS.reasonMax}
            value={form.rationale}
            placeholder={
              form.decision === "NOT_REPORTABLE"
                ? "e.g. The malfunction could not cause or contribute to a death or serious injury (procedure QP-08, step 4)"
                : "e.g. Death reported by the user facility; reported within 30 days"
            }
            onChange={(event) => setForm({ ...form, rationale: event.target.value })}
          />
        </label>
        <Starters
          starters={starters}
          onPick={(starter) => {
            setForm({ ...form, rationale: starter });
            window.setTimeout(() => field.current?.focus(), 0);
          }}
        />
        {form.decision && !form.rationale && (
          <p className="ac-muted">In your own words: why this event is, or is not, reportable.</p>
        )}
        {form.decision && form.rationale && problem && <p className="uw-hint">{problem}</p>}
        <InlineError text={error} />
        <p className="ac-muted">
          MDARIX does not submit reports: record what was filed in the authority&apos;s system. The decision and its
          rationale are in the audit trail.
        </p>
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Saving…" : "Record decision"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}
