import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Circle,
  MessageSquare,
  ShieldCheck,
  Signpost,
  Star,
  Upload,
  Users,
} from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Tabs, errorText, send, useResource } from "../../customer-admin/shared";
import { sectionAllowed, useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { ImportPanel, templateSummary, type ImportTemplate } from "./ImportData";
import { formatDay } from "../../../app/dates";
import { countOf } from "./common";
import { QualityLoop } from "./QualityLoop";
import { BookDemo, DEMO_REQUEST_PATH, type TrialDemoRequest } from "./BookDemo";
import { TrialJourney } from "./TrialJourney";
import { EndTrialPanel } from "./EndTrial";
import { CitedFor } from "./CitedFor";
import { RemoveSamplePanel } from "./RemoveSample";
import { TeamPanel } from "./TrialTeam";
import { journeyProgress, type JourneyKey } from "../../help/trialGuide";
import { NEXT_STEPS_LINK, NEXT_STEPS_SECTION, NEXT_STEPS_SUMMARY } from "../../help/trialNextSteps";
import { SampleDataPanel } from "./SampleData";
import { InsightsPanel } from "./TrialInsights";
import type { Insights } from "../trialInsights";
import { featureSetOf, importTemplatesFor } from "../../../app/featureSet";
import type { SampleCounts } from "../sampleStory";
import {
  CHAPTER_ACTION,
  TRIAL_STORY_PATH,
  chapterStatus,
  chapterTone,
  loopFromStory,
  storyHeadline,
  type StoryChapter,
  type TrialStory,
} from "../trialStory";

export type TrialStatus = {
  is_trial: boolean;
  is_owner?: boolean;
  expires_at?: string;
  data_deleted_at?: string;
  days_left?: number;
  limits?: { users: number; rows: number; file_bytes: number };
  usage?: { users: number; rows: number };
  sample?: SampleCounts;
  own_data?: { products: number; lots: number; complaints: number };
  templates?: ImportTemplate[];
};
const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

/** The tabs below the story: everything that is not the story itself, one click away. */
export const TRIAL_TABS = ["Your data", "Team", "About the sample data", "Your trial"] as const;
export type TrialTab = (typeof TRIAL_TABS)[number];
/** The tab below the story that a link names, if it names one. */
export const trialTabFor = (name?: string): TrialTab | undefined => TRIAL_TABS.find((tab) => tab === name);

/**
 * Getting started: the free trial as a story. The quality loop MDARIX closes, chapter by chapter, each with what the
 * trial's records show (the sample data first, its own export later), why it matters to inspectors in 2026 and where
 * to try it. A chapter is done when the organization acted in it (a record it created in MDARIX), so the progress here
 * is the progress MDARIX sees (/api/v1/trial/story).
 */
export function GettingStartedSection({ focus }: { focus?: string } = {}) {
  const { open, work, session, notify } = useWorkspace();
  const status = useResource<TrialStatus>("/api/v1/trial/status");
  const insights = useResource<Insights>("/api/v1/trial/insights");
  const loadedStory = useResource<TrialStory>(TRIAL_STORY_PATH);
  // The last story read stays on screen while a reload is under way or has failed; with none at all, the headline
  // says the story could not be loaded and offers to try again (never "Reading..." for ever).
  const lastStory = useRef<TrialStory | null>(null);
  if (loadedStory.data) lastStory.current = loadedStory.data;
  const storyData = loadedStory.data ?? lastStory.current;
  const storyFailed = !storyData && (loadedStory.state === "error" || loadedStory.state === "forbidden");
  const story =
    storyData && loadedStory.state !== "ready"
      ? { ...loadedStory, state: "ready" as const, data: storyData }
      : loadedStory;
  const trial = status.data;
  const allowed = (section: string) =>
    section === "Getting started" ||
    sectionAllowed(section as WorkspaceSection, session?.allowed_menu, session?.business_permissions);
  const focusTab = trialTabFor(focus);
  const [tab, setTab] = useState<TrialTab>(focusTab ?? "Your data");
  // A tab below the story, opened and brought into view.
  const showTab = (name: TrialTab) => {
    setTab(name);
    window.setTimeout(() => scrollTo("trial-tabs"), 0);
  };
  // Opened on one of those tabs (Help, "Getting started and import templates"): brought into view once the story
  // above it has loaded, so the scroll lands on the tab and not where it was while the page was still filling in.
  const focused = useRef(false);
  const loaded = status.state !== "loading" && story.state !== "loading";
  useEffect(() => {
    if (!focusTab || !loaded || focused.current) return;
    focused.current = true;
    scrollTo("trial-tabs");
  }, [focusTab, loaded]);
  const go = (chapter: Pick<StoryChapter, "code" | "opens"> & Partial<Pick<StoryChapter, "case">>) => {
    if (chapter.code === "YOUR_DATA" || chapter.opens.section === "Getting started") return showTab("Your data");
    if (!allowed(chapter.opens.section)) return;
    // A chapter about the guided investigation opens that case, whatever the context bar holds.
    const known = chapter.case ?? chapters.find((item) => item.code === chapter.code)?.case;
    if (known) work.setInvestigationId(known.id, known.product_id);
    // Without its case (closed, or the sample data removed), a case chapter opens the list of investigations.
    const inCase = known || chapter.opens.section !== "Investigations";
    open(chapter.opens.section as WorkspaceSection, inCase ? (chapter.opens.tab ?? undefined) : undefined);
  };
  const chapters = story.data?.chapters ?? [];
  const acted = story.data?.acted ?? 0;
  const total = story.data?.total ?? 9;
  const headline = storyHeadline(story.data, storyFailed);
  const next = chapters.find((chapter) => chapter.code === story.data?.next) ?? null;
  const talk = () => window.open("/contact", "_blank", "noopener");
  const hasSample = (trial?.sample?.products ?? 0) > 0;
  // The trial journey (the free trial user guide's seven steps), ticked from the trial's own records.
  const feedback = useResource<{ submissions?: unknown[] }>("/api/v1/trial/feedback");
  const demo = useResource<{ request: TrialDemoRequest | null }>(DEMO_REQUEST_PATH);
  const own = trial?.own_data;
  const journey = journeyProgress({
    users: trial?.usage?.users,
    userLimit: trial?.limits?.users,
    chaptersTried: story.data?.acted,
    ownComplaints: own?.complaints,
    ownRecords: own ? own.products + own.lots : 0,
    feedbackSent: (feedback.data?.submissions?.length ?? 0) > 0,
    demoRequested: !!demo.data?.request,
  });
  const goJourney = (key: JourneyKey) => {
    if (key === "team") return showTab("Team");
    if (key === "sample") return scrollTo("trial-story");
    if (key === "own-data") return showTab("Your data");
    if (key === "feedback") return open("Share feedback");
    if (key === "demo") return scrollTo("trial-demo");
  };
  const feedbackSent = (feedback.data?.submissions?.length ?? 0) > 0;
  // Rated during this visit: the rating stays on screen with its thank-you and "tell us more", though the feedback
  // reloaded after it now holds a submission.
  const [ratedNow, setRatedNow] = useState(false);
  const tabs = TRIAL_TABS.filter((item) => item !== "About the sample data" || hasSample);

  if (status.state === "ready" && trial && !trial.is_trial)
    return <Empty title="Not a trial workspace" detail="Getting started is shown during a free trial." />;

  return (
    <div className="ac-overview uw-trial">
      <QualityLoop
        stations={loopFromStory(story.data)}
        eyebrow={
          trial?.days_left !== undefined
            ? `Your free trial · ${countOf(trial.days_left, "day")} left`
            : "Your free trial"
        }
        title={headline.title}
        detail={headline.detail}
        doneLabel="tried"
        focusKey={story.data?.next}
        onOpen={(station) => station.opens && go({ code: station.key, opens: station.opens as StoryChapter["opens"] })}
      >
        {next && (
          <button type="button" className="ac-primary" onClick={() => go(next)} disabled={!allowed(next.opens.section)}>
            {CHAPTER_ACTION[next.code] ?? "Open"} <ChevronRight size={15} aria-hidden="true" />
          </button>
        )}
        {storyFailed && (
          <>
            <button type="button" className="ac-primary" onClick={story.reload}>
              Try again
            </button>
            {allowed("Investigations") && (
              <button type="button" className="ac-secondary" onClick={() => open("Investigations")}>
                Go to Investigations <ChevronRight size={15} aria-hidden="true" />
              </button>
            )}
          </>
        )}
      </QualityLoop>

      <CitedFor onSaved={story.reload} />

      <TrialJourney steps={journey} source={story} onGo={goJourney} />

      <div id="trial-story" className="uw-anchor" />
      <Panel title="Your story, chapter by chapter" eyebrow={`${acted} of ${total} tried`} source={story}>
        <p className="uw-trial-lede">
          Each chapter is one pain FDA and notified bodies cite in 2026, shown on the sample records first and on your
          own export once you upload it. It counts as tried when you act in it: decide, record, run or sign.
          {hasSample && (
            <>
              {" "}
              <button type="button" className="ac-link" onClick={() => showTab("About the sample data")}>
                What is the sample data?
              </button>
            </>
          )}
        </p>
        <ol className="uw-trial-steps uw-story-steps">
          {chapters.map((chapter) => (
            <ChapterRow
              key={chapter.code}
              chapter={chapter}
              isNext={chapter.code === story.data?.next}
              allowed={allowed(chapter.opens.section)}
              templates={
                chapter.code === "YOUR_DATA"
                  ? importTemplatesFor(trial?.templates ?? [], featureSetOf(session?.feature_set)).core
                  : undefined
              }
              onOpen={() => go(chapter)}
            />
          ))}
        </ol>
        {quickRatingShown({ acted, feedbackLoaded: feedback.state === "ready", feedbackSent, ratedNow }) && (
          <QuickRating
            onSent={() => {
              setRatedNow(true);
              feedback.reload();
            }}
            onMore={() => open("Share feedback")}
          />
        )}
        <div id="trial-demo" className="uw-story-partner uw-anchor">
          <div>
            <strong>See it on your own records, one to one</strong>
            <p>
              The MDARIX team walks through what your trial found and how a pilot on your live QMS, PLM and ERP data
              would run, with onboarding support and a design-partner price.
            </p>
          </div>
          <div className="uw-story-partner-actions">
            <BookDemo chapters={chapters} variant="primary" onBooked={demo.reload} />
            <button type="button" className="ac-link" onClick={talk}>
              <MessageSquare size={15} aria-hidden="true" /> Other questions
            </button>
          </div>
        </div>
        <div id="trial-next-steps" className="uw-story-partner uw-anchor">
          <div>
            <strong>{NEXT_STEPS_LINK}</strong>
            <p>{NEXT_STEPS_SUMMARY}</p>
          </div>
          <div className="uw-story-partner-actions">
            <button type="button" className="ac-secondary" onClick={() => open("Next steps")}>
              <Signpost size={15} aria-hidden="true" /> Open {NEXT_STEPS_SECTION}
            </button>
          </div>
        </div>
      </Panel>

      <div id="trial-tabs" className="uw-anchor uw-trial-tabs">
        <Tabs tabs={tabs} active={tabs.includes(tab) ? tab : tabs[0]} onChange={setTab} label="Your trial">
          {tab === "Your data" && (
            <>
              {hasSample && (own?.complaints ?? 0) > 0 && trial?.is_owner && (
                <p className="uw-cited-line">
                  Your own data is in. Remove the sample so every screen shows only your records.{" "}
                  <button type="button" className="ac-link" onClick={() => setTab("About the sample data")}>
                    Remove the sample data
                  </button>
                </p>
              )}
              <ImportPanel
                id="trial-import"
                complaintsAlone
                templates={trial?.templates ?? []}
                basePath="/api/v1/trial/imports"
                fileLimitBytes={trial?.limits?.file_bytes}
                onImported={() => {
                  status.reload();
                  insights.reload();
                  story.reload();
                  work.refreshProducts();
                }}
              />
              <InsightsPanel insights={insights.data} source={insights} />
            </>
          )}
          {tab === "Team" && <TeamPanel onChanged={status.reload} />}
          {tab === "About the sample data" && hasSample && (
            <SampleDataPanel
              counts={trial?.sample}
              allowed={allowed}
              onOpen={(opens) => {
                if (allowed(opens.section)) open(opens.section as WorkspaceSection, opens.tab);
              }}
            />
          )}
          {tab === "About the sample data" && hasSample && (
            <RemoveSamplePanel
              onRemoved={(text) => {
                notify(text);
                setTab("Your data");
                status.reload();
                story.reload();
                insights.reload();
                work.refreshProducts();
              }}
            />
          )}
          {tab === "Your trial" && (
            <>
              <Panel title="Your free trial" eyebrow="Dates and limits" source={status}>
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
                      trial?.usage
                        ? `${trial.usage.rows.toLocaleString()} of ${trial.limits?.rows.toLocaleString()}`
                        : null
                    }
                    detail="One row in your file is one row; the sample data does not count"
                    icon={<Upload size={18} />}
                  />
                </div>
              </Panel>
              <EndTrialPanel onNextSteps={() => open("Next steps")} />
            </>
          )}
        </Tabs>
      </div>
    </div>
  );
}

/**
 * Whether the one-click rating shows: after three chapters tried, until feedback is sent; and, once rated during this
 * visit, still, so its thank-you and "tell us more" stay in view (exported for its test).
 */
export function quickRatingShown(state: {
  acted: number;
  feedbackLoaded: boolean;
  feedbackSent: boolean;
  ratedNow: boolean;
}): boolean {
  return state.ratedNow || (state.acted >= 3 && state.feedbackLoaded && !state.feedbackSent);
}

/** One click on how useful MDARIX is so far, sent privately; the full feedback stays one more click away. */
export function QuickRating({ onSent, onMore }: { onSent: () => void; onMore: () => void }) {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rate = async (score: number) => {
    setBusy(true);
    setError("");
    try {
      await send("/api/v1/trial/feedback", "POST", { rating_overall: score, publish_consent: "PRIVATE" });
      setSent(true);
      onSent();
    } catch (failure) {
      setError(errorText(failure, "Your rating was not sent. Please try again."));
    } finally {
      setBusy(false);
    }
  };
  if (sent)
    return (
      <p className="uw-quick-rating is-sent" role="status">
        <CheckCircle2 size={16} aria-hidden="true" /> Thank you.{" "}
        <button type="button" className="ac-link" onClick={onMore}>
          Tell us more in two minutes
        </button>
      </p>
    );
  return (
    <div className="uw-quick-rating" role="group" aria-label="How useful is MDARIX so far?">
      <span>How useful is MDARIX so far?</span>
      <span className="uw-quick-stars">
        {[1, 2, 3, 4, 5].map((score) => (
          <button
            key={score}
            type="button"
            disabled={busy}
            onClick={() => void rate(score)}
            aria-label={`${score} of 5`}
            title={`${score} of 5`}
          >
            <Star size={18} aria-hidden="true" />
          </button>
        ))}
      </span>
      <small className="ac-muted">Private to the MDARIX team.</small>
      {error && (
        <p className="uw-flag-critical" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/** One chapter: what it does, what your records show, why it matters, and where to try it (exported for its test). */
export function ChapterRow({
  chapter,
  isNext,
  allowed,
  templates,
  onOpen,
}: {
  chapter: StoryChapter;
  isNext: boolean;
  allowed: boolean;
  templates?: ImportTemplate[];
  onOpen: () => void;
}) {
  const done = chapter.acted.done;
  const finding = chapter.finding.text;
  return (
    <li className={`uw-story-step${done ? " is-done" : ""}${isNext ? " is-next" : ""}`}>
      <span className="uw-trial-step-mark" aria-hidden="true">
        {done ? <CheckCircle2 size={20} /> : <Circle size={20} />}
      </span>
      <div className="uw-story-body">
        <strong>
          {chapter.number}. {chapter.title}
          {chapter.cited && <span className="uw-cited-badge">You were cited for this</span>}
        </strong>
        {finding && (
          <p className="uw-story-finding">
            {done ? (
              <ToneBadge tone={chapterTone(chapter)} label={chapterStatus(chapter)} />
            ) : (
              // Not tried yet is no failure: an empty circle and "To do", whatever the finding's tone.
              <span className="ac-badge tone-neutral">
                <Circle size={14} aria-hidden="true" />
                {chapterStatus(chapter)}
              </span>
            )}{" "}
            {finding}
          </p>
        )}
        <details className="uw-story-more">
          <summary>What MDARIX does here, and why it matters</summary>
          <p>{chapter.promise}</p>
          {templates?.length ? (
            <p className="uw-story-templates">Data: {templateSummary(templates)}, under Your data below.</p>
          ) : null}
          <p className="uw-story-pain">
            <b>Why it matters:</b> {chapter.pain}
          </p>
        </details>
      </div>
      <button
        type="button"
        className={done ? "ac-secondary" : "ac-primary"}
        onClick={onOpen}
        disabled={!allowed}
        title={allowed ? undefined : "Your role does not include this screen"}
      >
        {done ? "Open again" : (CHAPTER_ACTION[chapter.code] ?? "Open")}
      </button>
      <span className="ca-sr-only">{done ? "Tried" : "Not tried yet"}</span>
    </li>
  );
}
