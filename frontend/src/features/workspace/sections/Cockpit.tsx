import { useContext, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { listOf, useResource } from "../../customer-admin/shared";
import { WorkspaceContext } from "../workspaceContext";
import { WhyAsked } from "../../shared/Basis";
import { CASE_STEP_WHY } from "../whyAsked";
import {
  STEP_QUESTION,
  caseProgress,
  nextCaseStep,
  readinessChecks,
  type CaseReadiness,
  type CaseSection,
  type CaseStep,
} from "../caseWorkflow";
import {
  evidenceStates,
  humanStatusOf,
  intelligencePath,
  type IntelHypothesis,
  type IntelUnknown,
  type StoredChain,
} from "../intelligence";

/**
 * The investigation cockpit (UX3, Persona Blueprint wave C): a summary strip (evidence for, against and missing; the
 * possible causes; what blocks the decision; the one next step) over one 6-step rail. It replaces the four-section
 * progress line, the six-question guide and the two in-page tab lists; the steps' content is in CaseSections.tsx.
 */

export type CockpitFigures = {
  evidenceFor: number;
  evidenceAgainst: number;
  evidenceMissing: number;
  causes: number;
  leading: number;
  blocking: { count: number; first: string | null };
};

/** The strip's figures from the case's own records (pure, for its test). Each one's definition is on the strip. */
export function cockpitFigures(input: {
  hypotheses?: IntelHypothesis[] | null;
  unknowns?: IntelUnknown[] | null;
  chains?: StoredChain[] | null;
  readiness?: CaseReadiness | null;
}): CockpitFigures {
  const states = evidenceStates({ hypotheses: input.hypotheses, unknowns: input.unknowns, chains: input.chains });
  const considered = (input.hypotheses ?? []).filter((item) => humanStatusOf(item.human_status) !== "RETIRED");
  const blocking = readinessChecks(input.readiness).filter(
    (check) => (check.result === "BLOCKED" || check.result === "PENDING") && check.key !== "decision",
  );
  return {
    evidenceFor: states.known.length,
    evidenceAgainst: states.contradicted.length,
    evidenceMissing: states.unknown.length + states.missing.length,
    causes: considered.length,
    leading: considered.filter((item) => humanStatusOf(item.human_status) === "STRONGLY_SUPPORTED").length,
    blocking: { count: blocking.length, first: blocking[0]?.label ?? null },
  };
}

/** One figure of the strip: what it counts, its number, its definition; a click opens the step holding its records. */
function Figure({
  label,
  value,
  definition,
  onOpen,
}: {
  label: string;
  value: string;
  definition: string;
  onOpen: () => void;
}) {
  return (
    <li>
      <button type="button" className="uw-cockpit-figure" onClick={onOpen}>
        <span className="ac-eyebrow">{label}</span>
        <strong>{value}</strong>
        <small>{definition}</small>
      </button>
    </li>
  );
}

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

/**
 * The cockpit's head: the summary strip and the rail. `active` is the step shown; the rail marks it, and each step
 * says whether its recorded work is done.
 */
export function Cockpit({
  investigationId,
  steps,
  readiness,
  active,
  onSection,
}: {
  investigationId: string;
  steps: CaseStep[];
  readiness: CaseReadiness | null | undefined;
  active?: CaseSection;
  onSection: (section: CaseSection, part?: string) => void;
}) {
  const hypotheses = useResource<{ items?: IntelHypothesis[] | null }>(intelligencePath(investigationId, "hypotheses"));
  const unknowns = useResource<{ items?: IntelUnknown[] | null }>(intelligencePath(investigationId, "unknowns"));
  const chains = useResource<{ stored?: StoredChain[] | null }>(intelligencePath(investigationId, "failure-chains"));
  // On the flagship story the step's own action (Accept, Sign) is the screen's one main button; the story bar's Next
  // link leads on, so this one steps back to secondary (W1 open item 3).
  const story = useContext(WorkspaceContext)?.story;
  const nextClass = story === "flagship" || story === "flagship-branch" ? "ac-secondary" : "ac-primary";
  const figures = cockpitFigures({
    hypotheses: listOf(hypotheses.data?.items),
    unknowns: listOf(unknowns.data?.items),
    chains: listOf(chains.data?.stored),
    readiness,
  });
  const read = hypotheses.state === "ready" ? (text: string) => text : () => "…";
  const next = steps.length ? nextCaseStep(steps) : null;
  const decided = steps.some((step) => step.key === "human_review" && step.status === "DONE");
  return (
    <div className="uw-cockpit">
      <ul className="uw-cockpit-strip" aria-label="The investigation in four figures">
        <Figure
          label="Evidence"
          value={read(
            `${figures.evidenceFor} for · ${figures.evidenceAgainst} against · ${figures.evidenceMissing} missing`,
          )}
          definition="For: records a person linked in support. Against: explanations with a record against them. Missing: open questions and unshown links of a failure chain."
          onOpen={() => onSection("Evidence", "glance")}
        />
        <Figure
          label="Possible causes"
          value={read(`${figures.causes}${figures.leading ? `, ${figures.leading} leading` : ""}`)}
          definition="Explanations still considered (not retired). Leading: judged strongly supported by a person; never a concluded root cause."
          onOpen={() => onSection("Possible causes", "causes")}
        />
        <Figure
          label="Blocking the decision"
          value={
            readiness
              ? figures.blocking.count
                ? plural(figures.blocking.count, "open check", "open checks")
                : "Nothing"
              : "…"
          }
          definition={
            figures.blocking.first
              ? `First: ${figures.blocking.first}. Readiness checks still open before a person can decide.`
              : "Readiness checks still open before a person can decide."
          }
          onOpen={() => (next ? onSection(next.section, next.part) : onSection("Brief", "board"))}
        />
        <li className="uw-cockpit-next">
          {!steps.length ? (
            <p className="ac-muted" role="status">
              Reading where this investigation stands…
            </p>
          ) : next ? (
            <>
              <button type="button" className={nextClass} onClick={() => onSection(next.section, next.part)}>
                Next: {next.label} <ChevronRight size={15} aria-hidden="true" />
              </button>
              <WhyAsked why={CASE_STEP_WHY[next.key]} />
            </>
          ) : (
            <>
              <button type="button" className={nextClass} onClick={() => onSection("Decision & action", "summary")}>
                {decided ? "See the decision and its follow-up" : "See the decision"}{" "}
                <ChevronRight size={15} aria-hidden="true" />
              </button>
              <small className="ac-muted">Every step is done: the decision is signed.</small>
            </>
          )}
        </li>
      </ul>
      <CockpitRail steps={steps} active={active} onSection={onSection} />
    </div>
  );
}

/** The 6-step rail: each step's name, its state and the question it answers; the one shown is marked. */
export function CockpitRail({
  steps,
  active,
  onSection,
}: {
  steps: CaseStep[];
  active?: CaseSection;
  onSection: (section: CaseSection, part?: string) => void;
}) {
  const progress = caseProgress(steps);
  return (
    <nav className="uw-case-progress uw-cockpit-rail" aria-label="Investigation steps">
      <ol>
        {progress.map((item, index) => (
          <li key={item.section} className={`state-${item.state.toLowerCase()}`}>
            <button
              type="button"
              aria-current={item.section === active ? "step" : undefined}
              onClick={() => onSection(item.section)}
            >
              <strong>
                <span className="uw-num">{index + 1}</span> {item.section}
              </strong>
              <small>
                {!steps.length
                  ? "…"
                  : item.state === "READ"
                    ? "Versions, changes, lots"
                    : item.state === "DONE"
                      ? "Done"
                      : `${item.done} of ${item.total} done`}
              </small>
            </button>
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** A step's heading: its number and the question it answers. */
export function StepHeading({ step }: { step: CaseSection }) {
  return <h2 className="uw-question">{STEP_QUESTION[step]}</h2>;
}

/**
 * A labelled fold whose content is drawn (and read from the server) only once opened: the tools a step holds below
 * its main content, each named, never an unlabelled tab list.
 */
export function Fold({
  id,
  summary,
  initiallyOpen = false,
  children,
}: {
  id?: string;
  summary: string;
  initiallyOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <details
      className="uw-more uw-case-part"
      id={id}
      open={open}
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>{summary}</summary>
      {open && children}
    </details>
  );
}
