import { useEffect, useState } from "react";
import { AlertTriangle, Bot, Download, ListChecks, User } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, SearchBox, Table, formatDate, listOf, useResource } from "../../customer-admin/shared";
import { describeError } from "../../../app/apiClient";
import { titleCase } from "../../admin/console/dashboardModel";
import { safeText } from "../../../app/displayId";
import { downloadFile } from "../../reports/download";
import { StatementKind } from "../../shared/StatementKind";
import "../../shared/statement-kind.css";
import { chooseCase, useCan, usePanelState, useWorkspace } from "../workspaceContext";
import {
  caseDecisionPath,
  decisionHistory,
  outcomeLabel,
  outcomeTone,
  type CaseDecisionContext,
} from "../humanDecision";
import {
  EMPTY_TIMELINE_FILTERS,
  TIMELINE_PAGE_SIZE,
  actorOptions,
  aiModelText,
  aiRunCountsText,
  aiRunKindLabel,
  aiRunStatus,
  aiVersionText,
  auditChainView,
  briefHashRows,
  categoryChips,
  chipCounts,
  categoryClass,
  categoryLabel,
  dateRangeProblem,
  durationText,
  eventActor,
  eventMatches,
  eventObject,
  eventTitle,
  guardrailItems,
  guardrailSummary,
  humanReviewView,
  integrityHeadline,
  isoFromLocalInput,
  knownSplit,
  localInputValue,
  originView,
  pageCount,
  replayDecisionOptions,
  replayIntegrity,
  replayItem,
  replayList,
  replayPath,
  signatureRows,
  signerText,
  timelinePath,
  toggleCategory,
  trustExportName,
  trustExportPath,
  trustPath,
  usageText,
  type AiRun,
  type AiRunsResponse,
  type ExportFormat,
  type IntegrityResponse,
  type ObjectTarget,
  type ReplayResponse,
  type TimelineEvent,
  type TimelineFilters,
  type TimelineResponse,
} from "../caseAudit";
import { Fingerprint } from "./DecisionRecord";
import { countOf } from "./common";

const record = (value: unknown): Record<string, any> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, any>) : {};

/**
 * Who made an event, in the statement-kind style: a person (solid), AI (dashed violet, robot icon) or MDARIX itself.
 * An AI event never looks like a person's act.
 */
export function OriginBadge({ event }: { event: Pick<TimelineEvent, "origin" | "category"> }) {
  const view = originView(event);
  const Icon = view.code === "AI" ? Bot : view.code === "SYSTEM" ? ListChecks : User;
  return (
    <span
      className={`sk-badge ${view.code === "AI" ? "sk-ai" : `ta-origin-${view.style}`}`}
      title={view.help}
      aria-label={`Made by: ${view.label}. ${view.help}`}
      data-origin={view.code ?? "UNKNOWN"}
    >
      <span className="sk-kind" aria-hidden="true">
        <Icon size={13} />
        {view.label}
      </span>
    </span>
  );
}

/** The category of an event: its label on a coloured badge (never colour alone). */
export function CategoryBadge({ category }: { category: unknown }) {
  return <span className={`ta-category ${categoryClass(category)}`}>{categoryLabel(category)}</span>;
}

/** Download the case's audit trail (JSON or CSV), for people who may export; the server checks and records it. */
function TrustExport({ investigationId, caseLabel }: { investigationId: string; caseLabel: string }) {
  const canExport = useCan("data.export");
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  if (!canExport) return null;
  const download = async (format: ExportFormat) => {
    setBusy(format);
    setResult(null);
    try {
      const name = await downloadFile(trustExportPath(investigationId, format), {
        fallbackName: trustExportName(caseLabel, format),
      });
      setResult({ ok: true, text: `Investigation audit trail downloaded as ${name}.` });
    } catch (reason) {
      setResult({ ok: false, text: describeError(reason, "The investigation audit trail could not be downloaded.") });
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="ta-export" role="group" aria-label="Export the investigation audit trail">
      <span>Export</span>
      {(["json", "csv"] as const).map((format) => (
        <button
          key={format}
          type="button"
          className="ac-secondary"
          disabled={busy !== null}
          onClick={() => void download(format)}
          aria-label={`Export the investigation audit trail as ${format.toUpperCase()}`}
        >
          <Download size={14} aria-hidden="true" /> {busy === format ? "Preparing…" : format.toUpperCase()}
        </button>
      ))}
      {result &&
        (result.ok ? (
          <p className="ca-inline-ok" role="status">
            {result.text}
          </p>
        ) : (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {result.text}
          </p>
        ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Case timeline

/**
 * Everything recorded on the case, in order: what happened, who did it in which role (a person, AI or MDARIX), the
 * record it concerns (opened where a screen shows it) and the reason given. Filters by category, person and days;
 * search looks through the page shown.
 */
export function CaseTimeline({
  investigationId,
  caseLabel,
  onOpenDecision,
}: {
  investigationId: string;
  caseLabel: string;
  onOpenDecision: (decisionId: string) => void;
}) {
  const { open, work } = useWorkspace();
  const [filters, setFilters] = useState<TimelineFilters>(EMPTY_TIMELINE_FILTERS);
  const [page, setPage] = useState(1);
  const [actors, setActors] = useState<string[]>([]);
  // The category counts from before any category was chosen (see chipCounts).
  const [baseCounts, setBaseCounts] = useState<Record<string, number> | null>(null);
  const problem = dateRangeProblem(filters);
  const timeline = useResource<TimelineResponse>(problem ? null : timelinePath(investigationId, filters, page));
  const items = listOf(timeline.data?.items) as TimelineEvent[];
  const shown = items.filter((event) => eventMatches(event, filters.search));
  const total = typeof timeline.data?.total === "number" ? timeline.data.total : null;
  const pages = pageCount(total ?? items.length);
  const chips = categoryChips(
    chipCounts(baseCounts, timeline.data?.categories ?? null, filters.categories),
    filters.categories,
  );
  useEffect(() => {
    if (!filters.categories.length && timeline.data?.categories) setBaseCounts(timeline.data.categories);
    setActors((previous) => {
      const next = actorOptions(previous, items);
      return next.length === previous.length ? previous : next;
    });
  }, [timeline.data]);
  const change = (patch: Partial<TimelineFilters>) => {
    setFilters((current) => ({ ...current, ...patch }));
    if (!("search" in patch)) setPage(1);
  };
  // A record of this case opens with this case as the context (the timeline may show another case than the one open).
  const go = async (target: ObjectTarget) => {
    if (target.kind === "decision") return onOpenDecision(target.id);
    if (investigationId !== work.investigationId) {
      if (work.investigations.some((item) => String(item.id) === investigationId))
        work.setInvestigationId(investigationId);
      else await chooseCase(work, caseLabel);
    }
    open(target.section, target.tab);
  };
  const filtered =
    filters.categories.length > 0 || !!filters.actor || !!filters.since || !!filters.until || !!filters.search.trim();
  return (
    <Panel
      eyebrow={caseLabel}
      title={`Investigation timeline${total !== null ? ` · ${total}` : ""}`}
      source={timeline}
      action={<TrustExport investigationId={investigationId} caseLabel={caseLabel} />}
    >
      <p className="ac-note">
        Every recorded step of this investigation, oldest first. Each event says who made it: a person, AI or MDARIX
        itself. AI never decides or signs; people do.
      </p>
      <div className="ca-chips ta-chips" role="group" aria-label="Event categories">
        <button
          type="button"
          aria-pressed={filters.categories.length === 0}
          className={filters.categories.length === 0 ? "selected" : ""}
          onClick={() => change({ categories: [] })}
        >
          All
        </button>
        {chips.map((chip) => (
          <button
            type="button"
            key={chip.code}
            aria-pressed={chip.selected}
            className={chip.selected ? "selected" : ""}
            onClick={() => change({ categories: toggleCategory(filters.categories, chip.code) })}
          >
            {chip.label}
            {chip.count !== null && <span className="ac-tab-count">{chip.count}</span>}
          </button>
        ))}
      </div>
      <div className="ca-toolbar ta-toolbar">
        <SearchBox
          value={filters.search}
          onChange={(search) => change({ search })}
          label="Search this page of the timeline"
        />
        <select aria-label="Person" value={filters.actor} onChange={(event) => change({ actor: event.target.value })}>
          <option value="">Anyone</option>
          {actors.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <label className="ca-inline-select">
          From
          <input type="date" value={filters.since} onChange={(event) => change({ since: event.target.value })} />
        </label>
        <label className="ca-inline-select">
          To
          <input type="date" value={filters.until} onChange={(event) => change({ until: event.target.value })} />
        </label>
        {filtered && (
          <button
            type="button"
            className="ac-link"
            onClick={() => {
              setFilters(EMPTY_TIMELINE_FILTERS);
              setPage(1);
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      {problem && (
        <p className="ca-inline-error" role="alert">
          <AlertTriangle size={15} aria-hidden="true" /> {problem}
        </p>
      )}
      {shown.length ? (
        <ol className="ta-timeline" aria-label="Investigation events">
          {shown.map((event, index) => {
            const actor = eventActor(event);
            const object = eventObject(event);
            const reason = safeText(event.reason);
            return (
              <li
                key={`${event.at ?? ""}:${event.event ?? ""}:${index}`}
                className={`ta-event ta-origin-row-${originView(event).style}`}
              >
                <time className="ta-event-time" dateTime={safeText(event.at) ?? undefined}>
                  {formatDate(event.at)}
                </time>
                <div className="ta-event-body">
                  <div className="ta-event-head">
                    <CategoryBadge category={event.category} />
                    <OriginBadge event={event} />
                    <strong>{eventTitle(event)}</strong>
                  </div>
                  <small className="ac-muted">
                    {actor.name}
                    {actor.role ? ` · ${actor.role}` : ""}
                    {object && (
                      <>
                        {" · "}
                        {object.typeLabel}{" "}
                        {object.target ? (
                          <button
                            type="button"
                            className="ac-link"
                            onClick={() => void go(object.target as ObjectTarget)}
                          >
                            {object.label}
                          </button>
                        ) : (
                          <span>{object.label}</span>
                        )}
                      </>
                    )}
                  </small>
                  {reason && (
                    <p className="ta-event-reason">
                      <strong>Reason: </strong>
                      {reason}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <Empty
          title={filtered ? "No matching events" : "No events recorded yet"}
          detail={
            filtered
              ? "Change the filters or the search to see more."
              : "Each step of the investigation (trends, scope, evidence, reviews, the brief and the decision) appears here."
          }
        />
      )}
      {pages > 1 && (
        <div className="ca-action-row uw-pager">
          <span className="ac-muted">
            Page {Math.min(page, pages)} of {pages}
            {total !== null ? ` · ${countOf(total, "event")}` : ""} · {TIMELINE_PAGE_SIZE} per page
          </span>
          <button
            type="button"
            className="ac-secondary"
            disabled={page <= 1 || timeline.state === "loading"}
            onClick={() => setPage((value) => Math.max(1, value - 1))}
          >
            Previous
          </button>
          <button
            type="button"
            className="ac-secondary"
            disabled={page >= pages || timeline.state === "loading"}
            onClick={() => setPage((value) => value + 1)}
          >
            Next
          </button>
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Replay

function ItemList({ items, empty, kind }: { items: unknown[]; empty: string; kind?: string }) {
  if (!items.length) return <p className="ac-muted">{empty}</p>;
  return (
    <ul className="uw-intel-list">
      {items.map((item, index) => {
        const view = replayItem(item);
        const row = record(item);
        const origin = row.origin ?? row.source_origin;
        return (
          <li key={`${view.label}:${index}`}>
            {(origin || row.statement_kind || kind) && (
              <>
                <StatementKind kind={row.statement_kind ?? kind} origin={origin} />{" "}
              </>
            )}
            <strong>{view.label}</strong>
            {view.detail ? ` · ${view.detail}` : ""}
            {view.status && <small className="ac-muted"> · {view.status}</small>}
            {view.at && <small className="ac-muted"> · {formatDate(view.at)}</small>}
          </li>
        );
      })}
    </ul>
  );
}

function KnownColumns({ title, value, noun }: { title: string; value: unknown; noun: string }) {
  const split = knownSplit(value);
  return (
    <section className="ca-drawer-section" aria-label={title}>
      <h3>{title}</h3>
      <div className="ta-replay-columns">
        <div>
          <h3>
            Known then <span className="ac-tab-count">{split.knownThen.length}</span>
          </h3>
          <ItemList items={split.knownThen} empty={`No ${noun} were known then.`} />
        </div>
        <div>
          <h3>
            Arrived later <span className="ac-tab-count">{split.arrivedLater.length}</span>
          </h3>
          <ItemList items={split.arrivedLater} empty={`No ${noun} arrived later.`} />
        </div>
      </div>
    </section>
  );
}

/**
 * The case as it was known at one moment: by default when its decision was signed (any decision, superseded ones
 * too), or at a date and time the person chooses. What was known then is shown beside what arrived later.
 */
export function CaseReplay({
  investigationId,
  caseLabel,
  onOpenDecision,
}: {
  investigationId: string;
  caseLabel: string;
  onOpenDecision: (decisionId: string) => void;
}) {
  const decisions = useResource<CaseDecisionContext>(caseDecisionPath(investigationId));
  const history = decisionHistory(decisions.data?.decisions, decisions.data?.current_decision ?? null);
  const options = replayDecisionOptions(history);
  const [mode, setMode] = useState<"decision" | "moment">("decision");
  const [decisionId, setDecisionId] = useState("");
  const [moment, setMoment] = useState(() => localInputValue(new Date().toISOString()));
  const decisionsKnown = decisions.state !== "loading";
  const chosenDecision = decisionId && options.some((item) => item.id === decisionId) ? decisionId : options[0]?.id;
  // Without a signed decision (or when decisions cannot be read) the replay is at a chosen moment.
  const effectiveMode = mode === "decision" && decisionsKnown && !chosenDecision ? "moment" : mode;
  const asKnownAt = isoFromLocalInput(moment);
  const path =
    effectiveMode === "decision"
      ? chosenDecision
        ? replayPath(investigationId, { decisionId: chosenDecision })
        : null
      : replayPath(investigationId, { asKnownAt });
  const replay = useResource<ReplayResponse>(path);
  const data = path ? replay.data : null;
  return (
    <>
      <Panel eyebrow={caseLabel} title="Replay the investigation at a moment">
        <p className="ac-note">
          See the investigation as it was known at a moment: the complaints, evidence, hypotheses, unknowns and reviews
          then, and what arrived later. Nothing recorded is changed.
        </p>
        <fieldset className="ta-replay-mode">
          <legend className="ca-sr-only">Moment to replay</legend>
          <label className="ca-check">
            <input
              type="radio"
              name="replay-mode"
              checked={effectiveMode === "decision"}
              disabled={decisionsKnown && !options.length}
              onChange={() => setMode("decision")}
            />
            As known when the decision was signed
          </label>
          {effectiveMode === "decision" && options.length > 1 && (
            <label className="ca-inline-select">
              Decision
              <select value={chosenDecision ?? ""} onChange={(event) => setDecisionId(event.target.value)}>
                {options.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="ca-check">
            <input
              type="radio"
              name="replay-mode"
              checked={effectiveMode === "moment"}
              onChange={() => setMode("moment")}
            />
            At a moment I choose
          </label>
          {effectiveMode === "moment" && (
            <label className="ca-inline-select">
              Date and time
              <input type="datetime-local" value={moment} onChange={(event) => setMoment(event.target.value)} />
            </label>
          )}
        </fieldset>
        {decisionsKnown && !options.length && (
          <p className="ac-muted">No decision has been signed on this investigation; choose a moment to replay.</p>
        )}
        {effectiveMode === "moment" && !asKnownAt && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> Enter a full date and time.
          </p>
        )}
      </Panel>
      {path && (
        <Panel
          eyebrow="Replay"
          title={data?.as_known_at ? `As known on ${formatDate(data.as_known_at)}` : "As known then"}
          source={replay}
        >
          {data && <ReplayBody data={data} history={history} onOpenDecision={onOpenDecision} />}
        </Panel>
      )}
    </>
  );
}

function ReplayBody({
  data,
  history,
  onOpenDecision,
}: {
  data: ReplayResponse;
  history: ReturnType<typeof decisionHistory>;
  onOpenDecision: (decisionId: string) => void;
}) {
  const decision = record(data.decision);
  const snapshot = record(data.snapshot);
  const brief = record(data.brief);
  const integrity = replayIntegrity(data.integrity);
  const decisionBusiness = safeText(decision.business_id);
  const decisionId = decisionBusiness ? history.find((row) => row.businessId === decisionBusiness)?.id : null;
  const limitations = replayList(data.limitations);
  const snapshotBrief = record(snapshot.brief);
  const snapshotBriefId = safeText(snapshot.brief_business_id) ?? safeText(snapshotBrief.business_id);
  const snapshotBriefVersion = snapshot.brief_version ?? snapshotBrief.version;
  const snapshotBriefHash = snapshot.brief_hash ?? snapshot.brief_content_hash ?? snapshotBrief.hash;
  return (
    <>
      <div
        className={`ac-message tone-${integrity.tone === "neutral" ? "neutral" : integrity.tone} ta-integrity-banner`}
        role="status"
      >
        <span>
          <ToneBadge tone={integrity.tone} label="Evidence set changed since then?" /> {integrity.headline}
        </span>
        <small>
          Fingerprint then <Fingerprint value={integrity.then} /> · now <Fingerprint value={integrity.now} />
        </small>
      </div>
      {Object.keys(decision).length > 0 && (
        <section className="ca-drawer-section" aria-label="Decision">
          <h3>Decision</h3>
          <dl className="ca-facts">
            <div>
              <dt>Decision ID</dt>
              <dd>
                {decisionId ? (
                  <button type="button" className="ac-link" onClick={() => onOpenDecision(String(decisionId))}>
                    {decisionBusiness}
                  </button>
                ) : (
                  (decisionBusiness ?? "—")
                )}
              </dd>
            </div>
            <div>
              <dt>Outcome</dt>
              <dd>
                <ToneBadge
                  tone={outcomeTone(decision.outcome)}
                  label={outcomeLabel(decision.outcome, decision.outcome_label)}
                />
              </dd>
            </div>
            <div>
              <dt>Signed</dt>
              <dd>{formatDate(decision.decided_at)}</dd>
            </div>
            <div>
              <dt>Signed by</dt>
              <dd>{signerText(decision.signer) ?? "—"}</dd>
            </div>
            {safeText(decision.status_now) && (
              <div>
                <dt>Status now</dt>
                <dd>{titleCase(String(decision.status_now))}</dd>
              </div>
            )}
          </dl>
        </section>
      )}
      <section className="ca-drawer-section" aria-label="Snapshot">
        <h3>Snapshot taken at signing</h3>
        {snapshot.available === false || !Object.keys(snapshot).length ? (
          <p className="ac-muted">
            {safeText(snapshot.reason) ?? "No snapshot was recorded for this moment"}. What follows is rebuilt from the
            records.
          </p>
        ) : (
          <dl className="ca-facts">
            <div>
              <dt>Brief</dt>
              <dd>
                {snapshotBriefId ?? "—"}
                {snapshotBriefVersion !== undefined && snapshotBriefVersion !== null
                  ? ` · version ${snapshotBriefVersion}`
                  : ""}
              </dd>
            </div>
            <div>
              <dt>Brief fingerprint</dt>
              <dd>
                <Fingerprint value={snapshotBriefHash} />
              </dd>
            </div>
            <div>
              <dt>Evidence fingerprint</dt>
              <dd>
                <Fingerprint value={snapshot.evidence_set_hash} />
              </dd>
            </div>
            <div>
              <dt>Scope version</dt>
              <dd>{safeText(snapshot.scope_version) ?? "—"}</dd>
            </div>
          </dl>
        )}
      </section>
      <KnownColumns title="Complaints" value={data.complaints} noun="complaints" />
      <KnownColumns title="Evidence" value={data.evidence} noun="evidence records" />
      <section className="ca-drawer-section" aria-label="Hypotheses then">
        <h3>Hypotheses then</h3>
        <ItemList items={replayList(data.hypotheses)} empty="No hypotheses were recorded then." kind="HYPOTHESIS" />
      </section>
      <section className="ca-drawer-section" aria-label="Unknowns then">
        <h3>Unknowns then</h3>
        <ItemList items={replayList(data.unknowns)} empty="No unknowns were recorded then." />
      </section>
      <section className="ca-drawer-section" aria-label="Reviews then">
        <h3>Reviews then</h3>
        <ItemList items={replayList(data.reviews)} empty="No reviews were recorded then." />
      </section>
      <section className="ca-drawer-section" aria-label="Decision Brief then">
        <h3>Decision Brief then</h3>
        {Object.keys(brief).length ? (
          <dl className="ca-facts">
            <div>
              <dt>Brief</dt>
              <dd>
                {safeText(brief.business_id) ?? "—"}
                {brief.version !== undefined && brief.version !== null ? ` · version ${brief.version}` : ""}
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                {safeText(brief.status_label) ??
                  (safeText(brief.status ?? brief.status_now)
                    ? titleCase(String(brief.status ?? brief.status_now))
                    : "—")}
              </dd>
            </div>
            <div>
              <dt>Fingerprint</dt>
              <dd>
                <Fingerprint value={brief.content_hash ?? brief.hash} />
              </dd>
            </div>
          </dl>
        ) : (
          <p className="ac-muted">No Decision Brief existed then.</p>
        )}
      </section>
      <section className="ca-drawer-section" aria-label="Limitations of this replay">
        <h3>Limitations of this replay</h3>
        {limitations.length ? (
          <ul className="uw-intel-list">
            {limitations.map((item, index) => (
              <li key={index}>{replayItem(item).label}</li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No limitations reported.</p>
        )}
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// AI runs

const AI_ORIGIN = { origin: "AI", category: "AI" } as const;

/** Every AI run on the case: what it was, which model and versions, its guardrails, and whether a person reviewed it. */
export function CaseAiRuns({ investigationId, caseLabel }: { investigationId: string; caseLabel: string }) {
  const runs = useResource<AiRunsResponse>(trustPath(investigationId, "ai-runs"));
  const rows = listOf(runs.data?.items) as AiRun[];
  // The open run has its own address (panel=ai-run:<id>), so Back closes it and a refresh reopens it.
  const [chosen, setChosen] = usePanelState<AiRun>(
    "ai-run",
    (run) => String(run.business_id),
    (id) => rows.find((run) => String(run.business_id) === id) ?? null,
  );
  const counts = aiRunCountsText(runs.data?.counts);
  return (
    <>
      <Panel eyebrow={caseLabel} title={`AI runs${runs.data ? ` · ${rows.length}` : ""}`} source={runs}>
        <p className="ac-note">
          Each row is work done by AI, never by a person. An AI result is used only after a person reviews it, and only
          people sign decisions.
        </p>
        {counts && <p className="ac-muted">{counts}</p>}
        <Table
          caption="AI runs"
          rows={rows}
          rowKey={(row, index) => `${safeText(row.business_id) ?? "run"}:${index}`}
          empty={{
            title: "No AI runs on this investigation",
            detail: "AI work on this investigation (with its model and checks) appears here.",
          }}
          columns={[
            {
              key: "business_id",
              label: "Run ID",
              sortValue: (row) => safeText(row.business_id),
              render: (row) => (
                <span className="ca-person">
                  <strong>{safeText(row.business_id) ?? "AI run"}</strong>
                  <OriginBadge event={AI_ORIGIN} />
                </span>
              ),
            },
            { key: "kind", label: "What it did", render: (row) => aiRunKindLabel(row) },
            { key: "model", label: "Model", render: (row) => aiModelText(row) },
            {
              key: "status",
              label: "Status",
              sortValue: (row) => aiRunStatus(row.status).label,
              render: (row) => {
                const view = aiRunStatus(row.status);
                return <ToneBadge tone={view.tone} label={view.label} />;
              },
            },
            {
              key: "guardrails",
              label: "Guardrails",
              sortValue: (row) => guardrailSummary(row.guardrails).text,
              render: (row) => {
                const view = guardrailSummary(row.guardrails);
                return <ToneBadge tone={view.tone} label={view.text} />;
              },
            },
            {
              key: "execution_timestamp",
              label: "Run at",
              render: (row) => formatDate(row.execution_timestamp),
            },
            {
              key: "human_review",
              label: "Human review",
              sortValue: (row) => humanReviewView(row.human_review).label,
              render: (row) => {
                const view = humanReviewView(row.human_review);
                return <ToneBadge tone={view.tone} label={view.label} />;
              },
            },
            {
              key: "used_in_signed_decision",
              label: "Signed decision",
              sortValue: (row) => (row.used_in_signed_decision ? 1 : 0),
              render: (row) =>
                row.used_in_signed_decision ? (
                  <span className="ta-used-badge">Used in signed decision</span>
                ) : (
                  <span className="ac-muted">Not used</span>
                ),
            },
            {
              key: "details",
              label: "",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => setChosen(row)}>
                  Details
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {chosen && <AiRunDrawer run={chosen} onClose={() => setChosen(null)} />}
    </>
  );
}

function AiRunDrawer({ run, onClose }: { run: AiRun; onClose: () => void }) {
  const status = aiRunStatus(run.status);
  const review = humanReviewView(run.human_review);
  const guardrails = guardrailItems(run.guardrails);
  const usage = usageText(run);
  return (
    <Drawer title={`AI run: ${safeText(run.business_id) ?? aiRunKindLabel(run)}`} onClose={onClose}>
      <section className="ca-drawer-section" aria-label="AI run">
        <p>
          <OriginBadge event={AI_ORIGIN} /> <ToneBadge tone={status.tone} label={status.label} />
        </p>
        <p className="ac-muted">
          This is AI work, not a person's act. Its result counts only once a person reviewed it.
        </p>
        <dl className="ca-facts">
          <div>
            <dt>What it did</dt>
            <dd>{aiRunKindLabel(run)}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{aiModelText(run)}</dd>
          </div>
          <div>
            <dt>Prompt and software versions</dt>
            <dd>{aiVersionText(run)}</dd>
          </div>
          <div>
            <dt>Run at</dt>
            <dd>{formatDate(run.execution_timestamp)}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{durationText(run.duration ?? run.duration_ms) ?? "—"}</dd>
          </div>
          <div>
            <dt>Tokens and cost</dt>
            <dd>{usage ?? "Not reported"}</dd>
          </div>
          <div>
            <dt>Context fingerprint</dt>
            <dd>
              {safeText(run.context_hash) ? (
                <code className="ca-mono-sm ta-hash-full">{run.context_hash}</code>
              ) : (
                "Not recorded"
              )}
            </dd>
          </div>
          <div>
            <dt>Human review</dt>
            <dd>
              <ToneBadge tone={review.tone} label={review.label} />
              {review.at ? ` · ${formatDate(review.at)}` : ""}
            </dd>
          </div>
          <div>
            <dt>Signed decision</dt>
            <dd>{run.used_in_signed_decision ? "Used in a signed decision" : "Not used in a signed decision"}</dd>
          </div>
        </dl>
      </section>
      <section className="ca-drawer-section" aria-label="Guardrails">
        <h3>Guardrails</h3>
        {guardrails.length ? (
          <ul className="uw-checklist" aria-label="Guardrail checks">
            {guardrails.map((item) => (
              <li key={item.key}>
                <ToneBadge
                  tone={item.ok === true ? "good" : item.ok === false ? "critical" : "neutral"}
                  label={item.ok === true ? "Passed" : item.ok === false ? "Failed" : "Not reported"}
                />
                <span>
                  <strong>{item.label}</strong>
                  {item.detail && <small>{item.detail}</small>}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No guardrail results were reported for this run.</p>
        )}
      </section>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------------------
// Integrity

/** The integrity checks of the case: its signatures, its audit chain and its Decision Brief fingerprints. */
export function CaseIntegrity({
  investigationId,
  caseLabel,
  onOpenDecision,
}: {
  investigationId: string;
  caseLabel: string;
  onOpenDecision: (decisionId: string) => void;
}) {
  const integrity = useResource<IntegrityResponse>(trustPath(investigationId, "integrity"));
  const decisions = useResource<CaseDecisionContext>(caseDecisionPath(investigationId));
  const history = decisionHistory(decisions.data?.decisions, decisions.data?.current_decision ?? null);
  const signatures = signatureRows(integrity.data?.signatures, history);
  const chain = auditChainView(integrity.data?.audit_chain);
  const briefs = briefHashRows(integrity.data?.brief_hashes);
  const headline = integrityHeadline(integrity.data);
  return (
    <>
      <Panel
        eyebrow={caseLabel}
        title="Signatures"
        source={integrity}
        action={integrity.data ? <ToneBadge tone={headline.tone} label={headline.label} /> : undefined}
      >
        <p className="ac-note">
          MDARIX checks that each signature still matches the decision that was signed, that the investigation's audit
          events are unchanged, and that each Decision Brief still matches its fingerprint.
        </p>
        <Table
          caption="Signature verification"
          rows={signatures}
          rowKey={(row) => row.key}
          empty={{
            title: "No signatures yet",
            detail: "Signatures appear once an authorized person signs a decision.",
          }}
          columns={[
            { key: "businessId", label: "Signature ID", render: (row) => <strong>{row.businessId}</strong> },
            {
              key: "decision",
              label: "Decision",
              sortValue: (row) => row.decisionBusinessId ?? "",
              render: (row) =>
                row.decisionId ? (
                  <button type="button" className="ac-link" onClick={() => onOpenDecision(String(row.decisionId))}>
                    {row.decisionBusinessId ?? "Signed record"}
                  </button>
                ) : (
                  (row.decisionBusinessId ?? "—")
                ),
            },
            {
              key: "status",
              label: "Status",
              sortValue: (row) => row.label,
              render: (row) => <ToneBadge tone={row.tone} label={row.label} />,
            },
            {
              key: "failed",
              label: "Failed checks",
              sortValue: (row) => row.failed.length,
              render: (row) =>
                row.failed.length ? (
                  <span className="ca-person">
                    {row.failed.map((check) => (
                      <small key={check.key}>
                        {check.label}
                        {check.detail ? ` (${check.detail})` : ""}
                      </small>
                    ))}
                  </span>
                ) : (
                  <span className="ac-muted">None</span>
                ),
            },
          ]}
        />
      </Panel>
      <Panel
        eyebrow="Audit chain"
        title="Audit events of this investigation"
        source={integrity}
        action={integrity.data ? <ToneBadge tone={chain.tone} label={chain.label} /> : undefined}
      >
        <p
          className={chain.state === "broken" ? "ac-message tone-critical" : "ac-muted"}
          role={chain.state === "broken" ? "alert" : undefined}
        >
          {chain.state === "broken" ? `${chain.label}. ` : ""}
          {chain.detail ?? "Each audit event is linked to the one before it, so a changed event is detected."}
        </p>
      </Panel>
      <Panel eyebrow="Decision Brief" title="Brief version fingerprints" source={integrity}>
        <Table
          caption="Brief version fingerprints"
          rows={briefs}
          rowKey={(row) => row.key}
          empty={{ title: "No brief versions yet", detail: "Each approved Decision Brief version is checked here." }}
          columns={[
            { key: "businessId", label: "Brief ID", render: (row) => <strong>{row.businessId}</strong> },
            { key: "version", label: "Version", render: (row) => row.version ?? "—" },
            {
              key: "label",
              label: "Fingerprint check",
              render: (row) => <ToneBadge tone={row.tone} label={row.label} />,
            },
          ]}
        />
      </Panel>
    </>
  );
}
