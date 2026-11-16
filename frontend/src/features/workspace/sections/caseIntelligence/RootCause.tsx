/** RCA tools on a case: the overview, the fishbone grid and the 5 Whys (G-2: flat operational screens). Plus the
 * Pareto of confirmed causes and the version at the event date. (Part of CaseIntelligence.tsx.) */
import { useState } from "react";
import { ArrowDown, CalendarClock, ListTree, Plus, Network } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../../admin/console/charts";
import { Drawer, Table, formatDate, listOf, useResource } from "../../../customer-admin/shared";
import { safeText } from "../../../../app/displayId";
import { useCan, useRcaMethods } from "../../workspaceContext";
import { ResolutionTrend } from "../Dispositions";
import { intelligencePath, type IntelligenceView } from "../../intelligence";
import {
  CAUSE_CATEGORIES,
  PARETO_GROUPS,
  categoryLabel,
  causeState,
  overviewLines,
  paretoPath,
  paretoRows,
  quickAddProblem,
  rcaPath,
  whysBody,
  whysProblem,
  WHYS_MAX,
  type EventVersion,
  type Fishbone,
  type FishboneCause,
  type Pareto,
  ACCEPTING_OUTCOMES,
  NOT_DETERMINED,
  type CauseForm,
} from "../../rca";
import { DrawerActions, DrawerError, Problem, ReasonField, useSend } from "./shared";

const CONFIRMED_NOTE = "Each possible cause is a hypothesis. Only a signed decision confirms a cause.";

// ---------------------------------------------------------------------------------------------------- overview

export function OverviewView({
  investigationId,
  caseLabel,
  onView,
  methods,
}: {
  investigationId: string;
  caseLabel: string;
  onView: (view: IntelligenceView) => void;
  methods: boolean;
}) {
  const hypotheses = useResource<any>(intelligencePath(investigationId, "hypotheses"));
  const contradictions = useResource<any>(intelligencePath(investigationId, "contradictions"));
  const unknowns = useResource<any>(intelligencePath(investigationId, "unknowns"));
  const observations = useResource<any>(intelligencePath(investigationId, "observations"));
  const whys = useResource<any>(methods ? rcaPath(investigationId, "five-whys") : null);
  const lines = overviewLines({
    hypotheses: listOf(hypotheses.data?.items),
    contradictions: listOf(contradictions.data?.items ?? contradictions.data),
    unknowns: listOf(unknowns.data?.items),
    observations: listOf(observations.data?.items),
    whys: listOf(whys.data?.items),
  });
  const count = (tag: string) => lines.filter((line) => line.tag === tag).length;
  return (
    <>
      <Panel eyebrow={caseLabel} title="Version at the event date" className="rca-panel">
        <EventVersions investigationId={investigationId} />
      </Panel>
      <Panel eyebrow={caseLabel} title="Investigation overview" source={hypotheses} className="rca-panel">
        <p className="ac-note">
          Read only. Each line names the record it comes from; open it to change it. Nothing here is a finding until a
          person signs a decision.
        </p>
        <ul className="rca-counts" aria-label="What the overview holds">
          {["Verified fact", "Source assertion", "Hypothesis", "Contradiction", "Unknown", "5 Whys"].map((tag) => (
            <li key={tag}>
              <strong>{count(tag)}</strong> {tag === "5 Whys" ? tag : `${tag.toLowerCase()}s`}
            </li>
          ))}
        </ul>
        {lines.length ? (
          <ul className="rca-lines">
            {lines.map((line) => (
              <li key={line.key} className={`rca-line tone-${line.tone}`}>
                <ToneBadge tone={line.tone} label={line.tag} />
                <span className="rca-line-text">
                  {line.text}
                  {line.detail && <small className="ac-muted">{line.detail}</small>}
                </span>
                <button type="button" className="ac-link" onClick={() => onView(line.view)}>
                  {line.record}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty
            title="Nothing recorded yet"
            detail="Add hypotheses, unknowns or observations and they are listed here."
          />
        )}
      </Panel>
    </>
  );
}

export function EventVersions({ investigationId }: { investigationId: string }) {
  const data = useResource<{ items: EventVersion[]; note?: string }>(rcaPath(investigationId, "event-versions"));
  const items = listOf(data.data?.items) as EventVersion[];
  if (data.state === "ready" && !items.length)
    return <Empty title="No complaints in scope" detail="Add complaints to the scope to see their versions." />;
  return (
    <>
      <p className="ac-note">{data.data?.note ?? "A date never chooses a version."}</p>
      <ul className="rca-versions">
        {items.map((item) => (
          <li key={item.complaint.id} className="rca-version">
            <CalendarClock size={16} aria-hidden="true" />
            <div>
              <strong>
                {safeText(item.complaint.business_id) ?? safeText(item.complaint.identifier) ?? "Complaint"}
              </strong>
              <small className="ac-muted">
                {item.anchor_label}
                {item.anchor_date ? `: ${formatDate(item.anchor_date)}` : ""}
                {item.lot?.identifier ? ` · lot ${item.lot.identifier}` : ""}
              </small>
            </div>
            <div>
              <strong>{item.version?.version_identifier ?? "Version unknown"}</strong>
              <small className="ac-muted">
                {item.version
                  ? item.version_label
                  : item.candidate_versions.length
                    ? `Released by then: ${item.candidate_versions.map((v) => v.version_identifier).join(", ")}`
                    : "No version recorded"}
              </small>
            </div>
            <div className="rca-version-flags">
              {item.flags.map((flag) => (
                <ToneBadge key={flag.code} tone="warning" label={flag.label} />
              ))}
              {item.components.length > 0 && (
                <small className="ac-muted">
                  {item.components.map((c) => `${c.name}${c.revision ? ` ${c.revision}` : ""}`).join(" · ")}
                </small>
              )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

// ---------------------------------------------------------------------------------------------------- fishbone

export function FishboneView({
  investigationId,
  caseLabel,
  readOnly = false,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly?: boolean;
}) {
  const fishbone = useResource<Fishbone>(rcaPath(investigationId, "fishbone"));
  const canWork = useCan("investigation.work") && !readOnly && fishbone.data?.actions?.can_add !== false;
  const [adding, setAdding] = useState<string | null>(null);
  const [changing, setChanging] = useState<FishboneCause | null>(null);
  const data = fishbone.data;
  const done = () => {
    setAdding(null);
    setChanging(null);
    fishbone.reload();
  };
  const total = (data?.categories ?? []).reduce((sum, column) => sum + column.causes.length, 0);
  return (
    <Panel
      eyebrow={caseLabel}
      title="Fishbone"
      source={fishbone}
      className="rca-panel"
      action={
        canWork ? (
          <button type="button" className="ac-primary" onClick={() => setAdding("")}>
            <Plus size={15} aria-hidden="true" /> Add a possible cause
          </button>
        ) : undefined
      }
    >
      <p className="ac-note">{data?.note ?? CONFIRMED_NOTE} Ruled-out causes stay visible with the reason.</p>
      <p className="rca-summary">
        <Network size={16} aria-hidden="true" /> {total} possible {total === 1 ? "cause" : "causes"} in{" "}
        {(data?.categories ?? []).filter((column) => column.causes.length).length} categories
      </p>
      <div className="rca-fishbone" role="list" aria-label="Fishbone categories">
        {(data?.categories ?? []).map((column) => (
          <section key={column.code} className="rca-column" role="listitem" aria-label={column.label}>
            <header>
              <h3>{column.label}</h3>
              <span className="ac-muted">{column.causes.length}</span>
            </header>
            {column.causes.map((cause) => (
              <CauseCard key={cause.id} cause={cause} onChange={canWork ? () => setChanging(cause) : undefined} />
            ))}
            {canWork && (
              <button type="button" className="ac-link" onClick={() => setAdding(column.code)}>
                + Add to {column.label}
              </button>
            )}
          </section>
        ))}
      </div>
      {(data?.uncategorised ?? []).length > 0 && (
        <section className="rca-uncategorised">
          <h3>Hypotheses without a category</h3>
          <div className="rca-card-row">
            {data!.uncategorised.map((cause) => (
              <CauseCard key={cause.id} cause={cause} onChange={canWork ? () => setChanging(cause) : undefined} />
            ))}
          </div>
        </section>
      )}
      {adding !== null && (
        <QuickAdd
          investigationId={investigationId}
          data={data}
          initial={adding}
          onClose={() => setAdding(null)}
          onDone={done}
        />
      )}
      {changing && (
        <ChangeCause
          investigationId={investigationId}
          data={data}
          cause={changing}
          onClose={() => setChanging(null)}
          onDone={done}
        />
      )}
    </Panel>
  );
}

export function CauseCard({ cause, onChange }: { cause: FishboneCause; onChange?: () => void }) {
  const state = causeState(cause);
  return (
    <article
      className={`rca-cause${cause.ruled_out ? " is-ruled-out" : ""}${cause.confirmed_in ? " is-confirmed" : ""}`}
    >
      <header>
        <small className="ac-muted">{safeText(cause.business_id) ?? "Hypothesis"}</small>
        <ToneBadge tone={state.tone} label={state.label} />
      </header>
      <p className="rca-cause-text">{cause.statement}</p>
      {cause.ruled_out && cause.ruled_out_reason && <p className="uw-intel-reason">Reason: {cause.ruled_out_reason}</p>}
      <p className="rca-evidence">
        {cause.evidence_for + cause.evidence_against > 0 && (
          <span className="rca-evidence-bar" aria-hidden="true">
            <i style={{ flexGrow: cause.evidence_for }} />
            <i style={{ flexGrow: cause.evidence_against }} />
          </span>
        )}
        <span className={cause.evidence_for ? "rca-for" : "rca-for is-zero"}>{cause.evidence_for} for</span>
        <span className={cause.evidence_against ? "rca-against" : "rca-against is-zero"}>
          {cause.evidence_against} against
        </span>
      </p>
      {cause.failure_mode ? (
        <p className="ac-muted">
          FMEA: {safeText(cause.failure_mode.identifier)} {safeText(cause.failure_mode.name)}
          {cause.failure_mode.risks.length > 0 &&
            ` → can lead to ${cause.failure_mode.risks.map((risk) => safeText(risk.identifier)).join(", ")}`}
        </p>
      ) : null}
      {cause.fmea_prompt && <ToneBadge tone="warning" label={cause.fmea_prompt} />}
      {cause.confirmed_in?.signed_by_name && (
        <small className="ac-muted">
          Signed by {cause.confirmed_in.signed_by_name}
          {cause.confirmed_in.signed_at ? ` · ${formatDate(cause.confirmed_in.signed_at)}` : ""}
        </small>
      )}
      {onChange && (
        <button type="button" className="ac-link" onClick={onChange}>
          Category or failure mode
        </button>
      )}
    </article>
  );
}

function CategorySelect({
  value,
  onChange,
  data,
}: {
  value: string;
  onChange: (v: string) => void;
  data?: Fishbone | null;
}) {
  const options = data?.all_categories ?? CAUSE_CATEGORIES;
  return (
    <label className="ca-field">
      Category
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose a category</option>
        {options.map((item) => (
          <option key={item.code} value={item.code}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function FailureModeSelect({
  value,
  onChange,
  data,
}: {
  value: string;
  onChange: (v: string) => void;
  data?: Fishbone | null;
}) {
  return (
    <label className="ca-field">
      Failure mode in your FMEA (optional)
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">None</option>
        {(data?.failure_modes ?? []).map((mode) => (
          <option key={mode.id} value={mode.id}>
            {[safeText(mode.identifier), safeText(mode.name)].filter(Boolean).join(" · ")}
          </option>
        ))}
      </select>
    </label>
  );
}

function QuickAdd({
  investigationId,
  data,
  initial,
  onClose,
  onDone,
}: {
  investigationId: string;
  data?: Fishbone | null;
  initial: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [statement, setStatement] = useState("");
  const [category, setCategory] = useState(initial);
  const [mode, setMode] = useState("");
  const [touched, setTouched] = useState(false);
  const { busy, error, run } = useSend(onDone);
  const problem = quickAddProblem(statement, category);
  return (
    <Drawer title="Add a possible cause" onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (problem) return;
          void run(
            rcaPath(investigationId, "causes"),
            { statement: statement.trim(), cause_category: category, ...(mode ? { failure_mode_id: mode } : {}) },
            "Possible cause added as a proposed hypothesis.",
            "The possible cause could not be added.",
          );
        }}
      >
        <p className="ac-note">It is added as a proposed hypothesis: weigh evidence for and against it as usual.</p>
        <label className="ca-field">
          Possible cause (one line)
          <input value={statement} onChange={(event) => setStatement(event.target.value)} maxLength={2000} />
        </label>
        <CategorySelect value={category} onChange={setCategory} data={data} />
        <FailureModeSelect value={mode} onChange={setMode} data={data} />
        <Problem problem={problem} touched={touched} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={false} label="Add" />
      </form>
    </Drawer>
  );
}

function ChangeCause({
  investigationId,
  data,
  cause,
  onClose,
  onDone,
}: {
  investigationId: string;
  data?: Fishbone | null;
  cause: FishboneCause;
  onClose: () => void;
  onDone: () => void;
}) {
  const [category, setCategory] = useState(cause.cause_category ?? "");
  const [mode, setMode] = useState(cause.failure_mode?.id ?? "");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useSend(onDone);
  const problem = !category
    ? "Choose a category."
    : reason.trim().length < 10
      ? "Say why in at least 10 characters."
      : null;
  return (
    <Drawer title="Category or failure mode" onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (problem) return;
          void run(
            rcaPath(investigationId, `causes/${encodeURIComponent(cause.id)}`),
            { cause_category: category, failure_mode_id: mode || null, reason: reason.trim() },
            "Cause updated.",
            "The cause could not be updated.",
          );
        }}
      >
        <p className="uw-intel-statement">{cause.statement}</p>
        <CategorySelect value={category} onChange={setCategory} data={data} />
        <FailureModeSelect value={mode} onChange={setMode} data={data} />
        <ReasonField label="Why" value={reason} onChange={setReason} />
        <p className="ac-muted">To rule a cause out, judge the hypothesis Contradicted or Retired with the reason.</p>
        <Problem problem={problem} touched={reason.length > 0} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Save" />
      </form>
    </Drawer>
  );
}

// ------------------------------------------------------------------------------------------------------ 5 Whys

export function FiveWhysView({
  investigationId,
  caseLabel,
  readOnly = false,
  onView,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly?: boolean;
  onView: (view: IntelligenceView) => void;
}) {
  const whys = useResource<any>(rcaPath(investigationId, "five-whys"));
  const canWork = useCan("investigation.work") && !readOnly && whys.data?.actions?.can_add !== false;
  const [adding, setAdding] = useState(false);
  const [asking, setAsking] = useState<string | null>(null);
  const { run } = useSend(() => {
    setAsking(null);
    whys.reload();
  });
  const items = listOf(whys.data?.items) as any[];
  return (
    <Panel
      eyebrow={caseLabel}
      title="5 Whys"
      source={whys}
      className="rca-panel"
      action={
        canWork ? (
          <button type="button" className="ac-primary" onClick={() => setAdding(true)}>
            <ListTree size={15} aria-hidden="true" /> Start a 5 Whys
          </button>
        ) : undefined
      }
    >
      <p className="ac-note">
        Each why answers the step before it, with evidence or as unknown. The last why is not a root cause: it may name
        the hypothesis it is. Link states change in Failure chain.
      </p>
      {items.length ? (
        items.map((chain) => (
          <section key={chain.id} className="rca-whys" aria-label={chain.name}>
            <header>
              <strong>{safeText(chain.business_id) ?? "5 Whys"}</strong>
              <button type="button" className="ac-link" onClick={() => onView("Failure chain")}>
                Change link states
              </button>
            </header>
            <ol>
              {(chain.nodes ?? []).map((node: any, index: number) => {
                const link = (chain.links ?? [])[index - 1];
                return (
                  <li key={node.id} className={`rca-why ${node.kind === "PROBLEM" ? "is-problem" : ""}`}>
                    {index > 0 && (
                      <span className="rca-why-link">
                        <ArrowDown size={14} aria-hidden="true" /> Why? ·{" "}
                        <ToneBadge
                          tone={
                            link?.state === "UNKNOWN" ? "warning" : link?.state === "CONTRADICTED" ? "critical" : "good"
                          }
                          label={safeText(link?.state_label) ?? "Unknown"}
                        />
                        {link?.evidence ? (
                          <small className="ac-muted">{safeText(link.evidence.business_id)}</small>
                        ) : (
                          <small className="ac-muted">{link?.unknown_prompt}</small>
                        )}
                      </span>
                    )}
                    <span className="rca-why-text">
                      <small className="ac-muted">{node.kind === "PROBLEM" ? "Problem" : `Why ${index}`}</small>
                      {node.label}
                    </span>
                    {node.is_last && node.hypothesis && (
                      <small className="ac-muted">This why is hypothesis {safeText(node.hypothesis.business_id)}</small>
                    )}
                    {canWork && index > 0 && !link?.evidence && (
                      <button
                        type="button"
                        className="ac-link"
                        disabled={asking === node.id}
                        onClick={() => {
                          setAsking(node.id);
                          void run(
                            intelligencePath(investigationId, "unknowns"),
                            { description: `Unknown in the 5 Whys: ${node.label}`.slice(0, 2000) },
                            "Open question added to Unknowns.",
                            "The question could not be added.",
                          );
                        }}
                      >
                        Open a question
                      </button>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        ))
      ) : (
        <Empty title="No 5 Whys yet" detail="Start one from the problem the complaints describe." />
      )}
      {adding && (
        <NewWhys
          investigationId={investigationId}
          onClose={() => setAdding(false)}
          onDone={() => {
            setAdding(false);
            whys.reload();
          }}
        />
      )}
    </Panel>
  );
}

function NewWhys({
  investigationId,
  onClose,
  onDone,
}: {
  investigationId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [problem, setProblem] = useState("");
  const [whys, setWhys] = useState<string[]>(["", ""]);
  const [touched, setTouched] = useState(false);
  const { busy, error, run } = useSend(onDone);
  const issue = whysProblem(problem, whys);
  return (
    <Drawer title="Start a 5 Whys" onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (issue) return;
          void run(
            rcaPath(investigationId, "five-whys"),
            whysBody(problem, whys),
            "5 Whys saved.",
            "The 5 Whys could not be saved.",
          );
        }}
      >
        <label className="ca-field">
          The problem
          <input value={problem} onChange={(event) => setProblem(event.target.value)} maxLength={255} />
        </label>
        {whys.map((why, index) => (
          <label key={index} className="ca-field">
            Why {index + 1}?
            <input
              value={why}
              maxLength={255}
              onChange={(event) => setWhys(whys.map((item, at) => (at === index ? event.target.value : item)))}
            />
          </label>
        ))}
        {whys.length < WHYS_MAX && (
          <button type="button" className="ac-link" onClick={() => setWhys([...whys, ""])}>
            + Ask why again
          </button>
        )}
        <p className="ac-muted">Each why starts as unknown; add its evidence on the Failure chain tab.</p>
        <Problem problem={issue} touched={touched} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={false} label="Save" />
      </form>
    </Drawer>
  );
}

// ------------------------------------------------------------------------------------------------------ Pareto

export function ConfirmedCausePareto() {
  const [group, setGroup] = useState("category");
  const [productId, setProductId] = useState("");
  const pareto = useResource<Pareto>(paretoPath(group, { productId }));
  const rows = paretoRows(pareto.data);
  return (
    <Panel eyebrow="Root causes" title="Pareto of confirmed causes" source={pareto} className="rca-panel">
      <p className="ac-note">
        {pareto.data?.note ?? "Counts of complaints, each once under its current confirmed cause. Not a rate."} A cause
        is confirmed only by a signed decision.
      </p>
      <div className="ca-action-row">
        <label className="ca-field">
          Group by
          <select value={group} onChange={(event) => setGroup(event.target.value)}>
            {PARETO_GROUPS.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Product
          <select value={productId} onChange={(event) => setProductId(event.target.value)}>
            <option value="">All products</option>
            {(pareto.data?.products ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ol className="rca-pareto" aria-label="Bars, largest first, with the cumulative share">
        {rows.map((row) => (
          <li key={row.label} className={row.confirmed ? "" : "is-none"}>
            <span className="rca-pareto-label">{row.label}</span>
            <span className="rca-pareto-bar" aria-hidden="true">
              <span style={{ width: `${row.width}%` }} />
            </span>
            <span className="rca-pareto-count">{row.count}</span>
            <span className="rca-pareto-cum">
              {row.cumulative_share}%{row.reachesMark ? " · reaches 80%" : ""}
            </span>
          </li>
        ))}
      </ol>
      <Table
        caption="Complaints and decisions per bar"
        rowKey={(row) => row.label}
        empty={{ title: "No complaints", detail: "Complaints appear here once they are recorded." }}
        rows={rows.filter((row) => row.count)}
        columns={[
          { key: "label", label: "Bar", render: (row) => row.label },
          { key: "count", label: "Complaints", numeric: true, render: (row) => row.count },
          {
            key: "complaints",
            label: "Complaint IDs",
            render: (row) => row.complaints.map((item) => safeText(item.business_id)).join(", "),
          },
          {
            key: "decisions",
            label: "Signed decisions",
            render: (row) => row.decisions.map((item) => safeText(item.business_id)).join(", ") || "None",
          },
        ]}
      />
    </Panel>
  );
}

/** Trends › By resolution: the Pareto of confirmed causes (while the RCA methods are on) above the resolutions. */
export function ResolutionWithCauses() {
  const methods = useRcaMethods();
  return (
    <>
      {methods && <ConfirmedCausePareto />}
      <ResolutionTrend />
    </>
  );
}

/** Signing: the hypotheses the decision maker ticks as the accepted root cause and their category. Nothing is
 * pre-ticked; the brief's leading hypothesis stays a proposal. Retired and superseded hypotheses are not offered. */
export function CauseFields({
  investigationId,
  form,
  outcome,
  set,
}: {
  investigationId: string;
  form: CauseForm;
  outcome: string;
  set: (change: Partial<CauseForm>) => void;
}) {
  const hypotheses = useResource<any>(intelligencePath(investigationId, "hypotheses"));
  const items = listOf(hypotheses.data?.items) as any[];
  const required = ACCEPTING_OUTCOMES.includes(outcome);
  const toggle = (id: string) =>
    set({
      rootCauseHypotheses: form.rootCauseHypotheses.includes(id)
        ? form.rootCauseHypotheses.filter((item) => item !== id)
        : [...form.rootCauseHypotheses, id],
    });
  return (
    <fieldset className="uw-dp-choices rca-sign">
      <legend>Confirmed root cause{required ? "" : " (optional)"}</legend>
      <p className="ac-muted">
        Tick the hypotheses you accept as the root cause. Only your signed decision confirms a cause; no hypothesis
        status changes.
      </p>
      {items.length ? (
        <ul className="rca-tick-list">
          {items.map((item) => (
            <li key={item.id}>
              <label className="ca-check">
                <input
                  type="checkbox"
                  checked={form.rootCauseHypotheses.includes(item.id)}
                  disabled={form.rootCauseCategory === NOT_DETERMINED}
                  onChange={() => toggle(item.id)}
                />
                <span>
                  <strong>{safeText(item.business_id) ?? "Hypothesis"}</strong> {item.statement}
                  <small className="ac-muted">
                    {" "}
                    · {safeText(item.human_status_label) ?? "Not judged"}
                    {item.cause_category ? ` · ${categoryLabel(item.cause_category)}` : ""}
                  </small>
                </span>
              </label>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">No hypotheses to tick in this investigation.</p>
      )}
      <label className="ca-field">
        Cause category
        <select
          value={form.rootCauseCategory}
          onChange={(event) =>
            set({
              rootCauseCategory: event.target.value,
              ...(event.target.value === NOT_DETERMINED ? { rootCauseHypotheses: [] } : {}),
            })
          }
        >
          <option value="">Choose a category</option>
          {CAUSE_CATEGORIES.map((item) => (
            <option key={item.code} value={item.code}>
              {item.label}
            </option>
          ))}
          <option value={NOT_DETERMINED}>Not determined</option>
        </select>
      </label>
      {form.rootCauseCategory === NOT_DETERMINED && (
        <label className="ca-field">
          Why the cause cannot be determined
          <input value={form.rootCauseReason} onChange={(event) => set({ rootCauseReason: event.target.value })} />
        </label>
      )}
    </fieldset>
  );
}
