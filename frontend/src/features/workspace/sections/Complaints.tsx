import { useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  FileSearch,
  HeartPulse,
  Hourglass,
  Inbox,
  ScanSearch,
  Sparkles,
  Timer,
  XCircle,
} from "lucide-react";
import { BarList, Empty, Panel, StatTile, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { Drawer, Table, Tabs, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { offeredTab } from "../../../app/featureSet";
import { investigationRequestFor, useCan, useCanRunAi, useOpenInvestigation, useWorkspace } from "../workspaceContext";
import { StatusBadge, countOf } from "./common";
import { Hero, InlineError, Pager, ProductFilter } from "./boardParts";
import { TrustBadge } from "./TrustBadge";
import { ReportabilityWatch } from "./ReportabilityWatch";
import { ReportingWindows } from "./ReportingWindows";
import { Starters } from "./Starters";
import { ComplaintList } from "./ComplaintList";
import { COMPLAINT_LIST_TAB, parseComplaintListTab } from "../complaintList";
import { SECOND_LOOK_STARTERS, STARTER_MIN_EXTRA, starterProblem } from "../starters";
import {
  BACKLOG_SHOWS,
  COMPLAINTS_TABS,
  REVIEW_LIMITS,
  backlogAgeText,
  backlogHeadline,
  backlogPath,
  backlogStateOf,
  bandSlices,
  decisionBody,
  decisionProblem,
  decisionText,
  explainPath,
  explanationNote,
  highlightParts,
  otherDecision,
  reasonSlices,
  recordId,
  recordName,
  recordTone,
  secondLookHeadline,
  secondLookPath,
  settingsBody,
  settingsChanged,
  settingsForm,
  settingsProblem,
  signTone,
  targetShare,
  wordsOf,
  type BacklogItem,
  type BacklogList,
  type BacklogShow,
  type ComplaintsTab,
  type ReviewSettings,
  type SecondLookExplanation,
  type SecondLookItem,
  type SecondLookList,
  type SettingsForm,
} from "../complaintReview";

/**
 * Complaints: the second look (records cancelled or logged as inquiries that carry signs of a complaint, and recurring
 * No Fault Found codes, for a person to decide on), the backlog board (open complaints in no signal and no case,
 * against the organization's target) and the reportability watch (reporting clocks against the organization's own
 * windows), and the complaint list with its filters (a link may carry them: complaintListTab in ../complaintList.ts).
 * MDARIX never changes a record in the customer's system and never submits a report.
 */
export function ComplaintsSection({ tab }: { tab?: string }) {
  const [target] = useState(() => parseComplaintListTab(tab));
  const [active, setActive] = useState<ComplaintsTab>(() =>
    target.isList ? COMPLAINT_LIST_TAB : offeredTab(tab, COMPLAINTS_TABS, "Second look"),
  );
  return (
    <Tabs tabs={COMPLAINTS_TABS} active={active} onChange={setActive} label="Complaint sections">
      {active === "Second look" && <SecondLook />}
      {active === "Backlog" && <Backlog />}
      {active === "Reportability" && <ReportabilityWatch onOpenTab={setActive} />}
      {active === COMPLAINT_LIST_TAB && <ComplaintList eyebrow="Complaints" initialFilters={target.filters} />}
      {active === "Review settings" && <ReviewSettingsPanel />}
      {active === "Reporting windows" && <ReportingWindows />}
    </Tabs>
  );
}

/** Whether the signed-in role may decide on a flagged record (the server's rule: triage, open cases or quality). */
function useCanDecide() {
  const triage = useCan("signal.triage");
  const create = useCan("investigation.create");
  const quality = useCan("quality.review");
  return triage || create || quality;
}

// The second look ----------------------------------------------------------------------------------------------------

function SecondLook() {
  const [state, setState] = useState<"open" | "decided">("open");
  const [product, setProduct] = useState("");
  const [page, setPage] = useState(1);
  const [deciding, setDeciding] = useState<{ item: SecondLookItem; decision: "CONFIRMED" | "DISMISSED" } | null>(null);
  const list = useResource<SecondLookList>(secondLookPath(state, product, page));
  const summary = list.data?.summary;
  const headline = secondLookHeadline(summary);
  const items = list.data?.items ?? [];
  const choose = (next: "open" | "decided") => {
    setState(next);
    setPage(1);
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={list.data ? headline.tone : "neutral"}
        icon={<ScanSearch size={28} />}
        eyebrow="Second look"
        title={list.data ? headline.title : "Checking your records…"}
        detail={
          list.data ? headline.detail : "Looking for complaints hidden as cancellations, inquiries or No Fault Found."
        }
      />
      <div className="uw-cr-stats">
        <StatTile
          label="To review"
          value={summary ? summary.to_review : null}
          detail="May be hidden complaints"
          icon={<Inbox size={18} />}
          onOpen={() => choose("open")}
        />
        <StatTile
          label="Death or serious injury"
          value={summary ? summary.with_harm : null}
          detail="Among those to review"
          icon={<HeartPulse size={18} />}
          tone={summary?.with_harm ? "critical" : undefined}
        />
        <StatTile
          label="Confirmed complaints"
          value={summary ? summary.confirmed : null}
          detail="Decided by your team"
          icon={<CheckCircle2 size={18} />}
          onOpen={() => choose("decided")}
        />
        <StatTile
          label="Dismissed"
          value={summary ? summary.dismissed : null}
          detail="Not complaints, with a reason"
          icon={<XCircle size={18} />}
          onOpen={() => choose("decided")}
        />
      </div>
      <div className="ac-grid uw-cr-split">
        <Panel
          eyebrow="Second look"
          title={state === "open" ? "Records to review, most serious first" : "Decided records"}
          source={list}
        >
          <div className="uw-cr-toolbar">
            <div className="ca-chips" role="radiogroup" aria-label="Which records">
              {(["open", "decided"] as const).map((value) => (
                <button
                  type="button"
                  role="radio"
                  key={value}
                  aria-checked={state === value}
                  className={state === value ? "selected" : ""}
                  onClick={() => choose(value)}
                >
                  {value === "open" ? "To review" : "Decided"}
                  {summary && (
                    <span className="ac-tab-count">
                      {value === "open" ? summary.to_review : summary.confirmed + summary.dismissed}
                    </span>
                  )}
                </button>
              ))}
            </div>
            <ProductFilter
              value={product}
              onChange={(value) => {
                setProduct(value);
                setPage(1);
              }}
            />
          </div>
          {list.data?.truncated && (
            <p className="uw-hint">
              Only your most recent 20,000 candidate records were checked. Choose a product to check all of its records.
            </p>
          )}
          {items.length ? (
            <ul className="uw-cr-list">
              {items.map((item) => (
                <SecondLookCard key={item.id} item={item} onDecide={(decision) => setDeciding({ item, decision })} />
              ))}
            </ul>
          ) : state === "open" ? (
            <Empty
              title="Nothing to review"
              detail="No cancelled record or inquiry carries a sign of a complaint, and no No Fault Found or User Error code recurs."
            />
          ) : (
            <Empty title="No decisions yet" detail="Records your team decides on appear here, with who and why." />
          )}
          <Pager page={page} pages={list.data?.pages ?? 1} onPage={setPage} />
        </Panel>
        <Panel eyebrow="Why records are flagged" title="What the second look checks">
          <BarList items={reasonSlices(summary?.by_reason)} colour="series" />
          <p className="ac-note">
            FDA inspection findings include complaints that were cancelled or logged as inquiries although they met the
            firm's own complaint definition, and No Fault Found codes that hid a recurring problem. A cancelled record
            or an inquiry is flagged only when it also carries a sign of a complaint: harm, a malfunction, a serious
            severity, a problem code or one of your organization's words. A No Fault Found or User Error code is flagged
            when it recurs: 3 or more times on one product in 12 months.
          </p>
        </Panel>
      </div>
      {deciding && (
        <DecisionDrawer
          item={deciding.item}
          decision={deciding.decision}
          onClose={() => setDeciding(null)}
          onDecided={list.reload}
        />
      )}
    </div>
  );
}

function Highlighted({ text, words }: { text: string | null; words: readonly string[] }) {
  const parts = highlightParts(text, words);
  if (!parts.length) return <span className="ac-muted">No description recorded</span>;
  return <>{parts.map((part, index) => (part.match ? <mark key={index}>{part.text}</mark> : part.text))}</>;
}

/** One flagged record: why, its signs, its words marked, and the decision (exported for its unit test). */
export function SecondLookCard({
  item,
  onDecide,
}: {
  item: SecondLookItem;
  onDecide: (decision: "CONFIRMED" | "DISMISSED") => void;
}) {
  const canDecide = useCanDecide();
  const openInvestigation = useOpenInvestigation();
  const decided = decisionText(item.decision?.decision);
  const tone = recordTone(item.signs);
  const request = investigationRequestFor(item);
  const name = recordId(item);
  return (
    <li className="uw-cr-card">
      <span className={`uw-cr-rail tone-${tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <strong className="uw-cr-id">{name}</strong>
          {item.business_id && item.complaint_identifier && (
            <span className="uw-cr-meta">Source ID {item.complaint_identifier}</span>
          )}
          <span className="uw-cr-meta">
            {item.product_name ?? "No product"}
            {item.version ? ` · ${item.version}` : ""} · Received {formatDay(item.received_date)}
          </span>
          <StatusBadge value={item.status} />
        </div>
        <ul className="uw-cr-chips" aria-label="Why it is flagged">
          {item.reasons.map((reason) => (
            <li key={reason.code} className="uw-cr-chip is-reason">
              <ScanSearch size={13} aria-hidden="true" /> {reason.label}
            </li>
          ))}
        </ul>
        {item.signs.length > 0 && (
          <ul className="uw-cr-chips" aria-label="Signs of a complaint">
            {item.signs.map((sign) => (
              <li key={sign.code} className={`uw-cr-chip tone-${signTone(sign.code)}`}>
                <ToneIcon tone={signTone(sign.code)} size={13} /> {sign.label}
              </li>
            ))}
          </ul>
        )}
        <p className="uw-cr-text">
          <Highlighted text={item.description} words={item.words} />
        </p>
        <ExplainWithAi item={item} name={name} />
        {item.decision && decided && (
          <div className="uw-cr-decision">
            <ToneBadge tone={decided.tone} label={decided.badge} />
            <span className="uw-cr-meta">
              {item.decision.decided_by} · {formatDate(item.decision.decided_at)}
            </span>
            <q>{item.decision.reason}</q>
          </div>
        )}
      </div>
      <div className="uw-cr-actions">
        {canDecide && !item.decision && (
          <>
            <button
              type="button"
              className="ac-primary"
              onClick={() => onDecide("CONFIRMED")}
              aria-label={`${name}: it is a complaint`}
            >
              It is a complaint
            </button>
            <button
              type="button"
              className="ac-secondary"
              onClick={() => onDecide("DISMISSED")}
              aria-label={`${name}: not a complaint`}
            >
              Not a complaint
            </button>
          </>
        )}
        {canDecide && item.decision && (
          <button
            type="button"
            className="ac-secondary"
            onClick={() => onDecide(otherDecision(item.decision?.decision))}
            aria-label={`${name}: change the decision`}
          >
            Change decision
          </button>
        )}
        {item.decision?.decision === "CONFIRMED" && openInvestigation && request && (
          <button type="button" className="ac-link" onClick={() => openInvestigation(request)}>
            <FileSearch size={15} aria-hidden="true" /> Open investigation
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * The AI's explanation of a flagged record, on request: at most three sentences, each with the record's own words it
 * quotes (checked by the server), and its trust check. When AI is off or unavailable, it says why; the rules' reasons
 * above stand either way, and a person decides (exported for its unit test).
 */
export function ExplainWithAi({ item, name }: { item: SecondLookItem; name: string }) {
  const canRun = useCanRunAi();
  const [explanation, setExplanation] = useState<SecondLookExplanation | null>(item.explanation ?? null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const explain = async () => {
    setBusy(true);
    setError("");
    setNote(null);
    try {
      const result = await send<SecondLookExplanation>(explainPath(item.id), "POST");
      if (result.author === "AI") setExplanation(result);
      else setNote(explanationNote(result));
    } catch (failure) {
      setError(errorText(failure, "The explanation could not be made."));
    } finally {
      setBusy(false);
    }
  };
  const shown = explanation?.author === "AI" ? explanation : null;
  if (!shown && !canRun) return null;
  const dropped = shown?.ai.dropped?.length ?? 0;
  return (
    <div className="uw-cr-explain" aria-live="polite">
      {shown && (
        <>
          <div className="uw-ai-head">
            <p className="uw-ai-label">
              <Sparkles size={14} aria-hidden="true" /> {shown.ai.label ?? "AI interpretation: a person decides"}
            </p>
            <TrustBadge trust={shown.ai.trust} />
          </div>
          <ul className="uw-cr-explain-list">
            {shown.sentences.map((sentence, index) => (
              <li key={index}>
                <span>{sentence.text}</span>
                {sentence.quotes.map((quote, position) => (
                  <q key={position} className="uw-cr-quote">
                    <b>{quote.label}:</b> {quote.text}
                  </q>
                ))}
              </li>
            ))}
          </ul>
          {dropped > 0 && (
            <p className="ac-muted">
              {dropped} sentence{dropped === 1 ? "" : "s"} left out: a quote not in the record, a decision or a stated
              cause.
            </p>
          )}
        </>
      )}
      {note && (
        <p className="ac-muted" role="status">
          {note}
        </p>
      )}
      {canRun && (
        <button
          type="button"
          className="ac-link"
          disabled={busy}
          onClick={() => void explain()}
          aria-label={`${name}: ${shown ? "explain again with AI" : "explain with AI why it may be a complaint"}`}
        >
          <Sparkles size={15} aria-hidden="true" /> {busy ? "Explaining…" : shown ? "Explain again" : "Explain with AI"}
        </button>
      )}
      <InlineError text={error} />
    </div>
  );
}

function DecisionDrawer({
  item,
  decision,
  onClose,
  onDecided,
}: {
  item: SecondLookItem;
  decision: "CONFIRMED" | "DISMISSED";
  onClose: () => void;
  onDecided: () => void;
}) {
  const { notify } = useWorkspace();
  const openInvestigation = useOpenInvestigation();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const text = decisionText(decision)!;
  // A starter begins the sentence; the person finishes it in their own words (workspace/starters.ts).
  const starters = SECOND_LOOK_STARTERS[decision];
  const problem = decisionProblem(reason) ?? starterProblem(reason, starters);
  const field = useRef<HTMLTextAreaElement>(null);
  // The MDARIX ID with the source system's number beside it: "CMP000029 (SAMPLE-RV-01): it is a complaint" (DEV-008).
  const name = recordName(item);
  const revising = !!item.decision;
  const request = investigationRequestFor(item);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(
        `/api/v1/complaints/${encodeURIComponent(item.id)}/second-look`,
        "POST",
        decisionBody(decision, reason),
      );
      notify(`${name}: ${decision === "CONFIRMED" ? "confirmed as a complaint" : "dismissed as not a complaint"}.`);
      onDecided();
      setDone(true);
    } catch (failure) {
      setError(errorText(failure, "The decision was not recorded."));
    } finally {
      setBusy(false);
    }
  };
  if (done)
    return (
      <Drawer title={`${name}: decision recorded`} onClose={onClose}>
        <section className="ca-drawer-section" role="status">
          <h3>
            <ToneIcon tone="good" /> {decision === "CONFIRMED" ? "Confirmed as a complaint" : "Dismissed"}
          </h3>
          <p>
            {decision === "CONFIRMED"
              ? "It now counts on the backlog board until it joins a signal or a case. Your source system is unchanged; record the complaint there as your procedure says."
              : "It leaves the second look. Your reason is kept in the audit trail."}
          </p>
        </section>
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose}>
            Done
          </button>
          {decision === "CONFIRMED" && openInvestigation && request && (
            <button
              type="button"
              className="ac-primary"
              onClick={() => {
                onClose();
                openInvestigation(request);
              }}
            >
              <FileSearch size={16} aria-hidden="true" /> Open an investigation
            </button>
          )}
        </div>
      </Drawer>
    );
  return (
    <Drawer title={`${name}: ${text.action.toLowerCase()}`} onClose={onClose}>
      <form className="ca-form" onSubmit={submit}>
        <section className="ca-drawer-section">
          <h3>{revising ? "Change the decision" : "Your decision"}</h3>
          <p>
            {decision === "CONFIRMED"
              ? "You are confirming that this record meets your complaint definition. It joins the backlog board, so it is handled and trended like any complaint."
              : "You are confirming that this record is not a complaint. Say why, so an auditor can follow your reasoning."}
          </p>
          <ul className="uw-cr-chips" aria-label="Why it is flagged">
            {[...item.reasons, ...item.signs].map((entry) => (
              <li key={entry.code} className="uw-cr-chip">
                {entry.label}
              </li>
            ))}
          </ul>
          {revising && item.decision && (
            <p className="uw-hint">
              Decided earlier by {item.decision.decided_by}: “{item.decision.reason}”
            </p>
          )}
        </section>
        <label className="ca-field">
          Reason
          <textarea
            ref={field}
            required
            rows={4}
            maxLength={REVIEW_LIMITS.reasonMax}
            value={reason}
            placeholder={
              decision === "CONFIRMED"
                ? "e.g. The customer reports the pump stopped during therapy: meets our complaint definition"
                : "e.g. A duplicate of CMP000123, already handled as a complaint"
            }
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <Starters
          starters={starters}
          onPick={(starter) => {
            setReason(starter);
            window.setTimeout(() => field.current?.focus(), 0);
          }}
        />
        {reason ? (
          problem && <p className="uw-hint">{problem}</p>
        ) : (
          <p className="ac-muted">
            In your own words, at least {Math.max(REVIEW_LIMITS.reasonMin, STARTER_MIN_EXTRA)} characters: what in this
            record shows it.
          </p>
        )}
        {error && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {error}
          </p>
        )}
        <p className="ac-muted">MDARIX never changes the record in your system. The decision is in the audit trail.</p>
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Saving…" : text.action}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

// The backlog board ------------------------------------------------------------------------------------------------

function Backlog() {
  const openInvestigation = useOpenInvestigation();
  const [show, setShow] = useState<BacklogShow>("all");
  const [product, setProduct] = useState("");
  const [page, setPage] = useState(1);
  const list = useResource<BacklogList>(backlogPath(show, product, page));
  const summary = list.data?.summary;
  const target = summary?.target_days ?? 30;
  const headline = backlogHeadline(summary);
  const choose = (next: BacklogShow) => {
    setShow(next);
    setPage(1);
  };
  const shown: Record<BacklogShow, number | undefined> = {
    all: summary?.open_unlinked,
    past_target: summary?.past_target,
    due_soon: summary?.due_soon,
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={list.data ? headline.tone : "neutral"}
        icon={<Hourglass size={28} />}
        eyebrow={`Backlog · ${target}-day target`}
        title={list.data ? headline.title : "Reading your open complaints…"}
        detail={list.data ? headline.detail : "Open complaints in no signal and no case, against your target."}
      />
      <div className="uw-cr-stats">
        <StatTile
          label="Open, in no signal or case"
          value={summary ? summary.open_unlinked : null}
          detail="Waiting for triage"
          icon={<Inbox size={18} />}
          onOpen={() => choose("all")}
        />
        <StatTile
          label="Past target"
          value={summary ? summary.past_target : null}
          detail={`Older than ${countOf(target, "day")}`}
          icon={<AlertTriangle size={18} />}
          tone={summary?.past_target ? "critical" : undefined}
          onOpen={() => choose("past_target")}
        />
        <StatTile
          label="Due soon"
          value={summary ? summary.due_soon : null}
          detail="Within a week of the target"
          icon={<Timer size={18} />}
          tone={summary?.due_soon ? "warning" : undefined}
          onOpen={() => choose("due_soon")}
        />
        <StatTile
          label="Oldest"
          value={summary ? (summary.oldest_days === null ? "—" : countOf(summary.oldest_days, "day")) : null}
          detail="Since received"
          icon={<Hourglass size={18} />}
        />
      </div>
      <div className="ac-grid uw-cr-split">
        <Panel eyebrow="Backlog" title="Open complaints, oldest first" source={list}>
          <div className="uw-cr-toolbar">
            <div className="ca-chips" role="radiogroup" aria-label="Which complaints">
              {BACKLOG_SHOWS.map((option) => (
                <button
                  type="button"
                  role="radio"
                  key={option.value}
                  aria-checked={show === option.value}
                  className={show === option.value ? "selected" : ""}
                  onClick={() => choose(option.value)}
                >
                  {option.label}
                  {typeof shown[option.value] === "number" && (
                    <span className="ac-tab-count">{shown[option.value]}</span>
                  )}
                </button>
              ))}
            </div>
            <ProductFilter
              value={product}
              onChange={(value) => {
                setProduct(value);
                setPage(1);
              }}
            />
          </div>
          {list.data?.truncated && (
            <p className="uw-hint">
              Only your oldest 20,000 complaints were read. Choose a product to see all of its complaints.
            </p>
          )}
          <Table
            caption="Complaint backlog"
            rows={list.data?.items ?? []}
            rowKey={(row) => row.id}
            empty={{
              title: show === "all" ? "No open complaint is waiting" : "None here",
              detail: "Every open complaint is in a signal or a case.",
            }}
            columns={[
              {
                key: "business_id",
                label: "Complaint ID",
                render: (row: BacklogItem) => (
                  <span className="ca-person">
                    <strong>{recordId(row)}</strong>
                    {row.confirmed_on_second_look && <small>Confirmed on the second look</small>}
                  </span>
                ),
              },
              {
                key: "product_name",
                label: "Product",
                fields: ["version"],
                render: (row: BacklogItem) => `${row.product_name ?? "—"}${row.version ? ` · ${row.version}` : ""}`,
              },
              {
                key: "description",
                label: "Description",
                render: (row: BacklogItem) => <span className="uw-cr-clip">{row.description ?? "—"}</span>,
              },
              {
                key: "received_date",
                label: "Received",
                render: (row: BacklogItem) => formatDay(row.received_date),
              },
              {
                key: "age_days",
                label: "Age",
                numeric: true,
                render: (row: BacklogItem) => <AgeMeter item={row} target={target} />,
              },
              {
                key: "state",
                label: "Target",
                render: (row: BacklogItem) => {
                  const state = backlogStateOf(row.state);
                  return <ToneBadge tone={state.tone} label={state.label} />;
                },
              },
              {
                key: "harm",
                label: "Harm",
                fields: ["death", "serious_injury", "patient_involved", "malfunction"],
                render: (row: BacklogItem) =>
                  row.death || row.serious_injury ? (
                    <small className="uw-flag-critical">Serious injury or death</small>
                  ) : row.patient_involved ? (
                    <small>Patient involved</small>
                  ) : row.malfunction ? (
                    <small>Malfunction</small>
                  ) : (
                    <span className="ac-muted">—</span>
                  ),
              },
              ...(openInvestigation
                ? [
                    {
                      key: "open-investigation",
                      label: "",
                      render: (row: BacklogItem) => {
                        const request = investigationRequestFor(row);
                        return request ? (
                          <button
                            type="button"
                            className="ac-link"
                            aria-label={`Open an investigation for ${recordId(row)}`}
                            onClick={() => openInvestigation(request)}
                          >
                            Open investigation
                          </button>
                        ) : null;
                      },
                    },
                  ]
                : []),
            ]}
          />
          <Pager page={page} pages={list.data?.pages ?? 1} onPage={setPage} />
        </Panel>
        <Panel eyebrow="Backlog" title="Open complaints by age">
          <BarList items={bandSlices(summary?.bands, target)} />
          <p className="ac-note">
            Complaints are counted from the day they were received. One that is in no signal and no case has not been
            looked at as part of a trend, and complaint handling is among the observations FDA cites most often. A
            cancelled record or an inquiry counts here once your team confirms it on the second look.
          </p>
        </Panel>
      </div>
    </div>
  );
}

function AgeMeter({ item, target }: { item: BacklogItem; target: number }) {
  const state = backlogStateOf(item.state);
  return (
    <span className="uw-cr-age" title={backlogAgeText(item.age_days, target)}>
      <span>{backlogAgeText(item.age_days, target)}</span>
      <span className="uw-cr-age-track" aria-hidden="true">
        <span
          className={`uw-cr-age-fill tone-${state.tone}`}
          style={{ width: `${targetShare(item.age_days, target)}%` }}
        />
      </span>
    </span>
  );
}

// Settings -----------------------------------------------------------------------------------------------------------

function ReviewSettingsPanel() {
  const settings = useResource<ReviewSettings>("/api/v1/complaints/review-settings");
  return (
    <Panel eyebrow="Complaints" title="Review settings" source={settings}>
      {settings.data && (
        <SettingsBody key={`${settings.data.version}`} settings={settings.data} onSaved={settings.reload} />
      )}
    </Panel>
  );
}

/** The settings and, for a triage lead, the form that changes them (exported for its unit test). */
export function SettingsBody({ settings, onSaved }: { settings: ReviewSettings; onSaved: () => void }) {
  const { notify } = useWorkspace();
  const canEdit = useCan("signal.triage");
  const [form, setForm] = useState<SettingsForm>(() => settingsForm(settings));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const changed = settingsChanged(settings, form);
  const problem = settingsProblem(form);
  const words = form.useDefaults ? settings.default_words : wordsOf(form.words);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!changed || problem) return;
    setBusy(true);
    setError("");
    try {
      await send("/api/v1/complaints/review-settings", "PUT", settingsBody(form));
      notify("The complaint review settings were changed.");
      onSaved();
    } catch (reason) {
      setError(errorText(reason, "The settings were not changed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <dl className="ca-facts">
        <div>
          <dt>Backlog target</dt>
          <dd>{countOf(settings.backlog_target_days, "day")} from receipt</dd>
        </div>
        <div>
          <dt>Second look words</dt>
          <dd>
            {settings.custom_words
              ? `Your organization's ${countOf(settings.second_look_words.length, "word")}`
              : `The ${countOf(settings.default_words.length, "default word")}`}
          </dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{settings.version || "Defaults, never changed"}</dd>
        </div>
        <div>
          <dt>Changed</dt>
          <dd>
            {settings.updated_at ? formatDate(settings.updated_at) : "—"}
            {settings.updated_by_name ? ` · ${settings.updated_by_name}` : ""}
          </dd>
        </div>
      </dl>
      {!canEdit && (
        <>
          <ul className="uw-cr-chips" aria-label="Second look words">
            {settings.second_look_words.map((word) => (
              <li key={word} className="uw-cr-chip">
                {word}
              </li>
            ))}
          </ul>
          <p className="ac-muted">A triage lead can change these settings.</p>
        </>
      )}
      {canEdit && (
        <form className="ca-form ca-drawer-section" onSubmit={submit}>
          <h3>
            <ClipboardCheck size={16} aria-hidden="true" /> Change the settings
          </h3>
          <label className="ca-field">
            Backlog target (days from receipt)
            <input
              type="number"
              inputMode="numeric"
              min={REVIEW_LIMITS.targetDays[0]}
              max={REVIEW_LIMITS.targetDays[1]}
              step={1}
              value={form.targetDays}
              onChange={(event) => setForm({ ...form, targetDays: event.target.value })}
            />
          </label>
          <label className="ca-check">
            <input
              type="checkbox"
              checked={form.useDefaults}
              onChange={(event) =>
                setForm({
                  ...form,
                  useDefaults: event.target.checked,
                  words: event.target.checked ? settings.default_words.join("\n") : form.words,
                })
              }
            />
            Use the default words (harm, failures and hazards)
          </label>
          <label className="ca-field">
            Words that suggest a complaint (one per line)
            <textarea
              rows={8}
              disabled={form.useDefaults}
              value={form.words}
              onChange={(event) => setForm({ ...form, words: event.target.value })}
            />
          </label>
          <p className="ac-muted">
            {countOf(words.length, "word")}. A cancelled record or an inquiry whose description contains one of them is
            flagged for a second look, as whole words in any case.
          </p>
          <label className="ca-field">
            Reason for the change
            <textarea
              required
              rows={3}
              maxLength={REVIEW_LIMITS.reasonMax}
              value={form.reason}
              placeholder="At least 10 characters"
              onChange={(event) => setForm({ ...form, reason: event.target.value })}
            />
          </label>
          {changed && form.reason && problem && <p className="uw-hint">{problem}</p>}
          {error && (
            <p className="ca-inline-error" role="alert">
              <AlertTriangle size={15} aria-hidden="true" /> {error}
            </p>
          )}
          <p className="ac-muted">A change makes a new version of the settings, recorded in the audit trail.</p>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={busy || (!changed && !form.reason)}
              onClick={() => setForm(settingsForm(settings))}
            >
              Undo changes
            </button>
            <button type="submit" className="ac-primary" disabled={busy || !changed || !!problem}>
              {busy ? "Saving…" : "Save settings"}
            </button>
          </div>
        </form>
      )}
    </>
  );
}
