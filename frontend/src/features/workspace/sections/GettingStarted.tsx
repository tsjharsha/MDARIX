import { useState } from "react";
import {
  Bot,
  CheckCircle2,
  Circle,
  Download,
  FileSearch,
  LayoutDashboard,
  MessageSquare,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { BarList, Empty, Panel, RingMeter, StatTile, type PanelSource } from "../../admin/console/charts";
import type { Slice } from "../../admin/console/dashboardModel";
import { useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { ImportPanel, templateSummary, type ImportTemplate } from "./ImportData";
import { formatDay } from "../../../app/dates";
import { countOf } from "./common";

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

const VISITED_KEY = "mdarix.trial.visited";
const readVisited = (): string[] => {
  try {
    return JSON.parse(window.localStorage.getItem(VISITED_KEY) ?? "[]");
  } catch {
    return [];
  }
};
const markVisited = (step: string) => {
  try {
    window.localStorage.setItem(VISITED_KEY, JSON.stringify([...new Set([...readVisited(), step])]));
  } catch {
    // Progress ticks are a convenience; the checklist still works without browser storage.
  }
};
const slices = (items: { label: string; count: number }[]): Slice[] =>
  items.map((item) => ({ key: item.label, label: item.label, count: item.count, tone: "neutral" }));

export function GettingStartedSection() {
  const { open, work } = useWorkspace();
  const status = useResource<TrialStatus>("/api/v1/trial/status");
  const insights = useResource<Insights>("/api/v1/trial/insights");
  const [visited, setVisited] = useState<string[]>(readVisited);
  const trial = status.data;

  const go = (step: string, section: WorkspaceSection, tab?: string) => {
    markVisited(step);
    setVisited(readVisited());
    open(section, tab);
  };
  const ownComplaints = trial?.own_data?.complaints ?? 0;
  const steps: {
    id: string;
    title: string;
    detail: string;
    icon: typeof Bot;
    done: boolean;
    action: () => void;
    label: string;
  }[] = [
    {
      id: "overview",
      title: "Look at the Dashboard",
      detail: "Signals, investigations and evidence from the sample data, in one view.",
      icon: LayoutDashboard,
      done: visited.includes("overview"),
      action: () => go("overview", "Dashboard"),
      label: "Open Dashboard",
    },
    {
      id: "investigation",
      title: "Open the guided investigation",
      detail: "Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?",
      icon: FileSearch,
      done: visited.includes("investigation"),
      action: () => go("investigation", "Investigations"),
      label: "Open investigation",
    },
    {
      id: "ask",
      title: "Ask MDARIX a question",
      detail: "Every answer cites the evidence it used, and says what is still unknown.",
      icon: Bot,
      done: visited.includes("ask"),
      action: () => go("ask", "Intelligence", "Ask MDARIX"),
      label: "Ask MDARIX",
    },
    {
      id: "templates",
      title: "Download the CSV templates",
      detail: `${
        trial?.templates?.length ? templateSummary(trial.templates) : "Products, lots, complaints and more"
      }: fill them from an export of your own system.`.replace(/^./, (letter) => letter.toUpperCase()),
      icon: Download,
      done: visited.includes("templates"),
      action: () => {
        markVisited("templates");
        setVisited(readVisited());
        document.getElementById("trial-import")?.scrollIntoView({ behavior: "smooth" });
      },
      label: "Go to templates",
    },
    {
      id: "upload",
      title: "Upload your data and review the insights",
      detail: "Each file is checked for problems and personal data before anything is saved.",
      icon: Upload,
      done: ownComplaints > 0,
      action: () => document.getElementById("trial-import")?.scrollIntoView({ behavior: "smooth" }),
      label: "Upload data",
    },
    {
      id: "talk",
      title: "Talk to us about becoming a design partner",
      detail: "Live connections to your QMS, PLM and ERP, and onboarding support.",
      icon: MessageSquare,
      done: visited.includes("talk"),
      action: () => {
        markVisited("talk");
        setVisited(readVisited());
        window.open("/contact", "_blank", "noopener");
      },
      label: "Contact us",
    },
  ];
  const doneCount = steps.filter((step) => step.done).length;

  if (status.state === "ready" && trial && !trial.is_trial)
    return <Empty title="Not a trial workspace" detail="Getting started is shown during a free trial." />;

  return (
    <div className="ac-overview uw-trial">
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
          <RingMeter value={doneCount} total={steps.length} label="checklist done" />
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

      <Panel title="Your first steps" eyebrow={`${doneCount} of ${steps.length} done`}>
        <ol className="uw-trial-steps">
          {steps.map((step, index) => (
            <li key={step.id} className={step.done ? "is-done" : ""}>
              <span className="uw-trial-step-mark" aria-hidden="true">
                {step.done ? <CheckCircle2 size={20} /> : <Circle size={20} />}
              </span>
              <div>
                <strong>
                  {index + 1}. {step.title}
                </strong>
                <p>{step.detail}</p>
              </div>
              <button type="button" className={step.done ? "ac-secondary" : "ac-primary"} onClick={step.action}>
                <step.icon size={15} aria-hidden="true" /> {step.label}
              </button>
              <span className="ca-sr-only">{step.done ? "Done" : "Not done yet"}</span>
            </li>
          ))}
        </ol>
      </Panel>

      <ImportPanel
        id="trial-import"
        templates={trial?.templates ?? []}
        basePath="/api/v1/trial/imports"
        fileLimitBytes={trial?.limits?.file_bytes}
        onImported={() => {
          status.reload();
          insights.reload();
          work.refreshProducts();
        }}
      />

      <InsightsPanel insights={insights.data} source={insights} />

      <TeamPanel onChanged={status.reload} />
    </div>
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
          ? { tone: "good", text: `Invitation emailed to ${result.email}. The link is valid for 72 hours.` }
          : link
            ? {
                tone: "good",
                text: `Email is not set up on this development server. Send ${result.email} this one-time link (valid 72 hours):`,
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
