/** Observations recorded on the case's evidence, and the AI's interpretations beside them. (Part of CaseIntelligence.tsx.) */
import { useState, type ReactNode } from "react";
import { FilePlus2 } from "lucide-react";
import { Panel } from "../../../admin/console/charts";
import { titleCase } from "../../../admin/console/dashboardModel";
import { Drawer, Table, formatDate, listOf, useResource } from "../../../customer-admin/shared";
import { safeText } from "../../../../app/displayId";
import { StatementKind } from "../../../shared/StatementKind";
import { AiReviewActions } from "../../../shared/AiReview";
import { STATEMENT_KIND, statementOriginLabel } from "../../../shared/epistemic";
import { useCan, usePanelFlag } from "../../workspaceContext";
import {
  EMPTY_OBSERVATION_FILTER,
  NEW_OBSERVATION,
  OBSERVATION_KINDS,
  ORIGIN_FILTERS,
  evidenceName,
  filterObservations,
  intelligencePath,
  limitationsText,
  observationBody,
  observationProblem,
  type Observation,
  type ObservationFilter,
  type ObservationForm,
  type ObservationKind,
} from "../../intelligence";
import { DrawerActions, DrawerError, EvidenceSelect, Problem, ReasonField, useSend } from "./shared";

const OBSERVATION_FILTER_KINDS = [...OBSERVATION_KINDS, "AI_INTERPRETATION"] as const;

export function ObservationsView({
  investigationId,
  caseLabel,
  readOnly,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly: boolean;
}) {
  const canWork = useCan("investigation.work") && !readOnly;
  const canReview = useCan("ai.run") && !readOnly;
  const observations = useResource<{ items?: Observation[] | null }>(intelligencePath(investigationId, "observations"));
  const [filter, setFilter] = useState<ObservationFilter>(EMPTY_OBSERVATION_FILTER);
  const [recording, setRecording] = usePanelFlag("record-observation");
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
        What the investigation's evidence shows, each with its kind: a fact recorded in a source, what a source asserts,
        or what is derived from the records.
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
        caption="Investigation observations"
        rows={shown}
        rowKey={(row) => String(row.id)}
        empty={
          items.length
            ? { title: "No matching observations", detail: "Change the filters to see more." }
            : { title: "No observations yet", detail: "Record what a piece of the investigation's evidence shows." }
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
                {row.ai_label && row.ai_execution_id ? (
                  <AiReviewActions
                    outputId={row.ai_execution_id}
                    text={row.statement}
                    disabled={!canReview}
                    onReviewed={() => observations.reload()}
                  />
                ) : null}
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
