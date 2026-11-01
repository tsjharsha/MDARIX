import { useState } from "react";
import { CheckCircle2, FileWarning, GitBranch, Inbox, Link2, ShieldAlert, Timer, Wrench } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { ImdrfCodes, RecordOrigin } from "./ImportReports";
import { formatDay } from "../../../app/dates";
import { useCan, useWorkspace } from "../workspaceContext";
import { countOf } from "./common";
import { ChipFilter, Hero, InlineError, Pager } from "./boardParts";
import { TrainingPanel } from "./MarketAssessment";
import { EscalateButton } from "./Triage";
import {
  BRANCH_LABELS,
  BRANCH_TONES,
  boardPath,
  covers,
  dispositionPath,
  formOf,
  handsOnText,
  signBody,
  signProblem,
  treeStates,
  trendPath,
  type BoardItem,
  type Branch,
  type DispositionBoard,
  type DispositionForm,
  type DispositionScreen,
  type DispositionVersion,
  type QuestionState,
} from "../disposition";

/** The second look's rule: triage, opening cases or quality review may sign a disposition. */
function useCanDispose() {
  const triage = useCan("signal.triage");
  const create = useCan("investigation.create");
  const quality = useCan("quality.review");
  return triage || create || quality;
}

const SHOWS = [
  { value: "waiting" as const, label: "Waiting for a disposition" },
  { value: "signed" as const, label: "Signed" },
];

/**
 * Complaints › Dispositions: the open complaints still waiting for a disposition (newest first, the routine path
 * marked where it is offered) and the signed ones. Each opens the decision tree: escalation trigger, known issue,
 * service level, escalation by choice; one signature. The disposition never replaces the reportability assessment.
 */
export function Dispositions() {
  const [show, setShow] = useState<"waiting" | "signed">("waiting");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<BoardItem | null>(null);
  const list = useResource<DispositionBoard>(boardPath(show, page));
  const summary = list.data?.summary;
  const items = list.data?.items ?? [];
  const choose = (next: "waiting" | "signed") => {
    setShow(next);
    setPage(1);
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={summary?.waiting ? "warning" : "good"}
        icon={<GitBranch size={28} />}
        eyebrow="Dispositions"
        title={
          summary
            ? summary.waiting
              ? `${countOf(summary.waiting, "complaint")} waiting for a disposition`
              : "Every open complaint has a disposition"
            : "Dispositions"
        }
        detail="Most complaints are resolved at service level with a documented reason (ISO 13485 clause 8.2.2). A complaint that meets an escalation trigger opens a case."
      />
      <div className="uw-cr-stats">
        <StatTile
          label="Waiting"
          value={summary ? summary.waiting : null}
          detail="Open, in no case, no disposition yet"
          icon={<Inbox size={18} />}
          tone={summary?.waiting ? "warning" : undefined}
          onOpen={() => choose("waiting")}
        />
        <StatTile
          label="Resolved at service level"
          value={summary ? summary.by_branch.SERVICE_LEVEL : null}
          detail="Signed, with the reason no investigation is needed"
          icon={<Wrench size={18} />}
          onOpen={() => choose("signed")}
        />
        <StatTile
          label="Known issues linked"
          value={summary ? summary.by_branch.KNOWN_ISSUE : null}
          detail="Added to an open case's scope"
          icon={<Link2 size={18} />}
          onOpen={() => choose("signed")}
        />
        <StatTile
          label="Escalated to a case"
          value={summary ? summary.by_branch.ESCALATED_BY_TRIGGER + summary.by_branch.ESCALATED_BY_CHOICE : null}
          detail={summary ? `${summary.by_branch.ESCALATED_BY_TRIGGER} by a trigger` : "By trigger or by choice"}
          icon={<ShieldAlert size={18} />}
          onOpen={() => choose("signed")}
        />
      </div>
      <Panel
        eyebrow="Dispositions"
        title={show === "signed" ? "Signed dispositions, latest first" : "Complaints waiting, newest first"}
        source={list}
      >
        <div className="uw-cr-toolbar">
          <ChipFilter
            label="Which complaints"
            options={SHOWS}
            value={show}
            counts={{ waiting: summary?.waiting, signed: summary?.signed }}
            onChange={choose}
          />
        </div>
        {items.length ? (
          <ul className="uw-cr-list">
            {items.map((item) => (
              <DispositionCard key={item.id} item={item} onOpen={() => setOpen(item)} />
            ))}
          </ul>
        ) : (
          <Empty
            title={show === "signed" ? "No disposition signed yet" : "Nothing waits for a disposition"}
            detail="Open complaints that are in no case appear here until a person signs how each is resolved."
          />
        )}
        <Pager page={page} pages={list.data?.pages ?? 1} onPage={setPage} />
      </Panel>
      {open && (
        <DispositionDrawer
          complaintId={open.id}
          title={open.ref}
          onClose={() => setOpen(null)}
          onChanged={() => list.reload()}
        />
      )}
    </div>
  );
}

export function DispositionCard({ item, onOpen }: { item: BoardItem; onOpen: () => void }) {
  const signed = item.disposition;
  // The branch the tree is expected to take, in its order: a trigger, then a known issue, then service level.
  const known = !item.triggers.length && item.known_issue.length > 0;
  const tone = signed
    ? BRANCH_TONES[signed.branch]
    : item.triggers.length
      ? "critical"
      : known
        ? BRANCH_TONES.KNOWN_ISSUE
        : item.routine_offered
          ? "good"
          : "warning";
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{item.ref}</strong>
          {item.complaint_identifier !== item.ref && (
            <span className="uw-cr-meta">Source ID {item.complaint_identifier}</span>
          )}
          <span className="uw-cr-meta">
            {item.product_name ?? "No product"}
            {item.version ? ` · ${item.version}` : ""}
            {item.received_date ? ` · received ${formatDay(item.received_date)}` : ""}
          </span>
          {signed ? (
            <ToneBadge tone={tone} label={signed.branch_label} />
          ) : item.triggers.length ? (
            <ToneBadge
              tone="critical"
              label={`Trigger: ${item.triggers.join(", ").replace(/_/g, " ").toLowerCase()}`}
            />
          ) : known ? (
            <ToneBadge tone={BRANCH_TONES.KNOWN_ISSUE} label="Known issue" />
          ) : item.routine_offered ? (
            <ToneBadge tone="good" label="Routine path" />
          ) : (
            <ToneBadge tone="warning" label="Standard path" />
          )}
          {item.on_watch && <ToneBadge tone="serious" label="On the reportability watch" />}
        </div>
        {item.description && <q className="uw-cr-text uw-cr-clip">{item.description}</q>}
        {item.known_issue.length > 0 && !signed && (
          <p className="uw-cr-meta">Open case with the same problem or lot: {item.known_issue.join(", ")}</p>
        )}
        {signed && (
          <p className="uw-cr-meta">
            Version {signed.version} · {signed.signed_by} · {formatDate(signed.signed_at)}
            {signed.investigation_ref ? ` · case ${signed.investigation_ref}` : ""}
            {signed.attribution_label ? ` · ${signed.attribution_label}` : ""}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className={signed ? "ac-secondary" : "ac-primary"} onClick={onOpen}>
            {signed
              ? "Open the disposition"
              : known
                ? "Link to the open case"
                : item.routine_offered && !item.triggers.length
                  ? "Close on the routine path"
                  : "Decide the disposition"}
          </button>
          {!signed && <EscalateButton kind="COMPLAINT" id={item.id} />}
        </div>
      </div>
    </li>
  );
}

const STATE_LABELS: Record<QuestionState, { label: string; tone: "good" | "neutral" | "critical" | "warning" }> = {
  taken: { label: "This branch", tone: "good" },
  no: { label: "No", tone: "neutral" },
  refused: { label: "Refused: a trigger is met", tone: "critical" },
  open: { label: "Not reached", tone: "neutral" },
};

/** The decision tree for one complaint, read now from the server, and its one signature (exported for tests). */
export function DispositionDrawer({
  complaintId,
  title,
  onClose,
  onChanged,
}: {
  complaintId: string;
  title: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const screen = useResource<DispositionScreen>(dispositionPath(complaintId));
  return (
    <Drawer title={`${title}: disposition`} onClose={onClose}>
      {screen.state === "error" && <InlineError text="The disposition could not be read." />}
      {screen.data && (
        <DispositionPanel
          key={`${screen.data.version}-${screen.data.trigger_codes.join()}`}
          screen={screen.data}
          onSigned={() => {
            screen.reload();
            onChanged();
          }}
          onTrained={screen.reload}
        />
      )}
    </Drawer>
  );
}

export function DispositionPanel({
  screen,
  onSigned,
  onTrained,
}: {
  screen: DispositionScreen;
  onSigned: () => void;
  onTrained: () => void;
}) {
  const canSign = useCanDispose();
  const { notify, open } = useWorkspace();
  const [form, setForm] = useState<DispositionForm>(() => formOf(screen));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // A signed disposition is shown as signed; changing it is a new version, opened on request.
  const [changing, setChanging] = useState(!screen.current);
  const complaint = screen.complaint;
  const triggered = screen.trigger_codes.length > 0;
  const missing = screen.training_required ? screen.training.filter((item) => item.state !== "CURRENT") : [];
  const problem = signProblem(screen, form, !missing.length);
  const states = treeStates(screen, form.branch);
  const set = (patch: Partial<DispositionForm>) => setForm((current) => ({ ...current, ...patch }));
  const setRecord = (key: keyof DispositionForm["record"], value: string) =>
    setForm((current) => ({ ...current, record: { ...current.record, [key]: value } }));
  const choose = (branch: Branch) => set({ branch });
  const sign = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await send(dispositionPath(complaint.id, "/sign"), "POST", signBody(screen, form));
      notify(`${complaint.ref}: the disposition is signed.`);
      onSigned();
    } catch (failure) {
      setError(errorText(failure, "The disposition was not signed."));
    } finally {
      setBusy(false);
    }
  };
  const proposed = screen.classification;
  return (
    <div className="uw-dp">
      <section className="ca-drawer-section">
        <p>
          {complaint.product_name ?? "No product"}
          {complaint.version ? ` · ${complaint.version}` : ""}
          {complaint.lot ? ` · lot ${complaint.lot}` : ""}
          {complaint.source ? ` · source ${complaint.source}` : ""}
          {complaint.awareness_date ? ` · aware ${formatDay(complaint.awareness_date)}` : ""}
        </p>
        {complaint.description && <q className="uw-cr-text">{complaint.description}</q>}
        {screen.practice_label && <p className="uw-ma-practice">{screen.practice_label}</p>}
        <ImdrfCodes problemCode={complaint.problem_code} />
        <RecordOrigin
          entity="complaints"
          recordId={complaint.id}
          onOpenReport={(importRef) => open("Import data", `report=${importRef}`)}
        />
      </section>

      {screen.current && <SignedDisposition version={screen.current} />}
      {screen.current && (
        <ul className="uw-dp-basis">
          <li>
            Classification: {screen.use_environments[proposed.use_environment] ?? proposed.use_environment}
            {proposed.use_environment_text ? ` (${proposed.use_environment_text})` : ""} ·{" "}
            {screen.user_types[proposed.user_type] ?? proposed.user_type}
            {proposed.state === "CONFIRMED"
              ? `, confirmed by ${proposed.confirmed_by} under ${proposed.coding_criteria_version}`
              : ", proposed"}
          </li>
          {screen.current.routine_path && screen.routine.markets.length > 0 && (
            <li>
              Market conclusions on the routine basis: not reportable for{" "}
              {screen.routine.markets.map((market) => market.label).join(", ")}
            </li>
          )}
        </ul>
      )}
      {screen.reportability.on_watch && (
        <p className="uw-hint">
          The disposition never replaces the reportability assessment:{" "}
          {screen.reportability.settled
            ? "its markets are concluded."
            : "its market assessment is still due under Complaints › Reportability."}
        </p>
      )}

      {screen.current && !changing && canSign && (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={() => setChanging(true)}>
            Sign a new version
          </button>
        </div>
      )}
      {changing && (
        <>
          <section className={`ca-drawer-section uw-dp-path tone-${screen.routine.offered ? "good" : "warning"}`}>
            {screen.routine.offered ? (
              <>
                <h4>
                  <Timer size={15} aria-hidden="true" /> Routine path: one screen, one signature
                </h4>
                <ul className="uw-dp-basis">
                  {screen.routine.markets.map((market) => (
                    <li key={market.market}>
                      <strong>{market.label}</strong>: not reportable. {screen.routine.basis}.
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <h4>Standard path</h4>
                <ul className="uw-dp-basis">
                  {screen.routine.blocked.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <form onSubmit={sign}>
            <ol className="uw-dp-tree" aria-label="Decision tree">
              <li className={`uw-dp-step is-${states.TRIGGER === "taken" ? "taken" : "no"}`}>
                <QuestionHead number={1} text="Is an escalation trigger met?" state={triggered ? "taken" : "no"} />
                {triggered ? (
                  <ul className="uw-dp-facts">
                    {screen.triggers.map((item) => (
                      <li key={`${item.code}-${item.field}`}>
                        <ToneBadge tone="critical" label={item.code} /> {item.fact}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="uw-cr-meta">No: none of the five starter triggers is met.</p>
                )}
                <details className="uw-dp-show">
                  <summary>Show the triggers</summary>
                  <dl>
                    {screen.trigger_rules.map((rule) => (
                      <div key={rule.code}>
                        <dt>{rule.label}</dt>
                        <dd>{rule.definition}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
                {triggered && (
                  <label className="ca-field">
                    Why the case is needed
                    <textarea
                      rows={2}
                      value={form.rationale}
                      onChange={(event) => set({ rationale: event.target.value })}
                    />
                  </label>
                )}
              </li>

              <li className={`uw-dp-step is-${states.KNOWN_ISSUE}`}>
                <QuestionHead number={2} text="Is it a known issue?" state={states.KNOWN_ISSUE} />
                {screen.candidates.length ? (
                  <fieldset className="uw-dp-choices" disabled={triggered}>
                    <legend className="uw-cr-meta">
                      Open cases with the same product and problem code, or the same lot
                    </legend>
                    {screen.candidates.map((item) => (
                      <label key={item.id} className="uw-dp-choice">
                        <input
                          type="radio"
                          name="branch"
                          checked={form.branch === "KNOWN_ISSUE" && form.caseId === item.id}
                          onChange={() => set({ branch: "KNOWN_ISSUE", caseId: item.id })}
                        />
                        <span>
                          <strong>{item.identifier}</strong> {item.question}{" "}
                          <span className="uw-cr-meta">({item.match.join(", ")})</span>
                        </span>
                      </label>
                    ))}
                  </fieldset>
                ) : (
                  <p className="uw-cr-meta">
                    No: no open case holds the same product and problem code, or the same lot.
                  </p>
                )}
                {!triggered && form.branch === "KNOWN_ISSUE" && (
                  <label className="ca-field">
                    Why it is the same issue
                    <textarea
                      rows={2}
                      value={form.rationale}
                      onChange={(event) => set({ rationale: event.target.value })}
                    />
                  </label>
                )}
                {!triggered && screen.candidates.length > 0 && form.branch !== "KNOWN_ISSUE" && (
                  <label className="ca-field">
                    Why it is not that known issue
                    <input
                      value={form.notKnownReason}
                      onChange={(event) => set({ notKnownReason: event.target.value })}
                    />
                  </label>
                )}
              </li>

              <li className={`uw-dp-step is-${states.SERVICE_LEVEL}`}>
                <QuestionHead number={3} text="Was it resolved at service level?" state={states.SERVICE_LEVEL} />
                <label className="uw-dp-choice">
                  <input
                    type="radio"
                    name="branch"
                    disabled={triggered}
                    checked={form.branch === "SERVICE_LEVEL"}
                    onChange={() => choose("SERVICE_LEVEL")}
                  />
                  <span>Yes, resolved at service level</span>
                </label>
                {form.branch === "SERVICE_LEVEL" && !triggered && (
                  <div className="uw-dp-record">
                    <label className="ca-field">
                      Troubleshooting done
                      <input
                        value={form.record.troubleshooting}
                        onChange={(event) => setRecord("troubleshooting", event.target.value)}
                      />
                    </label>
                    <div className="ca-form-grid">
                      <label className="ca-field">
                        Correction
                        <select
                          value={form.record.correction_type}
                          onChange={(event) => setRecord("correction_type", event.target.value)}
                        >
                          <option value="">Choose…</option>
                          {Object.entries(screen.corrections).map(([code, label]) => (
                            <option key={code} value={code}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="ca-field">
                        Service ticket
                        <input
                          value={form.record.service_ticket}
                          onChange={(event) => setRecord("service_ticket", event.target.value)}
                        />
                      </label>
                    </div>
                    <label className="ca-field">
                      What was done
                      <input
                        value={form.record.correction}
                        onChange={(event) => setRecord("correction", event.target.value)}
                      />
                    </label>
                    <label className="ca-field">
                      Result
                      <input value={form.record.result} onChange={(event) => setRecord("result", event.target.value)} />
                    </label>
                    <label className="ca-field">
                      Why no investigation is needed ({screen.no_investigation_clause})
                      <textarea
                        rows={2}
                        value={form.record.no_investigation_rationale}
                        onChange={(event) => setRecord("no_investigation_rationale", event.target.value)}
                      />
                    </label>
                    <fieldset className="uw-dp-choices">
                      <legend>Root-cause attribution</legend>
                      <div className="uw-dp-inline">
                        {screen.attributions.map((item) => (
                          <label key={item.code} className="uw-dp-choice">
                            <input
                              type="radio"
                              name="attribution"
                              checked={form.attribution === item.code}
                              onChange={() => set({ attribution: item.code })}
                            />
                            {item.label}
                          </label>
                        ))}
                      </div>
                      <details className="uw-dp-show">
                        <summary>Show definitions</summary>
                        <dl>
                          {screen.attributions.map((item) => (
                            <div key={item.code}>
                              <dt>{item.label}</dt>
                              <dd>{item.definition}</dd>
                            </div>
                          ))}
                        </dl>
                      </details>
                      {form.attribution === "UNDETERMINED" && (
                        <label className="ca-field">
                          Why the cause cannot be attributed
                          <input
                            value={form.attributionReason}
                            onChange={(event) => set({ attributionReason: event.target.value })}
                          />
                        </label>
                      )}
                    </fieldset>
                  </div>
                )}
              </li>

              <li className={`uw-dp-step is-${states.CHOICE}`}>
                <QuestionHead number={4} text="Otherwise: escalate by choice" state={states.CHOICE} />
                <label className="uw-dp-choice">
                  <input
                    type="radio"
                    name="branch"
                    disabled={triggered}
                    checked={form.branch === "ESCALATED_BY_CHOICE"}
                    onChange={() => choose("ESCALATED_BY_CHOICE")}
                  />
                  <span>Escalate: open a case</span>
                </label>
                {form.branch === "ESCALATED_BY_CHOICE" && (
                  <label className="ca-field">
                    Why you escalate it
                    <textarea
                      rows={2}
                      value={form.rationale}
                      onChange={(event) => set({ rationale: event.target.value })}
                    />
                  </label>
                )}
              </li>
            </ol>

            <section className="ca-drawer-section">
              <h4>Classification for trends</h4>
              <div className="ca-form-grid">
                <ClassificationField
                  label="Use environment"
                  options={screen.use_environments}
                  value={form.useEnvironment}
                  text={form.useEnvironmentText}
                  source={proposed.source_values.use_environment}
                  onChange={(value, text) => set({ useEnvironment: value, useEnvironmentText: text })}
                />
                <ClassificationField
                  label="User type"
                  options={screen.user_types}
                  value={form.userType}
                  text={form.userTypeText}
                  source={proposed.source_values.user_type}
                  onChange={(value, text) => set({ userType: value, userTypeText: text })}
                />
              </div>
              <p className="uw-cr-meta">
                {proposed.state === "CONFIRMED"
                  ? `Confirmed by ${proposed.confirmed_by}`
                  : "Proposed: your signature confirms it"}{" "}
                · coding criteria {screen.coding_criteria.version} · Unknown is never guessed
              </p>
              <details className="uw-dp-show">
                <summary>Show the coding criteria</summary>
                <ul>
                  {screen.coding_criteria.rules.map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ul>
              </details>
            </section>

            {missing.length > 0 && (
              <TrainingPanel
                documents={missing}
                colleagues={screen.trained_colleagues}
                required
                onDone={onTrained}
                note="Read the disposition rules and the coding criteria (Show, below), then confirm each."
              />
            )}
            <details className="uw-dp-show">
              <summary>Show the disposition rules ({screen.disposition_rules.version})</summary>
              <ol>
                {screen.disposition_rules.rules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ol>
            </details>
            <p className="uw-ma-starter" role="note">
              <FileWarning size={15} aria-hidden="true" /> {screen.starter_mark}
            </p>

            {canSign ? (
              <section className="ca-drawer-section uw-dp-sign">
                <h4>
                  <CheckCircle2 size={15} aria-hidden="true" /> One signature covers
                </h4>
                <ul>
                  {covers(screen, form.branch).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                {screen.current && (
                  <label className="ca-field">
                    Why the disposition changes (a new version)
                    <input value={form.changeReason} onChange={(event) => set({ changeReason: event.target.value })} />
                  </label>
                )}
                <div className="ca-form-grid">
                  <label className="ca-field">
                    Your password
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={form.password}
                      onChange={(event) => set({ password: event.target.value })}
                    />
                  </label>
                  <label className="ca-field">
                    Authenticator code
                    <input
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={form.code}
                      onChange={(event) => set({ code: event.target.value })}
                    />
                  </label>
                </div>
                {problem && <p className="uw-hint">{problem}</p>}
                <div className="ca-action-row">
                  <button type="submit" className="ac-primary" disabled={busy || !!problem}>
                    {busy ? "Signing…" : "Sign the disposition"}
                  </button>
                </div>
              </section>
            ) : (
              <p className="uw-hint">Signing a disposition needs signal triage, case opening or quality review.</p>
            )}
            <InlineError text={error} />
          </form>
        </>
      )}
      {screen.history.length > 0 && (
        <details className="uw-ma-history">
          <summary>Earlier versions ({screen.history.length})</summary>
          <ul>
            {screen.history.map((version) => (
              <li key={version.id}>
                Version {version.version}: {version.branch_label} · {version.signed_by} ·{" "}
                {formatDate(version.signed_at)}
                {version.superseded ? " · superseded" : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function QuestionHead({ number, text, state }: { number: number; text: string; state: QuestionState }) {
  const badge = STATE_LABELS[state];
  return (
    <div className="uw-dp-question">
      <span className="uw-dp-number">{number}</span>
      <strong>{text}</strong>
      <ToneBadge tone={badge.tone} label={badge.label} />
    </div>
  );
}

function ClassificationField({
  label,
  options,
  value,
  text,
  source,
  onChange,
}: {
  label: string;
  options: Record<string, string>;
  value: string;
  text: string;
  source?: string | null;
  onChange: (value: string, text: string) => void;
}) {
  const shownSource = source && source !== options[value] ? source : null;
  return (
    <div className="ca-field">
      <label>
        {label}
        <select value={value} onChange={(event) => onChange(event.target.value, text)}>
          {Object.entries(options).map(([code, name]) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
      </label>
      {shownSource && <span className="uw-cr-meta">Source value: “{shownSource}” (not on the list)</span>}
      {value === "OTHER" && (
        <input aria-label={`${label}: other`} value={text} onChange={(event) => onChange(value, event.target.value)} />
      )}
    </div>
  );
}

/** The current signed disposition, with its record, attribution and hands-on time (exported for tests). */
export function SignedDisposition({ version }: { version: DispositionVersion }) {
  const record = version.service_record;
  const time = handsOnText(version.hands_on_seconds);
  return (
    <section className="ca-drawer-section uw-ma-signed">
      <div className="uw-cr-head">
        <ToneBadge tone={BRANCH_TONES[version.branch]} label={BRANCH_LABELS[version.branch]} />
        <span className="uw-cr-meta">
          Version {version.version} · signed by {version.signed_by} · {formatDate(version.signed_at)}
          {version.sample ? " · sample" : ""}
        </span>
      </div>
      <dl className="uw-dp-record-view">
        {version.triggers.length > 0 && (
          <>
            <dt>Triggers met</dt>
            <dd>{version.triggers.map((item) => `${item.code}: ${item.fact}`).join("; ")}</dd>
          </>
        )}
        {version.investigation_ref && (
          <>
            <dt>Case</dt>
            <dd>{version.investigation_ref}</dd>
          </>
        )}
        {record && (
          <>
            <dt>Correction</dt>
            <dd>
              {record.correction} → {record.result} (ticket {record.service_ticket})
            </dd>
            <dt>No investigation</dt>
            <dd>
              {record.no_investigation_rationale} ({record.clause})
            </dd>
          </>
        )}
        {version.attribution_label && (
          <>
            <dt>Root-cause attribution</dt>
            <dd>
              {version.attribution_label}
              {version.attribution_reason ? `: ${version.attribution_reason}` : ""}
            </dd>
          </>
        )}
        {version.routine_path && time && (
          <>
            <dt>Hands-on time</dt>
            <dd>{time} (routine path; target under 10 minutes)</dd>
          </>
        )}
        {version.change_reason && (
          <>
            <dt>Why it changed</dt>
            <dd>{version.change_reason}</dd>
          </>
        )}
      </dl>
    </section>
  );
}

type TrendData = {
  group: string;
  groupings: string[];
  totals: { complaints: number; service_level: number; known_issue: number; escalated: number };
  items: { key: string[]; complaints: number; service_level: number; known_issue: number; escalated: number }[];
  use_environments: Record<string, string>;
  user_types: Record<string, string>;
  attributions: Record<string, string>;
  recurring: { product_name: string; problem_code: string; count: number; complaints: string[] }[];
  recurring_rule: string;
};

const GROUP_LABELS: Record<string, string> = {
  product: "Product",
  problem: "Product and problem code",
  lot: "Product and lot",
  use_environment: "Use environment",
  user_type: "User type",
  attribution: "Root-cause attribution",
};

/**
 * Signals › By resolution: service-level and known-issue resolutions beside the complaint counts, by product and
 * problem code (or lot, use environment, user type, attribution), so a recurring "fixed in the field" issue shows as
 * a trend (T-G36R). Unknown is its own group.
 */
export function ResolutionTrend() {
  const [group, setGroup] = useState("problem");
  const [filters, setFilters] = useState<Record<string, string>>({
    use_environment: "",
    user_type: "",
    attribution: "",
  });
  const trend = useResource<TrendData>(trendPath(group, filters));
  const data = trend.data;
  const filter = (key: string, label: string, options: Record<string, string> | undefined) => (
    <label className="ca-field">
      {label}
      <select value={filters[key]} onChange={(event) => setFilters({ ...filters, [key]: event.target.value })}>
        <option value="">All</option>
        {Object.entries(options ?? {}).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <div className="ac-overview">
      {data && data.recurring.length > 0 && (
        <div className="ac-message tone-warning uw-rw-callout" role="status">
          <Wrench size={16} aria-hidden="true" />
          <span>
            <strong>Recurring service-level matter:</strong>{" "}
            {data.recurring
              .map(
                (item) => `${item.product_name}, ${item.problem_code.replace(/_/g, " ").toLowerCase()}: ${item.count}`,
              )
              .join("; ")}
            . The next such complaint is escalated by RECURRENCE until a case covers it.
          </span>
        </div>
      )}
      <Panel eyebrow="Trend by resolution" title="Resolutions beside the complaint counts" source={trend}>
        <div className="ca-form-grid uw-dp-filters">
          <label className="ca-field">
            Group by
            <select value={group} onChange={(event) => setGroup(event.target.value)}>
              {Object.entries(GROUP_LABELS).map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          {filter("use_environment", "Use environment", data?.use_environments)}
          {filter("user_type", "User type", data?.user_types)}
          {filter("attribution", "Attribution", data?.attributions)}
        </div>
        {data && data.items.length ? (
          <div className="uw-table-scroll">
            <table className="ac-table">
              <thead>
                <tr>
                  <th scope="col">{GROUP_LABELS[data.group]}</th>
                  <th scope="col">Complaints</th>
                  <th scope="col">Service level</th>
                  <th scope="col">Known issue</th>
                  <th scope="col">Escalated</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.key.join("|")}>
                    <th scope="row">{item.key.map((part) => part.replace(/_/g, " ")).join(" · ")}</th>
                    <td>{item.complaints}</td>
                    <td>{item.service_level}</td>
                    <td>{item.known_issue}</td>
                    <td>{item.escalated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No complaints match" detail="Change the grouping or the filters." />
        )}
        {data && <p className="ac-note">Recurring rule (starter threshold): {data.recurring_rule}.</p>}
      </Panel>
    </div>
  );
}
