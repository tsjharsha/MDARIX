import { useEffect, useRef, useState, type RefObject } from "react";
import {
  CheckCircle2,
  ChevronRight,
  Circle,
  MessageSquare,
  ShieldCheck,
  Signpost,
  Star,
  PhoneCall,
  ClipboardList,
  Telescope,
  Upload,
  Users,
} from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Tabs, errorText, send, useResource, whenNoLongerPending } from "../../customer-admin/shared";
import { sectionAllowed, useWorkspace, type WorkspaceSection, useReportedTab } from "../workspaceContext";
import { placeOf } from "../../../app/linkTable";
import { templateSummary, type ImportResult, type ImportTemplate } from "./ImportData";
import { formatDay } from "../../../app/dates";
import { countOf } from "./common";
import { QualityLoop } from "./QualityLoop";
import { BookDemo, DEMO_REQUEST_PATH, type TrialDemoRequest } from "./BookDemo";
import { TrialJourney } from "./TrialJourney";
import { EndTrialPanel } from "./EndTrial";
import { CitedFor } from "./CitedFor";
import { RemoveSamplePanel, RestartSamplePanel } from "./RemoveSample";
import { Entrance } from "./Entrance";
import { OneStory } from "./OneStory";
import { ExploreCards, OTHER_WORKFLOWS, TrialSettings } from "./GettingStartedMore";
import { TeamPanel } from "./TrialTeam";
import { BESIDE_YOUR_QMS } from "../../help/besideYourQms";
import { DISCUSS_PILOT } from "../../shared/HelpMenu";
import { STORY_CHAPTERS, journeyProgress, type JourneyKey } from "../../help/trialGuide";
import { NEXT_STEPS_LINK, NEXT_STEPS_SECTION, NEXT_STEPS_SUMMARY } from "../../help/trialNextSteps";
import { LOOK_AHEAD_SECTION, LOOK_AHEAD_SUMMARY, LOOK_AHEAD_TABS } from "../partyPreview";
import { SampleDataPanel } from "./SampleData";
import { YourData } from "./YourData";
import type { Insights } from "../trialInsights";
import { IMPORTED_SOURCE } from "../complaintList";
import { featureSetOf, importTemplatesFor } from "../../../app/featureSet";
import type { SampleCounts } from "../sampleStory";
import { DETECTION_STATUS_PATH } from "../signals";
import type { TrialPerson } from "./ColleagueWelcome";
import {
  CHAPTER_ACTION,
  TRIAL_STORY_PATH,
  chapterStatus,
  chapterTone,
  findingSignals,
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
  /** The signed-in person: when they first signed in and who invited them (UX-26). */
  me?: TrialPerson | null;
};
const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

/** How many complaints of its own an import added (not the products, versions and lots it named, nor updates). */
export const newComplaints = (entity: string, result: ImportResult) =>
  entity === "complaints"
    ? (result.created ?? 0) - Object.values(result.also_created ?? {}).reduce((sum, count) => sum + count, 0)
    : 0;

/** Whether the insights are read from the organization's own imported complaints (not the sample's). */
export const ownInsights = (insights: Pick<Insights, "source_system"> | null | undefined) =>
  insights?.source_system === IMPORTED_SOURCE;

/** The tabs below the story: everything that is not the story itself, one click away. */
export const TRIAL_TABS = ["Your data", "Team", "About the sample data", "Your trial"] as const;
export type TrialTab = (typeof TRIAL_TABS)[number];
/** The tab below the story that a link names, if it names one. */
export const trialTabFor = (name?: string): TrialTab | undefined =>
  TRIAL_TABS.find((tab) => tab === (name ?? "").split("?")[0]);

/**
 * Getting started: the free trial as a story. The quality loop MDARIX closes, chapter by chapter, each with what the
 * trial's records show (the sample data first, its own export later), why it matters to inspectors in 2026 and where
 * to try it. A chapter is done when the organization acted in it (a record it created in MDARIX), so the progress here
 * is the progress MDARIX sees (/api/v1/trial/story).
 */
export function GettingStartedSection({
  focus,
  heading,
}: { focus?: string; heading?: RefObject<HTMLHeadingElement | null> } = {}) {
  const { open, work, session, notify, navigation, refreshTrial, personaTabs } = useWorkspace();
  const status = useResource<TrialStatus>("/api/v1/trial/status");
  // Right after an import its signals are still being found: the story is read again until they are. A reload that
  // fails for a moment (the server busy with the import's follow-up work) is asked again, so the page never stays on
  // the story from before the import (``retry``).
  const loadedStory = useResource<TrialStory>(TRIAL_STORY_PATH, {
    refreshWhile: (data) => !!data.signals_pending,
    statusPath: DETECTION_STATUS_PATH,
    retry: true,
  });
  // After an import whose signals are being found (they are in within seconds), the story is read again once the small
  // detection status says they are in, not at once: that read could only say "Finding signals", and right after a
  // large import it took seconds and slowed the finding itself (0.10.44). Until that read answers, the trend chapter
  // says the signals are being found ("waiting" for them, then "reading" the story).
  const [afterImport, setAfterImport] = useState<"waiting" | "reading" | null>(null);
  const awaitingSignals = afterImport !== null;
  const reloadStory = loadedStory.reload;
  // The last story read stays on screen while a reload is under way or has failed; with none at all, the headline
  // says the story could not be loaded and offers to try again (never "Reading..." for ever).
  const lastStory = useRef<TrialStory | null>(null);
  if (loadedStory.data) lastStory.current = loadedStory.data;
  const readFrom = useRef<TrialStory | null>(null);
  useEffect(() => {
    if (afterImport !== "waiting") return;
    return whenNoLongerPending(DETECTION_STATUS_PATH, () => {
      readFrom.current = lastStory.current;
      setAfterImport("reading");
      reloadStory();
    });
  }, [afterImport, reloadStory]);
  // The story read once the signals are in has answered (or failed for good): it is shown as it is.
  useEffect(() => {
    if (afterImport !== "reading") return;
    if (loadedStory.data !== readFrom.current || loadedStory.state === "error" || loadedStory.state === "forbidden")
      setAfterImport(null);
  }, [afterImport, loadedStory.data, loadedStory.state]);
  const lastData = loadedStory.data ?? lastStory.current;
  const storyData = lastData && awaitingSignals ? findingSignals(lastData) : lastData;
  const storyFailed = !storyData && (loadedStory.state === "error" || loadedStory.state === "forbidden");
  const story =
    storyData && (loadedStory.state !== "ready" || awaitingSignals)
      ? { ...loadedStory, state: "ready" as const, data: storyData }
      : loadedStory;
  const trial = status.data;
  const allowed = (section: string) =>
    section === "Getting started" ||
    sectionAllowed(
      section as WorkspaceSection,
      session?.allowed_menu,
      session?.business_permissions,
      session?.sample_only,
    );
  const focusTab = trialTabFor(focus);
  // On the new navigation Your data is its own page (0.10.80): defaulting to it wrote ?tab=Your+data into Getting
  // started's address, and a refresh then opened the Import page instead (0.10.82). There no tab is chosen until the
  // person picks one, so the address stays /app/getting-started (the first tab shows meanwhile).
  // On the new navigation the tab is the address's own name ("Other workflows" opens the library), so it stays there.
  const [tab, setTab] = useReportedTab<TrialTab>(
    focusTab ?? (navigation === "new" ? ((focus ?? "").split("?")[0] as TrialTab) : "Your data"),
  );
  // A tab below the story, opened and brought into view.
  const showTab = (name: TrialTab) => {
    setTab(name);
    window.setTimeout(() => scrollTo("trial-tabs"), 0);
  };
  // On the new navigation the upload is its own page, Import your data (0.10.80); a tab here on the classic one.
  const ownImport = () => (navigation === "new" ? open("Import your data") : showTab("Your data"));
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
    if (chapter.code === "YOUR_DATA" || chapter.opens.section === "Getting started") return ownImport();
    if (!allowed(chapter.opens.section)) return;
    // A chapter about the guided investigation opens that case, whatever the context bar holds.
    const known = chapter.case ?? chapters.find((item) => item.code === chapter.code)?.case;
    if (known) work.setInvestigationId(known.id, known.product_id);
    // Without its case (closed, or the sample data removed), a case chapter opens the list of investigations.
    const inCase = known || chapter.opens.section !== "Investigations";
    const place = placeOf(chapter.opens);
    open(place.section as WorkspaceSection, inCase ? place.tab : undefined);
  };
  const chapters = story.data?.chapters ?? [];
  const acted = story.data?.acted ?? 0;
  // While the story loads, the same count it will show (0.10.62 said 9 of a 10-chapter story).
  const total = story.data?.total ?? STORY_CHAPTERS;
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
    if (key === "team") return navigation === "new" ? open("Team") : showTab("Team");
    if (key === "sample") return scrollTo("trial-story");
    if (key === "own-data") return ownImport();
    if (key === "feedback") return open("Share feedback");
    if (key === "demo") return scrollTo("trial-demo");
  };
  const feedbackSent = (feedback.data?.submissions?.length ?? 0) > 0;
  // Rated during this visit: the rating stays on screen with its thank-you and "tell us more", though the feedback
  // reloaded after it now holds a submission.
  const [ratedNow, setRatedNow] = useState(false);
  // On the new navigation the team is its own screen, Team (0.10.68), and the upload its own page (0.10.80).
  const tabs = TRIAL_TABS.filter(
    (item) =>
      (item !== "About the sample data" || hasSample) &&
      ((item !== "Team" && item !== "Your data") || navigation !== "new"),
  );
  // The tab shown: the one chosen, else the first there is (on the new navigation a link may still name Your data).
  const shownTab = tabs.includes(tab) ? tab : tabs[0];

  if (status.state === "ready" && trial && !trial.is_trial)
    return <Empty title="Not a trial workspace" detail="Getting started is shown during a free trial." />;

  const restarted = (text: string) => {
    notify(text);
    status.reload();
    story.reload();
    work.refreshProducts();
    refreshTrial?.();
  };
  const chapterCount =
    navigation === "new"
      ? `${chapters.filter((chapter) => chapter.code !== "YOUR_DATA" && chapter.acted.done).length} of ${chapters.filter((chapter) => chapter.code !== "YOUR_DATA").length || total - 1} tried${session?.sample_only ? "" : " · your own data is optional"}`
      : `${acted} of ${total} tried`;
  const chapterList = (
    <ol className="uw-trial-steps uw-story-steps">
      {chapters
        .filter((chapter) => !(session?.sample_only && chapter.code === "YOUR_DATA"))
        .map((chapter) => (
          <ChapterRow
            key={chapter.code}
            chapter={chapter}
            isNext={chapter.code === story.data?.next}
            allowed={allowed(chapter.opens.section)}
            importHere={navigation !== "new"}
            templates={
              chapter.code === "YOUR_DATA"
                ? importTemplatesFor(trial?.templates ?? [], featureSetOf(session?.feature_set)).core
                : undefined
            }
            onOpen={() => go(chapter)}
          />
        ))}
    </ol>
  );
  const body = (
    <div className="ac-overview uw-trial">
      <QualityLoop
        stations={loopFromStory(story.data).filter(
          // A sample-only trial has no own data to try (0.10.71).
          (station) => !(session?.sample_only && station.key === "YOUR_DATA"),
        )}
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

      <TrialJourney
        steps={session?.sample_only ? journey.filter((step) => step.key !== "own-data") : journey}
        source={story}
        onGo={goJourney}
      />

      <div id="trial-story" className="uw-anchor" />
      <Panel title="Your story, chapter by chapter" eyebrow={chapterCount} source={story}>
        <p className="uw-trial-lede">
          {BESIDE_YOUR_QMS} Each chapter is one pain FDA and notified bodies cite in 2026, shown on the sample records
          first and on your own export once you upload it. It counts as tried when you act in it: decide, record, run or
          sign.
          {hasSample && (
            <>
              {" "}
              <button type="button" className="ac-link" onClick={() => showTab("About the sample data")}>
                What is the sample data?
              </button>
            </>
          )}
        </p>
        {allowed("Complaints") && (
          <div id="trial-first-contact" className="uw-story-partner uw-anchor">
            <div>
              <strong>
                <PhoneCall size={16} aria-hidden="true" /> Before a complaint: the first call and triage
              </strong>
              <p>
                Log a call from a hospital and see it become a complaint, a service job, both, or pending. Urgent
                intakes and calls that mention harm go to the triage list at once, with their clocks running from
                awareness.
              </p>
            </div>
            <div className="uw-story-partner-actions">
              <button type="button" className="ac-secondary" onClick={() => open("Complaints", "First contact")}>
                Log a case
              </button>
              <button type="button" className="ac-secondary" onClick={() => open("Complaints", "Triage")}>
                Triage list
              </button>
            </div>
          </div>
        )}
        {allowed("Complaints") && (
          <div id="trial-reports" className="uw-story-partner uw-anchor">
            <div>
              <strong>
                <ClipboardList size={16} aria-hidden="true" /> After a conclusion: the report, ready to file
              </strong>
              <p>
                A reportable US or India conclusion drafts its Form FDA 3500A or MvPI worksheet in the authority's field
                order. A colleague approves it, told by a task in My Work; working alone in the trial, you approve your
                own practice report. You enter it in the authority's route and record the submission and the receipt.
                The sample has a finished US report and an India report to correct.
              </p>
            </div>
            <div className="uw-story-partner-actions">
              <button type="button" className="ac-secondary" onClick={() => open("Complaints", "Reports")}>
                Open Reports
              </button>
            </div>
          </div>
        )}
        {chapterList}
        {hasSample && (
          <div id="trial-look-ahead" className="uw-story-partner uw-anchor uw-look-ahead">
            <div>
              <strong>
                <Telescope size={16} aria-hidden="true" /> {LOOK_AHEAD_SECTION}: distributors and your EU authorised
                representative
              </strong>
              <p>{LOOK_AHEAD_SUMMARY} Not a chapter: there is nothing to try or save.</p>
            </div>
            <div className="uw-story-partner-actions">
              {LOOK_AHEAD_TABS.map((page) => (
                <button
                  key={page}
                  type="button"
                  className="ac-secondary"
                  onClick={() => open(LOOK_AHEAD_SECTION, page)}
                >
                  {page}
                </button>
              ))}
            </div>
          </div>
        )}
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
        <Tabs tabs={tabs} active={shownTab} onChange={setTab} label="Your trial">
          {shownTab === "Your data" && session?.sample_only && <DiscussPilot onOpen={() => open("Next steps")} />}
          {shownTab === "Your data" && !session?.sample_only && (
            <YourData
              focus={focus}
              before={
                hasSample &&
                (own?.complaints ?? 0) > 0 &&
                trial?.is_owner && (
                  <p className="uw-cited-line">
                    Your own data is in. Remove the sample so every screen shows only your records.{" "}
                    <button type="button" className="ac-link" onClick={() => setTab("About the sample data")}>
                      Remove the sample data
                    </button>
                  </p>
                )
              }
              onImported={(result: ImportResult) => {
                status.reload();
                // Its signals being found: the story is read once they are in (``awaitingSignals``).
                if (result.signals === "FINDING") setAfterImport("waiting");
                else story.reload();
              }}
            />
          )}
          {shownTab === "Team" && <TeamPanel onChanged={status.reload} />}
          {shownTab === "About the sample data" && hasSample && (
            <SampleDataPanel
              counts={trial?.sample}
              allowed={allowed}
              onOpen={(opens) => {
                if (allowed(opens.section)) open(opens.section as WorkspaceSection, opens.tab);
              }}
            />
          )}
          {shownTab === "About the sample data" && hasSample && (
            <RestartSamplePanel
              onRestarted={(text) => {
                notify(text);
                status.reload();
                story.reload();
                work.refreshProducts();
              }}
            />
          )}
          {shownTab === "About the sample data" && hasSample && (
            <RemoveSamplePanel
              onRemoved={(text) => {
                notify(text);
                if (navigation !== "new") setTab("Your data");
                status.reload();
                story.reload();
                work.refreshProducts();
                refreshTrial?.();
              }}
            />
          )}
          {shownTab === "Your trial" && (
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
  if (navigation !== "new") return body;
  // The new navigation (owner's specification, 5 Nov 2026): the walkthrough, three cards to explore at one's own pace,
  // and one collapsed section for the sample data and the trial. A link to the sample data or the trial's dates
  // opens that section; "Choose a focus" opens the library of other workflows.
  if (focus?.split("?")[0] === OTHER_WORKFLOWS)
    return (
      <div className="uw-gs">
        <div className="uw-gs-more-head">
          <button type="button" className="ac-link" onClick={() => open("Getting started")}>
            <ChevronRight size={14} aria-hidden="true" className="uw-flip" /> Back to Getting started
          </button>
          <p className="ac-eyebrow">Getting started</p>
          <h1 ref={heading} tabIndex={-1}>
            Explore other workflows
          </h1>
          <p>Short stories and ten chapters, each on the sample first and on your own data once it is in.</p>
        </div>
        <CitedFor onSaved={story.reload} />
        {hasSample && <Entrance />}
        {/* "Workflows to try" (0.10.87): "ten chapters" beside the ten-step walkthrough read as one more count. */}
        <Panel title="Workflows to try" eyebrow={chapterCount} source={story}>
          <p className="uw-trial-lede">
            Each chapter is one problem inspectors cite. It counts as tried when you act in it: decide, record, run or
            sign.
            {hasSample && (
              <>
                {" "}
                <button
                  type="button"
                  className="ac-link"
                  onClick={() => open("Getting started", "About the sample data")}
                >
                  What is the sample data?
                </button>
              </>
            )}
          </p>
          {/* Feedback is asked by its own prompt and in Help (0.10.87): no second rating here. */}
          {chapterList}
        </Panel>
      </div>
    );
  return (
    <div className="uw-gs">
      <OneStory heading={heading} />
      <ExploreCards
        owner={!!trial?.is_owner}
        teamTab={!!personaTabs?.includes("team")}
        onTeam={() => open("Team")}
        onWorkflows={() => open("Getting started", OTHER_WORKFLOWS)}
        onNextSteps={() => open("Next steps")}
        chapters={chapters}
        onDemoBooked={demo.reload}
      />
      <TrialSettings
        trial={trial ?? null}
        startOpen={focusTab === "About the sample data" || focusTab === "Your trial"}
        allowed={allowed}
        onOpen={(opens) => {
          if (allowed(opens.section)) open(opens.section as WorkspaceSection, opens.tab);
        }}
        onRestarted={restarted}
        onRemoved={restarted}
        onNextSteps={() => open("Next steps")}
      />
    </div>
  );
}

/**
 * A sample-only trial (an event or judge trial, 0.10.71) has no upload: it offers a pilot conversation instead
 * (Next steps, from trial to pilot). The import routes refuse it as well (403 SAMPLE_ONLY_TRIAL).
 */
export function DiscussPilot({ onOpen }: { onOpen: () => void }) {
  return (
    <Panel eyebrow="Your data" title="This evaluation uses the sample only">
      <p>To try your own data, discuss a pilot: MDARIX on your real complaints, in a database set up for you.</p>
      <div className="ca-action-row">
        <button type="button" className="ac-primary" onClick={onOpen}>
          {DISCUSS_PILOT} <ChevronRight size={15} aria-hidden="true" />
        </button>
      </div>
    </Panel>
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
  importHere = true,
  onOpen,
}: {
  chapter: StoryChapter;
  isNext: boolean;
  allowed: boolean;
  templates?: ImportTemplate[];
  /** The upload is a tab below (classic), not its own page, Import your data (new navigation, 0.10.80). */
  importHere?: boolean;
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
            <p className="uw-story-templates">
              Data: {templateSummary(templates)}, {importHere ? "under Your data below" : "on Import your data"}.
            </p>
          ) : null}
          <p className="uw-story-pain">
            <b>Why it matters:</b> {chapter.pain}
          </p>
        </details>
      </div>
      <button
        type="button"
        className={isNext && !done ? "ac-primary" : "ac-secondary"}
        onClick={onOpen}
        disabled={!allowed}
        aria-describedby={allowed ? undefined : `chapter-${chapter.code}-reason`}
      >
        {done ? "Open again" : (CHAPTER_ACTION[chapter.code] ?? "Open")}
      </button>
      {!allowed && (
        <p className="ms-reason" id={`chapter-${chapter.code}-reason`}>
          Your role does not include this screen.
        </p>
      )}
      <span className="ca-sr-only">{done ? "Tried" : "Not tried yet"}</span>
    </li>
  );
}
