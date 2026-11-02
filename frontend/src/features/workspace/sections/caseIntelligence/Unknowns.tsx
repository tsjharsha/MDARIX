/** What the case still does not know, and how each unknown is settled. (Part of CaseIntelligence.tsx.) */
import { useState } from "react";
import { Plus } from "lucide-react";
import { Panel, ToneBadge } from "../../../admin/console/charts";
import { titleCase } from "../../../admin/console/dashboardModel";
import { Drawer, Table, listOf, useResource, type Column } from "../../../customer-admin/shared";
import { safeText } from "../../../../app/displayId";
import { statementOriginLabel } from "../../../shared/epistemic";
import { useCan, usePanelFlag, usePanelState } from "../../workspaceContext";
import {
  NEW_UNKNOWN,
  UNKNOWN_CATEGORIES,
  canRequestForUnknown,
  hypothesesPath,
  intelligencePath,
  unknownBody,
  unknownOptionLabel,
  unknownProblem,
  unknownStatusBody,
  unknownStatusLabel,
  unknownStatusProblem,
  unknownStatusTone,
  unknownTransitions,
  unknownsPath,
  type HypothesisList,
  type IntelHypothesis,
  type IntelUnknown,
  type UnknownForm,
  type UnknownList,
  type UnknownTransition,
} from "../../intelligence";
import { NewRequestDrawer } from "../EvidenceRequests";
import { hypothesisName } from "./Hypotheses";
import { DrawerActions, DrawerError, Problem, ReasonField, byWhom, useSend } from "./shared";

export function UnknownsView({
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
  const rows = listOf(unknowns.data?.items) as IntelUnknown[];
  // Each drawer has its own address (panel=<kind>:<id>), so Back closes it and a refresh reopens it.
  const byId = (id: string) => rows.find((row) => row.id === id) ?? null;
  const [adding, setAdding] = usePanelFlag("add-unknown");
  const [changing, setChanging] = usePanelState<{ unknown: IntelUnknown; transition: UnknownTransition }>(
    "unknown-status",
    ({ unknown, transition }) => `${unknown.id}.${transition.to}`,
    (key) => {
      const [id, to] = key.split(".");
      const unknown = byId(id);
      const transition = unknownTransitions(unknown?.status).find((item) => item.to === to);
      return unknown && transition ? { unknown, transition } : null;
    },
  );
  const [requesting, setRequesting] = usePanelState<IntelUnknown>("request-evidence", (row) => row.id, byId);
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
        visible wherever the investigation is summarized.
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
        caption="Investigation unknowns"
        rows={rows}
        rowKey={(row) => String(row.id)}
        empty={{
          title: "No unknowns recorded",
          detail: "Add what the investigation still needs to find out, or run Unknowns in the workspace.",
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
