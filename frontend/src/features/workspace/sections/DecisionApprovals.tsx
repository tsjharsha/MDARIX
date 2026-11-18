import { useState } from "react";
import { ChevronRight, FileSignature } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Table, formatDate, listOf, useResource } from "../../customer-admin/shared";
import { sectionAllowed, useCan, useWorkspace } from "../workspaceContext";
import { CasePriority } from "./CaseHeader";
import { DecisionRecordDrawer } from "./DecisionRecord";
import {
  DECISIONS_SUMMARY_PATH,
  decisionTiles,
  QUEUE_SORTS,
  decisionsQueuePath,
  queueRow,
  recentDecision,
  sortQueue,
  type DecisionSummary,
  type QueueRow,
  type RecentDecision,
} from "../humanDecision";
import { decisionTab } from "../decisionTabs";
import { useServerSort } from "../../../app/tableSort";

const PAGE_SIZE = 20;

function QueueDue({ row }: { row: QueueRow }) {
  if (!row.dueAt) return row.overdue ? <span className="uw-flag-critical">Overdue</span> : <>No due date</>;
  return row.overdue ? (
    <span className="uw-flag-critical">{formatDate(row.dueAt)} · overdue</span>
  ) : (
    <>{formatDate(row.dueAt)}</>
  );
}

/** The count tiles of the decision maker's summary. */
function DecisionTiles({ summary, ready }: { summary: DecisionSummary | null; ready: boolean }) {
  return (
    <div className="uw-task-counts" role="group" aria-label="Decision counts">
      {decisionTiles(summary).map((tile) => (
        <div key={tile.key} className={`uw-task-count ${tile.urgent && (tile.value ?? 0) > 0 ? "urgent" : ""}`}>
          <strong>{ready ? (tile.value ?? 0) : "…"}</strong>
          <span>{tile.label}</span>
        </div>
      ))}
    </div>
  );
}

/** Recently signed decisions, each opening its signed record. */
function RecentDecisions({ items, onRecord }: { items: RecentDecision[]; onRecord: (ref: string) => void }) {
  if (!items.length)
    return <Empty title="No decisions signed recently" detail="Decisions signed in your organization appear here." />;
  return (
    <ul className="uw-list" aria-label="Recently signed decisions">
      {items.map((item) => (
        <li key={item.key}>
          <span>
            <strong>
              {item.decisionId}
              {item.caseId ? ` · ${item.caseId}` : ""}
            </strong>
            <small>
              {item.signer ? `Signed by ${item.signer}` : "Signed"}
              {item.decidedAt ? ` · ${formatDate(item.decidedAt)}` : ""}
            </small>
          </span>
          <ToneBadge tone={item.outcomeTone} label={item.outcome} />
          {item.ref && (
            <button
              type="button"
              className="ac-link"
              aria-label={`Open the signed record of ${item.decisionId}`}
              onClick={() => onRecord(String(item.ref))}
            >
              <FileSignature size={14} aria-hidden="true" /> Signed record
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Decisions › Approvals: the briefs accepted for decision that wait for a signature, critical and overdue first, with
 * the case, its due date, how long it has waited and the reviews it needed; and the decisions signed recently.
 */
export function ApprovalsPanel({ onOpen }: { onOpen: (row: QueueRow) => void }) {
  const [page, setPage] = useState(1);
  const { sort, onSort } = useServerSort(() => setPage(1));
  const queue = useResource<{ items?: unknown[]; total?: number }>(decisionsQueuePath(page, PAGE_SIZE, sort));
  const summary = useResource<DecisionSummary>(DECISIONS_SUMMARY_PATH);
  const [recordId, setRecordId] = useState<string | null>(null);
  // The server orders the whole queue (most critical first, or the column a heading chose); rows are one page.
  const rows = listOf(queue.data?.items ?? queue.data).map((item, index) => queueRow(item, index));
  const total = typeof queue.data?.total === "number" ? queue.data.total : rows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const recent = listOf(summary.data?.recent).map((item, index) => recentDecision(item, index));
  return (
    <>
      {summary.state !== "forbidden" && (
        <Panel eyebrow="Decisions" title="Your decision work" source={summary}>
          <DecisionTiles summary={summary.data} ready={summary.state === "ready"} />
        </Panel>
      )}
      <Panel eyebrow="Approvals" title="Briefs awaiting your decision" source={queue}>
        <Table
          caption="Briefs awaiting a decision"
          rows={rows}
          rowKey={(row) => row.key}
          serverSort={{ sort, onSort, keys: QUEUE_SORTS }}
          empty={{
            title: "Nothing awaits your decision",
            detail: "Decision Briefs a quality reviewer accepted for decision appear here.",
          }}
          columns={[
            {
              key: "caseId",
              label: "Investigation",
              fields: ["question"],
              render: (row) => (
                <span className="ca-person">
                  <strong>
                    {row.reference}
                    {row.critical && (
                      <>
                        {" "}
                        <ToneBadge tone="critical" label="Critical" />
                      </>
                    )}
                  </strong>
                  {row.question && <small>{row.question}</small>}
                </span>
              ),
            },
            { key: "product", label: "Product", render: (row) => row.product ?? "—" },
            {
              key: "brief",
              label: "Brief",
              sortValue: (row) => row.briefId ?? "",
              render: (row) => (
                <span className="ca-person">
                  <span>
                    {row.briefId ?? "—"}
                    {row.version ? ` · v${row.version}` : ""}
                  </span>
                  {row.qualityReviewer && <small>Accepted by {row.qualityReviewer}</small>}
                </span>
              ),
            },
            {
              key: "priority",
              label: "Priority",
              sortValue: (row) => row.priority ?? "",
              render: (row) => <CasePriority priority={row.priority} />,
            },
            {
              key: "dueAt",
              label: "Due",
              sortValue: (row) => row.dueAt ?? "",
              render: (row) => <QueueDue row={row} />,
            },
            {
              key: "awaitingSince",
              label: "Awaiting since",
              sortValue: (row) => row.awaitingSince ?? "",
              render: (row) => formatDate(row.awaitingSince),
            },
            {
              key: "reviews",
              label: "Required reviews",
              sortValue: (row) => row.requiredReviews.join(", "),
              render: (row) =>
                row.requiredReviews.length ? (
                  <span className="ca-person">
                    {row.requiredReviews.map((review) => (
                      <small key={review}>{review}</small>
                    ))}
                  </span>
                ) : (
                  <span className="ac-muted">None</span>
                ),
            },
            {
              key: "open",
              label: "",
              render: (row) =>
                row.investigationId ? (
                  <span className="ca-person">
                    <button
                      type="button"
                      className="ac-link"
                      aria-label={`Open the decision of ${row.reference}`}
                      onClick={() => onOpen(row)}
                    >
                      Open <ChevronRight size={14} aria-hidden="true" />
                    </button>
                    {!row.canDecide && row.reason && <small className="ac-muted">{row.reason}</small>}
                  </span>
                ) : null,
            },
          ]}
        />
        {pages > 1 && (
          <div className="ca-action-row uw-pager">
            <span className="ac-muted">
              Page {page} of {pages}
            </span>
            <button
              type="button"
              className="ac-secondary"
              disabled={page <= 1 || queue.state === "loading"}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="ac-secondary"
              disabled={page >= pages || queue.state === "loading"}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </button>
          </div>
        )}
        <p className="ac-note">
          You never sign a brief you prepared or reviewed, and administrators never sign. MDARIX checks this again when
          you sign.
        </p>
      </Panel>
      {summary.state === "ready" && (
        <Panel eyebrow="Decisions" title="Recently signed">
          <RecentDecisions items={recent} onRecord={setRecordId} />
        </Panel>
      )}
      {recordId && <DecisionRecordDrawer key={recordId} decisionId={recordId} onClose={() => setRecordId(null)} />}
    </>
  );
}

/** Dashboard: the decision maker's work (decision.sign): counts, what awaits a signature, what was signed recently. */
export function DecisionsDashboardPanel() {
  const { session } = useWorkspace();
  const canSign = useCan("decision.sign");
  const allowed = sectionAllowed(
    "Decisions",
    session?.allowed_menu,
    session?.business_permissions,
    session?.sample_only,
  );
  if (!canSign || !allowed) return null;
  return <DecisionsDashboard />;
}

function DecisionsDashboard() {
  const { work, open } = useWorkspace();
  const summary = useResource<DecisionSummary>(DECISIONS_SUMMARY_PATH);
  const [recordId, setRecordId] = useState<string | null>(null);
  // A role that may not read the summary simply does not see the panel.
  if (summary.state === "forbidden") return null;
  const ready = summary.state === "ready";
  const awaiting = sortQueue(listOf(summary.data?.awaiting).map((item, index) => queueRow(item, index))).slice(0, 6);
  const recent = listOf(summary.data?.recent)
    .map((item, index) => recentDecision(item, index))
    .slice(0, 6);
  const openCase = (row: QueueRow) => {
    if (!row.investigationId) return;
    // With its product the case also becomes the working context; without, the Decision tab opens it on its own.
    if (row.productId) work.setInvestigationId(row.investigationId, row.productId);
    open("Decisions", decisionTab({ caseId: row.investigationId }));
  };
  return (
    <Panel
      eyebrow="Decisions"
      title="Decisions awaiting your signature"
      source={summary}
      action={
        <button type="button" className="ac-link" onClick={() => open("Decisions", "Approvals")}>
          Approvals <ChevronRight size={14} aria-hidden="true" />
        </button>
      }
    >
      <DecisionTiles summary={summary.data} ready={ready} />
      {ready && (
        <div className="ac-grid two">
          <section aria-label="Awaiting your signature">
            <h3>Awaiting your signature</h3>
            {awaiting.length ? (
              <ul className="uw-list">
                {awaiting.map((row) => (
                  <li key={row.key}>
                    <span>
                      <strong>
                        {row.reference}
                        {row.briefId ? ` · ${row.briefId}` : ""}
                        {row.version ? ` · version ${row.version}` : ""}
                      </strong>
                      <small>{row.question ?? "No question recorded"}</small>
                      <small className="ac-muted">
                        {row.awaitingSince ? `Waiting since ${formatDate(row.awaitingSince)}` : "Waiting"}
                        {row.critical ? " · critical" : ""}
                      </small>
                    </span>
                    <span className="uw-case-meta">
                      {row.priority && <CasePriority priority={row.priority} />}
                      <small>
                        <QueueDue row={row} />
                      </small>
                    </span>
                    {row.investigationId && (
                      <button
                        type="button"
                        className="ac-link"
                        aria-label={`Open the decision of ${row.reference}`}
                        onClick={() => openCase(row)}
                      >
                        Open <ChevronRight size={14} aria-hidden="true" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="Nothing awaits your signature" detail="Briefs accepted for decision appear here." />
            )}
          </section>
          <section aria-label="Recently signed">
            <h3>Recently signed</h3>
            <RecentDecisions items={recent} onRecord={setRecordId} />
          </section>
        </div>
      )}
      <p className="ac-note">MDARIX prepares the context. The decision and its signature are always a person's own.</p>
      {recordId && <DecisionRecordDrawer key={recordId} decisionId={recordId} onClose={() => setRecordId(null)} />}
    </Panel>
  );
}
