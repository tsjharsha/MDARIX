import type { CSSProperties } from "react";
import {
  ClipboardCheck,
  DraftingCompass,
  Factory,
  FlaskConical,
  Lightbulb,
  Radar,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import { Reveal } from "./motion";

// Medical device design and development, phase 0 to 6, with the design-control records each phase leaves. The same
// phases as the picture this replaces; the records are the ones the section's copy names (user needs, design inputs
// and outputs, verification, validation, the risk file).
const PHASES: { title: string; icon: LucideIcon; records: string[] }[] = [
  { title: "Concept and ideation", icon: Lightbulb, records: ["Intended use", "First hazards"] },
  { title: "User needs and feasibility", icon: UsersRound, records: ["User needs", "Development plan"] },
  { title: "Design inputs and prototyping", icon: FlaskConical, records: ["Design inputs", "Risk analysis"] },
  {
    title: "Detailed design and design controls",
    icon: DraftingCompass,
    records: ["Design outputs", "Design reviews"],
  },
  { title: "Verification and validation", icon: ClipboardCheck, records: ["Verification", "Validation"] },
  {
    title: "Manufacturing transfer and regulatory submission",
    icon: Factory,
    records: ["Design transfer", "Submission"],
  },
  { title: "Post-market surveillance and feedback loops", icon: Radar, records: ["Complaints", "CAPA"] },
];

/** The phases as a journey that draws itself: each phase lights up in turn with its records, the risk file fills
 * beneath them all, and a feedback arc runs from post-market back to the first phases, where an investigation traces
 * a field problem. Everything is shown at once, without motion, for people who ask for reduced motion. */
export function DesignPhases() {
  const last = PHASES.length - 1;
  return (
    <Reveal className="ms-dp">
      <div className="ms-dp-body">
        <svg className="ms-dp-arc" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true">
          <path
            className="ms-dp-arc-base"
            d="M 92.86 40 C 92.86 0, 7.14 0, 7.14 40"
            vectorEffect="non-scaling-stroke"
          />
          <path
            className="ms-dp-arc-flow"
            d="M 92.86 40 C 92.86 0, 7.14 0, 7.14 40"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        <span className="ms-dp-arc-head" aria-hidden="true" />
        <p className="ms-dp-arc-label">
          <strong>Feedback loop.</strong> A field problem is traced back through these records.
        </p>
        <span className="ms-dp-track" aria-hidden="true">
          <span className="ms-dp-track-fill" />
          <span className="ms-dp-sheen" />
        </span>
        <ol className="ms-dp-phases" aria-label="Design and development phases 0 to 6">
          {PHASES.map((phase, index) => {
            const Icon = phase.icon;
            return (
              <li
                key={phase.title}
                className={index === last ? "is-field" : undefined}
                style={{ "--p": index } as CSSProperties}
              >
                <span className="ms-dp-medal" aria-hidden="true">
                  <Icon size={26} />
                </span>
                <span className="ms-dp-num">Phase {index}</span>
                <strong>{phase.title}</strong>
                <ul aria-label={`Records from phase ${index}`}>
                  {phase.records.map((record) => (
                    <li key={record}>{record}</li>
                  ))}
                </ul>
                {index === last && <span className="ms-dp-flag">MDARIX starts here</span>}
              </li>
            );
          })}
        </ol>
      </div>
      <div className="ms-dp-risk">
        <span className="ms-dp-risk-fill" aria-hidden="true" />
        <strong>Risk file</strong>
        <span>Opened at the first hazards and updated in every phase, through to what the field reports.</span>
      </div>
    </Reveal>
  );
}
