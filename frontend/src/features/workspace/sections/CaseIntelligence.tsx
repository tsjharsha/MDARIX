import { useState, type ReactNode } from "react";
import { FilePlus2, GitBranch, Link2, Plus, Scale, Trash2 } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import {
  Drawer,
  Table,
  Tabs,
  errorText,
  formatDate,
  listOf,
  send,
  useResource,
  type Column,
} from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { roleLabel } from "../../../app/roles";
import { AiInterpretationNote, StatementKind } from "../../shared/StatementKind";
import { STATEMENT_KIND, statementOriginLabel } from "../../shared/epistemic";
import { useCan, useWorkspace } from "../workspaceContext";
import {
  inventoryPath,
  itemReview,
  reviewStatusLabel,
  type EvidenceInventory,
  type InventoryItem,
} from "../evidenceWorkflow";
import {
  EMPTY_OBSERVATION_FILTER,
  HUMAN_STATUS,
  INTELLIGENCE_VIEWS,
  LINK_LEGEND,
  LINK_STATE,
  LINK_STATES,
  NEW_HYPOTHESIS,
  NEW_OBSERVATION,
  NEW_UNKNOWN,
  OBSERVATION_KINDS,
  ORIGIN_FILTERS,
  RELATION,
  RELATIONS,
  TEXT_MAX,
  UNKNOWN_CATEGORIES,
  addedByText,
  aiChainId,
  aiChainLayout,
  aiStatusText,
  allowedHumanStatuses,
  canRequestForUnknown,
  chainLayout,
  chainName,
  contradictionView,
  evidenceName,
  filterObservations,
  groupEvidence,
  historyEventText,
  historyEvents,
  humanStatusLabel,
  humanStatusTone,
  hypothesesPath,
  hypothesisBody,
  hypothesisProblem,
  intelligencePath,
  limitationsText,
  linkBody,
  linkProblem,
  linkStateBody,
  linkStateLabel,
  linkStateProblem,
  manualChainBody,
  manualChainProblem,
  newManualChain,
  observationBody,
  observationProblem,
  retractProblem,
  stateNeedsEvidence,
  statusBody,
  statusProblem,
  unknownBody,
  unknownOptionLabel,
  unknownProblem,
  unknownStatusBody,
  unknownStatusLabel,
  unknownStatusProblem,
  unknownStatusTone,
  unknownTransitions,
  unknownsPath,
  withNode,
  withoutNode,
  type ChainLayout,
  type ChainSegment,
  type EvidenceLink,
  type FailureChains,
  type HumanStatus,
  type HypothesisForm,
  type HypothesisList,
  type IntelHypothesis,
  type IntelUnknown,
  type IntelligenceView,
  type LinkForm,
  type LinkState,
  type LinkStateForm,
  type ManualChainForm,
  type Observation,
  type ObservationFilter,
  type ObservationForm,
  type ObservationKind,
  type Relation,
  type StatusForm,
  type UnknownForm,
  type UnknownList,
  type UnknownTransition,
} from "../intelligence";
import { NewRequestDrawer } from "./EvidenceRequests";

/**
 * A case's intelligence: hypotheses and how people judge them, contradictions, unknowns, failure chains, observations
 * and the history of every judgement. AI output stays as the AI produced it; people record their own judgements here,
 * each with a reason. Works with AI switched off: everything can be added by hand.
 */
export function CaseIntelligencePanel({
  investigationId,
  caseLabel,
  view,
  onView,
  readOnly = false,
}: {
  investigationId: string;
  caseLabel: string;
  view: IntelligenceView;
  onView: (view: IntelligenceView) => void;
  /** A closed or cancelled case: its intelligence can be read, not changed. */
  readOnly?: boolean;
}) {
  return (
    <>
      <p className="ac-note">
        Every statement shows what kind it is and who made it. AI interpretations are suggestions to review, never facts
        or signed records; a person's judgement is recorded with its reason.
      </p>
      {readOnly && (
        <p className="ac-message tone-warning" role="note">
          This case is closed: its intelligence can be read but not changed.
        </p>
      )}
      <Tabs tabs={INTELLIGENCE_VIEWS} active={view} onChange={onView} label="Case intelligence views">
        {view === "Hypotheses" && (
          <HypothesesView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "Contradictions" && (
          <ContradictionsView investigationId={investigationId} caseLabel={caseLabel} onView={onView} />
        )}
        {view === "Unknowns" && (
          <UnknownsView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "Failure chain" && (
          <FailureChainView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "Observations" && (
          <ObservationsView investigationId={investigationId} caseLabel={caseLabel} readOnly={readOnly} />
        )}
        {view === "History" && <HistoryView investigationId={investigationId} caseLabel={caseLabel} />}
      </Tabs>
    </>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Shared pieces: sending a change, the case's evidence for pickers, a reason field

/** Send one change; on success say so and call onDone, on failure keep the drawer open with the server's message. */
function useSend(onDone: () => void) {
  const { notify } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path: string, body: unknown, done: string, failed: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await send(path, "POST", body);
      notify(done);
      onDone();
    } catch (failure) {
      setError(errorText(failure, failed));
      setBusy(false);
    }
  };
  return { busy, error, run };
}

function DrawerError({ error }: { error: string }) {
  return error ? (
    <p className="ac-message tone-critical" role="alert">
      {error}
    </p>
  ) : null;
}

function DrawerActions({
  onClose,
  busy,
  disabled,
  label,
}: {
  onClose: () => void;
  busy: boolean;
  disabled: boolean;
  label: string;
}) {
  return (
    <div className="ca-action-row">
      <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
        Cancel
      </button>
      <button type="submit" className="ac-primary" disabled={busy || disabled}>
        {busy ? "Saving…" : label}
      </button>
    </div>
  );
}

/** The case's evidence (Phase 3 inventory), for choosing the record a link or an observation is about. */
function useCaseEvidence(investigationId: string) {
  const inventory = useResource<EvidenceInventory>(inventoryPath(investigationId));
  return { inventory, items: listOf(inventory.data?.items) as InventoryItem[] };
}

const evidenceOption = (item: InventoryItem) =>
  `${safeText(item.evidence?.business_id) ?? safeText(item.evidence?.evidence_identifier) ?? "Evidence"} · ${
    safeText(item.evidence?.title) ?? "Untitled record"
  } (${reviewStatusLabel(itemReview(item), item.link?.review_status_label)})`;

function EvidenceSelect({
  investigationId,
  value,
  onChange,
  label,
  optional = false,
}: {
  investigationId: string;
  value: string;
  onChange: (id: string) => void;
  label: string;
  optional?: boolean;
}) {
  const { inventory, items } = useCaseEvidence(investigationId);
  return (
    <label className="ca-field">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">
          {inventory.state === "loading" && !inventory.data
            ? "Loading the case's evidence…"
            : items.length
              ? optional
                ? "No evidence"
                : "Choose evidence from this case"
              : "No evidence in this case yet"}
        </option>
        {items
          .filter((item) => item.evidence?.id)
          .map((item) => (
            <option key={item.evidence.id} value={String(item.evidence.id)}>
              {evidenceOption(item)}
            </option>
          ))}
      </select>
      {inventory.state !== "loading" && inventory.state !== "ready" && (
        <small className="ca-inline-error">{inventory.error ?? "The case's evidence could not be read."}</small>
      )}
    </label>
  );
}

function ReasonField({
  label,
  value,
  onChange,
  required = true,
  min = 10,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  min?: number;
}) {
  return (
    <label className="ca-field">
      {label}
      <textarea
        required={required}
        rows={3}
        maxLength={TEXT_MAX}
        value={value}
        placeholder={required ? `At least ${min} characters` : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

const Problem = ({ problem, touched }: { problem: string | null; touched: boolean }) =>
  problem && touched ? <p className="uw-hint">{problem}</p> : null;

const byWhom = (name: unknown, when: unknown) => {
  const who = safeText(name);
  return [who ? `by ${who}` : null, when ? formatDate(when) : null].filter(Boolean).join(" · ");
};

// ---------------------------------------------------------------------------------------------------------------
// Hypotheses

function HypothesesView({
  investigationId,
  caseLabel,
  readOnly,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly: boolean;
}) {
  const canWork = useCan("investigation.work");
  const canReview = useCan("evidence.review");
  const [includeRetired, setIncludeRetired] = useState(false);
  const hypotheses = useResource<HypothesisList>(hypothesesPath(investigationId, { includeRetired }));
  const [adding, setAdding] = useState(false);
  const [judging, setJudging] = useState<IntelHypothesis | null>(null);
  const [linking, setLinking] = useState<IntelHypothesis | null>(null);
  const [retracting, setRetracting] = useState<{ hypothesis: IntelHypothesis; link: EvidenceLink } | null>(null);
  const items = listOf(hypotheses.data?.items) as IntelHypothesis[];
  const fromAi = items.filter((item) => String(item.origin ?? "").toUpperCase() === "AI");
  const fromPeople = items.filter((item) => String(item.origin ?? "").toUpperCase() !== "AI");
  const can = (item: IntelHypothesis) => ({
    status: !readOnly && (item.actions?.can_set_status ?? canWork),
    link: !readOnly && (item.actions?.can_link_evidence ?? (canWork && canReview)),
  });
  const done = () => {
    setAdding(false);
    setJudging(null);
    setLinking(null);
    setRetracting(null);
    hypotheses.reload();
  };
  const column = (title: string, detail: string, rows: IntelHypothesis[]) => (
    <section className="uw-intel-column" aria-label={title}>
      <h3>
        {title} <span className="ac-tab-count">{rows.length}</span>
      </h3>
      <p className="ac-muted">{detail}</p>
      {rows.length ? (
        rows.map((item) => (
          <HypothesisCard
            key={item.id}
            hypothesis={item}
            can={can(item)}
            onJudge={() => setJudging(item)}
            onLink={() => setLinking(item)}
            onRetract={(link) => setRetracting({ hypothesis: item, link })}
          />
        ))
      ) : (
        <p className="ac-muted">None yet.</p>
      )}
    </section>
  );
  return (
    <Panel
      eyebrow={caseLabel}
      title="Hypotheses"
      source={hypotheses}
      action={
        canWork && !readOnly ? (
          <button type="button" className="ac-primary" onClick={() => setAdding(true)}>
            <Plus size={15} aria-hidden="true" /> Add hypothesis
          </button>
        ) : undefined
      }
    >
      <p className="ac-note">
        The AI status is what the AI said; the judgement is a person's, with their reason. Neither concludes a root
        cause.
      </p>
      <div className="ca-toolbar">
        <label className="ca-check">
          <input
            type="checkbox"
            checked={includeRetired}
            onChange={(event) => setIncludeRetired(event.target.checked)}
          />
          Include retired hypotheses
        </label>
      </div>
      {items.length ? (
        <div className="uw-intel-board">
          {column("Proposed by AI", "AI interpretations: judge each one before relying on it.", fromAi)}
          {column("Added by people or MDARIX rules", "Hypotheses recorded by hand or by MDARIX's rules.", fromPeople)}
        </div>
      ) : (
        <Empty
          title="No hypotheses yet"
          detail="Add one by hand, or generate AI hypotheses in the workspace and judge them here."
        />
      )}
      {adding && (
        <AddHypothesisDrawer investigationId={investigationId} onClose={() => setAdding(false)} onDone={done} />
      )}
      {judging && (
        <JudgeDrawer
          investigationId={investigationId}
          hypothesis={judging}
          onClose={() => setJudging(null)}
          onDone={done}
        />
      )}
      {linking && (
        <LinkEvidenceDrawer
          investigationId={investigationId}
          hypothesis={linking}
          onClose={() => setLinking(null)}
          onDone={done}
        />
      )}
      {retracting && (
        <RetractDrawer
          investigationId={investigationId}
          hypothesis={retracting.hypothesis}
          link={retracting.link}
          onClose={() => setRetracting(null)}
          onDone={done}
        />
      )}
    </Panel>
  );
}

const hypothesisName = (item: IntelHypothesis) => safeText(item.business_id) ?? "Hypothesis";

function HypothesisCard({
  hypothesis,
  can,
  onJudge,
  onLink,
  onRetract,
}: {
  hypothesis: IntelHypothesis;
  can: { status: boolean; link: boolean };
  onJudge: () => void;
  onLink: () => void;
  onRetract: (link: EvidenceLink) => void;
}) {
  const ai = String(hypothesis.origin ?? "").toUpperCase() === "AI";
  const groups = groupEvidence(hypothesis.evidence);
  const unknowns = listOf(hypothesis.unknowns);
  const changed = byWhom(hypothesis.status_changed_by_name, hypothesis.status_changed_at);
  return (
    <article className={`uw-intel-card ${ai ? "is-ai" : ""}`}>
      <header>
        <strong>{hypothesisName(hypothesis)}</strong>
        <StatementKind
          kind={ai ? "AI_INTERPRETATION" : "HYPOTHESIS"}
          origin={hypothesis.origin}
          kindLabel={hypothesis.kind_label}
        />
      </header>
      <p className="uw-intel-statement">{safeText(hypothesis.statement) ?? "No statement recorded."}</p>
      {!ai && safeText(hypothesis.created_by_name) && (
        <small className="ac-muted">Added by {hypothesis.created_by_name}</small>
      )}
      <dl className="uw-intel-judgement">
        <div>
          <dt>AI status</dt>
          <dd>{aiStatusText(hypothesis)}</dd>
        </div>
        <div>
          <dt>Person's judgement</dt>
          <dd>
            <ToneBadge
              tone={humanStatusTone(hypothesis.human_status)}
              label={humanStatusLabel(hypothesis.human_status, hypothesis.human_status_label)}
            />
            {changed && <small className="ac-muted"> {changed}</small>}
            {safeText(hypothesis.status_reason) && (
              <small className="uw-intel-reason">{hypothesis.status_reason}</small>
            )}
          </dd>
        </div>
      </dl>
      <div className="uw-intel-evidence">
        {groups.map((group) => (
          <section key={group.relation} aria-label={`${group.label} evidence`}>
            <h4>
              <ToneBadge tone={group.tone} label={group.label} />{" "}
              <span className="ac-tab-count">{group.active.length}</span>
            </h4>
            {group.active.length ? (
              <ul>
                {group.active.map((link) => (
                  <li key={link.id}>
                    <span>
                      <strong>{evidenceName(link.evidence)}</strong>
                      {safeText(link.evidence?.title) ? ` · ${link.evidence?.title}` : ""}
                    </span>
                    {safeText(link.rationale) && <small>{link.rationale}</small>}
                    <small className="ac-muted">
                      {addedByText(link)}
                      {link.created_at ? ` · ${formatDate(link.created_at)}` : ""}
                    </small>
                    {can.link && (
                      <button type="button" className="ac-link" onClick={() => onRetract(link)}>
                        Withdraw link
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">None.</p>
            )}
            {group.withdrawn.length > 0 && (
              <details>
                <summary>Withdrawn ({group.withdrawn.length})</summary>
                <ul>
                  {group.withdrawn.map((link) => (
                    <li key={link.id} className="uw-intel-withdrawn">
                      <span>
                        <strong>{evidenceName(link.evidence)}</strong>
                        {safeText(link.evidence?.title) ? ` · ${link.evidence?.title}` : ""}
                      </span>
                      <small className="ac-muted">
                        Withdrawn{safeText(link.retracted_by_name) ? ` by ${link.retracted_by_name}` : ""}
                        {safeText(link.retraction_reason) ? `: ${link.retraction_reason}` : ""}
                      </small>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        ))}
      </div>
      {unknowns.length > 0 && (
        <p className="ac-muted">
          Unknowns:{" "}
          {unknowns
            .map((unknown) =>
              [
                safeText(unknown.business_id) ?? "Unknown",
                unknown.status ? `(${unknownStatusLabel(unknown.status)})` : "",
              ]
                .filter(Boolean)
                .join(" "),
            )
            .join(", ")}
        </p>
      )}
      {(can.status || can.link) && (
        <div className="ca-action-row">
          {can.status && (
            <button type="button" className="ac-secondary" onClick={onJudge}>
              <Scale size={15} aria-hidden="true" /> Judge
            </button>
          )}
          {can.link && (
            <button type="button" className="ac-secondary" onClick={onLink}>
              <Link2 size={15} aria-hidden="true" /> Link evidence
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function AddHypothesisDrawer({
  investigationId,
  onClose,
  onDone,
}: {
  investigationId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<HypothesisForm>(NEW_HYPOTHESIS);
  const { busy, error, run } = useSend(onDone);
  const problem = hypothesisProblem(form);
  return (
    <Drawer title="Add a hypothesis" onClose={onClose}>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem)
            void run(
              intelligencePath(investigationId, "hypotheses"),
              hypothesisBody(form),
              "Hypothesis added.",
              "The hypothesis was not added.",
            );
        }}
      >
        <ReasonField
          label="The possible explanation"
          value={form.statement}
          onChange={(statement) => setForm((value) => ({ ...value, statement }))}
        />
        <ReasonField
          label="Why it is worth considering (optional)"
          value={form.rationale}
          required={false}
          onChange={(rationale) => setForm((value) => ({ ...value, rationale }))}
        />
        <p className="ac-muted">It is recorded as a hypothesis made by you: a possibility, not a conclusion.</p>
        <Problem problem={problem} touched={Boolean(form.statement.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Add hypothesis" />
      </form>
    </Drawer>
  );
}

function JudgeDrawer({
  investigationId,
  hypothesis,
  onClose,
  onDone,
}: {
  investigationId: string;
  hypothesis: IntelHypothesis;
  onClose: () => void;
  onDone: () => void;
}) {
  const options = allowedHumanStatuses(hypothesis.human_status);
  const [form, setForm] = useState<StatusForm>({ status: "", reason: "" });
  const { busy, error, run } = useSend(onDone);
  const problem = statusProblem(form);
  const name = hypothesisName(hypothesis);
  return (
    <Drawer title={`Judge ${name}`} onClose={onClose}>
      <p className="ac-muted">{safeText(hypothesis.statement)}</p>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem)
            void run(
              intelligencePath(investigationId, `hypotheses/${encodeURIComponent(hypothesis.id)}/status`),
              statusBody(form),
              `${name}: judgement recorded.`,
              "The judgement was not recorded.",
            );
        }}
      >
        <p>
          Now: <strong>{humanStatusLabel(hypothesis.human_status, hypothesis.human_status_label)}</strong> · AI status:{" "}
          {aiStatusText(hypothesis)}
        </p>
        <label className="ca-field">
          Your judgement
          <select
            value={form.status}
            onChange={(event) => setForm((value) => ({ ...value, status: event.target.value as HumanStatus | "" }))}
          >
            <option value="">Choose</option>
            {options.map((status) => (
              <option key={status} value={status}>
                {HUMAN_STATUS[status].label}
              </option>
            ))}
          </select>
          {form.status && <small className="ac-muted">{HUMAN_STATUS[form.status].help}</small>}
        </label>
        <ReasonField
          label="Reason (kept in the history and the audit trail)"
          value={form.reason}
          onChange={(reason) => setForm((value) => ({ ...value, reason }))}
        />
        <Problem problem={problem} touched={Boolean(form.status || form.reason.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Record judgement" />
      </form>
    </Drawer>
  );
}

function LinkEvidenceDrawer({
  investigationId,
  hypothesis,
  onClose,
  onDone,
}: {
  investigationId: string;
  hypothesis: IntelHypothesis;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<LinkForm>({ evidenceId: "", relation: "", rationale: "" });
  const { busy, error, run } = useSend(onDone);
  const problem = linkProblem(form);
  const name = hypothesisName(hypothesis);
  return (
    <Drawer title={`Link evidence to ${name}`} onClose={onClose}>
      <p className="ac-muted">{safeText(hypothesis.statement)}</p>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem)
            void run(
              intelligencePath(investigationId, `hypotheses/${encodeURIComponent(hypothesis.id)}/evidence`),
              linkBody(form),
              `Evidence linked to ${name}.`,
              "The evidence was not linked.",
            );
        }}
      >
        <EvidenceSelect
          investigationId={investigationId}
          label="Evidence from this case"
          value={form.evidenceId}
          onChange={(evidenceId) => setForm((value) => ({ ...value, evidenceId }))}
        />
        <fieldset className="ca-fieldset">
          <legend>How it bears on the hypothesis</legend>
          <div className="ca-chips" role="radiogroup" aria-label="Relation">
            {RELATIONS.map((relation) => (
              <button
                type="button"
                role="radio"
                key={relation}
                aria-checked={form.relation === relation}
                className={form.relation === relation ? "selected" : ""}
                onClick={() => setForm((value) => ({ ...value, relation: relation as Relation }))}
              >
                {RELATION[relation].label}
              </button>
            ))}
          </div>
          {form.relation && <small className="ac-muted">{RELATION[form.relation].help}</small>}
        </fieldset>
        <ReasonField
          label="Rationale"
          value={form.rationale}
          onChange={(rationale) => setForm((value) => ({ ...value, rationale }))}
        />
        <Problem problem={problem} touched={Boolean(form.evidenceId || form.rationale.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Link evidence" />
      </form>
    </Drawer>
  );
}

function RetractDrawer({
  investigationId,
  hypothesis,
  link,
  onClose,
  onDone,
}: {
  investigationId: string;
  hypothesis: IntelHypothesis;
  link: EvidenceLink;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSend(onDone);
  const problem = retractProblem(reason);
  const name = hypothesisName(hypothesis);
  return (
    <Drawer title={`Withdraw ${evidenceName(link.evidence)} from ${name}`} onClose={onClose}>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem)
            void run(
              intelligencePath(
                investigationId,
                `hypotheses/${encodeURIComponent(hypothesis.id)}/evidence/${encodeURIComponent(link.id)}/retract`,
              ),
              { reason: reason.trim() },
              "Link withdrawn.",
              "The link was not withdrawn.",
            );
        }}
      >
        <p className="ac-muted">The link stays in the history, marked as withdrawn, with your reason.</p>
        <ReasonField label="Why it is withdrawn" value={reason} onChange={setReason} />
        <Problem problem={problem} touched={Boolean(reason.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Withdraw link" />
      </form>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Contradictions

function ContradictionsView({
  investigationId,
  caseLabel,
  onView,
}: {
  investigationId: string;
  caseLabel: string;
  onView: (view: IntelligenceView) => void;
}) {
  const contradictions = useResource<any>(intelligencePath(investigationId, "contradictions"));
  const rows = listOf(contradictions.data?.items ?? contradictions.data).map(contradictionView);
  return (
    <Panel eyebrow={caseLabel} title="Contradictions" source={contradictions}>
      <p className="ac-note">
        Evidence that speaks against a hypothesis. A contradiction is documented when a person has judged the hypothesis
        with it in view.
      </p>
      {rows.length ? (
        <ul className="uw-intel-list">
          {rows.map((row) => (
            <li key={row.key} className="uw-intel-card">
              <header>
                <ToneBadge tone="critical" label={row.label} />
                <StatementKind kind={row.kind} origin={row.origin} kindLabel={row.kindLabel} />
              </header>
              <p>
                <strong>{row.evidence ?? "Evidence"}</strong>
                {row.evidenceTitle ? ` · ${row.evidenceTitle}` : ""} contradicts{" "}
                <strong>{row.hypothesis ?? "a hypothesis"}</strong>
                {row.hypothesisStatement ? `: ${row.hypothesisStatement}` : ""}
              </p>
              {row.rationale && <p className="uw-intel-reason">{row.rationale}</p>}
              {row.addedBy && <small className="ac-muted">Added by {row.addedBy}</small>}
              {row.judgedSince === true && <ToneBadge tone="good" label="A person has judged the hypothesis since" />}
              {row.judgedSince === false && (
                <ToneBadge tone="warning" label="Not judged by a person since: review the hypothesis" />
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Empty
          title="No contradictions recorded"
          detail="Link contradicting evidence to a hypothesis and it is listed here."
        />
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-link" onClick={() => onView("Hypotheses")}>
          Open hypotheses
        </button>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Unknowns

function UnknownsView({
  investigationId,
  caseLabel,
  readOnly,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly: boolean;
}) {
  const canWork = useCan("investigation.work") && !readOnly;
  const canRequest = useCan("evidence.request") && !readOnly;
  const [includeSuperseded, setIncludeSuperseded] = useState(false);
  const unknowns = useResource<UnknownList>(unknownsPath(investigationId, includeSuperseded));
  const [adding, setAdding] = useState(false);
  const [changing, setChanging] = useState<{ unknown: IntelUnknown; transition: UnknownTransition } | null>(null);
  const [requesting, setRequesting] = useState<IntelUnknown | null>(null);
  const rows = listOf(unknowns.data?.items) as IntelUnknown[];
  const done = () => {
    setAdding(false);
    setChanging(null);
    unknowns.reload();
  };
  const columns: Column<IntelUnknown>[] = [
    {
      key: "business_id",
      label: "Unknown ID",
      render: (row) => safeText(row.business_id) ?? "—",
    },
    {
      key: "description",
      label: "What is unknown",
      fields: ["category", "evidence_needed"],
      render: (row) => (
        <span className="ca-person">
          <span>{safeText(row.description) ?? "—"}</span>
          {safeText(row.category) && <small>{titleCase(String(row.category))}</small>}
          {safeText(row.evidence_needed) && <small>Evidence needed: {row.evidence_needed}</small>}
        </span>
      ),
    },
    {
      key: "status",
      label: "Status",
      fields: ["status_label", "resolution", "status_changed_by_name", "status_changed_at"],
      render: (row) => (
        <span className="ca-person">
          <ToneBadge tone={unknownStatusTone(row.status)} label={unknownStatusLabel(row.status, row.status_label)} />
          {byWhom(row.status_changed_by_name, row.status_changed_at) && (
            <small>{byWhom(row.status_changed_by_name, row.status_changed_at)}</small>
          )}
          {safeText(row.resolution) && <small>{row.resolution}</small>}
        </span>
      ),
    },
    {
      key: "hypothesis",
      label: "Hypothesis",
      sortValue: (row) => row.hypothesis?.business_id ?? "",
      render: (row) =>
        row.hypothesis ? (
          <span title={safeText(row.hypothesis.statement) ?? undefined}>
            {safeText(row.hypothesis.business_id) ?? "Hypothesis"}
          </span>
        ) : (
          <span className="ac-muted">—</span>
        ),
    },
    {
      key: "requests",
      label: "Evidence requests",
      sortValue: (row) => listOf(row.requests).length,
      render: (row) =>
        listOf(row.requests).length ? (
          <span className="ca-person">
            {listOf(row.requests).map((request: any) => (
              <small key={request.id}>
                {safeText(request.business_id) ?? "Request"} ·{" "}
                {safeText(request.status_label) ?? (request.status ? titleCase(String(request.status)) : "—")}
              </small>
            ))}
          </span>
        ) : (
          <span className="ac-muted">None</span>
        ),
    },
    {
      key: "origin",
      label: "Recorded by",
      fields: ["origin_label", "created_by_name"],
      sortValue: (row) => safeText(row.origin_label) ?? statementOriginLabel(row.origin),
      render: (row) => (
        <span className="ca-person">
          <span>{safeText(row.origin_label) ?? statementOriginLabel(row.origin)}</span>
          {safeText(row.created_by_name) && <small>{row.created_by_name}</small>}
        </span>
      ),
    },
    {
      key: "actions",
      label: "",
      render: (row) => (
        <span className="uw-task-actions">
          {canWork &&
            unknownTransitions(row.status).map((transition) => (
              <button
                type="button"
                key={transition.to}
                className="ac-link"
                onClick={() => setChanging({ unknown: row, transition })}
              >
                {transition.label}
              </button>
            ))}
          {canRequest && canRequestForUnknown(row.status) && (
            <button type="button" className="ac-link" onClick={() => setRequesting(row)}>
              Request evidence
            </button>
          )}
        </span>
      ),
    },
  ];
  return (
    <Panel
      eyebrow={caseLabel}
      title="Unknowns"
      source={unknowns}
      action={
        canWork ? (
          <button type="button" className="ac-primary" onClick={() => setAdding(true)}>
            <Plus size={15} aria-hidden="true" /> Add unknown
          </button>
        ) : undefined
      }
    >
      <p className="ac-note">
        What the case does not know yet. Each status change carries a reason; an unknown accepted as a limitation stays
        visible wherever the case is summarized.
      </p>
      <div className="ca-toolbar">
        <label className="ca-check">
          <input
            type="checkbox"
            checked={includeSuperseded}
            onChange={(event) => setIncludeSuperseded(event.target.checked)}
          />
          Include superseded unknowns
        </label>
      </div>
      <Table
        caption="Case unknowns"
        rows={rows}
        rowKey={(row) => String(row.id)}
        empty={{
          title: "No unknowns recorded",
          detail: "Add what the case still needs to find out, or run Unknowns in the workspace.",
        }}
        columns={columns}
      />
      {adding && <AddUnknownDrawer investigationId={investigationId} onClose={() => setAdding(false)} onDone={done} />}
      {changing && (
        <UnknownStatusDrawer
          investigationId={investigationId}
          unknown={changing.unknown}
          transition={changing.transition}
          onClose={() => setChanging(null)}
          onDone={done}
        />
      )}
      {requesting && (
        <NewRequestDrawer
          investigationId={investigationId}
          unknownId={requesting.id}
          unknownOption={{ id: requesting.id, label: unknownOptionLabel(requesting) }}
          onClose={() => setRequesting(null)}
          onCreated={() => {
            setRequesting(null);
            unknowns.reload();
          }}
        />
      )}
    </Panel>
  );
}

function AddUnknownDrawer({
  investigationId,
  onClose,
  onDone,
}: {
  investigationId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<UnknownForm>(NEW_UNKNOWN);
  const hypotheses = useResource<HypothesisList>(hypothesesPath(investigationId));
  const { busy, error, run } = useSend(onDone);
  const problem = unknownProblem(form);
  const set = (change: Partial<UnknownForm>) => setForm((value) => ({ ...value, ...change }));
  return (
    <Drawer title="Add an unknown" onClose={onClose}>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem)
            void run(
              intelligencePath(investigationId, "unknowns"),
              unknownBody(form),
              "Unknown added.",
              "The unknown was not added.",
            );
        }}
      >
        <ReasonField
          label="What is not known yet"
          value={form.description}
          onChange={(description) => set({ description })}
        />
        <label className="ca-field">
          Category (optional)
          <select value={form.category} onChange={(event) => set({ category: event.target.value })}>
            <option value="">Not set</option>
            {UNKNOWN_CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {titleCase(category)}
              </option>
            ))}
          </select>
        </label>
        <ReasonField
          label="Evidence that would resolve it (optional)"
          value={form.evidenceNeeded}
          required={false}
          onChange={(evidenceNeeded) => set({ evidenceNeeded })}
        />
        <label className="ca-field">
          Hypothesis it bears on (optional)
          <select value={form.hypothesisId} onChange={(event) => set({ hypothesisId: event.target.value })}>
            <option value="">{hypotheses.state === "loading" ? "Loading…" : "None"}</option>
            {(listOf(hypotheses.data?.items) as IntelHypothesis[]).map((item) => (
              <option key={item.id} value={item.id}>
                {hypothesisName(item)} · {safeText(item.statement) ?? ""}
              </option>
            ))}
          </select>
        </label>
        <Problem problem={problem} touched={Boolean(form.description.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Add unknown" />
      </form>
    </Drawer>
  );
}

function UnknownStatusDrawer({
  investigationId,
  unknown,
  transition,
  onClose,
  onDone,
}: {
  investigationId: string;
  unknown: IntelUnknown;
  transition: UnknownTransition;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSend(onDone);
  const problem = unknownStatusProblem(reason);
  const name = safeText(unknown.business_id) ?? "Unknown";
  return (
    <Drawer title={`${transition.label}: ${name}`} onClose={onClose}>
      <p className="ac-muted">{safeText(unknown.description)}</p>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem)
            void run(
              intelligencePath(investigationId, `unknowns/${encodeURIComponent(unknown.id)}/status`),
              unknownStatusBody(transition.to, reason),
              `${name}: ${unknownStatusLabel(transition.to).toLowerCase()}.`,
              "The unknown's status was not changed.",
            );
        }}
      >
        <ReasonField label={transition.prompt} value={reason} onChange={setReason} />
        <Problem problem={problem} touched={Boolean(reason.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label={transition.label} />
      </form>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Failure chains

/** What each line style means; the chain is never read from colour alone. */
export function ChainLegend() {
  return (
    <ul className="uw-chain-legend" aria-label="Failure chain legend">
      {LINK_LEGEND.map((item) => (
        <li key={item.state}>
          <span className={`uw-chain-line line-${item.line}`} aria-hidden="true">
            <span />
            <span />
          </span>
          <span>
            <strong>{item.label}</strong> <small className="ac-muted">{item.help}</small>
          </span>
        </li>
      ))}
    </ul>
  );
}

function SegmentText({ segment }: { segment: ChainSegment }) {
  return (
    <>
      <strong>{segment.stateLabel}</strong>
      {segment.relationship && <small>{segment.relationship}</small>}
      {segment.evidence && <small>Evidence {segment.evidence}</small>}
    </>
  );
}

/** A chain drawn left to right: each step, then the link to the next one in its line style. */
export function ChainDiagram({
  layout,
  label,
  onLink,
}: {
  layout: ChainLayout;
  label: string;
  onLink?: (segment: ChainSegment) => void;
}) {
  if (!layout.nodes.length) return <p className="ac-muted">This chain has no steps recorded.</p>;
  return (
    <>
      <ol className="uw-chain" aria-label={`${label}, left to right`}>
        {layout.nodes.map((node, index) => {
          const segment = layout.segments[index];
          return (
            <li key={node.key} className="uw-chain-item">
              <span className="uw-chain-node">{node.label}</span>
              {segment && index < layout.nodes.length - 1 && (
                <span className={`uw-chain-link state-${segment.state.toLowerCase()}`}>
                  <span className={`uw-chain-line line-${LINK_STATE[segment.state].line}`} aria-hidden="true">
                    <span />
                    <span />
                  </span>
                  <span className="uw-chain-link-text" title={segment.rationale ?? undefined}>
                    <span className="ca-sr-only">Link to the next step: </span>
                    <SegmentText segment={segment} />
                    {onLink && segment.linkId && (
                      <button type="button" className="ac-link" onClick={() => onLink(segment)}>
                        Change state
                      </button>
                    )}
                  </span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {layout.other.length > 0 && (
        <ul className="uw-intel-list">
          {layout.other.map((segment) => (
            <li key={segment.key}>
              {segment.from} → {segment.to}: <SegmentText segment={segment} />
              {onLink && segment.linkId && (
                <button type="button" className="ac-link" onClick={() => onLink(segment)}>
                  Change state
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function FailureChainView({
  investigationId,
  caseLabel,
  readOnly,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly: boolean;
}) {
  const canWork = useCan("investigation.work") && !readOnly;
  const chains = useResource<FailureChains>(intelligencePath(investigationId, "failure-chains"));
  const [building, setBuilding] = useState(false);
  const [changing, setChanging] = useState<{ chainId: string; segment: ChainSegment } | null>(null);
  const [adopting, setAdopting] = useState<string | null>(null);
  const [adoptError, setAdoptError] = useState("");
  const { notify } = useWorkspace();
  const stored = listOf(chains.data?.stored);
  const aiLatest = chains.data?.ai_latest ?? null;
  const aiChains = listOf(aiLatest?.chains);
  const done = () => {
    setBuilding(false);
    setChanging(null);
    chains.reload();
  };
  const adopt = async (chainId: string) => {
    if (adopting || !aiLatest?.ai_execution_id) return;
    setAdopting(chainId);
    setAdoptError("");
    try {
      await send(intelligencePath(investigationId, "failure-chains/adopt"), "POST", {
        ai_execution_id: aiLatest.ai_execution_id,
        ai_chain_id: chainId,
      });
      notify("AI chain adopted as a working chain. Judge each link before relying on it.");
      chains.reload();
    } catch (failure) {
      setAdoptError(errorText(failure, "The AI chain was not adopted."));
    } finally {
      setAdopting(null);
    }
  };
  return (
    <Panel
      eyebrow={caseLabel}
      title="Failure chain"
      source={chains}
      action={
        canWork ? (
          <button type="button" className="ac-primary" onClick={() => setBuilding(true)}>
            <GitBranch size={15} aria-hidden="true" /> Build a chain by hand
          </button>
        ) : undefined
      }
    >
      <p className="ac-note">
        A failure chain shows how one condition may lead to the next. Each link's state says how well evidence supports
        it; an unresolved chain is a valid result, not a failure.
      </p>
      <ChainLegend />
      {stored.length ? (
        stored.map((chain) => (
          <section key={chain.id} className="uw-intel-card uw-chain-card" aria-label={chainName(chain)}>
            <header>
              <strong>{chainName(chain)}</strong>
              <StatementKind
                kind={
                  String(chain.origin ?? "")
                    .toUpperCase()
                    .startsWith("AI")
                    ? "AI_INTERPRETATION"
                    : "HYPOTHESIS"
                }
                origin={chain.origin}
                kindLabel="Working chain"
              />
              {safeText(chain.status) && <ToneBadge tone="neutral" label={titleCase(String(chain.status))} />}
            </header>
            {safeText(chain.created_by_name) && <small className="ac-muted">Recorded by {chain.created_by_name}</small>}
            <ChainDiagram
              layout={chainLayout(chain)}
              label={chainName(chain)}
              onLink={canWork ? (segment) => setChanging({ chainId: chain.id, segment }) : undefined}
            />
          </section>
        ))
      ) : (
        <Empty
          title="No working chain yet"
          detail="Build one by hand, or adopt the latest AI chain below and judge its links."
        />
      )}
      {aiChains.length > 0 && (
        <section className="ca-drawer-section">
          <h3>Latest AI chains</h3>
          <AiInterpretationNote />
          {aiChains.map((chain, index) => {
            const id = aiChainId(chain);
            const layout = aiChainLayout(chain);
            return (
              <section key={id || index} className="uw-intel-card is-ai uw-chain-card">
                <header>
                  <strong>AI chain {index + 1}</strong>
                  <StatementKind kind="AI_INTERPRETATION" origin="AI" />
                  {safeText(chain.overall_status) && (
                    <ToneBadge tone="neutral" label={titleCase(String(chain.overall_status))} />
                  )}
                </header>
                {safeText(chain.chain_statement) && <p className="uw-intel-statement">{chain.chain_statement}</p>}
                <ChainDiagram layout={layout} label={`AI chain ${index + 1}`} />
                {canWork && id && aiLatest?.ai_execution_id && (
                  <div className="ca-action-row">
                    <button
                      type="button"
                      className="ac-secondary"
                      disabled={Boolean(adopting)}
                      onClick={() => void adopt(id)}
                    >
                      {adopting === id ? "Adopting…" : "Adopt this AI chain"}
                    </button>
                    <small className="ac-muted">
                      Adopting copies it as a working chain marked as AI-made; its links still need a person's
                      judgement.
                    </small>
                  </div>
                )}
              </section>
            );
          })}
          <DrawerError error={adoptError} />
        </section>
      )}
      {building && (
        <ManualChainDrawer investigationId={investigationId} onClose={() => setBuilding(false)} onDone={done} />
      )}
      {changing && (
        <LinkStateDrawer
          investigationId={investigationId}
          chainId={changing.chainId}
          segment={changing.segment}
          onClose={() => setChanging(null)}
          onDone={done}
        />
      )}
    </Panel>
  );
}

function LinkStateDrawer({
  investigationId,
  chainId,
  segment,
  onClose,
  onDone,
}: {
  investigationId: string;
  chainId: string;
  segment: ChainSegment;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<LinkStateForm>({ state: "", reason: "", evidenceId: "" });
  const { busy, error, run } = useSend(onDone);
  const problem = linkStateProblem(form, segment.state);
  return (
    <Drawer title="Change a link's state" onClose={onClose}>
      <p className="ac-muted">
        Now: {linkStateLabel(segment.state, segment.stateLabel)}
        {segment.evidence ? ` · evidence ${segment.evidence}` : ""}
      </p>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem && segment.linkId)
            void run(
              intelligencePath(
                investigationId,
                `failure-chains/${encodeURIComponent(chainId)}/links/${encodeURIComponent(segment.linkId)}/state`,
              ),
              linkStateBody(form),
              "Link state recorded.",
              "The link's state was not changed.",
            );
        }}
      >
        <label className="ca-field">
          New state
          <select
            value={form.state}
            onChange={(event) => setForm((value) => ({ ...value, state: event.target.value as LinkState | "" }))}
          >
            <option value="">Choose</option>
            {LINK_STATES.map((state) => (
              <option key={state} value={state}>
                {LINK_STATE[state].label}
              </option>
            ))}
          </select>
          {form.state && <small className="ac-muted">{LINK_STATE[form.state].help}</small>}
        </label>
        <EvidenceSelect
          investigationId={investigationId}
          label={form.state && stateNeedsEvidence(form.state) ? "Evidence behind it" : "Evidence behind it (optional)"}
          optional={!(form.state && stateNeedsEvidence(form.state))}
          value={form.evidenceId}
          onChange={(evidenceId) => setForm((value) => ({ ...value, evidenceId }))}
        />
        <ReasonField
          label="Reason (kept in the history)"
          value={form.reason}
          onChange={(reason) => setForm((value) => ({ ...value, reason }))}
        />
        <Problem problem={problem} touched={Boolean(form.state || form.reason.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Record state" />
      </form>
    </Drawer>
  );
}

function ManualChainDrawer({
  investigationId,
  onClose,
  onDone,
}: {
  investigationId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<ManualChainForm>(newManualChain);
  const [touched, setTouched] = useState(false);
  const { busy, error, run } = useSend(onDone);
  const { items } = useCaseEvidence(investigationId);
  const problem = manualChainProblem(form);
  const setNode = (index: number, text: string) =>
    setForm((value) => ({ ...value, nodes: value.nodes.map((node, position) => (position === index ? text : node)) }));
  const setLink = (index: number, change: Partial<ManualChainForm["links"][number]>) =>
    setForm((value) => ({
      ...value,
      links: value.links.map((link, position) => (position === index ? { ...link, ...change } : link)),
    }));
  const stepName = (index: number) => `${index + 1}. ${form.nodes[index]?.trim() || "(not described)"}`;
  return (
    <Drawer title="Build a failure chain" onClose={onClose}>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (!problem)
            void run(
              intelligencePath(investigationId, "failure-chains"),
              manualChainBody(form),
              "Failure chain recorded.",
              "The failure chain was not recorded.",
            );
        }}
      >
        <label className="ca-field">
          Name
          <input
            required
            maxLength={200}
            value={form.name}
            onChange={(event) => setForm((value) => ({ ...value, name: event.target.value }))}
            placeholder="e.g. Seal wear to occlusion alarm"
          />
        </label>
        <fieldset className="ca-fieldset">
          <legend>Steps, in order</legend>
          {form.nodes.map((node, index) => (
            <div className="uw-chain-row" key={index}>
              <label className="ca-field">
                Step {index + 1}
                <input
                  maxLength={255}
                  value={node}
                  onChange={(event) => setNode(index, event.target.value)}
                  placeholder={index === 0 ? "e.g. Supplier changed seal material" : "e.g. Seal hardness lower"}
                />
              </label>
              {form.nodes.length > 2 && (
                <button
                  type="button"
                  className="ac-link"
                  aria-label={`Remove step ${index + 1}`}
                  onClick={() => setForm((value) => withoutNode(value, index))}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              )}
            </div>
          ))}
          <button type="button" className="ac-secondary" onClick={() => setForm(withNode)}>
            <Plus size={15} aria-hidden="true" /> Add step
          </button>
        </fieldset>
        <fieldset className="ca-fieldset">
          <legend>Links between steps</legend>
          {form.links.map((link, index) => (
            <div className="uw-chain-link-form" key={index}>
              <div className="ca-form-grid">
                <label className="ca-field">
                  From
                  <select
                    value={link.fromIndex}
                    onChange={(event) => setLink(index, { fromIndex: Number(event.target.value) })}
                  >
                    {form.nodes.map((_, position) => (
                      <option key={position} value={position}>
                        {stepName(position)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ca-field">
                  To
                  <select
                    value={link.toIndex}
                    onChange={(event) => setLink(index, { toIndex: Number(event.target.value) })}
                  >
                    {form.nodes.map((_, position) => (
                      <option key={position} value={position}>
                        {stepName(position)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ca-field">
                  State
                  <select
                    value={link.state}
                    onChange={(event) => setLink(index, { state: event.target.value as LinkState })}
                  >
                    {LINK_STATES.map((state) => (
                      <option key={state} value={state}>
                        {LINK_STATE[state].label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ca-field">
                  {stateNeedsEvidence(link.state) ? "Evidence" : "Evidence (optional)"}
                  <select
                    value={link.evidenceId}
                    onChange={(event) => setLink(index, { evidenceId: event.target.value })}
                  >
                    <option value="">No evidence</option>
                    {items
                      .filter((item) => item.evidence?.id)
                      .map((item) => (
                        <option key={item.evidence.id} value={String(item.evidence.id)}>
                          {evidenceOption(item)}
                        </option>
                      ))}
                  </select>
                </label>
              </div>
              <label className="ca-field">
                Rationale (optional)
                <input
                  maxLength={TEXT_MAX}
                  value={link.rationale}
                  onChange={(event) => setLink(index, { rationale: event.target.value })}
                />
              </label>
              {form.links.length > 1 && (
                <button
                  type="button"
                  className="ac-link"
                  onClick={() =>
                    setForm((value) => ({ ...value, links: value.links.filter((_, position) => position !== index) }))
                  }
                >
                  Remove link {index + 1}
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            className="ac-secondary"
            onClick={() =>
              setForm((value) => ({
                ...value,
                links: [
                  ...value.links,
                  {
                    fromIndex: 0,
                    toIndex: value.nodes.length - 1,
                    state: "HYPOTHESIZED",
                    evidenceId: "",
                    rationale: "",
                  },
                ],
              }))
            }
          >
            <Plus size={15} aria-hidden="true" /> Add link
          </button>
        </fieldset>
        <p className="ac-muted">
          A supported or partially supported link names the evidence behind it. The chain is recorded as yours; it is a
          working explanation, not a concluded root cause.
        </p>
        <Problem problem={problem} touched={touched || Boolean(form.name.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Record chain" />
      </form>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Observations

const OBSERVATION_FILTER_KINDS = [...OBSERVATION_KINDS, "AI_INTERPRETATION"] as const;

function ObservationsView({
  investigationId,
  caseLabel,
  readOnly,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly: boolean;
}) {
  const canWork = useCan("investigation.work") && !readOnly;
  const observations = useResource<{ items?: Observation[] | null }>(intelligencePath(investigationId, "observations"));
  const [filter, setFilter] = useState<ObservationFilter>(EMPTY_OBSERVATION_FILTER);
  const [recording, setRecording] = useState(false);
  const items = listOf(observations.data?.items) as Observation[];
  const shown = filterObservations(items, filter);
  const chip = (group: keyof ObservationFilter, key: string, label: ReactNode) => (
    <button
      type="button"
      key={key}
      aria-pressed={filter[group] === key}
      className={filter[group] === key ? "selected" : ""}
      onClick={() => setFilter((value) => ({ ...value, [group]: value[group] === key ? "" : key }))}
    >
      {label}
    </button>
  );
  return (
    <Panel
      eyebrow={caseLabel}
      title="Observations"
      source={observations}
      action={
        canWork ? (
          <button type="button" className="ac-primary" onClick={() => setRecording(true)}>
            <FilePlus2 size={15} aria-hidden="true" /> Record observation
          </button>
        ) : undefined
      }
    >
      <p className="ac-note">
        What the case's evidence shows, each with its kind: a fact recorded in a source, what a source asserts, or what
        is derived from the records.
      </p>
      <div className="uw-evidence-chips">
        <div className="ca-chips" role="group" aria-label="Filter by kind">
          <span className="ac-muted">Kind</span>
          {OBSERVATION_FILTER_KINDS.map((kind) => chip("kind", kind, STATEMENT_KIND[kind].label))}
        </div>
        <div className="ca-chips" role="group" aria-label="Filter by origin">
          <span className="ac-muted">Made by</span>
          {ORIGIN_FILTERS.map((origin) => chip("origin", origin.key, origin.label))}
        </div>
      </div>
      <Table
        caption="Case observations"
        rows={shown}
        rowKey={(row) => String(row.id)}
        empty={
          items.length
            ? { title: "No matching observations", detail: "Change the filters to see more." }
            : { title: "No observations yet", detail: "Record what a piece of the case's evidence shows." }
        }
        columns={[
          {
            key: "statement",
            label: "Observation",
            fields: ["epistemic_type", "epistemic_label", "origin", "origin_label"],
            render: (row) => (
              <span className="ca-person">
                <StatementKind
                  kind={row.epistemic_type}
                  origin={row.origin}
                  kindLabel={row.epistemic_label}
                  originLabel={row.origin_label}
                />
                <span>{safeText(row.statement) ?? "—"}</span>
              </span>
            ),
          },
          {
            key: "evidence",
            label: "Evidence",
            sortValue: (row) => row.evidence?.business_id ?? "",
            render: (row) => (
              <span className="ca-person">
                <strong>{evidenceName(row.evidence)}</strong>
                {safeText(row.evidence?.title) && <small>{row.evidence?.title}</small>}
              </span>
            ),
          },
          {
            key: "quality_status",
            label: "Quality",
            fields: ["limitations"],
            render: (row) => (
              <span className="ca-person">
                <span>{row.quality_status ? titleCase(String(row.quality_status)) : "—"}</span>
                {limitationsText(row.limitations) && <small>Limitation: {limitationsText(row.limitations)}</small>}
              </span>
            ),
          },
          {
            key: "created_by_name",
            label: "Recorded",
            fields: ["created_at"],
            sortValue: (row) => row.created_at ?? "",
            render: (row) => (
              <span className="ca-person">
                <span>
                  {safeText(row.created_by_name) ?? safeText(row.origin_label) ?? statementOriginLabel(row.origin)}
                </span>
                <small>{formatDate(row.created_at)}</small>
              </span>
            ),
          },
        ]}
      />
      {recording && (
        <RecordObservationDrawer
          investigationId={investigationId}
          onClose={() => setRecording(false)}
          onDone={() => {
            setRecording(false);
            observations.reload();
          }}
        />
      )}
    </Panel>
  );
}

function RecordObservationDrawer({
  investigationId,
  onClose,
  onDone,
}: {
  investigationId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<ObservationForm>(NEW_OBSERVATION);
  const { busy, error, run } = useSend(onDone);
  const problem = observationProblem(form);
  const set = (change: Partial<ObservationForm>) => setForm((value) => ({ ...value, ...change }));
  return (
    <Drawer title="Record an observation" onClose={onClose}>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem)
            void run(
              intelligencePath(investigationId, "observations"),
              observationBody(form),
              "Observation recorded.",
              "The observation was not recorded.",
            );
        }}
      >
        <EvidenceSelect
          investigationId={investigationId}
          label="Evidence it is about"
          value={form.evidenceId}
          onChange={(evidenceId) => set({ evidenceId })}
        />
        <fieldset className="ca-fieldset">
          <legend>What kind of statement is it?</legend>
          <div className="ca-chips" role="radiogroup" aria-label="Kind of statement">
            {OBSERVATION_KINDS.map((kind) => (
              <button
                type="button"
                role="radio"
                key={kind}
                aria-checked={form.kind === kind}
                className={form.kind === kind ? "selected" : ""}
                onClick={() => set({ kind: kind as ObservationKind })}
              >
                {STATEMENT_KIND[kind].label}
              </button>
            ))}
          </div>
          {form.kind && <small className="ac-muted">{STATEMENT_KIND[form.kind].help}</small>}
        </fieldset>
        <ReasonField
          label="The observation"
          min={5}
          value={form.statement}
          onChange={(statement) => set({ statement })}
        />
        <ReasonField
          label="Rationale (optional)"
          required={false}
          value={form.rationale}
          onChange={(rationale) => set({ rationale })}
        />
        <Problem problem={problem} touched={Boolean(form.statement.trim() || form.evidenceId)} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Record observation" />
      </form>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// History

function HistoryView({ investigationId, caseLabel }: { investigationId: string; caseLabel: string }) {
  const history = useResource<unknown>(intelligencePath(investigationId, "history"));
  const events = historyEvents(history.data);
  const total = (history.data as { total?: unknown } | null)?.total;
  return (
    <Panel eyebrow={caseLabel} title="Intelligence history" source={history}>
      <p className="ac-note">Every judgement on this case's intelligence: what changed, why, by whom and when.</p>
      {events.length ? (
        <>
          <ol className="ca-timeline uw-task-history">
            {events.map((event, index) => (
              <li key={event.id ?? `${event.created_at ?? ""}:${index}`}>
                <strong>{historyEventText(event)}</strong>
                <small className="ac-muted">
                  {safeText(event.actor_name) ?? "MDARIX"}
                  {event.actor_role ? ` (${roleLabel(event.actor_role)})` : ""} · {formatDate(event.created_at)}
                </small>
                {safeText(event.reason) && <p>{event.reason}</p>}
              </li>
            ))}
          </ol>
          {typeof total === "number" && total > events.length && (
            <p className="ac-muted">
              Showing the latest {events.length} of {total} events.
            </p>
          )}
        </>
      ) : (
        <Empty
          title="No history yet"
          detail="Judgements on hypotheses, unknowns, chains and observations appear here."
        />
      )}
    </Panel>
  );
}
