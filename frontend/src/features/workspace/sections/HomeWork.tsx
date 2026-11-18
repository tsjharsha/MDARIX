import type { ReactNode } from "react";
import {
  ChevronRight,
  Factory,
  FileSignature,
  Gauge,
  PhoneCall,
  SearchCheck,
  ShieldAlert,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";
import { ProgressArc } from "../../shared/hero/HeroVisuals";
import { formatDay } from "../../../app/dates";
import { useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { caseDecisionPath, decisionsQueuePath } from "../humanDecision";
import { reviewListPath, type Review } from "../reviews";
import { FLAGSHIP_STEPS, flagshipCount, openFlagshipStep, type FlagshipRun } from "../oneStory";
import { useAiReady } from "../useAiStatus";
import { flagshipCopy } from "./OneStory";

/**
 * Home's first piece of work for each persona (UX1, Persona Blueprint waves A and B). The trial owner and the Quality
 * Leader continue the one onboarding story, the 7-step flagship that Getting started tells; every other persona gets
 * its own first task, and a persona that cannot act (the Executive) gets a place to look, never an action.
 */

/** The investigation's place for a decision or a review, opened in one click from Home. */
export const DECISION_PLACE = "Decisions & actions?part=decision";
/** The review opens in its own drawer: its address is the panel's (panel=review:<id>, CaseReviews.tsx). */
export const reviewPlace = (reviewId: string) =>
  `Decisions & actions?${new URLSearchParams({ part: "reviews", panel: `review:${reviewId}` })}`;

/** The reference people read (SAMPLE-INV-001), else the system ID. */
const ref = (row: { identifier?: string | null; business_id?: string | null }) => row.identifier ?? row.business_id;

type QueueItem = {
  investigation: {
    id: string;
    business_id?: string | null;
    identifier?: string | null;
    question?: string | null;
    product?: { id?: string | null; name?: string | null };
  };
  brief?: { business_id?: string | null; version?: number | null; quality_reviewer_name?: string | null } | null;
  awaiting_since?: string | null;
};
type Queue = { items?: QueueItem[] | null; total?: number | null };

/** The briefs waiting for a signature (GET /api/v1/decisions/queue): asked only for a persona that signs. */
export function useApprovals(on: boolean) {
  return useResource<Queue>(on ? decisionsQueuePath(1, 5) : null);
}

/** Risk reviews requested and not yet taken by anyone, and the person's own open ones. */
export function useRiskReviews(on: boolean): { items: Review[]; loading: boolean } {
  const queue = useResource<{ items?: Review[] | null }>(
    on ? reviewListPath({ type: "RISK", box: "queue", pageSize: 5 }) : null,
  );
  const mine = useResource<{ items?: Review[] | null }>(
    on ? reviewListPath({ type: "RISK", box: "mine", status: "REQUESTED,IN_PROGRESS", pageSize: 5 }) : null,
  );
  const items = [...(mine.data?.items ?? []), ...(queue.data?.items ?? [])];
  return { items, loading: queue.state === "loading" || mine.state === "loading" };
}

/** A lead without a button says plainly that nothing waits (never a promise of work that is not there). */
type Lead = { icon: LucideIcon; eyebrow: string; title: string; button?: string; go?: () => void } | null;

/** The personas whose Home leads with their own work rather than the flagship. */
export const OWN_LEAD = ["servicedesk", "handler", "investigator", "risk", "regulatory", "decision", "executive"];

/** The flagship on Home (UX1): the same seven steps as Getting started, at the step Getting started is on. */
export function FlagshipLead({ run }: { run: FlagshipRun }) {
  const { open, work } = useWorkspace();
  const aiReady = useAiReady(run.current === 3);
  const go = (section: string, tab?: string) => open(section as WorkspaceSection, tab);
  if (run.finished)
    return (
      <section className="uw-card uw-home-banner" aria-label="The sample investigation">
        <ProgressArc done={FLAGSHIP_STEPS} size={56} decorative />
        <span>
          <span className="ms-chip is-sample">Sample investigation</span> <b>All seven steps done</b>{" "}
          <span className="ac-muted uw-home-ref">{run.investigation.ref}</span>
        </span>
        <button type="button" className="ac-primary" onClick={() => open("Getting started")}>
          See what comes next <ChevronRight size={15} aria-hidden="true" />
        </button>
      </section>
    );
  return (
    <section className="uw-card uw-home-banner" aria-label="The sample investigation">
      <ProgressArc done={run.steps.filter((step) => step.done).length} size={56} decorative />
      <span>
        <span className="ms-chip is-sample">Sample investigation</span>{" "}
        <b>
          {flagshipCount(run)}: {run.steps[run.current].label}
        </b>{" "}
        <span className="ac-muted uw-home-ref">
          {run.product.label ?? run.product.name} · {run.investigation.ref}
        </span>
      </span>
      <button
        type="button"
        className="ac-primary"
        onClick={() => openFlagshipStep(run, run.current, go, work.setInvestigationId)}
      >
        {flagshipCopy(run, run.current, aiReady).b} <ChevronRight size={15} aria-hidden="true" />
      </button>
    </section>
  );
}

/**
 * The persona's own first piece of work in Home's band (UX1): Log a call, Triage, the investigation, the risk review,
 * the nearest legal clock, the decision waiting for a signature, the products. Null for a persona whose Home leads
 * with the flagship (the trial owner, the Quality Leader).
 */
export function PersonaLead({ clock }: { clock?: () => void }) {
  const { persona = "admin", open, work } = useWorkspace();
  const approvals = useApprovals(persona === "decision");
  const risk = useRiskReviews(persona === "risk");
  const waiting = approvals.data?.items?.[0];
  const review = risk.items[0];
  const lead: Lead =
    persona === "servicedesk"
      ? {
          icon: PhoneCall,
          eyebrow: "Calls to check",
          title: "Log a call the moment it comes in: MDARIX asks for the missing facts.",
          button: "Log a call",
          go: () => open("Complaints", "Calls to check?log=1"),
        }
      : persona === "handler"
        ? {
            icon: Stethoscope,
            eyebrow: "To triage",
            title: "Triage the most urgent complaint first.",
            button: "Triage next complaint",
            go: () => open("Complaints", "To triage"),
          }
        : persona === "investigator"
          ? {
              icon: SearchCheck,
              eyebrow: "Your investigation",
              title: "What is known, what is not, and the possible causes.",
              button: "Open the investigation",
              go: () => open("Investigations", "Evidence"),
            }
          : persona === "risk"
            ? review
              ? {
                  icon: ShieldAlert,
                  eyebrow: `${risk.items.length} risk ${risk.items.length === 1 ? "review" : "reviews"} requested`,
                  title: `${(review.investigation && ref(review.investigation)) ?? "An investigation"}: does the risk file need updating?`,
                  button: review.status === "IN_PROGRESS" ? "Continue the risk review" : "Start the risk review",
                  go: () => {
                    if (review.investigation?.id) work.setInvestigationId(review.investigation.id);
                    open("Investigations", reviewPlace(review.id));
                  },
                }
              : {
                  icon: ShieldAlert,
                  eyebrow: "Risk reviews",
                  title: risk.loading ? "Reading the risk reviews…" : "No risk review is requested from you right now.",
                }
            : persona === "regulatory" && clock
              ? {
                  icon: Gauge,
                  eyebrow: "Legal clocks",
                  title: "The nearest reporting deadline, with its market's decision tree.",
                  button: "Open the nearest clock",
                  go: clock,
                }
              : persona === "decision"
                ? waiting
                  ? {
                      icon: FileSignature,
                      eyebrow: `${approvals.data?.total ?? 1} ${
                        (approvals.data?.total ?? 1) === 1 ? "decision waits" : "decisions wait"
                      } for your signature`,
                      title: `${ref(waiting.investigation) ?? "An investigation"}: ${
                        waiting.investigation.question ?? "the brief accepted for decision"
                      }`,
                      button: "Review and sign",
                      go: () => {
                        work.setInvestigationId(
                          waiting.investigation.id,
                          waiting.investigation.product?.id ?? undefined,
                        );
                        open("Investigations", DECISION_PLACE);
                      },
                    }
                  : {
                      icon: FileSignature,
                      eyebrow: "Approvals",
                      title:
                        approvals.state === "loading" ? "Reading what waits…" : "Nothing waits for your signature now.",
                    }
                : persona === "executive"
                  ? {
                      icon: Factory,
                      eyebrow: "Product exposure",
                      title: "Each product's open complaints, investigations and actions, in one place.",
                      button: "See product exposure",
                      go: () => open("Products"),
                    }
                  : null;
  if (!lead) return null;
  const Icon = lead.icon;
  return (
    <section className="uw-card uw-home-banner" aria-label="Your first piece of work">
      <span className="uw-home-lead-ic" aria-hidden="true">
        <Icon size={30} />
      </span>
      <span>
        <span className="ac-eyebrow">{lead.eyebrow}</span> <b>{lead.title}</b>
      </span>
      {lead.button && (
        <button type="button" className="ac-primary" onClick={lead.go}>
          {lead.button} <ChevronRight size={15} aria-hidden="true" />
        </button>
      )}
    </section>
  );
}

/** One line of the one-page summary; "Not recorded" when the brief has none. */
function Line({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

type Brief = {
  created_by_name?: string | null;
  submitted_by_name?: string | null;
  quality_reviewer_name?: string | null;
  narrative?: { proposed_conclusion?: string | null; recommended_actions?: string[] | null; ai_draft_used?: boolean };
  supporting_evidence?: unknown[] | null;
  contradictions?: unknown[] | null;
  unknowns?: { open_count?: number | null } | null;
};

/**
 * The Decision Maker's approvals on Home (UX1, item 8): what waits for their signature, and for the first one a
 * one-page summary from the brief itself: the decision asked, who prepared and checked it, the evidence for and
 * against, what is still unknown and what happens if it is approved. One click opens it to sign or return.
 */
export function ApprovalsCard() {
  const { open, work } = useWorkspace();
  const approvals = useApprovals(true);
  const items = approvals.data?.items ?? [];
  const first = items[0];
  const screen = useResource<{ brief?: Brief | null }>(first ? caseDecisionPath(first.investigation.id) : null);
  const brief = screen.data?.brief;
  const sign = (item: QueueItem) => {
    work.setInvestigationId(item.investigation.id, item.investigation.product?.id ?? undefined);
    open("Investigations", DECISION_PLACE);
  };
  const actions = (brief?.narrative?.recommended_actions ?? []).slice(0, 3);
  return (
    <section className="uw-card uw-card-pad uw-home-approvals" aria-labelledby="home-approvals">
      <div className="uw-card-head">
        <h2 id="home-approvals">Approvals</h2>
        <span className="ac-muted">Briefs accepted for decision, waiting for a signature</span>
      </div>
      {approvals.state === "loading" ? (
        <p className="ac-muted" role="status">
          Reading what waits for your signature…
        </p>
      ) : !first ? (
        <p className="ac-muted">
          Nothing waits for your signature. A brief appears here once it is accepted for decision.
        </p>
      ) : (
        <>
          <p>
            <strong>
              {ref(first.investigation)} · brief v{first.brief?.version ?? 1}
            </strong>{" "}
            <span className="ac-muted">
              {first.investigation.product?.name ?? ""}
              {first.awaiting_since ? ` · waiting since ${formatDay(first.awaiting_since)}` : ""}
            </span>
          </p>
          <dl className="uw-os-lines uw-home-onepage">
            <Line term="Decision asked">
              {brief?.narrative?.proposed_conclusion || first.investigation.question || "Not recorded"}
              {brief?.narrative?.ai_draft_used && <span className="ms-chip">Started from an AI draft</span>}
            </Line>
            <Line term="Prepared by">
              {brief
                ? `${brief.submitted_by_name ?? brief.created_by_name ?? "Not recorded"}; checked by ${
                    brief.quality_reviewer_name ?? first.brief?.quality_reviewer_name ?? "not recorded"
                  }`
                : "…"}
            </Line>
            <Line term="Evidence">
              {brief
                ? `${brief.supporting_evidence?.length ?? 0} for · ${brief.contradictions?.length ?? 0} against`
                : "…"}
            </Line>
            <Line term="Still unknown">
              {brief
                ? `${brief.unknowns?.open_count ?? 0} open ${brief.unknowns?.open_count === 1 ? "unknown" : "unknowns"}`
                : "…"}
            </Line>
            <Line term="If approved">
              {actions.length ? (
                <ul>
                  {actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ul>
              ) : brief ? (
                "No follow-up action proposed"
              ) : (
                "…"
              )}
            </Line>
          </dl>
          <p className="ac-muted">
            Nothing is signed until you sign with your password and authenticator code. You may also return it with
            comments.
          </p>
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={() => sign(first)}>
              Open {ref(first.investigation)} to sign or return
            </button>
          </div>
          {items.length > 1 && (
            <ul className="uw-home-list">
              {items.slice(1).map((item) => (
                <li key={item.investigation.id}>
                  <button type="button" className="ac-link" onClick={() => sign(item)}>
                    {ref(item.investigation)} · brief v{item.brief?.version ?? 1}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

/** The Risk Reviewer's requested reviews on Home (UX1): each opens its review on the investigation in one click. */
export function RiskReviewsCard() {
  const { open, work } = useWorkspace();
  const { items, loading } = useRiskReviews(true);
  return (
    <section className="uw-card uw-card-pad uw-home-approvals" aria-labelledby="home-risk">
      <div className="uw-card-head">
        <h2 id="home-risk">Risk reviews requested</h2>
        <span className="ac-muted">Requested from the risk reviewers, or taken by you</span>
      </div>
      {loading ? (
        <p className="ac-muted" role="status">
          Reading the risk reviews…
        </p>
      ) : !items.length ? (
        <p className="ac-muted">No risk review is requested. A request appears here first.</p>
      ) : (
        <ul className="uw-home-list">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="uw-home-row"
                onClick={() => {
                  if (item.investigation?.id) work.setInvestigationId(item.investigation.id);
                  open("Investigations", reviewPlace(item.id));
                }}
              >
                <ShieldAlert size={18} aria-hidden="true" />
                <span className="uw-home-what">
                  <b>
                    {(item.investigation && ref(item.investigation)) ?? "An investigation"} · {item.business_id}
                  </b>
                  <small>
                    {item.status_label ?? item.status}
                    {item.due_at ? ` · Due ${formatDay(item.due_at)}` : ""}
                    {item.request_reason ? ` · ${item.request_reason}` : ""}
                  </small>
                </span>
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
