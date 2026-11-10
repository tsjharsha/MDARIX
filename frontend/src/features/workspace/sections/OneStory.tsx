import { useState, type ReactNode, type RefObject } from "react";
import {
  Archive,
  Check,
  ChevronRight,
  Eye,
  FileText,
  GitFork,
  ListChecks,
  Minus,
  Phone,
  Send,
  Stethoscope,
  TrendingUp,
  UserCheck,
  type LucideIcon,
} from "lucide-react";
import { MonitorBand, ProgressArc } from "../../shared/hero/HeroVisuals";
import { BedsideScene, SignedSeal } from "../../shared/hero/HeroArt";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { IMPORTED_SOURCE } from "../complaintList";
import { TEAM_PATH } from "./TrialTeam";
import { chanceText, trendCountText, trendResultLabel, type TrendItem } from "../signalAi";
import {
  STORY_STEPS,
  casePlace,
  openStep,
  shownRun,
  stepBlocker,
  stepCount,
  stepPlace,
  takeMarkProblem,
  useOneStory,
  type MoreCase,
  type OneStory as OneStoryData,
  type StoryRun,
} from "../oneStory";

/** Each step's words: the heading and its one main button. The record's facts are never written here: the complaint
 * summary below them reads them from the record (owner's specification, 5 Nov 2026). */
function stepCopy(run: StoryRun, index: number): { h: string; b: string } {
  const sample = run.run === "sample";
  const ref = run.complaint.ref;
  const market = run.market_label ?? "the market's";
  const copy = [
    sample
      ? { h: "Start with the hospital's call", b: `Open ${run.case?.ref ?? ref}` }
      : {
          // A reference never breaks at its hyphen (a non-breaking hyphen in the heading).
          h: `Your most urgent complaint: ${ref.replace(/-/g, "‑")}`,
          b: `Open ${run.case?.ref ?? ref}`,
        },
    { h: "Service, complaint, or both", b: "Sign the case check" },
    { h: "Triage: severity, owner, first action", b: "Open the triage" },
    { h: `Answer the ${market} questions on the tree`, b: "Open the decision tree" },
    { h: "Reportable or not, and sign it", b: "Go to the outcome and sign" },
    { h: "The right form for the incident's country", b: "Open the report" },
    { h: "Every field filled, then approved by a second person", b: "Open the missing fields" },
    { h: "The PDF, and your submission recorded", b: "Open the PDF step" },
    { h: "The record, ready for an inspector", b: "Open Records" },
    sample
      ? { h: "Is it happening elsewhere?", b: "Open the OrbitCare 300 trend" }
      : { h: "Is it happening elsewhere?", b: "Open your product's trend" },
  ][index];
  return copy;
}

/** Why each step is needed, who takes it and what ticks it (B2 spec 4.8's table), in the walkthrough's order. */
export const STEP_INFO: ReadonlyArray<{ why: string; who: string; evidence: string }> = [
  {
    why: "The reporter's words and the awareness time start everything; every fact is checked before anyone classifies.",
    who: "Service Desk, Complaint Handler",
    evidence: "All nine questions answered and saved on the case check",
  },
  {
    why: "An alleged deficiency is a complaint, even when service fixes it; classification is a controlled human decision.",
    who: "Service Desk, Complaint Handler, Quality Leader",
    evidence: "A signed case check, and its escalation",
  },
  {
    why: "Every complaint gets a first safety look, an owner and a first action; fast when harm is possible.",
    who: "Complaint Handler, Quality Leader, Regulatory Leader",
    evidence: "A complete triage version",
  },
  {
    why: "Each market decides from the facts, with Unknown kept apart from No.",
    who: "Regulatory Leader",
    evidence: "An assessment of the incident's market saved",
  },
  {
    why: "Reportable or not, why and by when, signed by your own role.",
    who: "Regulatory Leader",
    evidence: "That market's conclusion signed",
  },
  {
    why: "A “reportable” conclusion creates the right form for the incident's country.",
    who: "Regulatory Leader",
    evidence: "The report exists and was opened",
  },
  {
    why: "Every mandatory field filled, then a second person approves.",
    who: "Regulatory Leader, then Decision Maker",
    evidence: "Report status Approved",
  },
  {
    why: "MDARIX never submits: you record what you sent.",
    who: "Regulatory Leader",
    evidence: "Submission recorded",
  },
  {
    why: "The signed record is ready for an inspector.",
    who: "Quality Leader",
    evidence: "Records opened after the submission or the “not reportable” conclusion",
  },
  {
    why: "Is it happening elsewhere? Every complaint feeds trends, reportable or not.",
    who: "Quality Leader",
    evidence: "Trends opened",
  },
];

/** Who takes each step, for a colleague whose role cannot open its screen. */
const STEP_ROLE: Record<number, string> = {
  0: "A Service Desk agent or a Complaint Handler",
  1: "A Service Desk agent, a Complaint Handler or the Quality Leader",
  2: "A Complaint Handler or the Quality Leader",
  3: "A Regulatory Leader",
  4: "A Regulatory Leader",
  5: "A Regulatory Leader",
  6: "A Regulatory Leader, then a Decision Maker",
  7: "A Regulatory Leader",
};

/** "Check it as a case" for a complaint classified in your QMS (spec 4.8): opens a Case check linked to it. */
function CheckAsCase({ run, go }: { run: StoryRun; go: (section: string, tab?: string) => void }) {
  const [error, setError] = useState("");
  return (
    <p className="uw-wt-hint">
      <button
        type="button"
        className="ac-link"
        onClick={async () => {
          setError("");
          try {
            const event = await send<{ id: string }>(`/api/v1/intake/from-complaint/${run.complaint.id}`, "POST");
            const place = casePlace(event.id);
            go(place.section, place.tab);
          } catch (reason) {
            setError(errorText(reason, "The case check was not opened"));
          }
        }}
      >
        Check it as a case
      </button>
      {error && <span role="alert"> {error}</span>}
    </p>
  );
}

/** The practice line, said once on the page; "Fictional data" only while the walkthrough is on the sample. */
export const practiceLine = (sample: boolean) =>
  [...(sample ? ["Fictional data"] : []), "Trial outputs are practice records", "Human sign-off required"].join(" · ");

const HARM: Record<string, string> = {
  DEATH: "Death reported",
  SERIOUS_INJURY: "Serious injury reported",
  NONE: "None reported",
};
// The service work order's status (oversight/service_work.py), never the device's: "In service" read as "working".
const SERVICE: Record<string, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  COMPLETE: "Complete",
};

/** The harm the record states, or null when it does not say: never "None reported" for a record that is silent. */
export const harmText = (complaint: StoryRun["complaint"]): string | null => {
  const harm = complaint.harm ?? (complaint.death ? "DEATH" : complaint.serious_injury ? "SERIOUS_INJURY" : null);
  return harm ? HARM[harm] : null;
};

/** The complaint's first sentence: a short summary, never its whole narrative again (exported for its test). */
export function summaryOf(text: string | null | undefined): string | null {
  const first = (text ?? "").trim().split(/(?<=[.!?])\s+/)[0];
  if (!first) return null;
  return first.length > 140 ? `${first.slice(0, 137).replace(/\s+\S*$/, "")}…` : first;
}

/** The short summary of the walkthrough's complaint, read from its own record: reference, first sentence, facts. */
function ComplaintSummary({ run }: { run: StoryRun }) {
  const complaint = run.complaint;
  const summary = summaryOf(complaint.description);
  const harm = harmText(complaint);
  return (
    <div className="uw-wt-case" role="group" aria-label={`Complaint ${complaint.ref}`}>
      <p className="uw-wt-case-head">
        <b className="uw-num">{complaint.ref}</b>
        {summary && <span>{summary}</span>}
      </p>
      <dl className="uw-wt-facts">
        {complaint.product_name && (
          <div>
            <dt>Device</dt>
            <dd>{complaint.product_name}</dd>
          </div>
        )}
        <div>
          <dt>Reported harm</dt>
          <dd>{harm ?? <span className="ac-muted">Not recorded</span>}</dd>
        </div>
        {complaint.service_status && (
          <div>
            <dt>Service work</dt>
            <dd>{SERVICE[complaint.service_status] ?? complaint.service_status}</dd>
          </div>
        )}
      </dl>
      {run.needs.length > 0 && (
        <p className="uw-os-tags">
          Not in your file:{" "}
          {run.needs.map((need) => (
            <span key={need.fact} className="ms-chip is-soon">
              {need.label.toLowerCase()}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

/** Observed against expected, as two bars (Home's trend card). */
export function TrendBars({ row, bare = false }: { row: TrendItem; bare?: boolean }) {
  const top = Math.max(row.recent, row.expected, 0.01);
  const rising = row.result === "SIGNIFICANT" || row.result === "ELEVATED";
  return (
    <div className="uw-os-trend">
      {!bare && (
        <>
          {/* The trend check's own verdict, words and numbers as Trends shows them (0.10.84, M3): a count above the
              expected one that chance explains says so, never "in line" beside it alone. */}
          <b>
            {row.name}: {trendResultLabel(row).toLowerCase()}
          </b>
          <small className="ac-muted">
            {trendCountText(row)} · {chanceText(row)}
            {!rising && row.recent > row.expected && row.result === "STEADY" ? ": within chance, not a rise" : ""}
          </small>
        </>
      )}
      <div className="uw-bars">
        {[
          ["Observed", row.recent, rising ? "is-over" : "is-ok"],
          ["Expected", row.expected, "is-muted"],
        ].map(([label, value, tone]) => (
          <div key={label as string} className="uw-bar-row">
            <span>{label}</span>
            <span className="uw-bar-track">
              <span
                className={`uw-bar-fill ${tone}`}
                style={{ width: `${Math.max(3, Math.round(((value as number) / top) * 100))}%` }}
              />
            </span>
            <b className="uw-num">{label === "Expected" ? (value as number).toFixed(1) : value}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Getting started's walkthrough (owner's specification, 5 Nov 2026; first built in 0.10.82, D1): the page title, the
 * practice line once, and one white card. The card holds the count and one progress bar, the ten steps as a list on
 * the left, and the step chosen (the next one, or one picked to preview) on the right: a label, a heading, one
 * instruction, a short summary of the complaint from its own record and one main button that opens the real screen.
 * Ticks come from the saved record (the server's one-story read), never from the screen on show or a click here.
 */
export function OneStory({ heading }: { heading?: RefObject<HTMLHeadingElement | null> }) {
  const story = useOneStory();
  const team = useResource<{ seats_used: number }>(story.data?.yours?.finished ? TEAM_PATH : null);
  return (
    <StoryView
      story={story.data}
      state={story.state}
      onRetry={story.reload}
      heading={heading}
      colleagues={team.data?.seats_used ?? 1}
    />
  );
}

/**
 * What the card shows for a step picked on the list (null: none picked). Picking only previews: it changes what is
 * shown, never what is done, and the real next step stays marked as next (exported for its test).
 */
export function pickView(run: StoryRun, picked: number | null) {
  return {
    finished: run.finished && picked === null,
    selected: picked ?? Math.min(run.current, STORY_STEPS - 1),
    previewing: picked !== null && picked !== run.current,
  };
}

/** The pick a click on the list makes: the real next step resumes (no pick), any other step is previewed. */
export const pickOn = (run: StoryRun, index: number): number | null => (index === run.current ? null : index);

/** The walkthrough as read (exported for its test). */
export function StoryView({
  story,
  state = "ready",
  onRetry,
  heading,
  colleagues = 1,
}: {
  story: OneStoryData | null;
  /** The read's state. With no story read yet, the card says it is loading, failed (with Try again) or refused. */
  state?: string;
  onRetry?: () => void;
  heading?: RefObject<HTMLHeadingElement | null>;
  /** The people on the trial, the owner included. */
  colleagues?: number;
}) {
  const { open, dataSource, chooseDataSource, session, startStory, canOpen } = useWorkspace();
  const [picked, setPicked] = useState<number | null>(null);
  const [problem] = useState(takeMarkProblem);
  const run = shownRun(story, dataSource);
  const sample = run?.run === "sample";
  // The ten-step story replaces an older story's bar: one progress indicator per page (D1.5).
  const go = (section: string, tab?: string) => {
    startStory?.(null);
    open(section as WorkspaceSection, tab);
  };
  const ticked = run ? run.steps.filter((step) => step.done || step.skipped).length : 0;
  // The hero design's monitor band (0.10.90): the page's words, the ten-step arc and the bedside scene.
  const header = (
    <MonitorBand className="uw-gs-band">
      <header className="uw-gs-head">
        <h1 ref={heading} tabIndex={-1}>
          Getting started
        </h1>
        <p>
          {run && !sample
            ? "Follow your most urgent complaint from the first contact to the submission."
            : "Follow one sample complaint from the first contact to the submission."}
        </p>
        {/* Said once, after the read, so it never says "Fictional data" over your own records. */}
        {run && <p className="uw-gs-practice">{practiceLine(sample)}</p>}
        {run && (
          <div className="uw-gs-prog" aria-hidden="true">
            <ProgressArc done={ticked} size={64} decorative />
            <b className="uw-num">
              {ticked}
              <small>/{STORY_STEPS}</small>
            </b>
          </div>
        )}
      </header>
      <BedsideScene className="uw-gs-scene" />
    </MonitorBand>
  );
  if (!run) {
    const failed = state === "error" || state === "forbidden";
    return (
      <div className="uw-os">
        {header}
        <section className="uw-wt is-empty" aria-labelledby="uw-wt-title" aria-busy={state === "loading"}>
          <h2 id="uw-wt-title">
            {state === "loading"
              ? "Your sample walkthrough"
              : failed
                ? "The walkthrough could not be loaded"
                : "No complaint to follow yet"}
          </h2>
          {state === "loading" ? (
            <p className="ac-muted">Reading your walkthrough…</p>
          ) : state === "forbidden" ? (
            <p>Your role cannot read the walkthrough. Ask the trial owner.</p>
          ) : failed ? (
            <>
              <p role="alert">MDARIX could not read your progress just now. Nothing was changed.</p>
              {onRetry && (
                <div className="ca-action-row">
                  <button type="button" className="ac-primary" onClick={onRetry}>
                    Try again
                  </button>
                </div>
              )}
            </>
          ) : (
            <p>
              {session?.sample_only
                ? "The sample data is not in this workspace."
                : "The sample data is not in this workspace. Once your complaints are imported (Import your data, at the top), the walkthrough follows your most urgent one."}
            </p>
          )}
        </section>
      </div>
    );
  }
  const done = run.steps.filter((step) => step.done).length;
  const skipped = run.steps.filter((step) => step.skipped).length;
  const { finished, selected, previewing } = pickView(run, picked);
  const yoursNext = () => {
    if (story?.yours) {
      setPicked(null);
      chooseDataSource?.(IMPORTED_SOURCE);
    } else open("Import your data");
  };
  let body: ReactNode;
  if (finished) {
    body = (
      <>
        <div className="uw-os-art">
          <SignedSeal size={76} />
          <div>
            <p className="uw-wt-label">All ten steps done</p>
            <h3 id="uw-os-title">{sample ? "The sample walkthrough is complete" : "Your walkthrough is complete"}</h3>
          </div>
        </div>
        <p className="uw-wt-lead">
          {sample
            ? "From the call to a recorded submission and the trend check. Now the same ten steps on your own most urgent complaint."
            : `Your first complaint went from the call to its signed conclusion, with every missing fact asked for and nothing guessed. ${colleagues > 1 ? "Discuss a pilot with your team." : "Invite a colleague, or discuss a pilot."}`}
        </p>
        <ComplaintSummary run={run} />
        <div className="ca-action-row">
          {sample && !session?.sample_only ? (
            <button type="button" className="ac-primary uw-os-go" onClick={yoursNext}>
              Do the same with your data <ChevronRight size={15} aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              className="ac-primary uw-os-go"
              onClick={() => (session?.sample_only || colleagues > 1 ? open("Next steps") : open("Team"))}
            >
              {/* A colleague is invited once (0.10.84, L5): with a team already, the next step is the pilot. */}
              {session?.sample_only || colleagues > 1 ? "Discuss a pilot" : "Invite a colleague"}{" "}
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          )}
        </div>
      </>
    );
  } else {
    const copy = stepCopy(run, selected);
    const info = STEP_INFO[selected];
    const step = run.steps[selected];
    const blocked = stepBlocker(run, selected);
    // A step whose screen this person's role cannot open says so and who does it: never a dead click (0.10.85).
    const section = stepPlace(run, selected).section;
    const closed = canOpen ? !canOpen(section) : false;
    const then = selected < STORY_STEPS - 1 ? run.steps[selected + 1] : null;
    const action =
      blocked && !step.done && !run.report_id && run.needs.length === 0 && run.market
        ? "Open the decision tree"
        : blocked && !step.done && (run.needs.length || !run.market)
          ? `Open ${run.complaint.ref}`
          : copy.b;
    body = (
      <>
        <div className="uw-os-art">
          <span className="uw-os-art-ic" aria-hidden="true">
            <StepIcon index={selected} size={36} />
          </span>
          <p className="uw-wt-label">
            Step {selected + 1} · {step.label}
          </p>
        </div>
        {previewing && (
          <p className="uw-wt-preview">
            <Eye size={15} aria-hidden="true" />
            <span>
              Preview.{" "}
              {run.finished
                ? "All ten steps are done."
                : `Your next step is ${run.current + 1}, ${run.steps[run.current].label}.`}
            </span>
            <button type="button" className="ac-link" onClick={() => setPicked(null)}>
              {run.finished ? "Back to the summary" : `Back to step ${run.current + 1}`}
            </button>
          </p>
        )}
        <h3 id="uw-os-title">{copy.h}</h3>
        {/* Four lines, in this order (spec 4.8): the action, the reason, the role, what ticks it. */}
        <dl className="uw-os-lines">
          <div>
            <dt>Next</dt>
            <dd>{action}</dd>
          </div>
          <div>
            <dt>Why</dt>
            <dd>{info.why}</dd>
          </div>
          <div>
            <dt>Who</dt>
            <dd>{info.who}</dd>
          </div>
          <div>
            <dt>Evidence</dt>
            <dd>{info.evidence}</dd>
          </div>
        </dl>
        {step.skipped ? (
          <span className="ms-chip uw-os-state">{step.note ?? "Not needed"}</span>
        ) : step.done ? (
          <span className="ms-chip is-good uw-os-state">
            <Check size={13} aria-hidden="true" /> Done · read from the saved record
          </span>
        ) : step.earlier ? (
          <span className="ms-chip uw-os-state">
            Done earlier by your team · ticked once the steps before it are done
          </span>
        ) : null}
        {closed && (
          <p className="uw-os-differ" id="uw-os-closed">
            {STEP_ROLE[selected] ?? "A colleague with that role"} does this step: your role cannot open its screen. Ask
            the trial owner, or a colleague with that role, to take it.
          </p>
        )}
        {blocked && !step.done && <p className="uw-os-differ">{blocked}</p>}
        {/* A pending case keeps step 2 open: who it waits on and by when. */}
        {!step.done && !step.skipped && step.note && <p className="uw-os-differ">{step.note}</p>}
        {!run.case && selected <= 1 && <CheckAsCase run={run} go={go} />}
        {run.branch && run.case && selected >= 1 && selected <= 7 && (
          <div className="uw-os-differ" role="group" aria-label={run.branch.label}>
            <p>
              <b>{run.branch.label}</b> · {run.branch.done ? "Done" : "To do"}
            </p>
            <p>{run.branch.why}</p>
            <p>
              Who: {run.branch.who} · Evidence: {run.branch.evidence.toLowerCase()}
            </p>
            <button
              type="button"
              className="ac-link"
              onClick={() => {
                const place = casePlace(run.case!.id);
                go(place.section, place.tab);
              }}
            >
              Open the QA review of {run.case.ref}
            </button>
          </div>
        )}
        <ComplaintSummary run={run} />
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-primary uw-os-go"
            disabled={closed}
            aria-describedby={closed ? "uw-os-closed" : undefined}
            onClick={() => void openStep(run, selected, go)}
          >
            {action} <ChevronRight size={15} aria-hidden="true" />
          </button>
        </div>
        {then && (
          <p className="uw-wt-hint">
            Then:{" "}
            <button type="button" className="ac-link" onClick={() => setPicked(selected + 1)}>
              step {selected + 2}, {then.label}
            </button>
          </p>
        )}
      </>
    );
  }
  return (
    <div className="uw-os">
      {header}
      <section className="uw-wt" aria-labelledby="uw-wt-title">
        <div className="uw-wt-head">
          <h2 id="uw-wt-title">{sample ? "Your sample walkthrough" : "Your data walkthrough"}</h2>
          <h3 className="uw-os-part">Part 1: from the first contact to the submission</h3>
          <span className={`ms-chip ${sample ? "is-sample" : "is-yours"}`}>{sample ? "Sample data" : "Your data"}</span>
          <span className="uw-wt-count uw-num">
            {done} of {STORY_STEPS} completed{skipped ? ` · ${skipped} not needed` : ""}
          </span>
          <span className="sr-only">{stepCount(run)}</span>
          <div
            className="uw-wt-bar"
            role="progressbar"
            aria-label="Walkthrough progress"
            aria-valuemin={0}
            aria-valuemax={STORY_STEPS}
            aria-valuenow={done + skipped}
            aria-valuetext={`${done} of ${STORY_STEPS} completed`}
          >
            {/* Ten segments, one per step (0.10.90, the hero design). */}
            {run.steps.map((step, index) => (
              <i
                key={step.key}
                className={
                  step.done || step.skipped ? "is-on" : !run.finished && index === run.current ? "is-cur" : undefined
                }
              />
            ))}
          </div>
        </div>
        {problem && (
          <p className="uw-os-problem" role="status">
            {problem}
          </p>
        )}
        <div className="uw-os-grid">
          <ol className="uw-os-rail" aria-label="Walkthrough steps">
            {run.steps.map((step, index) => {
              const isNext = !run.finished && index === run.current;
              const status = step.skipped
                ? "Not needed"
                : step.done
                  ? "Completed"
                  : step.earlier
                    ? "Done earlier"
                    : isNext
                      ? "Next"
                      : null;
              return (
                <li key={step.key}>
                  <button
                    type="button"
                    className={`uw-os-step${step.skipped ? " is-skip" : step.done ? " is-done" : isNext ? " is-now" : step.earlier ? " is-earlier" : ""}${!finished && index === selected ? " is-sel" : ""}`}
                    aria-current={isNext ? "step" : undefined}
                    aria-pressed={!finished && index === selected}
                    title={step.earlier ? "Done earlier by your team" : undefined}
                    onClick={() => setPicked(pickOn(run, index))}
                  >
                    <span className="uw-os-k" aria-hidden="true">
                      <StepIcon index={index} />
                      {(step.done || step.skipped) && (
                        <span className="uw-os-ok">{step.done ? <Check size={11} /> : <Minus size={11} />}</span>
                      )}
                    </span>
                    <span className="uw-os-t">
                      <span className="uw-os-num" aria-hidden="true">
                        Step {index + 1}
                      </span>
                      <span className="sr-only">Step {index + 1}: </span>
                      {step.label}
                    </span>
                    {status && <small className="uw-os-s">{status}</small>}
                  </button>
                </li>
              );
            })}
          </ol>
          <div className={`uw-os-main${previewing ? " is-preview" : ""}`}>{body}</div>
        </div>
        <p className="uw-wt-hint uw-os-coming">Coming next: investigation to CAPA · trends to product improvement</p>
      </section>
      <MoreCases cases={story?.more_cases ?? []} onOpen={go} />
    </div>
  );
}

/** Each step's icon, in the walkthrough's order (0.10.90, the hero design); the fork at steps 2 and 5 marks where the
 * journey branches (spec 4.8). */
const STEP_ICONS: readonly LucideIcon[] = [
  Phone,
  GitFork,
  Stethoscope,
  ListChecks,
  GitFork,
  FileText,
  UserCheck,
  Send,
  Archive,
  TrendingUp,
];

function StepIcon({ index, size = 18 }: { index: number; size?: number }) {
  const Icon = STEP_ICONS[index] ?? ListChecks;
  return <Icon size={size} aria-hidden="true" />;
}

/**
 * "More cases to try" (0.10.93, spec 4.8; it replaces "Before a complaint"): the sample's other Cases, each opening
 * its own Case check, with its outcome as the record says. The server lists them (a trial seeded earlier keeps its
 * SAMPLE-CALL references), so nothing is shown once the sample is removed.
 */
export function MoreCases({ cases, onOpen }: { cases: MoreCase[]; onOpen: (section: string, tab?: string) => void }) {
  if (!cases.length) return null;
  return (
    <div id="trial-first-contact" className="uw-story-partner uw-anchor">
      <div>
        <strong>
          <Phone size={16} aria-hidden="true" /> More cases to try
        </strong>
        <p>
          Each opens its own case check: an inquiry, a pending case waiting for the reporter, one to confirm no
          deficiency, and an urgent case triaged at once.
        </p>
      </div>
      <div className="uw-story-partner-actions">
        {cases.map((item) => (
          <button
            key={item.id}
            type="button"
            className="ac-secondary"
            onClick={() => {
              const place = casePlace(item.id);
              onOpen(place.section, place.tab);
            }}
          >
            {item.ref} <small className="ac-muted">{item.label}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

/** "More cases to try" read on its own, for a page that does not show the walkthrough (the classic navigation). */
export function MoreCasesCard({ onOpen }: { onOpen: (section: string, tab?: string) => void }) {
  const story = useOneStory();
  return <MoreCases cases={story.data?.more_cases ?? []} onOpen={onOpen} />;
}

/**
 * The slim story pill on the story's own record (0.10.82, D1.5): "Story · Step 4 of 10 · Back", in place of a second
 * progress panel. Back returns to Getting started, where the step's card is.
 */
export function StoryPill({ run }: { run: StoryRun }) {
  const { open } = useWorkspace();
  return (
    <span className="uw-story-pill">
      <span className={`ms-chip ${run.run === "sample" ? "is-sample" : "is-yours"}`}>
        {run.run === "sample" ? "Story" : "Your data"}
      </span>
      {stepCount(run)}
      <button type="button" className="ac-link" onClick={() => open("Getting started")}>
        Back
      </button>
    </span>
  );
}

export type { OneStoryData };
