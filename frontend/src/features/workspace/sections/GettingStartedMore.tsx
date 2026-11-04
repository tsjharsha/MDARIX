import { useEffect, useState } from "react";
import { ChevronRight, Compass, Settings2, ShieldCheck, Signpost, Upload, Users } from "lucide-react";
import { Panel, StatTile } from "../../admin/console/charts";
import { NEXT_STEPS_LINK } from "../../help/trialNextSteps";
import { formatDay } from "../../../app/dates";
import { BookDemo } from "./BookDemo";
import { EndTrialPanel } from "./EndTrial";
import { RemoveSamplePanel, RestartSamplePanel } from "./RemoveSample";
import { SampleDataPanel } from "./SampleData";
import { sampleFacts } from "../sampleStory";
import type { StoryChapter } from "../trialStory";
import type { TrialStatus } from "./GettingStarted";

/** Getting started's library of other workflows, opened by "Choose a focus" (its address: ?tab=Other+workflows). */
export const OTHER_WORKFLOWS = "Other workflows";
/** The collapsed section's anchor: links to the sample data or the trial's dates open it here. */
export const TRIAL_SETTINGS_ID = "trial-settings";

/**
 * "Explore at your own pace" (owner's specification, 5 Nov 2026; trimmed by the owner-approved duplication review,
 * 0.10.87): compact cards under the walkthrough, none of them a main button. The team, only for a persona whose tabs
 * do not hold Team (inviting is the trial owner's; anyone else sees who is on it); the library of other workflows;
 * and the next steps: the one-to-one demo and the way from trial to pilot. The guides, support and feedback are in
 * Help, on every page.
 */
export function ExploreCards({
  owner,
  teamTab,
  onTeam,
  onWorkflows,
  onNextSteps,
  chapters,
  onDemoBooked,
}: {
  owner: boolean;
  /** The persona's tab bar already holds Team. */
  teamTab: boolean;
  onTeam: () => void;
  onWorkflows: () => void;
  onNextSteps: () => void;
  chapters: readonly StoryChapter[];
  onDemoBooked?: () => void;
}) {
  return (
    <section className="uw-gs-explore" aria-labelledby="gs-explore-title">
      <h2 id="gs-explore-title">Explore at your own pace</h2>
      <div className={`uw-gs-cards${teamTab ? " is-two" : ""}`}>
        {!teamTab && (
          <article className="uw-gs-card">
            <Users size={20} aria-hidden="true" />
            <h3>Invite your team</h3>
            <p>
              {owner
                ? "Try review and approval with colleagues."
                : "See who is on your trial. The trial owner invites and manages colleagues."}
            </p>
            <button type="button" className="ac-secondary" onClick={onTeam}>
              {owner ? "Manage team" : "View team"} <ChevronRight size={15} aria-hidden="true" />
            </button>
          </article>
        )}
        <article className="uw-gs-card">
          <Compass size={20} aria-hidden="true" />
          <h3>Explore other workflows</h3>
          <p>Routine complaints, trends, CAPA and more.</p>
          <button type="button" className="ac-secondary" onClick={onWorkflows}>
            Choose a focus <ChevronRight size={15} aria-hidden="true" />
          </button>
        </article>
        <article className="uw-gs-card">
          <Signpost size={20} aria-hidden="true" />
          <h3>Plan your next steps</h3>
          <p>A one-to-one demo on your records, or how a pilot starts.</p>
          <div className="uw-gs-card-actions">
            <BookDemo chapters={chapters} onBooked={onDemoBooked} />
            <button type="button" className="ac-link" onClick={onNextSteps}>
              {NEXT_STEPS_LINK}
            </button>
          </div>
        </article>
      </div>
    </section>
  );
}

/**
 * "Sample data & trial settings": one collapsed section at the foot of Getting started, the only place on it for the
 * sample's explanation and counts, the trial's dates and limits, and the trial owner's restart, removal and early end
 * (each with its own confirmation, unchanged). Nothing in it runs by itself. `startOpen`: a link named it.
 */
export function TrialSettings({
  trial,
  startOpen,
  allowed,
  onOpen,
  onRestarted,
  onRemoved,
  onNextSteps,
}: {
  trial: TrialStatus | null;
  startOpen: boolean;
  allowed: (section: string) => boolean;
  onOpen: (opens: { section: string; tab?: string }) => void;
  onRestarted: (text: string) => void;
  onRemoved: (text: string) => void;
  onNextSteps: () => void;
}) {
  const [shown, setShown] = useState(startOpen);
  useEffect(() => {
    if (!startOpen) return;
    setShown(true);
    const timer = window.setTimeout(
      () => document.getElementById(TRIAL_SETTINGS_ID)?.scrollIntoView?.({ block: "start" }),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [startOpen]);
  const hasSample = (trial?.sample?.products ?? 0) > 0;
  return (
    <details
      id={TRIAL_SETTINGS_ID}
      className="uw-gs-settings uw-anchor"
      open={shown}
      onToggle={(event) => setShown(event.currentTarget.open)}
    >
      <summary>
        <Settings2 size={16} aria-hidden="true" /> Sample data &amp; trial settings
      </summary>
      {shown && (
        <div className="uw-gs-settings-body">
          {/* The counts first; the long explanation (seven pain points) folds below the controls (0.10.87). */}
          {hasSample ? (
            <Panel eyebrow="Sample data" title="What the sample holds">
              <ul className="uw-sample-facts" aria-label="What the sample holds">
                {sampleFacts(trial?.sample).map((fact) => (
                  <li key={fact}>{fact}</li>
                ))}
              </ul>
            </Panel>
          ) : (
            trial && (
              <Panel eyebrow="Sample data" title="The sample data is not in this trial">
                <p className="uw-trial-note">Every screen shows only your own records.</p>
              </Panel>
            )
          )}
          <Panel title="Your free trial" eyebrow="Dates and limits">
            <div className="uw-trial-stats">
              <StatTile
                label="Trial ends"
                value={trial?.expires_at ? formatDay(trial.expires_at) : null}
                detail={
                  trial?.data_deleted_at
                    ? `Data is deleted on ${formatDay(trial.data_deleted_at)} unless you continue`
                    : "Your data stays if you continue"
                }
                icon={<ShieldCheck size={18} />}
              />
              <StatTile
                label="Users"
                value={trial?.usage ? `${trial.usage.users} of ${trial.limits?.users}` : null}
                detail={trial?.is_owner ? "Invite or remove colleagues under Team" : "Your trial team"}
                icon={<Users size={18} />}
              />
              <StatTile
                label="Uploaded rows"
                value={
                  trial?.usage ? `${trial.usage.rows.toLocaleString()} of ${trial.limits?.rows.toLocaleString()}` : null
                }
                detail="One row in your file is one row; the sample data does not count"
                icon={<Upload size={18} />}
              />
            </div>
          </Panel>
          {hasSample && !trial?.is_owner && (
            <p className="ac-muted">Only the person who started the trial can restart or remove the sample data.</p>
          )}
          {hasSample && <RestartSamplePanel onRestarted={onRestarted} />}
          {hasSample && <RemoveSamplePanel onRemoved={onRemoved} />}
          <EndTrialPanel onNextSteps={onNextSteps} />
          {hasSample && (
            <details className="uw-more uw-gs-about">
              <summary>About the sample data</summary>
              <SampleDataPanel counts={trial?.sample} allowed={allowed} onOpen={onOpen} facts={false} />
            </details>
          )}
        </div>
      )}
    </details>
  );
}
