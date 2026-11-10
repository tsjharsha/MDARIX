import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../../app/apiClient";
import { FilePlus2 } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import {
  Drawer,
  SearchBox,
  Table,
  Tabs,
  errorText,
  formatDate,
  idColumn,
  listOf,
  send,
  sourceIdColumn,
  useResource,
} from "../../customer-admin/shared";
import { displayId, referenceId } from "../../../app/displayId";
import { inData } from "../home";
import { InvestigationWorkspacePanel } from "../../investigator/InvestigationWorkspacePanel";
import { Stage2Experience } from "../../stage2/Stage2Experience";
import {
  chooseCase,
  useCan,
  useFeatureSet,
  useNavigation,
  useWorkspace,
  type OpenInvestigationRequest,
} from "../workspaceContext";
import { tabsFor } from "../../../app/featureSet";
import { tabParts } from "../../../app/linkTable";
import { InvestigationList } from "./ComplaintViews";
import { CaseEvidencePanel } from "./CaseEvidence";
import { CaseSections } from "./CaseSections";
import { AskMdarixPage } from "../../ask/AskMdarixPage";
import { CaseRecordDownload } from "../../reports/CaseRecordDownload";
import { trustTab } from "../caseAudit";
import { Embedded, StatusBadge } from "./common";
import { localDay } from "../workspaceModel";
import { CaseDue, CaseHeader, CasePriority, CaseStateBadge } from "./CaseHeader";
import { CaseScopePanel } from "./CaseScope";
import { LotImpactPanel } from "./LotImpact";
import { CaseIntelligencePanel } from "./CaseIntelligence";
import { CaseReviewsPanel, ReviewDrawer } from "./CaseReviews";
import { CaseDecisionBriefPanel } from "./CaseDecisionBrief";
import { CaseDecisionPanel } from "./CaseDecision";
import { CaseAiRunCard } from "./CaseAiRun";
import { ClosureCriteria } from "./AfterDecision";
import { parseReviewsTab } from "../reviews";
import { parseDecisionTab } from "../decisionTabs";
import { closureAllowed, closureCheckPath, type ClosureCheck } from "../afterDecision";
import { INTELLIGENCE_TAB, parseInvestigationsTab, type IntelligenceView } from "../intelligence";
import {
  CASE_PRIORITIES,
  caseState,
  caseStateLabel,
  caseStatusText,
  casePriorityLabel,
  dayFromDueAt,
  planningChange,
  type StepDestination,
} from "../caseWorkflow";
import { priorityRank } from "../tasks";
import { capaQmsText } from "../effectiveness";

const TABS = [
  "All investigations",
  "Workspace",
  "Intelligence",
  "Scope",
  "Reviews",
  "Decision Brief",
  "Decision",
  "Story",
  "CAPAs",
] as const;

/**
 * Under the MVP feature set this section is the one case page (app/featureSet.ts): every step of a case is a tab
 * here, including its evidence, Ask MDARIX about it and its record, so working a case never leaves the page.
 */
const CASE_PAGE_TABS = [
  "All investigations",
  "Workspace",
  "Evidence",
  "Intelligence",
  "Ask MDARIX",
  "Scope",
  "Reviews",
  "Decision Brief",
  "Decision",
  "Record",
  "CAPAs",
] as const;
type Tab = (typeof TABS)[number] | (typeof CASE_PAGE_TABS)[number];

export function InvestigationsSection({ tab: requested }: { tab?: string }) {
  // The new navigation (stage 8): one investigation in four sections; its list (0.10.74) is the tab's own.
  return useNavigation() === "new" ? <NewCaseSections tab={requested} /> : <ClassicInvestigations tab={requested} />;
}

function NewCaseSections({ tab }: { tab?: string }) {
  const { work, open, dataSource } = useWorkspace();
  const [managing, setManaging] = useState<any | null>(null);
  const selected = work.investigations.find((item) => String(item.id) === work.investigationId);
  // On your data the sample's investigation is not shown: the list (and its empty state) is (0.10.85, D3.9).
  const otherData =
    !!selected && !inData(String(selected.investigation_identifier ?? selected.business_id ?? ""), dataSource);
  // The tab lists every investigation (0.10.74, C2) when asked to, or when none is open; one opens its page.
  const listing =
    otherData ||
    tabParts(tab).name === "All investigations" ||
    (!work.investigationId && work.caseLink?.state !== "resolving");
  if (listing) return <InvestigationList />;
  return (
    <>
      <nav className="uw-crumbs" aria-label="Where you are">
        <button type="button" className="ac-link" onClick={() => open("Investigations", "All investigations")}>
          Investigations
        </button>
        {/* The reference is in the page's eyebrow (0.10.87): the crumb is the way back. */}
      </nav>
      <CaseSections tab={tab} onManage={setManaging} onChanged={() => work.refreshInvestigations()} />
      {managing && (
        <ManageInvestigation
          row={managing}
          onClose={() => setManaging(null)}
          onSaved={() => {
            setManaging(null);
            work.refreshInvestigations();
          }}
        />
      )}
    </>
  );
}

function ClassicInvestigations({ tab: requested }: { tab?: string }) {
  const { work, open, notify, reportStep, isTrial } = useWorkspace();
  // Under the MVP feature set the case story is parked and the decision is taken on this case's Decision tab
  // (featureSet.ts).
  const featureSet = useFeatureSet();
  const tabs: readonly Tab[] = featureSet === "mvp" ? CASE_PAGE_TABS : tabsFor("Investigations", TABS, featureSet);
  // "Intelligence?view=Unknowns" opens the Intelligence tab on that view (see intelligenceTab).
  const { tab, view: requestedView } = parseInvestigationsTab(requested);
  const [intelView, setIntelView] = useState<IntelligenceView>(requestedView ?? "Hypotheses");
  // "Add hypotheses by hand" opens the view with its form to add one (DEV-019), once.
  const [intelAdd, setIntelAdd] = useState(false);
  // Bumped when the case's AI run ends, so the results below are read again.
  const [aiRound, setAiRound] = useState(0);
  // "Reviews?review=<id>" opens the Reviews tab on that review (a review task, the dashboard).
  const [requestedReview] = useState(() => parseReviewsTab(requested));
  // "Decision?follow_up=<id>" or "Decision?assessment=<id>" opens the Decision tab on that follow-up or assessment.
  const [requestedDecision] = useState(() => parseDecisionTab(requested));
  // The case the review was requested with; another case chosen later does not reopen it.
  const [reviewCase] = useState(() => work.investigationId);
  const canOpen = useCan("records.write");
  // A complaint or signal asked to open an investigation for it (see useOpenInvestigation): open the form, ticked.
  const pending = work.openInvestigationRequest ?? null;
  const [prefill, setPrefill] = useState<OpenInvestigationRequest | null>(() => (canOpen ? pending : null));
  const [active, setActive] = useState<Tab>(() =>
    prefill
      ? "All investigations"
      : (tabs as readonly string[]).includes(tab ?? "")
        ? (tab as Tab)
        : "All investigations",
  );
  const [starting, setStarting] = useState(() => prefill !== null);
  // Lot impact (a free trial, T-G5) is a section of the Scope step, versioned with the case scope: the case summary's
  // Lot impact button opens Scope there. Each part is read again when the other saves a new scope version.
  const [lotFocus, setLotFocus] = useState(false);
  const [scopeRound, setScopeRound] = useState(0);
  const [lotRound, setLotRound] = useState(0);
  useEffect(() => {
    if (active !== "Scope") setLotFocus(false);
  }, [active]);
  // The Decision tab's "Review the brief first" opens the Decision Brief tab on its quality review.
  const [reviewFocus, setReviewFocus] = useState(false);
  useEffect(() => {
    if (active !== "Decision Brief") setReviewFocus(false);
  }, [active]);
  useEffect(() => {
    if (!pending) return;
    work.clearOpenInvestigationRequest();
    if (!canOpen || pending === prefill) return;
    setPrefill(pending);
    setActive("All investigations");
    setStarting(true);
  }, [pending]);
  // The step shown is part of the screen's address (workspaceAddress.ts).
  // The first report keeps what the link carried (a follow-up, a review, a view), so a refresh opens it again.
  const firstReport = useRef(true);
  useEffect(() => {
    const first = firstReport.current;
    const keep = first && !!requested && tabParts(requested).name === active;
    firstReport.current = false;
    reportStep?.(keep ? requested : active, first ? "replace" : "push");
  }, [active]);
  const [managing, setManaging] = useState<any | null>(null);
  const all = useResource<any>("/api/v1/analytics/investigations");
  const selected = work.investigations.find((item) => String(item.id) === work.investigationId);
  const openCase = (id: string) => {
    if (work.investigations.some((item) => String(item.id) === id)) {
      work.setInvestigationId(id);
      setActive("Workspace");
    }
  };
  const openAnyCase = async (row: { id: unknown; business_id?: string | null }) => {
    const id = String(row.id);
    if (work.investigations.some((item) => String(item.id) === id)) return openCase(id);
    if (row.business_id && (await chooseCase(work, row.business_id))) setActive("Workspace");
    else notify(`${row.business_id ?? "This case"} could not be opened right now.`, "critical");
  };
  // A step of the case stepper: a tab here, a part of the workspace panel, or another section.
  const goToStep = (destination: StepDestination) => {
    // On the one case page the evidence is a step of the case, not another section.
    if (featureSet === "mvp" && destination.section === "Evidence") {
      setActive("Evidence");
      return;
    }
    if (
      destination.section === "Investigations" &&
      (destination.tab === "Scope" ||
        destination.tab === "Reviews" ||
        destination.tab === "Decision Brief" ||
        destination.tab === "Decision")
    ) {
      setActive(destination.tab);
      return;
    }
    if (destination.section === "Investigations" && destination.tab === INTELLIGENCE_TAB) {
      if (destination.view) setIntelView(destination.view);
      setActive("Intelligence");
      return;
    }
    if (destination.section === "Investigations" && destination.anchor) {
      document.getElementById(destination.anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    open(destination.section, destination.tab);
  };
  return (
    <>
      <Tabs tabs={tabs} active={active} onChange={setActive} label="Investigation sections">
        {active === "All investigations" && canOpen && (
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-primary"
              onClick={() => {
                setStarting((value) => !value);
                setPrefill(null);
              }}
            >
              <FilePlus2 size={16} /> {starting ? "Close" : "Open an investigation"}
            </button>
          </div>
        )}
        {active === "All investigations" && starting && (
          <OpenInvestigation
            key={prefill?.complaint.id ?? "new"}
            prefill={prefill}
            onOpened={(id) => {
              setStarting(false);
              setPrefill(null);
              all.reload();
              work.refreshInvestigations(id);
              setActive("Workspace");
            }}
          />
        )}
        {active === "All investigations" && (
          <Panel eyebrow="Investigations" title="Investigations in your organization" source={all}>
            <Table
              caption="Investigations"
              rows={listOf(all.data?.investigations)}
              rowKey={(row) => String(row.id)}
              empty={{
                title: "No investigations yet",
                detail: "Investigations opened in your organization appear here.",
              }}
              columns={[
                idColumn("Investigation ID", "investigation_identifier"),
                sourceIdColumn("investigation_identifier"),
                { key: "question", label: "Question", render: (row) => row.investigation_question ?? "—" },
                {
                  key: "status",
                  label: "Status",
                  fields: ["status", "workflow_state", "workflow_state_label"],
                  sortValue: (row) => caseStatusText(row),
                  render: (row) => <CaseStateBadge row={row} />,
                },
                {
                  key: "priority",
                  label: "Priority",
                  sortValue: (row) => priorityRank(row.priority),
                  render: (row) => <CasePriority priority={row.priority} />,
                },
                {
                  key: "due_at",
                  label: "Due",
                  fields: ["due_at", "overdue"],
                  sortValue: (row) => row.due_at ?? "",
                  render: (row) => <CaseDue row={row} />,
                },
                ...(canOpen
                  ? [
                      {
                        key: "manage",
                        label: "",
                        render: (row: any) => (
                          <button type="button" className="ac-link" onClick={() => setManaging(row)}>
                            Manage
                          </button>
                        ),
                      },
                    ]
                  : []),
                {
                  key: "open",
                  label: "",
                  // A case of another product opens too: its product is looked up and becomes the context's.
                  render: (row) => (
                    <button type="button" className="ac-link" onClick={() => void openAnyCase(row)}>
                      Open workspace
                    </button>
                  ),
                },
              ]}
            />
          </Panel>
        )}
        {managing && (
          <ManageInvestigation
            row={managing}
            onClose={() => setManaging(null)}
            onSaved={() => {
              setManaging(null);
              all.reload();
              work.refreshInvestigations();
            }}
          />
        )}
        {active === "Workspace" &&
          (work.investigationId ? (
            <>
              <CaseHeader
                key={work.investigationId}
                investigationId={work.investigationId}
                row={selected}
                onManage={canOpen && selected ? () => setManaging(selected) : undefined}
                onLotImpact={
                  isTrial
                    ? () => {
                        setLotFocus(true);
                        setActive("Scope");
                      }
                    : undefined
                }
                onStep={goToStep}
                onChanged={() => {
                  all.reload();
                  work.refreshInvestigations();
                }}
              />
              <CaseAiRunCard
                key={`ai:${work.investigationId}`}
                caseId={work.investigationId}
                onFinished={() => setAiRound((value) => value + 1)}
              />
              <Embedded>
                <InvestigationWorkspacePanel
                  key={`${work.investigationId}:${aiRound}`}
                  investigationId={work.investigationId}
                  temporalMode={work.mode}
                  asOf={work.asOf}
                  onOpenDecision={() => (featureSet === "mvp" ? setActive("Decision") : open("Decisions"))}
                  onOpenIntelligence={(view, add) => {
                    setIntelView(view);
                    setIntelAdd(!!add);
                    setActive("Intelligence");
                  }}
                  onOpenBrief={() => setActive("Decision Brief")}
                />
              </Embedded>
            </>
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation"
                detail="Pick one in the context bar above, or open one from the list."
              />
            </Panel>
          ))}
        {active === "Intelligence" &&
          (work.investigationId ? (
            <CaseIntelligencePanel
              key={work.investigationId}
              investigationId={work.investigationId}
              caseLabel={selected ? displayId(selected, "investigation_identifier") : "Selected investigation"}
              view={intelView}
              onView={setIntelView}
              adding={intelAdd}
              onAddingShown={() => setIntelAdd(false)}
              readOnly={caseIsClosed(selected)}
            />
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation"
                detail="Hypotheses, unknowns and failure chains belong to one investigation. Pick one in the context bar above, or open one from the list."
              />
            </Panel>
          ))}
        {active === "Scope" &&
          (work.investigationId ? (
            <>
              <CaseScopePanel
                key={`scope:${work.investigationId}:${scopeRound}`}
                investigationId={work.investigationId}
                caseQuestion={selected?.investigation_question ?? undefined}
                onChanged={() => setLotRound((value) => value + 1)}
              />
              {isTrial && (
                <LotImpactPanel
                  key={`lot:${work.investigationId}:${lotRound}`}
                  investigationId={work.investigationId}
                  caseLabel={selected ? displayId(selected, "investigation_identifier") : "this case"}
                  focus={lotFocus}
                  onChanged={() => setScopeRound((value) => value + 1)}
                />
              )}
            </>
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation"
                detail="The scope belongs to one investigation. Pick one in the context bar above, or open one from the list."
              />
            </Panel>
          ))}
        {active === "Reviews" &&
          (work.investigationId || requestedReview ? (
            work.investigationId ? (
              <CaseReviewsPanel
                key={work.investigationId}
                investigationId={work.investigationId}
                caseLabel={selected ? displayId(selected, "investigation_identifier") : "Selected investigation"}
                initialReview={work.investigationId === reviewCase ? requestedReview : null}
                readOnly={caseIsClosed(selected)}
              />
            ) : (
              <ReviewOnly reviewId={requestedReview as string} />
            )
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation"
                detail="Risk and regulatory reviews belong to one investigation. Pick one in the context bar above, or open one from the list."
              />
            </Panel>
          ))}
        {active === "Decision Brief" &&
          (work.investigationId ? (
            <CaseDecisionBriefPanel
              key={work.investigationId}
              investigationId={work.investigationId}
              caseLabel={selected ? displayId(selected, "investigation_identifier") : "Selected investigation"}
              readOnly={caseIsClosed(selected)}
              focusReview={reviewFocus}
              onOpenDecision={() => setActive("Decision")}
            />
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation"
                detail="The Decision Brief belongs to one investigation. Pick one in the context bar above, or open one from the list."
              />
            </Panel>
          ))}
        {active === "Decision" &&
          (work.investigationId ? (
            <CaseDecisionPanel
              key={work.investigationId}
              investigationId={work.investigationId}
              caseLabel={selected ? displayId(selected, "investigation_identifier") : "Selected investigation"}
              initialFollowUp={work.investigationId === reviewCase ? requestedDecision.followUp : null}
              initialAssessment={work.investigationId === reviewCase ? requestedDecision.assessment : null}
              onCaseChanged={() => {
                all.reload();
                work.refreshInvestigations();
              }}
              onReviewBrief={() => {
                setReviewFocus(true);
                setActive("Decision Brief");
              }}
            />
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation"
                detail="The decision belongs to one investigation. Pick one in the context bar above, or open one from the list."
              />
            </Panel>
          ))}
        {active === "Story" &&
          (work.investigationId ? (
            <Embedded>
              <Stage2Experience mode="story" investigationId={work.investigationId} />
            </Embedded>
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation"
                detail="The story follows one investigation from signal to decision."
              />
            </Panel>
          ))}
        {active === "Evidence" &&
          (work.investigationId ? (
            <CaseEvidencePanel
              key={work.investigationId}
              investigationId={work.investigationId}
              caseLabel={selected ? displayId(selected, "investigation_identifier") : "this case"}
            />
          ) : (
            <NoCase detail="Case evidence belongs to one investigation. Pick one in the context bar above, or open one from the list." />
          ))}
        {active === "Ask MDARIX" && (
          <Embedded>
            <AskMdarixPage
              investigationId={work.investigationId || undefined}
              productVersionId={(work.view?.selected_version?.id as string | undefined) ?? undefined}
            />
          </Embedded>
        )}
        {active === "Record" &&
          (work.investigationId ? (
            <CaseRecord
              investigationId={work.investigationId}
              caseLabel={selected ? displayId(selected, "investigation_identifier") : "this case"}
              onTimeline={(caseId, caseLabel) =>
                open("Trust & Audit", trustTab({ tab: "Case timeline", caseId, caseLabel }))
              }
            />
          ) : (
            <NoCase detail="The record belongs to one investigation. Pick one in the context bar above, or open one from the list." />
          ))}
        {active === "CAPAs" && <Capas />}
        {selected && active !== "All investigations" && active !== "CAPAs" && (
          <p className="ac-note">
            Showing {displayId(selected, "investigation_identifier")} · {caseStateLabel(selected) ?? selected.status}
          </p>
        )}
      </Tabs>
    </>
  );
}

/** A case step shown while no case is chosen. */
function NoCase({ detail }: { detail: string }) {
  return (
    <Panel title="No investigation selected">
      <Empty title="Choose an investigation" detail={detail} />
    </Panel>
  );
}

/**
 * The case's record on the one case page: the signed, complete record to download (PDF for people, CSV and JSON for
 * systems) and its timeline (Records › Audit trail under the MVP feature set, else Trust & Audit).
 */
function CaseRecord({
  investigationId,
  caseLabel,
  onTimeline,
}: {
  investigationId: string;
  caseLabel: string;
  onTimeline: (caseId: string, caseLabel: string) => void;
}) {
  const canExport = useCan("data.export");
  return (
    <Panel eyebrow="Record" title={`The record of ${caseLabel}`}>
      <p className="ac-muted">
        Everything this case holds, from its question and evidence to its reviews, decision and audit trail, in one
        record you can hand an inspector.
      </p>
      {canExport ? (
        <CaseRecordDownload investigationId={investigationId} label={caseLabel} />
      ) : (
        <p className="ac-note">Your role cannot download case records. A colleague with export rights can.</p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={() => onTimeline(investigationId, caseLabel)}>
          Open the case timeline
        </button>
      </div>
    </Panel>
  );
}

/** A review opened from a task or the dashboard before any case is chosen: the review alone, in its drawer. */
function ReviewOnly({ reviewId }: { reviewId: string }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Panel title="No investigation selected">
        <Empty
          title="Choose an investigation"
          detail="Pick the review's case in the context bar above to see all of its reviews."
        />
      </Panel>
      {open && <ReviewDrawer reviewId={reviewId} onClose={() => setOpen(false)} onChanged={() => undefined} />}
    </>
  );
}

/** A closed or cancelled case: its intelligence is shown read-only (the server refuses changes with CASE_CLOSED). */
function caseIsClosed(row: Record<string, unknown> | null | undefined): boolean {
  const state = caseState(row);
  if (state) return state === "CLOSED" || state === "CANCELLED";
  return /^(closed|cancelled)$/i.test(String(row?.status ?? "").trim());
}

/** Corrective and preventive actions from the quality system, with the case they came from. */
export function Capas() {
  const capas = useResource<any>("/api/v1/data-plane/capas");
  const cases = useResource<any>("/api/v1/data-plane/investigations?limit=500");
  const caseName = new Map(
    listOf(cases.data?.records).map((row) => [String(row.id), displayId(row, "investigation_identifier")] as const),
  );
  const today = localDay();
  return (
    <Panel eyebrow="Quality system" title="CAPAs" source={capas}>
      <Table
        caption="CAPAs"
        rows={listOf(capas.data?.records)}
        rowKey={(row) => String(row.id)}
        empty={{
          title: "No CAPAs yet",
          detail: "Corrective and preventive actions appear here once your quality system is connected or imported.",
        }}
        columns={[
          idColumn("CAPA ID", "capa_identifier"),
          sourceIdColumn("capa_identifier"),
          { key: "capa", label: "Title", fields: ["title"], render: (row) => <strong>{row.title ?? "—"}</strong> },
          {
            key: "type",
            label: "Type",
            fields: ["action_type"],
            render: (row) => (row.action_type ? titleCase(String(row.action_type)) : "—"),
          },
          {
            key: "case",
            label: "From case",
            fields: ["investigation_business_id", "source_reference"],
            render: (row) =>
              referenceId(row, "investigation", caseName.get(String(row.investigation_id)), row.source_reference),
          },
          {
            key: "qms",
            label: "In your QMS",
            fields: ["qms_reference"],
            render: (row) => capaQmsText(row) ?? "From your QMS",
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
          {
            key: "due",
            label: "Due",
            fields: ["due_at"],
            render: (row) => {
              const due = row.due_at ? localDay(new Date(String(row.due_at))) : "";
              const late = due && due < today && !/closed/i.test(String(row.status));
              return late ? (
                <span className="uw-flag-critical">{formatDate(row.due_at)} · overdue</span>
              ) : (
                formatDate(row.due_at)
              );
            },
          },
        ]}
      />
    </Panel>
  );
}

/**
 * Open a case for one of the organization's products: the question it must answer and the complaints behind it.
 * `prefill` (from a complaint or signal) starts with that complaint ticked and offered, even when the selected
 * version's list does not hold it.
 */
function OpenInvestigation({
  onOpened,
  prefill = null,
}: {
  onOpened: (id: string) => void;
  prefill?: OpenInvestigationRequest | null;
}) {
  const { work, notify } = useWorkspace();
  const [question, setQuestion] = useState("");
  const requested = prefill ? [prefill.complaint, ...(prefill.also ?? [])] : [];
  const [chosen, setChosen] = useState<string[]>(() => requested.map((item) => item.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  // Only while the context is still on the complaint's product: a case links complaints of its own product only.
  const complaints = (prefill && prefill.productId === work.productId ? requested : []).reduce(
    withRequestedComplaint,
    (work.view?.complaints ?? []) as Array<Record<string, string | null>>,
  );
  const found = matchingComplaints(complaints, search, chosen);
  const product = work.products.find((item) => item.id === work.productId);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const made = await send<{ id: string; business_id?: string | null; investigation_identifier: string }>(
        "/api/v1/investigations",
        "POST",
        {
          product_id: work.productId,
          investigation_question: question.trim(),
          complaint_ids: chosen,
          ...(prefill?.openedFrom ? { opened_from: prefill.openedFrom } : {}),
        },
      );
      notify(`Investigation ${displayId(made, "investigation_identifier")} opened and assigned to you.`);
      onOpened(made.id);
    } catch (reason) {
      setError(errorText(reason, "The investigation could not be opened."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      eyebrow="New investigation"
      title={product ? `Open an investigation for ${product.name}` : "Open an investigation"}
    >
      {!work.productId ? (
        <Empty title="Choose a product first" detail="Pick the product in the context bar above." />
      ) : (
        <form className="ca-form" onSubmit={submit}>
          <label className="ca-field">
            The question this investigation must answer
            <textarea
              required
              minLength={10}
              maxLength={2000}
              rows={3}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="For example: Why did occlusion alarms rise after release B?"
            />
          </label>
          <fieldset className="ca-fieldset">
            <legend>Complaints that prompted it (optional)</legend>
            {complaints.length > 0 && (
              <SearchBox value={search} onChange={setSearch} label="Search complaints by ID or description" />
            )}
            {complaints.length > 0 && (
              <p className="ac-note" role="status">
                {chosen.length} selected · showing {found.shown.length} of {found.total}{" "}
                {found.total === 1 ? "complaint" : "complaints"}
                {found.total > found.shown.length ? ". Search to find the others." : "."}
              </p>
            )}
            {complaints.length ? (
              found.shown.map((row) => {
                const id = String(row.id ?? "");
                return (
                  <label className="ca-check" key={id || displayId(row, "complaint_identifier")}>
                    <input
                      type="checkbox"
                      disabled={!id}
                      checked={chosen.includes(id)}
                      onChange={(event) =>
                        setChosen((value) =>
                          event.target.checked ? [...value, id] : value.filter((item) => item !== id),
                        )
                      }
                    />
                    {displayId(row, "complaint_identifier")}
                    {row.business_id && row.complaint_identifier ? ` (source ${row.complaint_identifier})` : ""} ·{" "}
                    {row.description ?? "No description"}
                  </label>
                );
              })
            ) : (
              <p className="ac-muted">No complaints recorded for the selected version.</p>
            )}
          </fieldset>
          {error && (
            <p className="ac-message tone-critical" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || question.trim().length < 10}>
              {busy ? "Opening…" : "Open investigation"}
            </button>
          </div>
        </form>
      )}
    </Panel>
  );
}

/** Edit a case's question, assign it, close or reopen it. Every change carries a reason for the audit trail. */
function ManageInvestigation({ row, onClose, onSaved }: { row: any; onClose: () => void; onSaved: () => void }) {
  const { notify } = useWorkspace();
  const people = useResource<Array<{ id: string; display_name: string }>>("/api/v1/investigation-assignees");
  const closed = String(row.status ?? "").toLowerCase() === "closed";
  // What must be in place before the case can be closed (a signed decision's follow-ups, impact assessments…).
  const closure = useResource<ClosureCheck>(closed ? null : closureCheckPath(String(row.id)));
  const closureCheck = closure.state === "ready" ? closure.data : null;
  const canClose = closureAllowed(closureCheck);
  const [question, setQuestion] = useState(String(row.investigation_question ?? ""));
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState(String(row.priority ?? ""));
  const [dueDay, setDueDay] = useState(() => dayFromDueAt(row.due_at));
  const planning = planningChange(row, { priority, dueDay });
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (change: Record<string, unknown>, done: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/investigations/${row.id}`, "PATCH", { ...change, reason: reason.trim() });
      notify(done);
      onSaved();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "CLOSURE_CRITERIA_NOT_MET") {
        setError(`${failure.message} The criteria above show what still blocks closing.`);
        closure.reload();
      } else setError(errorText(failure, "The change was not saved."));
    } finally {
      setBusy(false);
    }
  };
  const reasonReady = reason.trim().length >= REASON_MIN;
  const label = displayId(row, "investigation_identifier");
  return (
    <Drawer title={`Manage ${label}`} onClose={onClose}>
      <label className="ca-field">
        Reason for the change (kept in the audit trail)
        <textarea
          rows={2}
          maxLength={1000}
          value={reason}
          aria-describedby="manage-reason-hint"
          onChange={(event) => setReason(event.target.value)}
        />
        <small id="manage-reason-hint" className={reasonReady ? "ac-muted" : "uw-hint"}>
          {reasonHint(reason)}
        </small>
      </label>
      {closed ? (
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-primary"
            disabled={!reasonReady || busy}
            onClick={() => void save({ status: "open" }, `${label} reopened.`)}
          >
            Reopen investigation
          </button>
        </div>
      ) : (
        <>
          <label className="ca-field">
            Question
            <textarea
              rows={3}
              minLength={10}
              maxLength={2000}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
          </label>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={
                !reasonReady || busy || question.trim().length < 10 || question.trim() === row.investigation_question
              }
              onClick={() => void save({ investigation_question: question.trim() }, "Question updated.")}
            >
              Save question
            </button>
          </div>
          <label className="ca-field">
            Assign to
            <select value={assignee} onChange={(event) => setAssignee(event.target.value)}>
              <option value="">Choose a colleague</option>
              {listOf(people.data).map((person) => (
                <option key={person.id} value={person.id}>
                  {person.display_name}
                </option>
              ))}
            </select>
          </label>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={!reasonReady || busy || !assignee}
              onClick={() => void save({ assignee_id: assignee }, `${label} assigned.`)}
            >
              Assign
            </button>
            <button
              type="button"
              className="ac-secondary"
              disabled={!reasonReady || busy}
              onClick={() => void save({ unassign: true }, `${label} has no owner now.`)}
            >
              Remove owner
            </button>
          </div>
          <div className="ca-form-grid">
            <label className="ca-field">
              Priority
              <select value={priority} onChange={(event) => setPriority(event.target.value)}>
                {!row.priority && <option value="">Not set</option>}
                {CASE_PRIORITIES.map((item) => (
                  <option key={item} value={item}>
                    {casePriorityLabel(item)}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Due date
              <input type="date" value={dueDay} onChange={(event) => setDueDay(event.target.value)} />
            </label>
          </div>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={!reasonReady || busy || !planning}
              onClick={() => planning && void save(planning, "Priority and due date updated.")}
            >
              Save priority and due date
            </button>
          </div>
          <ClosureCriteria check={closureCheck} state={closure.state} />
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-primary"
              disabled={!reasonReady || busy || !canClose}
              onClick={() => void save({ status: "closed" }, `${label} closed.`)}
            >
              Close investigation
            </button>
            {!canClose && <span className="uw-hint">Closing is blocked until the criteria above pass.</span>}
          </div>
          <p className="ac-muted">A case with a decision still awaiting its human review cannot be closed.</p>
        </>
      )}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
    </Drawer>
  );
}

// The server refuses a change to a case without a reason of at least this many characters (kept in the audit trail).
const REASON_MIN = 10;

/** Why the change buttons are not available yet, or that they are. */
export function reasonHint(reason: string): string {
  const missing = REASON_MIN - reason.trim().length;
  return missing > 0
    ? `Write a reason of at least ${REASON_MIN} characters to enable the changes below (${missing} more).`
    : "The reason is recorded with the change.";
}

const COMPLAINT_PAGE = 50;

/**
 * The complaints the open-investigation form offers, with the one an investigation was requested for (from the
 * complaint list or a signal) first when the selected version's list does not already hold it.
 */
export function withRequestedComplaint(
  complaints: Array<Record<string, string | null>>,
  requested: OpenInvestigationRequest["complaint"] | null | undefined,
): Array<Record<string, string | null>> {
  if (!requested?.id || complaints.some((row) => String(row.id ?? "") === requested.id)) return complaints;
  return [{ ...requested }, ...complaints];
}

/**
 * The complaints offered in the open-investigation form: those matching the search (MDARIX ID, source number or
 * description),
 * at most 50 at a time, with the ones already ticked always kept in view.
 */
export function matchingComplaints(
  complaints: Array<Record<string, string | null>>,
  search: string,
  chosen: string[],
): { shown: Array<Record<string, string | null>>; total: number } {
  const query = search.trim().toLowerCase();
  const matches = query
    ? complaints.filter((row) =>
        [row.business_id, row.complaint_identifier, row.description].some((value) =>
          String(value ?? "")
            .toLowerCase()
            .includes(query),
        ),
      )
    : complaints;
  const page = matches.slice(0, COMPLAINT_PAGE);
  const ticked = complaints.filter((row) => chosen.includes(String(row.id ?? "")) && !page.includes(row));
  return { shown: [...ticked, ...page], total: matches.length };
}
