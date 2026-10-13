import { useState } from "react";
import { Bot, CheckCircle2, ChevronRight, Circle, MessageSquare, ShieldCheck, Upload } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { BarList, Empty, Panel, RingMeter, StatTile, ToneBadge, type PanelSource } from "../../admin/console/charts";
import type { Slice } from "../../admin/console/dashboardModel";
import { useResource } from "../../customer-admin/shared";
import { sectionAllowed, useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { ImportPanel, templateSummary, type ImportTemplate } from "./ImportData";
import { formatDay } from "../../../app/dates";
import { countOf } from "./common";
import { QualityLoop } from "./QualityLoop";
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
  sample?: { products: number };
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

const scrollToImport = () => document.getElementById("trial-import")?.scrollIntoView({ behavior: "smooth" });

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
  const go = (chapter: Pick<StoryChapter, "code" | "opens">) => {
    if (chapter.code === "YOUR_DATA" || chapter.opens.section === "Getting started") return scrollToImport();
    if (allowed(chapter.opens.section)) open(chapter.opens.section as WorkspaceSection, chapter.opens.tab ?? undefined);
  };
  const chapters = story.data?.chapters ?? [];
  const acted = story.data?.acted ?? 0;
  const total = story.data?.total ?? 9;
  const headline = storyHeadline(story.data);
  const next = chapters.find((chapter) => chapter.code === story.data?.next) ?? null;
  const talk = () => window.open("/contact", "_blank", "noopener");

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
        <button type="button" className="ac-secondary" onClick={talk}>
          <MessageSquare size={15} aria-hidden="true" /> Talk to us
        </button>
      </QualityLoop>

      <Panel
        title={
          trial?.days_left !== undefined
            ? `${countOf(trial.days_left, "day")} left in your free trial`
            : "Your free trial"
        }
        eyebrow="Getting started"
        source={status}
      >
        <div className="uw-trial-head">
          <RingMeter value={acted} total={total} label="chapters tried" />
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
              detail={trial?.is_owner ? "Invite colleagues below" : "Your trial team"}
              icon={<CheckCircle2 size={18} />}
            />
            <StatTile
              label="Uploaded rows"
              value={
                trial?.usage ? `${trial.usage.rows.toLocaleString()} of ${trial.limits?.rows.toLocaleString()}` : null
              }
              detail="Sample data does not count"
              icon={<Upload size={18} />}
            />
          </div>
        </div>
      </Panel>

      <Panel title="Your story, chapter by chapter" eyebrow={`${acted} of ${total} tried`} source={story}>
        <p className="uw-trial-lede">
          Each chapter is one pain FDA and notified bodies cite in 2026, shown on the sample records first and on your
          own export once you upload it. A chapter counts as tried when you act in it: decide, record, run or sign.
        </p>
        <ol className="uw-trial-steps uw-story-steps">
          {chapters.map((chapter) => (
            <ChapterRow
              key={chapter.code}
              chapter={chapter}
              isNext={chapter.code === story.data?.next}
              allowed={allowed(chapter.opens.section)}
              templates={chapter.code === "YOUR_DATA" ? trial?.templates : undefined}
              onOpen={() => go(chapter)}
            />
          ))}
        </ol>
        <div className="uw-story-partner">
          <div>
            <strong>Ready to run it on your live systems?</strong>
            <p>Live connections to your QMS, PLM and ERP, onboarding support, and a design-partner price.</p>
          </div>
          <button type="button" className="ac-secondary" onClick={talk}>
            <MessageSquare size={15} aria-hidden="true" /> Talk to us about becoming a design partner
          </button>
        </div>
      </Panel>

      <ImportPanel
        id="trial-import"
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

      <TeamPanel onChanged={status.reload} />
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
        <p>{chapter.promise}</p>
        {finding && (
          <p className="uw-story-finding">
            <ToneBadge tone={chapterTone(chapter)} label={chapterStatus(chapter)} /> {finding}
          </p>
        )}
        {templates?.length ? (
          <p className="uw-story-templates">
            Templates: {templateSummary(templates)}; download them in the import panel below.
          </p>
        ) : null}
        <p className="uw-story-pain">
          <b>Why it matters:</b> {chapter.pain}
        </p>
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
