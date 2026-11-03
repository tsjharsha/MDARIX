import { useState, type RefObject } from "react";
import { Check, ChevronRight } from "lucide-react";
import { useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { IMPORTED_SOURCE } from "../complaintList";
import { trendPath, type TrendBoard, type TrendItem } from "../signalAi";
import {
  STORY_STEPS,
  openStep,
  shownRun,
  stepBlocker,
  stepCount,
  useOneStory,
  type OneStory as OneStoryData,
  type StoryRun,
} from "../oneStory";

/** Each step's words: the heading, one sentence of what the person will see, and its one main button. */
function stepCopy(run: StoryRun, index: number): { h: string; p: string; b: string; differ?: string } {
  const sample = run.run === "sample";
  const ref = run.complaint.ref;
  const market = run.market_label ?? "the market's";
  const copy = [
    sample
      ? {
          h: "A US hospital reports a monitor reading SpO2 high",
          p: "Biomedical engineering found a monitor reading 4 to 6 points high. No harm was reported; the monitor went for service. Read their words: the awareness time starts every clock.",
          b: `Open the call on ${ref}`,
        }
      : {
          h: `Your most urgent complaint: ${ref}`,
          p: "MDARIX picked it from your file: the most serious harm, then the shortest clock. Read what your file says, and see what it does not.",
          b: `Open ${ref}`,
        },
    {
      h: "Triage: severity, owner, first action",
      p: "Confirm what the record says, name an owner and the first action. The triage target and the legal clock both run from awareness.",
      b: "Open the triage",
    },
    {
      h: `Answer the ${market} questions on the tree`,
      p: "Facts stated in the record arrive as answers to confirm. Judgement questions are never pre-filled: they are yours.",
      b: "Open the decision tree",
    },
    {
      h: "Reportable or not, and sign it",
      p: "The outcome says reportable or not, why, and by when. You sign it: your role decides that, never the persona you view as.",
      b: "Go to the outcome and sign",
    },
    {
      h: "The right form for the incident's country",
      p: "Signing “reportable” creates the form for where it happened: US, FDA 3500A; EU, the MIR; Great Britain, the MHRA MIR; Canada, the mandatory problem report; India, the MvPI MDAE.",
      b: "Open the report",
    },
    {
      h: "Fill what is missing",
      p: "Most fields arrive filled from your records, each with its source. Each one still empty names its form box.",
      b: "Open the missing fields",
    },
    {
      h: "Approval by a second person",
      p: "Send it for approval. A colleague who may approve gets one task, and nobody approves what they prepared. Working alone in the trial, you approve your own practice report, marked so.",
      b: "Open the approval",
    },
    {
      h: "The PDF, and your submission recorded",
      p: "The PDF follows the form's field order, with the approval on its last page. You submit through the authority's own route and record it here. MDARIX never submits.",
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
          p: "First this monitor against its own history. Then the sample's real rise: OrbitCare 300 Rev B, per unit in the field.",
          b: "Open the OrbitCare 300 trend",
        }
      : {
          h: "Is it happening elsewhere?",
          p: "Trends compare each product version with its own history, per unit in the field where your file has units. A short history says what it can show now.",
          b: "Open Trends",
        },
  ][index];
  return copy;
}

/** The step's preview: a glimpse of the screen it opens, read from the same records. */
function StepPreview({ run, index, trends }: { run: StoryRun; index: number; trends: TrendItem[] }) {
  const frame = (title: string, body: React.ReactNode) => (
    <div className="uw-os-mini" aria-hidden="true">
      <div className="uw-os-mini-bar">
        <i />
        <i />
        <i />
        <span>{title}</span>
      </div>
      <div className="uw-os-mini-body">{body}</div>
    </div>
  );
  const ref = run.complaint.ref;
  if (index === 0)
    return frame(
      `Complaints › ${ref}`,
      <>
        <span className="ac-eyebrow">The reporter's words</span>
        <blockquote className="uw-os-quote">“{run.complaint.description ?? "No description recorded"}”</blockquote>
        {run.needs.length > 0 && (
          <span className="uw-os-tags">
            Not in your file:{" "}
            {run.needs.map((need) => (
              <span key={need.fact} className="ms-chip is-soon">
                {need.label.toLowerCase()}
              </span>
            ))}
          </span>
        )}
      </>,
    );
  if (index === 1)
    return frame(
      `${ref} › Triage`,
      <ul className="uw-os-lines">
        <li>Severity, from the record</li>
        <li>Owner and the first action</li>
        <li>Triage target · legal clock, from awareness</li>
      </ul>,
    );
  if (index <= 3)
    return frame(
      `Decision trees › ${run.market_label ?? "the country first"} › ${ref}`,
      <>
        <ul className="uw-os-lines">
          <li>Facts from the record: confirm them</li>
          <li>Judgement questions: yours, never pre-filled</li>
        </ul>
        <span className={`uw-os-outcome${run.conclusion ? " is-signed" : ""}`}>
          {run.conclusion === "REPORTABLE"
            ? "Signed: reportable"
            : run.conclusion === "NOT_REPORTABLE"
              ? "Signed: not reportable"
              : "Not decided yet"}
        </span>
      </>,
    );
  if (index === 4)
    return frame(
      "Reports",
      <>
        <span className="ac-muted">The incident's country picks the form</span>
        <span className="uw-os-tags">
          {["US", "EU_NI", "GB", "CA", "IN"].map((market) => (
            <span key={market} className={`ms-chip${market === run.market ? " is-current" : ""}`}>
              {{ US: "FDA 3500A", EU_NI: "EU MIR", GB: "MHRA MIR", CA: "Health Canada", IN: "MvPI MDAE" }[market]}
            </span>
          ))}
        </span>
      </>,
    );
  if (index <= 7) {
    const path = ["Created", "Fields complete", "Sent for approval", "Approved · PDF", "Submitted", "Acknowledged"];
    const codes = ["CREATED", "COMPLETE", "APPROVAL", "APPROVED", "SUBMITTED", "ACKNOWLEDGED"];
    const at = codes.indexOf(run.report_stage ?? "");
    return frame(
      "Report",
      <ol className="uw-os-path">
        {path.map((label, step) => (
          <li key={label} className={step < at ? "is-done" : step === at ? "is-now" : undefined}>
            {step < at && <Check size={12} aria-hidden="true" />} {label}
          </li>
        ))}
      </ol>,
    );
  }
  if (index === 8)
    return frame(
      "Records",
      <>
        <span className="ac-eyebrow">Your latest record</span>
        <b>{ref}</b>
        <span className="ac-muted">The signed conclusion, the approved report, its PDF and who signed</span>
      </>,
    );
  // The finale: the story's own product first, then the sample's real rise (OrbitCare 300 Rev B).
  const own = trends.find((row) => row.product.id === run.complaint.product_id);
  const rising = trends.find((row) => row.result === "SIGNIFICANT");
  const rows = [own, run.run === "sample" ? rising : undefined].filter(
    (row, i, all): row is TrendItem => !!row && all.indexOf(row) === i,
  );
  return frame(
    "Trends",
    rows.length ? (
      rows.map((row) => <TrendBars key={row.key} row={row} />)
    ) : (
      <span className="ac-muted">Reading the trend check…</span>
    ),
  );
}

/** Observed against expected, as two bars (Home's trend card and the story's finale). */
export function TrendBars({ row }: { row: TrendItem }) {
  const top = Math.max(row.recent, row.expected, 0.01);
  const rising = row.result === "SIGNIFICANT" || row.result === "ELEVATED";
  const ratio = typeof row.ratio === "number" ? ` · ${row.ratio.toFixed(1)}×` : "";
  return (
    <div className="uw-os-trend">
      <b>
        {row.name}
        {rising ? ratio : ": in line with its history"}
      </b>
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
            <b className="uw-num">{Number((value as number).toFixed(2))}</b>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Getting started's story (0.10.82, D1.1-D1.4): one hero, one ten-step rail with a Sample / Your data label, and one
 * card for the step picked (the next step, or the one chosen on the rail) with one main button that opens the real
 * screen. Ticks come from the saved record (the server's one-story read), never from the screen on show. After the
 * sample's tenth step: "Do the same with your data". Everything else folds under "More ways to explore".
 */
export function OneStory({ heading }: { heading?: RefObject<HTMLHeadingElement | null> }) {
  const story = useOneStory();
  const trends = useResource<TrendBoard>(trendPath("version"));
  return (
    <StoryView
      story={story.data}
      loading={story.state === "loading"}
      trends={trends.data?.items ?? []}
      heading={heading}
    />
  );
}

/** The story as read (exported for its test). */
export function StoryView({
  story,
  loading = false,
  trends,
  heading,
}: {
  story: OneStoryData | null;
  loading?: boolean;
  trends: TrendItem[];
  heading?: RefObject<HTMLHeadingElement | null>;
}) {
  const { open, dataSource, chooseDataSource, session } = useWorkspace();
  const [picked, setPicked] = useState<number | null>(null);
  const run = shownRun(story, dataSource);
  const go = (section: string, tab?: string) => open(section as WorkspaceSection, tab);
  const header = (
    <div className="uw-os-head">
      <span className="ac-eyebrow">Getting started</span>
      <h1 ref={heading} tabIndex={-1}>
        One complaint, from the first call to the signed report
      </h1>
      <p>Ten steps on a fictional hospital call, then the same ten on your own most urgent complaint.</p>
    </div>
  );
  if (!run)
    return (
      <section className="uw-os" aria-labelledby="uw-os-title">
        {header}
        <p className="uw-os-lead" id="uw-os-title">
          {loading ? "Reading your story…" : "Import your complaints to tell the story on your own data."}
        </p>
        {!loading && !session?.sample_only && (
          <div className="ca-action-row">
            <button type="button" className="ac-primary" onClick={() => open("Import your data")}>
              Import your data <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
        )}
      </section>
    );
  const done = run.steps.filter((step) => step.done).length;
  const finished = run.finished && picked === null;
  const selected = picked ?? Math.min(run.current, STORY_STEPS - 1);
  const sample = run.run === "sample";
  const yoursNext = () => {
    if (story?.yours) {
      setPicked(null);
      chooseDataSource?.(IMPORTED_SOURCE);
    } else open("Import your data");
  };
  let body: React.ReactNode;
  if (finished) {
    body = (
      <div className="uw-os-main">
        <span className="ac-eyebrow">All ten steps done · {run.complaint.ref}</span>
        <h2 id="uw-os-title">{sample ? "The sample story is complete" : "Your story is complete"}</h2>
        <p className="uw-os-lead">
          {sample
            ? "From the call to a recorded submission and the trend check. Now the same ten steps on your own most urgent complaint."
            : "Your first complaint went from the call to its signed conclusion, with every missing fact asked for and nothing guessed. Invite a colleague, or discuss a pilot."}
        </p>
        <div className="ca-action-row">
          {sample && !session?.sample_only ? (
            <button type="button" className="ac-primary uw-os-go" onClick={yoursNext}>
              Do the same with your data <ChevronRight size={15} aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              className="ac-primary uw-os-go"
              onClick={() => (session?.sample_only ? open("Next steps") : open("Team"))}
            >
              {session?.sample_only ? "Discuss a pilot" : "Invite a colleague"}{" "}
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    );
  } else {
    const copy = stepCopy(run, selected);
    const step = run.steps[selected];
    const blocked = stepBlocker(run, selected);
    body = (
      <div className="uw-os-main">
        <span className="ac-eyebrow">
          Step {selected + 1} of {STORY_STEPS} · {run.complaint.ref}
        </span>
        <h2 id="uw-os-title">{copy.h}</h2>
        <p className="uw-os-lead">{copy.p}</p>
        {step.skipped ? (
          <span className="ms-chip uw-os-state">Not needed: the signed conclusion is “not reportable”</span>
        ) : step.done ? (
          <span className="ms-chip is-good uw-os-state">
            <Check size={13} aria-hidden="true" /> Done · read from the saved record
          </span>
        ) : null}
        {blocked && !step.done && <p className="uw-os-differ">{blocked}</p>}
        <div className="ca-action-row">
          <button type="button" className="ac-primary uw-os-go" onClick={() => void openStep(run, selected, go)}>
            {blocked && !step.done && !run.report_id && run.needs.length === 0 && run.market
              ? "Open the decision tree"
              : blocked && !step.done && (run.needs.length || !run.market)
                ? `Open ${run.complaint.ref}`
                : copy.b}{" "}
            <ChevronRight size={15} aria-hidden="true" />
          </button>
          {selected < STORY_STEPS - 1 && (
            <button type="button" className="ac-link uw-os-see" onClick={() => setPicked(selected + 1)}>
              See step {selected + 2}
            </button>
          )}
        </div>
      </div>
    );
  }
  return (
    <section className="uw-os" aria-labelledby="uw-os-title">
      {header}
      <p className="uw-os-label">
        <span className={`ms-chip ${sample ? "is-sample" : "is-yours"}`}>{sample ? "Sample" : "Your data"}</span>
        <span className="uw-num">{done} of 10 done</span>
        <span className="sr-only">{stepCount(run)}</span>
      </p>
      <nav className="uw-os-rail" aria-label="Story steps">
        {run.steps.map((step, index) => (
          <button
            key={step.key}
            type="button"
            className={`uw-os-step${step.skipped ? " is-skip" : step.done ? " is-done" : index === run.current ? " is-now" : ""}${!finished && index === selected ? " is-sel" : ""}`}
            aria-current={!finished && index === selected ? "step" : undefined}
            onClick={() => setPicked(index)}
          >
            <span className="uw-os-k">{step.done ? <Check size={13} aria-label="done" /> : index + 1}</span>
            <span className="uw-os-t">{step.label}</span>
          </button>
        ))}
      </nav>
      <div className="uw-os-body">
        {body}
        <StepPreview run={run} index={finished ? 8 : selected} trends={trends} />
      </div>
    </section>
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
