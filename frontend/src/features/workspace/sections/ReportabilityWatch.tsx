import { useContext, useEffect, useState } from "react";
import { EscalateButton } from "./Triage";
import {
  AlarmClock,
  CheckCircle2,
  ClipboardList,
  FileSearch,
  HelpCircle,
  Hourglass,
  Scale,
  ScanSearch,
  Settings2,
} from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { formatDate, useResource } from "../../customer-admin/shared";
import { deadlineLabel, formatDay } from "../../../app/dates";
import {
  WorkspaceContext,
  investigationRequestFor,
  useCan,
  useNavigation,
  useOpenInvestigation,
  useTabParam,
} from "../workspaceContext";
import { treePlace } from "../decisionTrees";
import { recordId } from "../complaintReview";
import { owesWorksheet, reportsTab } from "../authorityReports";
import {
  AWARE_SOURCE,
  TRIGGER_LABELS,
  WATCH_SHOWS,
  clockText,
  timelinessOf,
  watchHeadline,
  watchPath,
  watchStateOf,
  type WatchItem,
  type WatchList,
  type WatchShow,
} from "../reportability";
import { marketChip } from "../marketAssessment";
import { AlsoKnownAs, StatusBadge, countOf } from "./common";
import { ChipFilter, Hero, Pager, ProductFilter } from "./boardParts";
import { MarketAssessmentDrawer } from "./MarketAssessment";
import { BasisChips, BasisNote } from "../../shared/Basis";

/** Whether the signed-in role may record a reportability decision (the server's rule). */
function useCanDecide() {
  const review = useCan("regulatory.review");
  const approve = useCan("regulatory.approve");
  return review || approve;
}

/**
 * Complaints › Reportability: every complaint that reports a death, a serious injury or a malfunction (or a patient
 * whose outcome is unknown), with its reporting clocks against the organization's own windows, most urgent first. A
 * person records the decision; MDARIX keeps the clock and never submits a report.
 */
export function ReportabilityWatch({ onOpenTab }: { onOpenTab: (tab: string) => void }) {
  const canEditWindows = useCan("regulatory.approve");
  const [show, setShow] = useState<WatchShow>("open");
  const [product, setProduct] = useState("");
  const [page, setPage] = useState(1);
  const [chosen, setDeciding] = useState<WatchItem | null>(null);
  // A complaint's page or a reportability task opens that complaint's assessment (Reportability?complaint=<id>).
  const [linked, setLinked] = useTabParam("complaint");
  const list = useResource<WatchList>(watchPath(show, product, page));
  const fromLink = linked ? ((list.data?.items ?? []).find((item) => item.id === linked) ?? null) : null;
  // 0.10.83 (D2.3): on the new navigation a complaint is answered on its market's tree; the drawer's address (a
  // complaint's page, a reportability task) still works and opens the tree.
  const workspace = useContext(WorkspaceContext);
  const toTree = useNavigation() === "new";
  useEffect(() => {
    if (!toTree || !linked || !workspace) return;
    const place = treePlace(null, linked);
    workspace.open(place.section, place.tab);
  }, [toTree, linked, workspace]);
  const deciding = toTree ? null : (chosen ?? fromLink);
  const summary = list.data?.summary;
  const headline = watchHeadline(summary);
  const items = list.data?.items ?? [];
  const choose = (next: WatchShow) => {
    setShow(next);
    setPage(1);
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={list.data ? headline.tone : "neutral"}
        icon={<AlarmClock size={28} />}
        eyebrow="Reportability watch"
        title={headline.title}
        detail={headline.detail}
      />
      {summary && !summary.configured && (
        <div className="ac-message tone-critical uw-rw-callout" role="status">
          <Settings2 size={16} aria-hidden="true" />
          <span>
            <strong>No reporting windows yet.</strong> Enter the windows from your procedure (FDA, EU or others) and
            every complaint here gets its due date.
          </span>
          <button type="button" className="ac-secondary" onClick={() => onOpenTab("Reporting windows")}>
            {canEditWindows ? "Enter reporting windows" : "See reporting windows"}
          </button>
        </div>
      )}
      {summary && summary.held_on_second_look > 0 && (
        <div className="ac-message tone-critical uw-rw-callout" role="status">
          <ScanSearch size={16} aria-hidden="true" />
          <span>
            <strong>
              {countOf(summary.held_on_second_look, "cancelled record or inquiry", "cancelled records or inquiries")}
            </strong>{" "}
            {summary.held_on_second_look === 1 ? "reports" : "report"} a death, a serious injury or a malfunction.
            Decide on the second look whether each is a complaint: a confirmed one joins this watch with its clock.
          </span>
          <button type="button" className="ac-secondary" onClick={() => onOpenTab("Second look")}>
            Open the second look
          </button>
        </div>
      )}
      <div className="uw-cr-stats">
        <StatTile
          label="Overdue"
          value={summary ? summary.overdue : null}
          detail="Past the reporting window"
          icon={<AlarmClock size={18} />}
          tone={summary?.overdue ? "critical" : undefined}
          onOpen={() => choose("overdue")}
        />
        <StatTile
          label="Due soon"
          value={summary ? summary.due_soon : null}
          detail="Within days of the window"
          icon={<Hourglass size={18} />}
          tone={summary?.due_soon ? "warning" : undefined}
          onOpen={() => choose("due_soon")}
        />
        <StatTile
          label="Missing answers"
          value={summary ? summary.follow_up : null}
          detail="Follow up before deciding"
          icon={<HelpCircle size={18} />}
          tone={summary?.follow_up ? "warning" : undefined}
          onOpen={() => choose("follow_up")}
        />
        <StatTile
          label="Decided inside the window"
          value={summary ? `${summary.decided_in_window} of ${summary.decided_in_window + summary.decided_late}` : null}
          detail={summary?.decided_late ? `${summary.decided_late} after the window` : "Timeliness of decisions"}
          icon={<CheckCircle2 size={18} />}
          tone={summary?.decided_late ? "serious" : undefined}
          onOpen={() => choose("decided")}
        />
      </div>
      <Panel
        eyebrow="Reportability"
        title={
          show === "decided" ? "Decided complaints, latest first" : "Complaints needing a decision, most urgent first"
        }
        source={list}
      >
        <div className="uw-cr-toolbar">
          <ChipFilter
            label="Which complaints"
            options={WATCH_SHOWS}
            value={show}
            counts={{
              open: summary?.open,
              overdue: summary?.overdue,
              due_soon: summary?.due_soon,
              follow_up: summary?.follow_up,
              decided: summary?.decided,
            }}
            onChange={choose}
          />
          <ProductFilter
            value={product}
            onChange={(value) => {
              setProduct(value);
              setPage(1);
            }}
          />
        </div>
        {list.data?.truncated && (
          <p className="uw-hint">Only the first 20,000 complaints were read. Choose a product to see all of its own.</p>
        )}
        {items.length ? (
          <ul className="uw-cr-list">
            {items.map((item) => (
              <WatchCard
                key={item.id}
                item={item}
                onDecide={() => {
                  if (!toTree) return setDeciding(item);
                  const place = treePlace(null, item.id);
                  workspace?.open(place.section, place.tab);
                }}
                onReports={() => onOpenTab(reportsTab(item.id))}
              />
            ))}
          </ul>
        ) : (
          <Empty
            title={show === "decided" ? "No decisions yet" : "Nothing waits for a decision"}
            detail="Complaints reporting a death, a serious injury or a malfunction, or a patient whose outcome is unknown, appear here."
          />
        )}
        <Pager page={page} pages={list.data?.pages ?? 1} onPage={setPage} />
        <p className="ac-note">
          The windows come from your procedure; MDARIX keeps the clock. Windows that rest on a judgment (an FDA
          5-work-day report, an EU serious public health threat) are applied by your reviewer.
        </p>
        <BasisNote />
      </Panel>
      {deciding && (
        <MarketAssessmentDrawer
          complaint={deciding}
          onClose={() => {
            setDeciding(null);
            if (linked) setLinked(null);
          }}
          onChanged={list.reload}
        />
      )}
    </div>
  );
}

/** One complaint on the watch (exported for its unit test). */
export function WatchCard({
  item,
  onDecide,
  onReports,
}: {
  item: WatchItem;
  onDecide: () => void;
  onReports?: () => void;
}) {
  const canDecide = useCanDecide();
  const openInvestigation = useOpenInvestigation();
  const navigation = useNavigation();
  const state = watchStateOf(item.state);
  const request = investigationRequestFor(item);
  const name = recordId(item);
  const timeliness = timelinessOf(item.decision);
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${state.tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{name}</strong>
          <span className="uw-cr-meta">
            {item.product_name ?? "No product"}
            {item.version ? ` · ${item.version}` : ""} · {item.country ?? "Country not recorded"}
          </span>
          <ToneBadge tone={state.tone} label={state.label} />
          <StatusBadge value={item.status} />
        </div>
        {item.state !== "DECIDED" && (
          <div className={`uw-rw-clock tone-${state.tone}`}>
            <strong>{item.binding ? clockText(item.binding) : state.label}</strong>
            {item.binding && (
              <span>
                Due by {deadlineLabel(item.binding)} · {item.binding.window}{" "}
                <BasisChips ids={item.binding.basis} label="Basis of the window" />
              </span>
            )}
            {item.aware_date && (
              <span>
                Aware {formatDay(item.aware_at ?? item.aware_date)} by the{" "}
                {AWARE_SOURCE[item.aware_source ?? ""] ?? "records"} · {countOf(item.days_since_aware ?? 0, "day")} ago
              </span>
            )}
          </div>
        )}
        <ul className="uw-cr-chips" aria-label="What it reports">
          {item.triggers.map((trigger) => (
            <li key={trigger} className={`uw-cr-chip tone-${trigger === "MALFUNCTION" ? "serious" : "critical"}`}>
              <ToneIcon tone={trigger === "MALFUNCTION" ? "serious" : "critical"} size={13} /> {TRIGGER_LABELS[trigger]}
            </li>
          ))}
          {item.clocks.slice(1).map((clock) => (
            <li key={clock.window} className="uw-cr-chip">
              Also: {clock.window} · {clockText(clock)}
            </li>
          ))}
        </ul>
        {item.follow_ups.length > 0 && (
          <ul className="uw-rw-followups" aria-label="Missing answers">
            {item.follow_ups.map((flag) => (
              <li key={flag.code}>
                <HelpCircle size={14} aria-hidden="true" /> {flag.label}
              </li>
            ))}
          </ul>
        )}
        {item.description && <p className="uw-cr-text uw-cr-clip-3">{item.description}</p>}
        <AlsoKnownAs id={item.business_id} shown={name} />
        {item.case && (
          <p className="uw-cr-meta">
            In investigation {item.case.case.business_id ?? "—"}
            {item.case.review
              ? ` · regulatory review ${item.case.review.business_id ?? ""}: ${
                  item.case.review.status === "COMPLETED"
                    ? (item.case.review.outcome ?? "completed").toLowerCase().replace(/_/g, " ")
                    : item.case.review.status.toLowerCase().replace(/_/g, " ")
                }`
              : " · no regulatory review yet"}
          </p>
        )}
        {item.markets.length > 0 && (
          <ul className="uw-cr-chips" aria-label="Markets">
            {item.markets.map((market) => {
              const chip = marketChip(market);
              return (
                <li key={market.market} className={`uw-cr-chip tone-${chip.tone}`}>
                  {chip.label}
                  {market.clock ? ` · ${clockText(market.clock)}` : ""}
                </li>
              );
            })}
          </ul>
        )}
        {item.decision && (
          <div className="uw-cr-decision">
            <ToneBadge tone="neutral" label="Single decision, recorded before per-market assessment" />
            <ToneBadge
              tone={item.decision.decision === "REPORTED" ? "good" : "neutral"}
              label={
                item.decision.decision === "REPORTED"
                  ? `Reported${item.decision.report_reference ? ` · ${item.decision.report_reference}` : ""}`
                  : "Not reportable"
              }
            />
            {timeliness && <ToneBadge tone={timeliness.tone} label={timeliness.label} />}
            <span className="uw-cr-meta">
              {item.decision.decided_by} · {formatDate(item.decision.decided_at)}
              {item.decision.reported_on ? ` · filed ${formatDay(item.decision.reported_on)}` : ""}
            </span>
            <q>{item.decision.rationale}</q>
          </div>
        )}
        {item.settled_by_case && !item.decision && (
          <p className="uw-cr-meta">Settled by the completed regulatory review of its investigation.</p>
        )}
      </div>
      <div className="uw-cr-actions">
        {canDecide && (
          <button
            type="button"
            className={item.state === "DECIDED" ? "ac-secondary" : "ac-primary"}
            onClick={onDecide}
            aria-label={`${name}: assess seriousness and causation per market`}
          >
            <Scale size={15} aria-hidden="true" />{" "}
            {item.state === "DECIDED" ? "Open the assessment" : "Assess per market"}
          </button>
        )}
        {onReports && owesWorksheet(item.markets, navigation) && (
          <button type="button" className="ac-secondary" onClick={onReports} aria-label={`${name}: report worksheets`}>
            <ClipboardList size={15} aria-hidden="true" /> Report worksheet
          </button>
        )}
        {openInvestigation && request && !item.case && (
          <button type="button" className="ac-link" onClick={() => openInvestigation(request)}>
            <FileSearch size={15} aria-hidden="true" /> Open investigation
          </button>
        )}
        <EscalateButton kind="COMPLAINT" id={item.id} />
      </div>
    </li>
  );
}
