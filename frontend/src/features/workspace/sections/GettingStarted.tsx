import { useState } from "react";
import { Bot, CheckCircle2, ChevronRight, Circle, MessageSquare, ShieldCheck, Star, Upload, Users } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { BarList, Empty, Panel, StatTile, ToneBadge, type PanelSource } from "../../admin/console/charts";
import type { Slice } from "../../admin/console/dashboardModel";
import { Tabs, errorText, send, useResource } from "../../customer-admin/shared";
import { sectionAllowed, useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { ImportPanel, templateSummary, type ImportTemplate } from "./ImportData";
import { formatDay } from "../../../app/dates";
import { countOf } from "./common";
import { QualityLoop } from "./QualityLoop";
import { BookDemo, DEMO_REQUEST_PATH, type TrialDemoRequest } from "./BookDemo";
import { TrialJourney } from "./TrialJourney";
import { EndTrialPanel } from "./EndTrial";
import { journeyProgress, type JourneyKey } from "../../help/trialGuide";
import { SampleDataPanel } from "./SampleData";
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
type Insights = {
  scope: string;
  total_complaints: number;
  by_product: { product_id: string; name: string; complaints: number }[];
  by_version: { product_id: string | null; version: string; complaints: number }[];
  by_lot: { lot_id: string; complaints: number }[];
  findings: string[];
  suggested_questions: string[];
  note: string;
};

const slices = (items: { label: string; count: number }[]): Slice[] =>
  items.map((item) => ({ key: item.label, label: item.label, count: item.count, tone: "neutral" }));

const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

/** The tabs below the story: everything that is not the story itself, one click away. */
export const TRIAL_TABS = ["Your data", "Team", "About the sample data", "Your trial"] as const;
export type TrialTab = (typeof TRIAL_TABS)[number];

/**
 * Getting started: the free trial as a story. The quality loop MDARIX closes, chapter by chapter, each with what the
 * trial's records show (the sample data first, its own export later), why it matters to inspectors in 2026 and where
 * to try it. A chapter is done when the organization acted in it (a record it created in MDARIX), so the progress here
 * is the progress MDARIX sees (/api/v1/trial/story).
 */
export function GettingStartedSection() {
  const { open, work, session } = useWorkspace();
  const status = useResource<TrialStatus>("/api/v1/trial/status");
  const insights = useResource<Insights>("/api/v1/trial/insights");
  const story = useResource<TrialStory>(TRIAL_STORY_PATH);
  const trial = status.data;
  const allowed = (section: string) =>
    section === "Getting started" ||
    sectionAllowed(section as WorkspaceSection, session?.allowed_menu, session?.business_permissions);
  const [tab, setTab] = useState<TrialTab>("Your data");
  // A tab below the story, opened and brought into view.
  const showTab = (name: TrialTab) => {
    setTab(name);
    window.setTimeout(() => scrollTo("trial-tabs"), 0);
  };
  const go = (chapter: Pick<StoryChapter, "code" | "opens"> & Partial<Pick<StoryChapter, "case">>) => {
    if (chapter.code === "YOUR_DATA" || chapter.opens.section === "Getting started") return showTab("Your data");
    if (!allowed(chapter.opens.section)) return;
    // A chapter about the guided investigation opens that case, whatever the context bar holds.
    const known = chapter.case ?? chapters.find((item) => item.code === chapter.code)?.case;
    if (known) work.setInvestigationId(known.id, known.product_id);
    open(chapter.opens.section as WorkspaceSection, chapter.opens.tab ?? undefined);
  };
  const chapters = story.data?.chapters ?? [];
  const acted = story.data?.acted ?? 0;
  const total = story.data?.total ?? 9;
  const headline = storyHeadline(story.data);
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
      </QualityLoop>

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
        {acted >= 3 && feedback.state === "ready" && !feedbackSent && (
          <QuickRating onSent={feedback.reload} onMore={() => open("Share feedback")} />
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
      </Panel>

      <div id="trial-tabs" className="uw-anchor uw-trial-tabs">
        <Tabs tabs={tabs} active={tabs.includes(tab) ? tab : tabs[0]} onChange={setTab} label="Your trial">
          {tab === "Your data" && (
            <>
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
                    detail={trial?.is_owner ? "Invite colleagues under Team" : "Your trial team"}
                    icon={<Users size={18} />}
                  />
                  <StatTile
                    label="Uploaded rows"
                    value={
                      trial?.usage
                        ? `${trial.usage.rows.toLocaleString()} of ${trial.limits?.rows.toLocaleString()}`
                        : null
                    }
                    detail="Sample data does not count"
                    icon={<Upload size={18} />}
                  />
                </div>
              </Panel>
              <EndTrialPanel />
            </>
          )}
        </Tabs>
      </div>
    </div>
  );
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
        </strong>
        {finding && (
          <p className="uw-story-finding">
            <ToneBadge tone={chapterTone(chapter)} label={chapterStatus(chapter)} /> {finding}
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

type TeamMember = {
  id: string;
  display_name: string;
  email: string;
  status: string;
  is_owner: boolean;
  is_you: boolean;
};
type Team = { can_invite: boolean; limit: number; seats_used: number; members: TeamMember[] };

function TeamPanel({ onChanged }: { onChanged: () => void }) {
  const team = useResource<Team>("/api/v1/trial/team");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string; link?: string } | null>(null);
  const data = team.data;
  const full = !!data && data.seats_used >= data.limit;

  const send = async (path: string, body?: object) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await requestJson<any>(path, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      const sent = result.email_delivery === "SENT";
      const link = !sent && result.activation_path ? `${window.location.origin}${result.activation_path}` : undefined;
      setMessage(
        sent
          ? { tone: "good", text: `Invitation emailed to ${result.email}. The link is valid for 48 hours.` }
          : link
            ? {
                tone: "good",
                text: `Email is not set up on this development server. Send ${result.email} this one-time link (valid 48 hours):`,
                link,
              }
            : {
                tone: "bad",
                text: `The invitation email to ${result.email} could not be sent. Try Resend in a few minutes, or contact MDARIX support.`,
              },
      );
      setName("");
      setEmail("");
      team.reload();
      onChanged();
    } catch (error) {
      setMessage({ tone: "bad", text: error instanceof Error ? error.message : "The invitation could not be sent." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="Your team" eyebrow={data ? `${data.seats_used} of ${data.limit} users` : "Team"} source={team}>
      {data && (
        <>
          <ul className="uw-team">
            {data.members.map((member) => (
              <li key={member.id}>
                <div>
                  <strong>
                    {member.display_name}
                    {member.is_you && <span className="uw-team-tag">You</span>}
                    {member.is_owner && <span className="uw-team-tag">Trial owner</span>}
                  </strong>
                  <small>{member.email}</small>
                </div>
                <span className={`uw-team-status ${member.status === "ACTIVE" ? "is-active" : ""}`}>
                  {member.status === "ACTIVE" ? "Active" : "Invited"}
                </span>
                {data.can_invite && member.status === "INVITED" && (
                  <button
                    type="button"
                    className="ac-link"
                    disabled={busy}
                    onClick={() => send(`/api/v1/trial/team/${member.id}/resend-invitation`)}
                  >
                    Resend invitation
                  </button>
                )}
              </li>
            ))}
          </ul>
          {data.can_invite && !full && (
            <form
              className="uw-team-form"
              onSubmit={(event) => {
                event.preventDefault();
                void send("/api/v1/trial/team", { email: email.trim(), display_name: name.trim() });
              }}
            >
              <label>
                Colleague's name
                <input required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label>
                Work email
                <input
                  required
                  type="email"
                  maxLength={254}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
              <button type="submit" className="ac-primary" disabled={busy}>
                {busy ? "Sending…" : "Invite colleague"}
              </button>
            </form>
          )}
          {data.can_invite && full && (
            <p className="uw-trial-note">
              All {data.limit} trial seats are in use.{" "}
              <a href="/contact" target="_blank" rel="noopener">
                Contact us
              </a>{" "}
              to add more people as a design partner.
            </p>
          )}
          {!data.can_invite && (
            <p className="uw-trial-note">The person who started this trial can invite colleagues.</p>
          )}
          {message && (
            <div className={`uw-trial-message is-${message.tone}`} role="status">
              <span>{message.text}</span>
              {message.link && <code className="uw-team-link">{message.link}</code>}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

function InsightsPanel({ insights, source }: { insights: Insights | null; source: PanelSource }) {
  const { open, notify } = useWorkspace();
  return (
    <Panel
      title="Automatic insights"
      eyebrow={insights ? `From ${insights.scope} · ${countOf(insights.total_complaints, "complaint")}` : "Insights"}
      source={source}
    >
      {insights && insights.total_complaints === 0 ? (
        <Empty title="No complaints yet" detail="Upload complaints to see where they concentrate." />
      ) : (
        insights && (
          <>
            {insights.findings.length > 0 && (
              <ul className="uw-trial-findings">
                {insights.findings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            )}
            <div className="ac-grid two">
              <div>
                <h3 className="uw-trial-subhead">Complaints by product version</h3>
                <BarList
                  colour="series"
                  items={slices(
                    insights.by_version.map((item) => ({
                      label: `${item.product_id ?? ""} ${item.version}`.trim(),
                      count: item.complaints,
                    })),
                  )}
                />
              </div>
              <div>
                <h3 className="uw-trial-subhead">Lots with the most complaints</h3>
                <BarList
                  colour="series"
                  items={slices(insights.by_lot.map((item) => ({ label: item.lot_id, count: item.complaints })))}
                />
              </div>
            </div>
            <div>
              <h3 className="uw-trial-subhead">Questions to ask next</h3>
              <div className="uw-trial-questions">
                {insights.suggested_questions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    className="ac-secondary"
                    onClick={() => {
                      void navigator.clipboard?.writeText(question).catch(() => undefined);
                      open("Intelligence", "Ask MDARIX");
                      notify(`Question copied. Paste it into Ask MDARIX: "${question}"`);
                    }}
                  >
                    <Bot size={15} aria-hidden="true" /> {question}
                  </button>
                ))}
              </div>
            </div>
            <p className="uw-trial-note">{insights.note}</p>
          </>
        )
      )}
    </Panel>
  );
}
