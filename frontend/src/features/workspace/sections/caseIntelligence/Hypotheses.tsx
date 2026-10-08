/** The case's hypotheses: the AI's as it wrote them, and how people judge each one, with evidence links. (Part of CaseIntelligence.tsx.) */
import { useState } from "react";
import { Link2, Plus, Scale } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../../admin/console/charts";
import { Drawer, formatDate, listOf, useResource } from "../../../customer-admin/shared";
import { safeText } from "../../../../app/displayId";
import { StatementKind } from "../../../shared/StatementKind";
import { useCan } from "../../workspaceContext";
import {
  HUMAN_STATUS,
  NEW_HYPOTHESIS,
  RELATION,
  RELATIONS,
  addedByText,
  aiStatusText,
  allowedHumanStatuses,
  evidenceName,
  groupEvidence,
  humanStatusLabel,
  humanStatusTone,
  hypothesesPath,
  hypothesisBody,
  hypothesisProblem,
  intelligencePath,
  linkBody,
  linkProblem,
  retractProblem,
  statusBody,
  statusProblem,
  unknownStatusLabel,
  type EvidenceLink,
  type HumanStatus,
  type HypothesisForm,
  type HypothesisList,
  type IntelHypothesis,
  type LinkForm,
  type Relation,
  type StatusForm,
} from "../../intelligence";
import { DrawerActions, DrawerError, EvidenceSelect, Problem, ReasonField, byWhom, useSend } from "./shared";

export function HypothesesView({
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

export const hypothesisName = (item: IntelHypothesis) => safeText(item.business_id) ?? "Hypothesis";

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
