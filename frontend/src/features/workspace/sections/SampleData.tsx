import type { CSSProperties } from "react";
import {
  AlarmClock,
  BadgeCheck,
  ChevronRight,
  EyeOff,
  FileWarning,
  FlaskConical,
  Microscope,
  ShieldAlert,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { SAMPLE_MADE, SAMPLE_PAINS, sampleFacts, type SampleCounts, type SamplePain } from "../sampleStory";
import { BasisNote } from "../../shared/Basis";

/** The panel's anchor, for the links that scroll to it (Getting started). */
export const SAMPLE_DATA_ID = "trial-sample-data";

export const scrollToSampleData = () =>
  document.getElementById(SAMPLE_DATA_ID)?.scrollIntoView({ behavior: "smooth", block: "start" });

const ICONS: Record<string, LucideIcon> = {
  hidden: EyeOff,
  clocks: AlarmClock,
  "harm-closed": FileWarning,
  trend: TrendingUp,
  investigate: Microscope,
  capa: BadgeCheck,
  risk: ShieldAlert,
};

/**
 * The sample data, explained point by point: what the trial's sample holds, the pain point each part re-creates with the
 * requirement behind it and the screen that shows it, and how the sample was made. Shown in Getting started while the workspace
 * holds the sample (its products are counted by the trial's status).
 */
export function SampleDataPanel({
  counts,
  allowed,
  onOpen,
  facts: showFacts = true,
}: {
  counts: SampleCounts | null | undefined;
  /** The facts list; left out where the counts are already shown above (Getting started's settings, 0.10.87). */
  facts?: boolean;
  allowed: (section: string) => boolean;
  onOpen: (opens: SamplePain["opens"]) => void;
}) {
  if (counts && !counts.products) return null;
  const facts = sampleFacts(counts);
  return (
    <div id={SAMPLE_DATA_ID} className="uw-sample">
      <Panel eyebrow="Sample data" title="What your sample data is, and why it looks like this">
        <div className="uw-sample-intro">
          <span className="uw-sample-badge" aria-hidden="true">
            <FlaskConical size={22} />
          </span>
          <p className="uw-trial-lede">
            Your trial opened with the records of a fictional manufacturer of three devices, so MDARIX has something
            real to show from the first minute. Each part was built from a pain point inspectors keep finding. The same
            checks run on your own export once you upload it.
          </p>
        </div>
        {showFacts && facts.length > 0 && (
          <ul className="uw-sample-facts" aria-label="What the sample holds">
            {facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        )}
        <ol className="uw-sample-list">
          {SAMPLE_PAINS.map((pain, index) => {
            const Icon = ICONS[pain.key] ?? FlaskConical;
            const canOpen = allowed(pain.opens.section);
            return (
              <li key={pain.key} className="uw-sample-point" style={{ "--i": index } as CSSProperties}>
                <span className="uw-sample-number" aria-hidden="true">
                  {index + 1}
                </span>
                <div className="uw-sample-body">
                  <h3>
                    <Icon size={17} aria-hidden="true" /> {pain.title}
                  </h3>
                  <p className="uw-sample-label">In the sample</p>
                  <ul>
                    {pain.inSample.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                  <p className="uw-sample-why">
                    <b>Why it matters:</b> {pain.requirement} <span className="uw-sample-ref">{pain.reference}</span>
                  </p>
                </div>
                <button
                  type="button"
                  className="ac-secondary uw-sample-open"
                  onClick={() => onOpen(pain.opens)}
                  disabled={!canOpen}
                  title={canOpen ? undefined : "Your role does not include this screen"}
                >
                  {pain.action} <ChevronRight size={14} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ol>
        <BasisNote />
        <details className="uw-sample-made">
          <summary>How the sample data was made</summary>
          <ul>
            {SAMPLE_MADE.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
        <p className="ac-muted uw-sample-note">
          Described as it was loaded at the start of your trial. As you work through the chapters, the screens show what
          you have done since.
        </p>
      </Panel>
    </div>
  );
}
