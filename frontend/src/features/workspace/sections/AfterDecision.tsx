import { useEffect, useState } from "react";
import { ChevronRight, ClipboardCheck, Play } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, Table, errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { roleLabel } from "../../../app/roles";
import { sectionAllowed, useCan, useWorkspace } from "../workspaceContext";
import {
  CLOSURE_RESULT,
  FOLLOW_UP_ACTIONS_SHOWN,
  FOLLOW_UP_NOTE_MAX,
  CAPA_TITLE_MAX,
  IMPACT_CONCLUSIONS,
  IMPACT_RATIONALE_MAX,
  caseFollowUpsPath,
  caseImpactAssessmentsPath,
  closureCriteria,
  closureHeadline,
  findByRef,
  followUpActionBody,
  followUpActionProblem,
  followUpActions,
  followUpAssignee,
  followUpCapaText,
  followUpCounts,
  followUpDecisionText,
  followUpListPath,
  followUpOverdue,
  followUpPath,
  followUpStatusView,
  followUpTypeLabel,
  impactBody,
  impactCanComplete,
  impactCompletePath,
  impactConclusionView,
  impactProblem,
  impactStatusView,
  impactTriggerLabel,
  type ClosureCheck,
  type FollowUp,
  type FollowUpActionKey,
  type FollowUpList,
  type ImpactAssessment,
} from "../afterDecision";

function FollowUpDue({ item }: { item: FollowUp }) {
  if (!item.due_at) return <>No due date</>;
  return followUpOverdue(item) ? (
    <span className="uw-flag-critical">{formatDate(item.due_at)} · overdue</span>
  ) : (
    <>{formatDate(item.due_at)}</>
  );
}

function FollowUpStatus({ item }: { item: FollowUp }) {
  const view = followUpStatusView(item);
  return <ToneBadge tone={view.tone} label={view.label} />;
}

/**
 * The follow-up actions a signed decision required on this case: who holds each, its due date and status, and what the
 * person may do with it (start, complete with a note, cancel with a reason, record the CAPA to raise in the QMS).
 */
export function FollowUpsPanel({
  investigationId,
  initialFollowUp = null,
  reloadKey = 0,
}: {
  investigationId: string;
  /** A follow-up to open at once (from a task: "Decision?follow_up=…"). */
  initialFollowUp?: string | null;
  /** Changes when a decision was signed here, so the new follow-ups are read. */
  reloadKey?: number;
}) {
  const list = useResource<{ items?: FollowUp[] }>(caseFollowUpsPath(investigationId));
  const [chosen, setChosen] = useState<FollowUp | null>(null);
  const [opened, setOpened] = useState(false);
  const rows = listOf(list.data?.items ?? list.data) as FollowUp[];
  useEffect(() => {
    if (reloadKey) list.reload();
  }, [reloadKey]);
  useEffect(() => {
    if (opened || !initialFollowUp || list.state !== "ready") return;
    const found = findByRef(rows, initialFollowUp);
    if (found) setChosen(found);
    setOpened(true);
  }, [list.state, initialFollowUp, opened]);
  const counts = followUpCounts(rows);
  return (
    <Panel
      eyebrow="After the decision"
      title="Follow-ups"
      source={list}
      action={
        rows.length ? (
          <span className="ac-muted">
            {counts.open} open{counts.overdue ? ` · ${counts.overdue} overdue` : ""}
          </span>
        ) : undefined
      }
    >
      {initialFollowUp && opened && !findByRef(rows, initialFollowUp) && (
        <p className="ac-muted" role="status">
          The follow-up from your task is not part of this case's list. It may belong to another case.
        </p>
      )}
      <Table
        caption="Follow-up actions"
        rows={rows}
        rowKey={(row) => String(row.id)}
        empty={{
          title: "No follow-ups",
          detail:
            "Follow-up actions required by a signed decision (CAPA, product change, field action review…) appear here.",
        }}
        columns={[
          {
            key: "business_id",
            label: "Follow-up ID",
            render: (row) => <strong>{safeText(row.business_id) ?? "—"}</strong>,
          },
          {
            key: "action",
            label: "Action",
            fields: ["action_type", "action_label", "title"],
            sortValue: (row) => followUpTypeLabel(row),
            render: (row) => (
              <span className="ca-person">
                <strong>{followUpTypeLabel(row)}</strong>
                {safeText(row.title) && <small>{row.title}</small>}
              </span>
            ),
          },
          {
            key: "status",
            label: "Status",
            sortValue: (row) => followUpStatusView(row).label,
            render: (row) => <FollowUpStatus item={row} />,
          },
          {
            key: "assignee",
            label: "Held by",
            sortValue: (row) => followUpAssignee(row),
            render: (row) => followUpAssignee(row),
          },
          {
            key: "due_at",
            label: "Due",
            fields: ["due_at", "overdue"],
            sortValue: (row) => row.due_at ?? "",
            render: (row) => <FollowUpDue item={row} />,
          },
          {
            key: "decision",
            label: "From decision",
            sortValue: (row) => followUpDecisionText(row),
            render: (row) => followUpDecisionText(row),
          },
          {
            key: "capa",
            label: "CAPA",
            sortValue: (row) => followUpCapaText(row) ?? "",
            render: (row) => followUpCapaText(row) ?? "—",
          },
          {
            key: "open",
            label: "",
            render: (row) => (
              <button type="button" className="ac-link" onClick={() => setChosen(row)}>
                {followUpActions(row).length ? "Act" : "Details"}
              </button>
            ),
          },
        ]}
      />
      <p className="ac-note">Follow-ups carry out the signed decision. Completing them never changes the decision.</p>
      {chosen && (
        <FollowUpDrawer
          followUp={chosen}
          onClose={() => setChosen(null)}
          onDone={() => {
            setChosen(null);
            list.reload();
          }}
        />
      )}
    </Panel>
  );
}

const FOLLOW_UP_COPY: Record<Exclude<FollowUpActionKey, "start">, { title: string; field: string; submit: string }> = {
  complete: { title: "Complete this follow-up", field: "What was done (kept in the audit trail)", submit: "Complete" },
  cancel: { title: "Cancel this follow-up", field: "Why is it cancelled?", submit: "Cancel follow-up" },
  capa: { title: "Record the CAPA to raise in your QMS", field: "CAPA title", submit: "Record the CAPA" },
};

/** One follow-up: its facts, and the form for the action chosen (start at once; the others need a few words). */
export function FollowUpDrawer({
  followUp,
  onClose,
  onDone,
}: {
  followUp: FollowUp;
  onClose: () => void;
  onDone: () => void;
}) {
  const { notify } = useWorkspace();
  const [mode, setMode] = useState<FollowUpActionKey | null>(null);
  const [text, setText] = useState("");
  const [dueDay, setDueDay] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = safeText(followUp.business_id) ?? "Follow-up";
  const allowed = followUpActions(followUp);
  const run = async (key: FollowUpActionKey) => {
    if (busy) return;
    const problem = followUpActionProblem(key, { text, dueDay });
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await send(followUpPath(followUp.id, key), "POST", followUpActionBody(key, { text, dueDay }));
      const label = FOLLOW_UP_ACTIONS_SHOWN.find((item) => item.key === key)?.label ?? "Update";
      notify(`${name}: ${label.toLowerCase()} recorded.`);
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The follow-up was not updated."));
      setBusy(false);
    }
  };
  const copy = mode && mode !== "start" ? FOLLOW_UP_COPY[mode] : null;
  const problem = mode && mode !== "start" ? followUpActionProblem(mode, { text, dueDay }) : null;
  const capa = followUpCapaText(followUp);
  return (
    <Drawer title={`${name}: ${followUpTypeLabel(followUp)}`} onClose={onClose}>
      <dl className="ca-facts">
        <div>
          <dt>Status</dt>
          <dd>
            <FollowUpStatus item={followUp} />
          </dd>
        </div>
        <div>
          <dt>Held by</dt>
          <dd>{followUpAssignee(followUp)}</dd>
        </div>
        <div>
          <dt>Due</dt>
          <dd>
            <FollowUpDue item={followUp} />
          </dd>
        </div>
        <div>
          <dt>Case</dt>
          <dd>{safeText(followUp.investigation?.business_id) ?? "—"}</dd>
        </div>
        <div>
          <dt>From decision</dt>
          <dd>{followUpDecisionText(followUp)}</dd>
        </div>
        <div>
          <dt>CAPA</dt>
          <dd>{capa ?? "None raised"}</dd>
        </div>
      </dl>
      {safeText(followUp.title) && <p className="uw-intel-statement">{followUp.title}</p>}
      {safeText(followUp.completion_note) && (
        <section className="ca-drawer-section">
          <h3>Completion</h3>
          <p className="uw-intel-statement">{followUp.completion_note}</p>
          <small className="ac-muted">
            {safeText(followUp.completed_by_name) ?? "—"}
            {followUp.completed_at ? ` · ${formatDate(followUp.completed_at)}` : ""}
          </small>
        </section>
      )}
      {!copy ? (
        <section className="ca-drawer-section">
          <h3>Actions</h3>
          <div className="ca-action-row">
            {allowed.map((key) => {
              const item = FOLLOW_UP_ACTIONS_SHOWN.find((entry) => entry.key === key);
              return (
                <button
                  type="button"
                  key={key}
                  className={key === "start" ? "ac-primary" : "ac-secondary"}
                  disabled={busy}
                  onClick={() => {
                    setError("");
                    setText("");
                    setDueDay("");
                    if (item?.needsInput) setMode(key);
                    else void run(key);
                  }}
                >
                  {key === "start" && <Play size={14} aria-hidden="true" />} {item?.label}
                </button>
              );
            })}
            {!allowed.length && <p className="ac-muted">Nothing for you to do on this follow-up right now.</p>}
          </div>
        </section>
      ) : (
        <form
          className="ca-form ca-drawer-section"
          onSubmit={(event) => {
            event.preventDefault();
            if (mode) void run(mode);
          }}
        >
          <h3>{copy.title}</h3>
          <label className="ca-field">
            {copy.field}
            {mode === "capa" ? (
              <input
                required
                maxLength={CAPA_TITLE_MAX}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            ) : (
              <textarea
                required
                rows={3}
                maxLength={FOLLOW_UP_NOTE_MAX}
                value={text}
                placeholder="At least 10 characters"
                onChange={(event) => setText(event.target.value)}
              />
            )}
          </label>
          {mode === "capa" && (
            <>
              <label className="ca-field">
                CAPA due date (optional)
                <input type="date" value={dueDay} onChange={(event) => setDueDay(event.target.value)} />
              </label>
              <p className="ac-muted">
                MDARIX records the CAPA to raise and links it to this follow-up. You raise and run the CAPA in your QMS.
              </p>
            </>
          )}
          {text.trim() && problem && <p className="ac-muted">{problem}</p>}
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={() => setMode(null)} disabled={busy}>
              Back
            </button>
            <button
              type="submit"
              className={mode === "cancel" ? "ca-danger" : "ac-primary"}
              disabled={busy || !!problem}
            >
              {busy ? "Saving…" : copy.submit}
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
    </Drawer>
  );
}

/**
 * Evidence that reached the case after its decision was signed, each to be assessed: no impact, or a material impact
 * that reopens the case so that a new decision can supersede the signed one. The signed decision is never changed.
 */
export function ImpactAssessmentsPanel({
  investigationId,
  initialAssessment = null,
  onReopened,
}: {
  investigationId: string;
  /** An assessment to open at once (from a task: "Decision?assessment=…"). */
  initialAssessment?: string | null;
  /** Called after a material impact was recorded (the case reopened). */
  onReopened?: () => void;
}) {
  const list = useResource<{ items?: ImpactAssessment[] }>(caseImpactAssessmentsPath(investigationId));
  const [chosen, setChosen] = useState<ImpactAssessment | null>(null);
  const [opened, setOpened] = useState(false);
  const rows = listOf(list.data?.items ?? list.data) as ImpactAssessment[];
  useEffect(() => {
    if (opened || !initialAssessment || list.state !== "ready") return;
    const found = findByRef(rows, initialAssessment);
    if (found) setChosen(found);
    setOpened(true);
  }, [list.state, initialAssessment, opened]);
  const open = rows.filter((row) => String(row.status ?? "").toUpperCase() !== "COMPLETED").length;
  return (
    <Panel
      eyebrow="After the decision"
      title="Impact assessments"
      source={list}
      action={rows.length ? <span className="ac-muted">{open} to assess</span> : undefined}
    >
      {initialAssessment && opened && !findByRef(rows, initialAssessment) && (
        <p className="ac-muted" role="status">
          The assessment from your task is not part of this case's list. It may belong to another case.
        </p>
      )}
      <Table
        caption="Impact assessments"
        rows={rows}
        rowKey={(row) => String(row.id)}
        empty={{
          title: "No impact assessments",
          detail: "Evidence that reaches the case after its decision was signed is listed here to be assessed.",
        }}
        columns={[
          {
            key: "business_id",
            label: "Assessment ID",
            render: (row) => <strong>{safeText(row.business_id) ?? "—"}</strong>,
          },
          {
            key: "trigger",
            label: "Prompted by",
            sortValue: (row) => impactTriggerLabel(row),
            render: (row) => impactTriggerLabel(row),
          },
          {
            key: "evidence",
            label: "Evidence",
            sortValue: (row) => safeText(row.evidence?.business_id) ?? "",
            render: (row) =>
              row.evidence ? (
                <span className="ca-person">
                  <strong>{safeText(row.evidence.business_id) ?? "Evidence"}</strong>
                  {safeText(row.evidence.title) && <small>{row.evidence.title}</small>}
                </span>
              ) : (
                "—"
              ),
          },
          {
            key: "decision",
            label: "Signed decision",
            sortValue: (row) => safeText(row.decision?.business_id) ?? "",
            render: (row) => safeText(row.decision?.business_id) ?? "—",
          },
          {
            key: "status",
            label: "Status",
            sortValue: (row) => impactStatusView(row).label,
            render: (row) => {
              const view = impactStatusView(row);
              const conclusion = impactConclusionView(row);
              return (
                <span className="ca-person">
                  <ToneBadge tone={view.tone} label={view.label} />
                  {conclusion && <small>{conclusion.label}</small>}
                </span>
              );
            },
          },
          { key: "created_at", label: "Raised", render: (row) => formatDate(row.created_at) },
          {
            key: "open",
            label: "",
            render: (row) => (
              <button type="button" className="ac-link" onClick={() => setChosen(row)}>
                {impactCanComplete(row) ? "Assess" : "Details"}
              </button>
            ),
          },
        ]}
      />
      <p className="ac-note">
        An assessment records whether new evidence changes the decision. A material impact reopens the case for a new
        decision; the signed decision stays as it was signed.
      </p>
      {chosen && (
        <ImpactDrawer
          assessment={chosen}
          onClose={() => setChosen(null)}
          onDone={(material) => {
            setChosen(null);
            list.reload();
            if (material) onReopened?.();
          }}
        />
      )}
    </Panel>
  );
}

/** One impact assessment: what prompted it, and (for someone who may) the conclusion and rationale to record. */
export function ImpactDrawer({
  assessment,
  onClose,
  onDone,
}: {
  assessment: ImpactAssessment;
  onClose: () => void;
  onDone: (material: boolean) => void;
}) {
  const { notify } = useWorkspace();
  const [conclusion, setConclusion] = useState("");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = safeText(assessment.business_id) ?? "Impact assessment";
  const problem = impactProblem(conclusion, rationale);
  const done = impactConclusionView(assessment);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(impactCompletePath(assessment.id), "POST", impactBody(conclusion, rationale));
      const material = conclusion === "MATERIAL_IMPACT";
      notify(
        material
          ? `${name}: material impact recorded. The case reopens for a new decision; the signed decision is unchanged.`
          : `${name}: no impact recorded. The signed decision stands.`,
      );
      onDone(material);
    } catch (failure) {
      setError(errorText(failure, "The assessment was not recorded."));
      setBusy(false);
    }
  };
  return (
    <Drawer title={`${name}: impact on the signed decision`} onClose={onClose}>
      <dl className="ca-facts">
        <div>
          <dt>Prompted by</dt>
          <dd>{impactTriggerLabel(assessment)}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>
            {safeText(assessment.evidence?.business_id) ?? "—"}
            {safeText(assessment.evidence?.title) ? ` · ${assessment.evidence?.title}` : ""}
          </dd>
        </div>
        <div>
          <dt>Signed decision</dt>
          <dd>{safeText(assessment.decision?.business_id) ?? "—"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <ToneBadge tone={impactStatusView(assessment).tone} label={impactStatusView(assessment).label} />
          </dd>
        </div>
        <div>
          <dt>Raised</dt>
          <dd>{formatDate(assessment.created_at)}</dd>
        </div>
      </dl>
      {done && (
        <section className="ca-drawer-section">
          <h3>Conclusion</h3>
          <p>
            <ToneBadge tone={done.tone} label={done.label} />
          </p>
          {safeText(assessment.rationale) && <p className="uw-intel-statement">{assessment.rationale}</p>}
          <small className="ac-muted">
            {safeText(assessment.assessed_by_name) ?? "—"}
            {safeText(assessment.assessed_role) ? ` (${roleLabel(assessment.assessed_role)})` : ""}
            {assessment.assessed_at ? ` · ${formatDate(assessment.assessed_at)}` : ""}
          </small>
        </section>
      )}
      {impactCanComplete(assessment) ? (
        <form className="ca-form ca-drawer-section" onSubmit={submit}>
          <h3>Your assessment</h3>
          <p className="ac-muted">
            The signed decision is never changed. A material impact reopens the case so that a new decision, signed by
            an authorized decision maker, can supersede it.
          </p>
          <fieldset className="ca-fieldset uw-pick-fieldset">
            <legend>Does this evidence change the decision?</legend>
            <ul className="uw-pick-list">
              {IMPACT_CONCLUSIONS.map((option) => (
                <li key={option.value}>
                  <label className="ca-check">
                    <input
                      type="radio"
                      name={`impact-${assessment.id}`}
                      value={option.value}
                      checked={conclusion === option.value}
                      onChange={() => setConclusion(option.value)}
                    />
                    <span>
                      <strong>{option.label}</strong>
                      <br />
                      <small className="ac-muted">{option.description}</small>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
          <label className="ca-field">
            Rationale
            <textarea
              required
              rows={4}
              maxLength={IMPACT_RATIONALE_MAX}
              value={rationale}
              placeholder="At least 20 characters"
              onChange={(event) => setRationale(event.target.value)}
            />
          </label>
          {(conclusion || rationale.trim()) && problem && <p className="ac-muted">{problem}</p>}
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
              Back
            </button>
            <button
              type="submit"
              className={conclusion === "MATERIAL_IMPACT" ? "ca-danger" : "ac-primary"}
              disabled={busy || !!problem}
            >
              {busy ? "Saving…" : conclusion === "MATERIAL_IMPACT" ? "Record material impact" : "Record assessment"}
            </button>
          </div>
        </form>
      ) : (
        !done && <p className="ac-muted">Someone who works this case records the assessment.</p>
      )}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
    </Drawer>
  );
}

/** The closure criteria shown before Close: Pass, Blocked or Not required, each with its rationale. */
export function ClosureCriteria({ check, state }: { check: ClosureCheck | null; state: string }) {
  if (state === "loading" && !check) return <p className="ac-muted">Checking the closure criteria…</p>;
  if (!check)
    return (
      <p className="ac-muted">
        The closure criteria could not be checked here. MDARIX checks them again when you close the case.
      </p>
    );
  if (check.applies === false) return null;
  const rows = closureCriteria(check);
  return (
    <section className="ca-drawer-section" aria-label="Closure criteria">
      <h3>Before closing</h3>
      <p className="ac-muted">{closureHeadline(rows)}</p>
      {rows.length > 0 && (
        <ul className="uw-checklist" aria-label="Closure criteria">
          {rows.map((row) => (
            <li key={row.key}>
              <ToneBadge tone={CLOSURE_RESULT[row.result].tone} label={CLOSURE_RESULT[row.result].label} />
              <span>
                <strong>{row.label}</strong>
                {row.rationale && <small>{row.rationale}</small>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Dashboard: the follow-up actions assigned to the person, for people who work investigations. */
export function AfterDecisionDashboardPanel() {
  const { session } = useWorkspace();
  const canWork = useCan("investigation.work");
  const allowed = sectionAllowed("Investigations", session?.allowed_menu, session?.business_permissions);
  if (!canWork || !allowed) return null;
  return <AfterDecisionDashboard />;
}

function AfterDecisionDashboard() {
  const mine = useResource<FollowUpList>(followUpListPath("mine", "", 1, 20));
  const [chosen, setChosen] = useState<FollowUp | null>(null);
  // A role that may not read follow-ups, or a server without them, simply does not show the panel.
  if (mine.state === "forbidden" || (mine.state === "error" && mine.code === undefined && !mine.data)) return null;
  const rows = listOf(mine.data?.items ?? mine.data) as FollowUp[];
  const counts = followUpCounts(rows);
  const ready = mine.state === "ready";
  const shown = rows
    .filter((row) => !["DONE", "CANCELLED"].includes(String(row.status ?? "").toUpperCase()))
    .slice(0, 6);
  return (
    <Panel eyebrow="After the decision" title="Follow-ups assigned to you" source={mine}>
      <div className="uw-task-counts" role="group" aria-label="Your follow-up counts">
        <div className="uw-task-count">
          <strong>{ready ? counts.open : "…"}</strong>
          <span>Open</span>
        </div>
        <div className={`uw-task-count ${counts.overdue > 0 ? "urgent" : ""}`}>
          <strong>{ready ? counts.overdue : "…"}</strong>
          <span>Overdue</span>
        </div>
      </div>
      {ready &&
        (shown.length ? (
          <ul className="uw-list" aria-label="Your follow-ups">
            {shown.map((row) => {
              const name = safeText(row.business_id) ?? "Follow-up";
              return (
                <li key={row.id}>
                  <span>
                    <strong>
                      {name} · {followUpTypeLabel(row)}
                    </strong>
                    <small>
                      {safeText(row.investigation?.business_id) ?? "Case"}
                      {safeText(row.title) ? ` · ${row.title}` : ""}
                    </small>
                  </span>
                  <span className="uw-case-meta">
                    <FollowUpStatus item={row} />
                    <small>
                      <FollowUpDue item={row} />
                    </small>
                  </span>
                  <button type="button" className="ac-link" aria-label={`Open ${name}`} onClick={() => setChosen(row)}>
                    Open <ChevronRight size={14} aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <Empty
            title="No follow-ups for you"
            detail="Follow-up actions a signed decision assigns to you appear here."
          />
        ))}
      <p className="ac-note">
        <ClipboardCheck size={14} aria-hidden="true" /> Follow-ups carry out signed decisions. Impact assessments of new
        evidence reach you as tasks in My Work.
      </p>
      {chosen && (
        <FollowUpDrawer
          followUp={chosen}
          onClose={() => setChosen(null)}
          onDone={() => {
            setChosen(null);
            mine.reload();
          }}
        />
      )}
    </Panel>
  );
}
