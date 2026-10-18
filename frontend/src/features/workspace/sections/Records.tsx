import { useState } from "react";
import {
  AlarmClock,
  BadgeCheck,
  CalendarClock,
  ClipboardList,
  FileSearch,
  PenLine,
  ShieldAlert,
  TrendingDown,
  XCircle,
} from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { Drawer, Tabs, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { sectionAllowed, useCan, useFeatureSet, useWorkspace } from "../workspaceContext";
import { MVP_RECORDS_TABS, recordsAuditView, type MvpRecordsTab } from "../../../app/featureSet";
import { ReportsPanel } from "../../reports/ReportsPanel";
import { SignatureVerificationWorkspace } from "../../signature/SignatureVerificationWorkspace";
import {
  BOARD_SHOWS,
  DIRECTION,
  EFFECTIVENESS_BASIS,
  EFFECTIVENESS_LIMITS,
  EMPTY_SIGN,
  RECORDS_TABS,
  boardHeadline,
  boardPath,
  capaPath,
  capaRef,
  dueText,
  parseRecordsTab,
  planBody,
  planForm,
  planProblem,
  recurrenceText,
  replanning,
  signBody,
  signProblem,
  stateOf,
  type Board,
  type BoardShow,
  type CapaDetail,
  type CapaItem,
  type PlanForm,
  type Recurrence,
  type RecordsTab,
  type SignForm,
} from "../effectiveness";
import { Embedded, StatusBadge } from "./common";
import { ChipFilter, Hero, InlineError, Pager } from "./boardParts";
import { BasisLine, SignatureBasis } from "../../shared/Basis";
import { RiskFileInput } from "./RiskFile";
import { TrustSection } from "./Trust";

/**
 * Records: what goes to an inspector or a management review. Effectiveness checks: every CAPA's check, planned with
 * criteria and a date, reminded before the day, and signed with its result and the complaint recurrence seen. Under the
 * MVP feature set Records also holds what the parked sections did (app/featureSet.ts): the audit trail with each case's
 * timeline, replay, AI runs and integrity; the reports; and signature verification. Each is shown only to people whose
 * menu holds the section it came from.
 */
export function RecordsSection({ tab }: { tab?: string }) {
  const { session } = useWorkspace();
  const mvp = useFeatureSet() === "mvp";
  const [target] = useState(() => parseRecordsTab(tab));
  const [auditView] = useState(() => recordsAuditView(tab));
  const menu = (section: "Trust & Audit" | "Intelligence" | "Decisions") =>
    sectionAllowed(section, session?.allowed_menu, session?.business_permissions);
  const tabs: readonly (RecordsTab | MvpRecordsTab)[] = mvp
    ? MVP_RECORDS_TABS.filter(
        (item) =>
          (item !== "Audit trail" || menu("Trust & Audit")) &&
          (item !== "Reports" || menu("Intelligence")) &&
          (item !== "Verify a signature" || menu("Decisions")),
      )
    : RECORDS_TABS;
  const requested = (tab ?? "").split("?")[0];
  const [active, setActive] = useState<RecordsTab | MvpRecordsTab>(() =>
    (tabs as readonly string[]).includes(requested) ? (requested as MvpRecordsTab) : target.tab,
  );
  return (
    <Tabs tabs={tabs} active={active} onChange={setActive} label="Record sections">
      {active === "Effectiveness checks" && <EffectivenessBoard initialCapa={target.capa} />}
      {active === "Risk file input" && <RiskFileInput />}
      {active === "Audit trail" && <TrustSection tab={auditView ?? undefined} />}
      {active === "Reports" && <ReportsPanel />}
      {active === "Verify a signature" && (
        <Embedded>
          <SignatureVerificationWorkspace />
        </Embedded>
      )}
    </Tabs>
  );
}

function EffectivenessBoard({ initialCapa }: { initialCapa: string | null }) {
  const [show, setShow] = useState<BoardShow>("attention");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(initialCapa);
  const board = useResource<Board>(boardPath(show, page));
  const summary = board.data?.summary;
  const headline = boardHeadline(summary);
  const items = board.data?.items ?? [];
  const choose = (next: BoardShow) => {
    setShow(next);
    setPage(1);
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={board.data ? headline.tone : "neutral"}
        icon={<BadgeCheck size={28} />}
        eyebrow="CAPA effectiveness"
        title={headline.title}
        detail={headline.detail}
      />
      <div className="uw-cr-stats">
        <StatTile
          label="Overdue"
          value={summary ? summary.overdue : null}
          detail="Past the planned day"
          icon={<AlarmClock size={18} />}
          tone={summary?.overdue ? "critical" : undefined}
          onOpen={() => choose("attention")}
        />
        <StatTile
          label="Due within 14 days"
          value={summary ? summary.due_soon : null}
          detail="Reminders sent to quality"
          icon={<CalendarClock size={18} />}
          tone={summary?.due_soon ? "warning" : undefined}
          onOpen={() => choose("attention")}
        />
        <StatTile
          label="No check planned"
          value={summary ? summary.not_planned : null}
          detail={
            summary?.closed_without_check
              ? `${summary.closed_without_check} already closed`
              : "Plan what will show it worked"
          }
          icon={<ShieldAlert size={18} />}
          tone={summary?.closed_without_check ? "critical" : summary?.not_planned ? "serious" : undefined}
          onOpen={() => choose("attention")}
        />
        <StatTile
          label="Signed effective"
          value={summary ? summary.effective : null}
          detail={summary?.not_effective ? `${summary.not_effective} not effective` : "With the evidence seen"}
          icon={<BadgeCheck size={18} />}
          tone={summary?.not_effective ? "critical" : undefined}
          onOpen={() => choose("done")}
        />
      </div>
      <Panel eyebrow="Records" title="Effectiveness checks" source={board}>
        <div className="uw-cr-toolbar">
          <ChipFilter label="Which CAPAs" options={BOARD_SHOWS} value={show} onChange={choose} />
        </div>
        {items.length ? (
          <ul className="uw-cr-list">
            {items.map((item) => (
              <CapaCard key={item.capa.id} item={item} onOpen={() => setOpen(item.capa.id)} />
            ))}
          </ul>
        ) : (
          <Empty
            title={show === "attention" ? "Nothing needs attention" : "No CAPAs here"}
            detail="CAPAs opened from a signed decision or imported from your quality system appear here with their check."
          />
        )}
        <Pager page={page} pages={board.data?.pages ?? 1} onPage={setPage} />
        <p className="ac-note">
          The complaint recurrence before and after the action is counted from your records on the CAPA&apos;s product
          and its case&apos;s problem codes; it is not a statistical test. The person signing judges against the
          criteria.
        </p>
        <BasisLine ids={EFFECTIVENESS_BASIS} />
      </Panel>
      {open && <CheckDrawer capaId={open} onClose={() => setOpen(null)} onChanged={board.reload} />}
    </div>
  );
}

/** One CAPA on the board (exported for its unit test). */
export function CapaCard({ item, onOpen }: { item: CapaItem; onOpen: () => void }) {
  const state = stateOf(item.state);
  const ref = capaRef(item);
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${state.tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{ref}</strong>
          <span className="uw-cr-meta">
            {item.capa.product_name ?? "No product"}
            {item.capa.investigation?.business_id ? ` · case ${item.capa.investigation.business_id}` : ""}
          </span>
          <ToneBadge tone={state.tone} label={state.label} />
          <StatusBadge value={item.capa.status} />
        </div>
        <p className="uw-cr-text">{item.capa.title}</p>
        {item.closed_without_check && (
          <p className="uw-rw-flag">
            <ToneIcon tone="critical" size={14} /> Closed without an effectiveness check
          </p>
        )}
        {item.planned_on && item.state !== "EFFECTIVE" && item.state !== "NOT_EFFECTIVE" && (
          <p className="uw-cr-meta">
            <strong>{dueText(item)}</strong> · {formatDay(item.planned_on)}
            {item.plan_source === "SOURCE_SYSTEM" ? " · date from your quality system: confirm the plan" : ""}
          </p>
        )}
        {item.check?.criteria && <p className="uw-cr-meta">Criteria: {item.check.criteria}</p>}
        {item.check?.signed_at && (
          <div className="uw-cr-decision">
            <ToneBadge tone={state.tone} label={`Round ${item.check.round}: ${state.label.toLowerCase()}`} />
            <span className="uw-cr-meta">
              Signed by {item.check.signed_by} · {formatDate(item.check.signed_at)}
            </span>
            <q>{item.check.result_summary}</q>
          </div>
        )}
      </div>
      <div className="uw-cr-actions">
        <button type="button" className={item.state === "EFFECTIVE" ? "ac-secondary" : "ac-primary"} onClick={onOpen}>
          <ClipboardList size={15} aria-hidden="true" /> {item.state === "EFFECTIVE" ? "View check" : "Open check"}
        </button>
      </div>
    </li>
  );
}

/** The recurrence as two bars (before, since) with their numbers, and which way the rate moved. */
export function RecurrenceView({ recurrence }: { recurrence: Partial<Recurrence> | null | undefined }) {
  if (!recurrence || recurrence.available === false || !recurrence.before || !recurrence.since)
    return <p className="ac-muted">{recurrence?.reason ?? "Recurrence was not measured."}</p>;
  const { before, since } = recurrence;
  const top = Math.max(before.per_30_days, since.per_30_days, 0.1);
  const direction = DIRECTION[recurrence.direction ?? "NONE"] ?? DIRECTION.NONE;
  return (
    <figure className="uw-ef-recurrence" aria-label={recurrenceText(recurrence)}>
      <div className="uw-ef-bars">
        {[
          { label: "Before", value: before },
          { label: "Since", value: since },
        ].map((bar) => (
          <div className="uw-ef-bar" key={bar.label}>
            <span className="uw-ef-bar-label">{bar.label}</span>
            <span className="uw-ef-bar-track" aria-hidden="true">
              <span
                className={`uw-ef-bar-fill ${bar.label === "Since" ? `tone-${direction.tone}` : ""}`}
                style={{ width: `${Math.max(2, (bar.value.per_30_days / top) * 100)}%` }}
              />
            </span>
            <strong>{bar.value.per_30_days}</strong>
            <small>
              per 30 days · {bar.value.complaints} in {bar.value.days} days
            </small>
          </div>
        ))}
      </div>
      <figcaption>
        <ToneBadge tone={direction.tone} label={direction.label} />
        {recurrence.too_early && (
          <span className="uw-hint">Less than two weeks since the start: too early to judge.</span>
        )}
        <span className="ac-muted">
          {recurrence.problem_codes?.length
            ? `Problem codes ${recurrence.problem_codes.join(", ")}`
            : "Every problem on the product"}
          {recurrence.measured_from ? ` · measured from ${formatDay(recurrence.measured_from)}` : ""}. {recurrence.note}
        </span>
      </figcaption>
    </figure>
  );
}

function CheckDrawer({ capaId, onClose, onChanged }: { capaId: string; onClose: () => void; onChanged: () => void }) {
  const detail = useResource<CapaDetail>(capaPath(capaId));
  const data = detail.data;
  return (
    <Drawer title={data ? `${capaRef(data)}: effectiveness check` : "Effectiveness check"} onClose={onClose}>
      <Panel title={data?.capa.title ?? "Loading"} source={detail}>
        {data && (
          <CheckBody
            key={`${data.check?.id ?? "none"}:${data.check?.plan_version ?? 0}:${data.check?.status ?? ""}`}
            detail={data}
            onChanged={() => {
              detail.reload();
              onChanged();
            }}
          />
        )}
      </Panel>
    </Drawer>
  );
}

/** A CAPA's check: the recurrence, the rounds, the plan form and the signing form (exported for its unit test). */
export function CheckBody({ detail, onChanged }: { detail: CapaDetail; onChanged: () => void }) {
  const { notify, open, work } = useWorkspace();
  const canPlanRole = useCan("investigation.work");
  const canPlanQuality = useCan("quality.review");
  const canSignQuality = useCan("quality.review");
  const canSignApprover = useCan("decision.sign");
  const canPlan = (canPlanRole || canPlanQuality) && detail.can_plan;
  const canSign = (canSignQuality || canSignApprover) && detail.can_sign;
  const [plan, setPlan] = useState<PlanForm>(() => planForm(detail));
  const [planning, setPlanning] = useState(!detail.check);
  const [sign, setSign] = useState<SignForm>(EMPTY_SIGN);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ref = capaRef(detail);
  const state = stateOf(detail.state);
  const planIssue = planProblem(plan, detail);
  const signIssue = signProblem(sign);
  const early = detail.check?.status === "PLANNED" && detail.check.planned_on > new Date().toISOString().slice(0, 10);
  /** Send a change; true when it was saved. */
  const run = async (action: () => Promise<unknown>, done: string, fallback: string): Promise<boolean> => {
    setBusy(true);
    setError("");
    try {
      await action();
      notify(done);
      onChanged();
      return true;
    } catch (failure) {
      setError(errorText(failure, fallback));
      return false;
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="ca-form">
      <section className="ca-drawer-section">
        <h3>
          <ToneIcon tone={state.tone} /> {state.label}
          {detail.planned_on && detail.days_left !== null ? ` · ${dueText(detail)}` : ""}
        </h3>
        <p className="uw-cr-meta">
          {detail.capa.product_name ?? "No product"}
          {detail.capa.investigation?.business_id ? ` · case ${detail.capa.investigation.business_id}` : ""}
          {detail.capa.due_on ? ` · action due ${formatDay(detail.capa.due_on)}` : ""}
        </p>
        {detail.plan_source === "SOURCE_SYSTEM" && (
          <p className="uw-hint">
            Your quality system gives the check day {formatDay(detail.planned_on)} but no criteria: plan it here so the
            result can be signed.
          </p>
        )}
      </section>
      <section className="ca-drawer-section">
        <h3>
          <TrendingDown size={16} aria-hidden="true" /> Complaint recurrence
        </h3>
        <RecurrenceView recurrence={detail.recurrence} />
      </section>
      {detail.rounds.length > 0 && (
        <section className="ca-drawer-section">
          <h3>Rounds</h3>
          <ol className="uw-ef-rounds">
            {detail.rounds.map((round) => {
              const roundState = stateOf(round.status === "PLANNED" ? "SCHEDULED" : round.status);
              return (
                <li key={round.id}>
                  <ToneBadge
                    tone={roundState.tone}
                    label={`Round ${round.round}: ${round.status === "PLANNED" ? "planned" : roundState.label.toLowerCase()}`}
                  />
                  <span>
                    Check {formatDay(round.planned_on)} · measured from {formatDay(round.measured_from)} · planned by{" "}
                    {round.planned_by}
                  </span>
                  <span>Criteria: {round.criteria}</span>
                  {round.signed_at && (
                    <span>
                      Signed by {round.signed_by} ({round.signer_role ?? "—"}) · {formatDate(round.signed_at)}:{" "}
                      <q>{round.result_summary}</q> · {recurrenceText(round.evidence)}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
          {detail.rounds.some((round) => round.signed_at) && <SignatureBasis />}
        </section>
      )}
      {canPlan && !planning && (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={() => setPlanning(true)}>
            <CalendarClock size={15} aria-hidden="true" />{" "}
            {replanning(detail) ? "Change the plan" : detail.check ? "Plan the next round" : "Plan the check"}
          </button>
        </div>
      )}
      {canPlan && planning && (
        <form
          className="ca-form ca-drawer-section"
          onSubmit={(event) => {
            event.preventDefault();
            if (planIssue || busy) return;
            void run(
              () => send(`${capaPath(detail.capa.id)}/plan`, "PUT", planBody(plan, detail)),
              `${ref}: the effectiveness check is planned.`,
              "The plan was not saved.",
            ).then((saved) => saved && setPlanning(false));
          }}
        >
          <h3>{replanning(detail) ? "Change the plan" : "Plan the check"}</h3>
          <label className="ca-field">
            What will show the action worked
            <textarea
              rows={3}
              maxLength={EFFECTIVENESS_LIMITS.criteriaMax}
              value={plan.criteria}
              onChange={(event) => setPlan({ ...plan, criteria: event.target.value })}
            />
          </label>
          <div className="ca-form-grid">
            <label className="ca-field">
              Measure from
              <input
                type="date"
                value={plan.measuredFrom}
                onChange={(event) => setPlan({ ...plan, measuredFrom: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Check on
              <input
                type="date"
                value={plan.plannedOn}
                min={plan.measuredFrom || undefined}
                onChange={(event) => setPlan({ ...plan, plannedOn: event.target.value })}
              />
            </label>
          </div>
          {replanning(detail) && (
            <label className="ca-field">
              Reason for the change
              <input value={plan.reason} onChange={(event) => setPlan({ ...plan, reason: event.target.value })} />
            </label>
          )}
          {planIssue && <p className="uw-hint">{planIssue}</p>}
          <p className="ac-muted">
            The quality reviewers get a reminder {EFFECTIVENESS_LIMITS.dueSoonDays} days before the check day.
          </p>
          <div className="ca-action-row">
            {detail.check && (
              <button type="button" className="ac-secondary" onClick={() => setPlanning(false)}>
                Cancel
              </button>
            )}
            <button type="submit" className="ac-primary" disabled={busy || !!planIssue}>
              {busy ? "Saving…" : "Save the plan"}
            </button>
          </div>
        </form>
      )}
      {canSign && detail.check && (
        <form
          className="ca-form ca-drawer-section"
          onSubmit={(event) => {
            event.preventDefault();
            if (signIssue || busy || !detail.check) return;
            const version = detail.check.plan_version;
            void run(
              () => send(`${capaPath(detail.capa.id)}/result`, "POST", signBody(sign, version)),
              `${ref}: the effectiveness result is signed.`,
              "The result was not signed.",
            ).then((saved) => saved && setSign(EMPTY_SIGN));
          }}
        >
          <h3>
            <PenLine size={16} aria-hidden="true" /> Sign the result of round {detail.check.round}
          </h3>
          <p className="uw-cr-meta">Criteria: {detail.check.criteria}</p>
          {early && (
            <p className="uw-hint">
              The planned day is {formatDay(detail.check.planned_on)}: signing now records the result early.
            </p>
          )}
          <fieldset className="ca-field uw-rw-choice">
            <legend>Result</legend>
            <label className="ca-check">
              <input
                type="radio"
                name="result"
                checked={sign.result === "EFFECTIVE"}
                onChange={() => setSign({ ...sign, result: "EFFECTIVE" })}
              />
              <BadgeCheck size={15} aria-hidden="true" /> Effective: the criteria are met
            </label>
            <label className="ca-check">
              <input
                type="radio"
                name="result"
                checked={sign.result === "NOT_EFFECTIVE"}
                onChange={() => setSign({ ...sign, result: "NOT_EFFECTIVE" })}
              />
              <XCircle size={15} aria-hidden="true" /> Not effective: plan a further action
            </label>
          </fieldset>
          <label className="ca-field">
            What you found
            <textarea
              rows={3}
              maxLength={EFFECTIVENESS_LIMITS.summaryMax}
              value={sign.summary}
              placeholder="e.g. One occlusion complaint in 90 days against four before; the criterion of at most one is met"
              onChange={(event) => setSign({ ...sign, summary: event.target.value })}
            />
          </label>
          <div className="ca-form-grid">
            <label className="ca-field">
              Your password
              <input
                type="password"
                autoComplete="current-password"
                value={sign.password}
                onChange={(event) => setSign({ ...sign, password: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Authenticator code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={sign.code}
                onChange={(event) => setSign({ ...sign, code: event.target.value })}
              />
            </label>
          </div>
          {sign.result && sign.summary && signIssue && <p className="uw-hint">{signIssue}</p>}
          <p className="ac-muted">
            Your signature covers the criteria, the result, your summary and the recurrence shown above, and is in the
            audit trail.
          </p>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !!signIssue}>
              {busy ? "Signing…" : "Sign the result"}
            </button>
          </div>
        </form>
      )}
      {detail.state === "NOT_EFFECTIVE" && detail.capa.investigation && (
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-link"
            onClick={() => {
              const investigation = detail.capa.investigation;
              if (investigation) work.setInvestigationId(investigation.id, detail.capa.product_id);
              open("Investigations", "Workspace");
            }}
          >
            <FileSearch size={15} aria-hidden="true" /> Go to the case
          </button>
        </div>
      )}
      <InlineError text={error} />
    </div>
  );
}
