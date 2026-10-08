import { useState } from "react";
import { ChevronRight, Play } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { sectionAllowed, useCan, useWorkspace } from "../workspaceContext";
import { CasePriority } from "./CaseHeader";
import { ReviewDue, ReviewStatusBadge } from "./CaseReviews";
import {
  REVIEW_SUMMARY_PATH,
  reviewCase,
  reviewPath,
  reviewTiles,
  reviewTypeLabel,
  reviewsTab,
  type Review,
  type ReviewSummary,
} from "../reviews";
import {
  BRIEF_SUMMARY_PATH,
  BRIEF_TAB,
  briefListPath,
  briefStatusView,
  briefTiles,
  summaryCase,
  type BriefSummary,
  type SummaryCase,
} from "../decisionBrief";

/** Dashboard: the risk and regulatory reviews of a reviewer (risk.review or regulatory.review). */
export function ReviewsDashboardPanel() {
  const { session } = useWorkspace();
  const risk = useCan("risk.review");
  const regulatory = useCan("regulatory.review");
  const allowed = sectionAllowed("Investigations", session?.allowed_menu, session?.business_permissions);
  if ((!risk && !regulatory) || !allowed) return null;
  return <ReviewsDashboard />;
}

function ReviewsDashboard() {
  const { work, open, notify } = useWorkspace();
  const summary = useResource<ReviewSummary>(REVIEW_SUMMARY_PATH);
  const [busy, setBusy] = useState("");
  // A role that may not read the summary simply does not see the panel.
  if (summary.state === "forbidden") return null;
  const ready = summary.state === "ready";
  const tiles = reviewTiles(summary.data);
  const mine = (listOf(summary.data?.mine) as Review[]).slice(0, 6);
  const queue = (listOf(summary.data?.queue) as Review[]).slice(0, 6);
  const openReview = (review: Review) => {
    const kase = reviewCase(review);
    if (kase) work.setInvestigationId(kase.investigationId, kase.productId);
    open("Investigations", reviewsTab(String(review.id)));
  };
  const start = async (review: Review) => {
    if (busy) return;
    setBusy(String(review.id));
    try {
      await send(reviewPath(String(review.id), "start"), "POST");
      notify(`${safeText(review.business_id) ?? "Review"} started. It is assigned to you.`);
      openReview(review);
    } catch (failure) {
      notify(errorText(failure, "The review could not be started."), "critical");
      summary.reload();
    } finally {
      setBusy("");
    }
  };
  const row = (review: Review, canStart: boolean) => {
    const name = safeText(review.business_id) ?? "Review";
    return (
      <li key={review.id}>
        <span>
          <strong>
            {name} · {reviewTypeLabel(review)}
          </strong>
          <small>
            {safeText(review.investigation?.business_id) ?? "Case"}
            {safeText(review.investigation?.product?.name) ? ` · ${review.investigation?.product?.name}` : ""}
            {safeText(review.investigation?.question) ? ` · ${review.investigation?.question}` : ""}
          </small>
        </span>
        <span className="uw-case-meta">
          <ReviewStatusBadge review={review} />
          <small>
            <ReviewDue review={review} />
          </small>
        </span>
        <span className="uw-task-actions">
          {canStart && review.actions?.can_start !== false && (
            <button
              type="button"
              className="ac-secondary"
              disabled={!!busy}
              aria-label={`Start ${name}`}
              onClick={() => void start(review)}
            >
              <Play size={14} aria-hidden="true" /> {busy === String(review.id) ? "Starting…" : "Start"}
            </button>
          )}
          <button type="button" className="ac-link" aria-label={`Open ${name}`} onClick={() => openReview(review)}>
            Open <ChevronRight size={14} aria-hidden="true" />
          </button>
        </span>
      </li>
    );
  };
  return (
    <Panel eyebrow="Reviews" title="Risk and regulatory reviews" source={summary}>
      <div className="uw-task-counts" role="group" aria-label="Your review counts">
        {tiles.map((tile) => (
          <div key={tile.key} className={`uw-task-count ${tile.urgent && (tile.value ?? 0) > 0 ? "urgent" : ""}`}>
            <strong>{ready ? (tile.value ?? 0) : "…"}</strong>
            <span>{tile.label}</span>
          </div>
        ))}
      </div>
      {ready && (
        <div className="ac-grid two">
          <section aria-label="My reviews">
            <h3>My reviews</h3>
            {mine.length ? (
              <ul className="uw-list">{mine.map((review) => row(review, false))}</ul>
            ) : (
              <Empty title="No reviews assigned to you" detail="Reviews you start or are given appear here." />
            )}
          </section>
          <section aria-label="Review queue">
            <h3>Waiting in your queue</h3>
            {queue.length ? (
              <ul className="uw-list">{queue.map((review) => row(review, true))}</ul>
            ) : (
              <Empty title="Your review queue is empty" detail="Reviews requested for your role appear here." />
            )}
          </section>
        </div>
      )}
      <p className="ac-note">MDARIX gathers each review's context. The outcome is always the reviewer's judgement.</p>
    </Panel>
  );
}

/** Dashboard: Decision Briefs for quality reviewers (quality.review). */
export function QualityReviewDashboardPanel() {
  const { session } = useWorkspace();
  const canReview = useCan("quality.review");
  const allowed = sectionAllowed("Investigations", session?.allowed_menu, session?.business_permissions);
  if (!canReview || !allowed) return null;
  return <QualityReviewDashboard />;
}

type BriefListView = "UNDER_REVIEW" | "RETURNED";

function QualityReviewDashboard() {
  const { work, open } = useWorkspace();
  const summary = useResource<BriefSummary>(BRIEF_SUMMARY_PATH);
  const [list, setList] = useState<BriefListView | null>(null);
  if (summary.state === "forbidden") return null;
  const ready = summary.state === "ready";
  const tiles = briefTiles(summary.data);
  const awaiting = listOf(summary.data?.awaiting).map((item, index) => summaryCase(item, index));
  const blocked = listOf(summary.data?.blocked).map((item, index) => summaryCase(item, index));
  const openBrief = (item: SummaryCase) => {
    if (item.investigationId) work.setInvestigationId(item.investigationId, item.productId);
    open("Investigations", BRIEF_TAB);
  };
  const listFor: Partial<Record<string, BriefListView>> = {
    under_review_by_me: "UNDER_REVIEW",
    returned_open: "RETURNED",
  };
  return (
    <Panel eyebrow="Quality review" title="Decision Briefs" source={summary}>
      <div className="uw-task-counts" role="group" aria-label="Decision Brief counts">
        {tiles.map((tile) => {
          const target = listFor[tile.key];
          const className = `uw-task-count ${tile.urgent && (tile.value ?? 0) > 0 ? "urgent" : ""}`;
          const body = (
            <>
              <strong>{ready ? (tile.value ?? 0) : "…"}</strong>
              <span>{tile.label}</span>
            </>
          );
          return target ? (
            <button
              type="button"
              key={tile.key}
              className={className}
              aria-pressed={list === target}
              onClick={() => setList((value) => (value === target ? null : target))}
            >
              {body}
            </button>
          ) : (
            <div key={tile.key} className={className}>
              {body}
            </div>
          );
        })}
      </div>
      {ready && (
        <div className="ac-grid two">
          <section aria-label="Awaiting review">
            <h3>Awaiting review</h3>
            {awaiting.length ? (
              <ul className="uw-list">
                {awaiting.map((item) => (
                  <li key={item.key}>
                    <span>
                      <strong>
                        {item.caseId}
                        {item.briefId ? ` · ${item.briefId}` : ""}
                        {item.version ? ` · version ${item.version}` : ""}
                      </strong>
                      <small>{item.question ?? "No question recorded"}</small>
                      <small className="ac-muted">
                        {item.submittedBy ? `Submitted by ${item.submittedBy}` : "Submitted"}
                        {item.submittedAt ? ` · ${formatDate(item.submittedAt)}` : ""}
                      </small>
                    </span>
                    {item.priority && <CasePriority priority={item.priority} />}
                    <button
                      type="button"
                      className="ac-link"
                      aria-label={`Open the Decision Brief of ${item.caseId}`}
                      onClick={() => openBrief(item)}
                    >
                      Open <ChevronRight size={14} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="Nothing awaits review" detail="Briefs submitted for a quality review appear here." />
            )}
          </section>
          <section aria-label="Blocked cases">
            <h3>Blocked cases</h3>
            {blocked.length ? (
              <ul className="uw-list">
                {blocked.map((item) => (
                  <li key={item.key}>
                    <span>
                      <strong>{item.caseId}</strong>
                      {item.question && <small>{item.question}</small>}
                      {item.blocking.length > 0 && (
                        <small className="uw-flag-critical">Blocked by: {item.blocking.join(" · ")}</small>
                      )}
                    </span>
                    <button
                      type="button"
                      className="ac-link"
                      aria-label={`Open the Decision Brief of ${item.caseId}`}
                      onClick={() => openBrief(item)}
                    >
                      Open <ChevronRight size={14} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty title="No blocked cases" detail="Cases whose brief cannot be submitted yet appear here." />
            )}
          </section>
        </div>
      )}
      {list && <BriefList status={list} onOpen={openBrief} />}
      <p className="ac-note">
        A quality review checks that a brief is fit to decide on. It does not decide the case: authorized approvers do.
      </p>
    </Panel>
  );
}

/** Briefs in one status (under review, returned), from the brief list. */
function BriefList({ status, onOpen }: { status: BriefListView; onOpen: (item: SummaryCase) => void }) {
  const briefs = useResource<unknown>(briefListPath(status, 1, 10));
  const rows = listOf(briefs.data) as Array<Record<string, unknown>>;
  const title = status === "UNDER_REVIEW" ? "Briefs under review" : "Briefs returned to their authors";
  if (briefs.state === "forbidden") return null;
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      {briefs.state === "loading" && <p className="ac-muted">Loading…</p>}
      {briefs.state === "error" && (
        <p className="ca-inline-error">{briefs.error ?? "The briefs could not be loaded."}</p>
      )}
      {briefs.state === "ready" &&
        (rows.length ? (
          <ul className="uw-list">
            {rows.map((row, index) => {
              const item = summaryCase(row, index);
              const brief = safeText(row.business_id);
              return (
                <li key={item.key}>
                  <span>
                    <strong>
                      {item.caseId}
                      {brief && brief !== item.caseId ? ` · ${brief}` : ""}
                      {item.version ? ` · version ${item.version}` : ""}
                    </strong>
                    {item.question && <small>{item.question}</small>}
                  </span>
                  <ReviewStatusLabel row={row} />
                  <button type="button" className="ac-link" onClick={() => onOpen(item)}>
                    Open <ChevronRight size={14} aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="ac-muted">None right now.</p>
        ))}
    </section>
  );
}

function ReviewStatusLabel({ row }: { row: Record<string, unknown> }) {
  return (
    <small>{briefStatusView({ status: row.status as string, status_label: row.status_label as string }).label}</small>
  );
}
