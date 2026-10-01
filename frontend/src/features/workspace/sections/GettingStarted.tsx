import { useEffect, useState } from "react";
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
import { BarList, Empty, Panel, RingMeter, StatTile } from "../../admin/console/charts";
import type { Slice } from "../../admin/console/dashboardModel";
import { useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";

export type TrialStatus = {
  is_trial: boolean;
  expires_at?: string;
  days_left?: number;
  limits?: { users: number; rows: number; file_bytes: number };
  usage?: { users: number; rows: number };
  sample?: { products: number };
  own_data?: { products: number; lots: number; complaints: number };
  templates?: { entity: string; title: string; required: string[]; optional: string[]; download: string }[];
};
type CheckReport = {
  entity: string;
  rows: number;
  new_records: number;
  error_count: number;
  issues: { row: number | null; column: string | null; message: string }[];
  ready: boolean;
  preview: Record<string, string>[];
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
  const { open } = useWorkspace();
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
      title: "Look at the Overview dashboard",
      detail: "Signals, investigations and evidence from the sample data, in one view.",
      icon: LayoutDashboard,
      done: visited.includes("overview"),
      action: () => go("overview", "Overview"),
      label: "Open Overview",
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
      detail: "Products, lots and complaints: fill them from an export of your own system.",
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
      detail: "Live connections to your QMS, PLM and ERP, single sign-on, and onboarding support.",
      icon: MessageSquare,
      done: visited.includes("talk"),
      action: () => {
        markVisited("talk");
        setVisited(readVisited());
        window.open("/company#contact", "_blank", "noopener");
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
        title={trial?.days_left !== undefined ? `${trial.days_left} days left in your free trial` : "Your free trial"}
        eyebrow="Getting started"
        state={status.state}
        error={status.error}
      >
        <div className="uw-trial-head">
          <RingMeter value={doneCount} total={steps.length} label="checklist done" />
          <div className="uw-trial-stats">
            <StatTile
              label="Trial ends"
              value={trial?.expires_at ? new Date(trial.expires_at).toLocaleDateString() : null}
              detail="Your data stays if you continue"
              icon={<ShieldCheck size={18} />}
            />
            <StatTile
              label="Users"
              value={trial?.usage ? `${trial.usage.users} of ${trial.limits?.users}` : null}
              detail="Ask us to add colleagues"
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
        trial={trial}
        onImported={() => {
          status.reload();
          insights.reload();
        }}
      />

      <InsightsPanel insights={insights.data} state={insights.state} error={insights.error} />
    </div>
  );
}

function ImportPanel({ trial, onImported }: { trial: TrialStatus | null; onImported: () => void }) {
  const templates = trial?.templates ?? [];
  const [entity, setEntity] = useState("products");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<CheckReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const template = templates.find((item) => item.entity === entity);

  useEffect(() => {
    setFile(null);
    setReport(null);
    setMessage(null);
  }, [entity]);

  const send = async (path: string) => {
    if (!file) return null;
    const limit = trial?.limits?.file_bytes ?? 2 * 1024 * 1024;
    if (file.size > limit) {
      setMessage({ tone: "bad", text: "Files can be up to 2 MB during the free trial." });
      return null;
    }
    return requestJson<any>(path, { method: "POST", body: await file.text(), headers: { "Content-Type": "text/csv" } });
  };
  const check = async () => {
    setBusy(true);
    setMessage(null);
    try {
      setReport(await send(`/api/v1/trial/imports/${entity}/check`));
    } catch (error) {
      setMessage({ tone: "bad", text: error instanceof Error ? error.message : "The file could not be checked." });
    } finally {
      setBusy(false);
    }
  };
  const runImport = async () => {
    setBusy(true);
    try {
      const result = await send(`/api/v1/trial/imports/${entity}`);
      if (result) {
        setMessage({
          tone: "good",
          text: `Imported ${template?.title.toLowerCase()}: ${result.created} new, ${result.updated} updated. Insights below are refreshed.`,
        });
        setReport(null);
        setFile(null);
        onImported();
      }
    } catch (error) {
      setMessage({
        tone: "bad",
        text: error instanceof Error ? error.message : "The import failed; nothing was saved.",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id="trial-import" className="ac-panel uw-trial-import" aria-labelledby="trial-import-title">
      <header className="ac-panel-head">
        <div>
          <p className="ac-eyebrow">Bring your own data</p>
          <h2 id="trial-import-title">Upload a CSV file</h2>
        </div>
      </header>
      <p className="uw-trial-note">
        Load in this order: products, then lots, then complaints. Remove patient and personal details first. Only
        template columns are accepted, and a file with any problem imports nothing.
      </p>
      <div className="ac-tabs" role="tablist" aria-label="Template">
        {templates.map((item, index) => (
          <button
            key={item.entity}
            type="button"
            role="tab"
            aria-selected={entity === item.entity}
            className={entity === item.entity ? "selected" : ""}
            disabled={busy}
            onClick={() => setEntity(item.entity)}
          >
            {index + 1}. {item.title}
          </button>
        ))}
      </div>
      {template && (
        <div className="uw-trial-template">
          <div>
            <strong>Required:</strong> {template.required.join(", ")}
            <br />
            <strong>Optional:</strong> {template.optional.join(", ")}
          </div>
          <a className="ac-secondary" href={template.download} download>
            <Download size={15} aria-hidden="true" /> Download {template.entity}.csv
          </a>
        </div>
      )}
      <div className="uw-trial-upload">
        <label className="ac-secondary">
          <Upload size={15} aria-hidden="true" /> {file ? file.name : "Choose a CSV file"}
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label={`Choose a ${entity} CSV file`}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setReport(null);
              setMessage(null);
            }}
          />
        </label>
        <button type="button" className="ac-primary" disabled={!file || busy} onClick={check}>
          {busy && !report ? "Checking…" : "Check file"}
        </button>
      </div>
      {message && (
        <p className={`uw-trial-message is-${message.tone}`} role="status">
          {message.text}
        </p>
      )}
      {report && (
        <div className="uw-trial-report" role="status">
          {report.ready ? (
            <p className="uw-trial-message is-good">
              <CheckCircle2 size={16} aria-hidden="true" /> {report.rows} rows are ready to import ({report.new_records}{" "}
              new records).
            </p>
          ) : (
            <>
              <p className="uw-trial-message is-bad">
                {report.error_count} problem{report.error_count === 1 ? "" : "s"} found. Nothing has been saved. Fix the
                file and check it again.
              </p>
              <ul className="uw-trial-issues">
                {report.issues.map((issue, index) => (
                  <li key={index}>
                    {issue.row ? `Row ${issue.row}` : "File"}
                    {issue.column ? ` · ${issue.column}` : ""}: {issue.message}
                  </li>
                ))}
              </ul>
            </>
          )}
          {report.preview.length > 0 && (
            <div className="ac-table-wrap">
              <table className="ac-table">
                <caption className="ca-sr-only">First rows of the file</caption>
                <thead>
                  <tr>
                    {Object.keys(report.preview[0]).map((column) => (
                      <th key={column} scope="col">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.preview.map((row, index) => (
                    <tr key={index}>
                      {Object.values(row).map((value, cell) => (
                        <td key={cell}>{value || "—"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {report.ready && (
            <button type="button" className="ac-primary" disabled={busy} onClick={runImport}>
              <Upload size={15} aria-hidden="true" /> {busy ? "Importing…" : `Import ${report.rows} rows`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function InsightsPanel({
  insights,
  state,
  error,
}: {
  insights: Insights | null;
  state: "loading" | "ready" | "error" | "forbidden";
  error?: string;
}) {
  const { open, notify } = useWorkspace();
  return (
    <Panel
      title="Automatic insights"
      eyebrow={insights ? `From ${insights.scope} · ${insights.total_complaints} complaints` : "Insights"}
      state={state}
      error={error}
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
