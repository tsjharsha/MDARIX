import { useState, type ReactNode, type RefObject } from "react";
import { Check, ChevronRight, Eye, Minus } from "lucide-react";
import { useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { IMPORTED_SOURCE } from "../complaintList";
import { TEAM_PATH } from "./TrialTeam";
import { chanceText, trendCountText, trendResultLabel, type TrendItem } from "../signalAi";
import {
  STORY_STEPS,
  openStep,
  shownRun,
  stepBlocker,
  stepCount,
  stepPlace,
  takeMarkProblem,
  useOneStory,
  type OneStory as OneStoryData,
  type StoryRun,
} from "../oneStory";

/** Each step's words: the heading, one short instruction, and its one main button. The record's facts are never
 * written here: the complaint summary below them reads them from the record (owner's specification, 5 Nov 2026). */
function stepCopy(run: StoryRun, index: number): { h: string; p: string; b: string } {
  const sample = run.run === "sample";
  const ref = run.complaint.ref;
  const market = run.market_label ?? "the market's";
  const copy = [
    sample
      ? {
          h: "Start with the hospital's report",
          p: "Read the event and check the available facts. The awareness time starts every clock.",
          b: "Open sample complaint",
        }
      : {
          // A reference never breaks at its hyphen (a non-breaking hyphen in the heading).
          h: `Your most urgent complaint: ${ref.replace(/-/g, "‑")}`,
          p: "MDARIX picked it from your file: the most serious harm, then the shortest clock. Check what the file says and what it lacks.",
          b: `Open ${ref}`,
        },
    {
      h: "Triage: severity, owner, first action",
      p: "Confirm the severity, name an owner and the first action. The triage target and the legal clock both run from awareness.",
      b: "Open the triage",
    },
    {
      h: `Answer the ${market} questions on the tree`,
      p: "Facts stated in the record arrive as answers to confirm. Judgement questions are never pre-filled: they are yours.",
      b: "Open the decision tree",
    },
    {
      h: "Reportable or not, and sign it",
      p: "The outcome says reportable or not, why, and by when. Your own role signs, never the persona you view as.",
      b: "Go to the outcome and sign",
    },
    {
      h: "The right form for the incident's country",
      p: "A signed “reportable” conclusion creates the form: FDA 3500A, the EU or MHRA MIR, Canada's problem report or India's MvPI MDAE.",
      b: "Open the report",
    },
    {
      h: "Fill what is missing",
      p: "What your records hold arrives filled, each with its source. Each field still empty names its form box and who knows it.",
      b: "Open the missing fields",
    },
    {
      h: "Approval by a second person",
      p: "A colleague who may approve gets one task, and nobody approves what they prepared. Working alone in the trial, you approve your own practice report, marked so.",
      b: "Open the approval",
    },
    {
      h: "The PDF, and your submission recorded",
      p: "The PDF follows the form's field order. You submit through the authority's own route and record it here. MDARIX never submits.",
      b: "Open the PDF step",
    },
    {
      h: "The record, ready for an inspector",
      p: "Records opens on what you just finished: the signed conclusion, the approved report, its PDF and who signed.",
      b: "Open Records",
    },
    sample
      ? {
          h: "Is it happening elsewhere?",
          p: "Trends compare each product version with its own history, per unit in the field. The sample holds a real rise: OrbitCare 300 Rev B.",
          b: "Open the OrbitCare 300 trend",
        }
      : {
          h: "Is it happening elsewhere?",
          p: "Trends compare each product version with its own history, per unit in the field where your file has units. A short history says what it can show now.",
          b: "Open your product's trend",
        },
  ][index];
  return copy;
}

/** Who takes each step, for a colleague whose role cannot open its screen. */
const STEP_ROLE: Record<number, string> = {
  1: "A Complaint Handler or the Quality Leader",
  2: "A Regulatory Leader",
  3: "A Regulatory Leader",
  4: "A Regulatory Leader",
  5: "A Regulatory Leader",
  6: "A Decision Maker",
  7: "A Regulatory Leader",
};

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
  const header = (
    <header className="uw-gs-head">
      <h1 ref={heading} tabIndex={-1}>
        Getting started
      </h1>
      <p>
        {run && !sample
          ? "Follow your most urgent complaint from first call to reporting."
          : "Follow one sample complaint from first call to reporting."}
      </p>
      {/* Said once, after the read, so it never says "Fictional data" over your own records. */}
      {run && <p className="uw-gs-practice">{practiceLine(sample)}</p>}
    </header>
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
        <p className="uw-wt-label">All ten steps done</p>
        <h3 id="uw-os-title">{sample ? "The sample walkthrough is complete" : "Your walkthrough is complete"}</h3>
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
    const step = run.steps[selected];
    const blocked = stepBlocker(run, selected);
    // A step whose screen this person's role cannot open says so and who does it: never a dead click (0.10.85).
    const section = stepPlace(run, selected).section;
    const closed = canOpen ? !canOpen(section) : false;
    const then = selected < STORY_STEPS - 1 ? run.steps[selected + 1] : null;
    body = (
      <>
        <p className="uw-wt-label">
          Step {selected + 1} · {step.label}
        </p>
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
        <p className="uw-wt-lead">{copy.p}</p>
        {step.skipped ? (
          <span className="ms-chip uw-os-state">
            {selected === 1
              ? "Not needed: not flagged for triage"
              : "Not needed: the signed conclusion is “not reportable”"}
          </span>
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
        <ComplaintSummary run={run} />
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-primary uw-os-go"
            disabled={closed}
            aria-describedby={closed ? "uw-os-closed" : undefined}
            onClick={() => void openStep(run, selected, go)}
          >
            {blocked && !step.done && !run.report_id && run.needs.length === 0 && run.market
              ? "Open the decision tree"
              : blocked && !step.done && (run.needs.length || !run.market)
                ? `Open ${run.complaint.ref}`
                : copy.b}{" "}
            <ChevronRight size={15} aria-hidden="true" />
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
            <span style={{ width: `${Math.round(((done + skipped) / STORY_STEPS) * 100)}%` }} />
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
                      {step.done ? <Check size={13} /> : step.skipped ? <Minus size={13} /> : index + 1}
                    </span>
                    <span className="uw-os-t">
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
      </section>
    </div>
  );
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
