import { useEffect, useState } from "react";
import { Eye, EyeOff, RefreshCw, Star } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { Table } from "../customer-admin/shared";

type Feedback = {
  id: string;
  tenant_key: string | null;
  organization_name: string;
  role_area: string | null;
  job_title: string | null;
  rating_overall: number;
  rating_ease: number | null;
  rating_usefulness: number | null;
  rating_ai_trust: number | null;
  rating_speed: number | null;
  rating_import: number | null;
  recommend_score: number | null;
  features_used: string[];
  liked: string | null;
  improve: string | null;
  missing: string | null;
  adoption: string | null;
  quote: string | null;
  publish_consent: "NAMED" | "ANONYMOUS" | "PRIVATE";
  consent_text: string;
  consent_at: string;
  contact_ok: boolean;
  publication_status: "NOT_REQUESTED" | "PENDING" | "PUBLISHED" | "HIDDEN";
  attribution: string | null;
  created_at: string;
};
type Summary = {
  responses: number;
  overall: number | null;
  ease: number | null;
  usefulness: number | null;
  ai_trust: number | null;
  speed: number | null;
  import: number | null;
  nps: number | null;
  nps_responses: number;
};

const FILTERS: [string, string, (row: Feedback) => boolean][] = [
  ["PENDING", "Awaiting review", (row) => row.publication_status === "PENDING"],
  ["PUBLISHED", "On the website", (row) => row.publication_status === "PUBLISHED"],
  ["ALL", "All responses", () => true],
];
const CONSENT: Record<Feedback["publish_consent"], string> = {
  NAMED: "May show with company name",
  ANONYMOUS: "May show anonymously",
  PRIVATE: "Private",
};
const ADOPTION: Record<string, string> = {
  YES: "Yes",
  MAYBE: "Maybe",
  NO: "No",
  NOT_MY_DECISION: "Not their decision",
};
const FEATURES: Record<string, string> = {
  PRODUCT_360: "Product 360",
  SIGNALS: "Signals and complaints",
  INVESTIGATIONS: "Investigations",
  ASK_MDARIX: "Ask MDARIX",
  EVIDENCE: "Evidence library",
  DECISIONS: "Decisions and sign-off",
  CSV_IMPORT: "CSV import",
  AUDIT_TRAIL: "Audit trail",
};
const titleCase = (value: string) =>
  value.toLowerCase().replace(/(^|_)(\w)/g, (_, gap, c) => (gap ? " " : "") + c.toUpperCase());
const score = (value: number | null) => (value === null ? "—" : `${value}/5`);

// Feedback from free-trial users. Quotes reach the website only when the person consented and staff publish them.
export function TrialFeedbackWorkspace() {
  const [items, setItems] = useState<Feedback[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [filter, setFilter] = useState("PENDING");
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<{ tone: "good" | "bad"; text: string } | null>(null);

  const load = () => {
    setState("loading");
    requestJson<{ items: Feedback[]; summary: Summary }>("/api/v1/platform-admin/feedback")
      .then((data) => {
        setItems(data.items);
        setSummary(data.summary);
        setState("ready");
      })
      .catch(() => setState("error"));
  };
  useEffect(load, []);

  const publication = async (row: Feedback, action: "PUBLISH" | "HIDE") => {
    setBusy(row.id);
    setResult(null);
    try {
      await requestJson(`/api/v1/platform-admin/feedback/${row.id}/publication`, {
        method: "POST",
        body: JSON.stringify({ action }),
      });
      setResult({
        tone: "good",
        text:
          action === "PUBLISH"
            ? `Published on the website, credited to "${row.attribution}".`
            : "Hidden from the website.",
      });
      load();
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "The change could not be saved." });
    } finally {
      setBusy(null);
    }
  };

  const [, , matches] = FILTERS.find(([value]) => value === filter) ?? FILTERS[2];
  const rows = items.filter(matches);
  const open = items.find((item) => item.id === selected) ?? null;
  return (
    <section className="platform-admin-card trial-queue" aria-labelledby="feedback-title">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Trial feedback</span>
          <h3 id="feedback-title">What trial users tell us</h3>
          <p>
            Answers to the questionnaire in the trial workspace. A quote can be published on the website only when the
            person agreed, and is credited exactly as they chose: with their company's name or anonymously.
          </p>
        </div>
        <div className="trial-queue-head-actions">
          <button className="platform-admin-secondary" onClick={load} disabled={state === "loading"}>
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </div>

      {summary && summary.responses > 0 && (
        <dl className="fb-summary">
          <div>
            <dt>Responses</dt>
            <dd>{summary.responses}</dd>
          </div>
          <div>
            <dt>Overall</dt>
            <dd>{summary.overall ?? "—"} / 5</dd>
          </div>
          <div>
            <dt>Ease of use</dt>
            <dd>{summary.ease ?? "—"} / 5</dd>
          </div>
          <div>
            <dt>Trust in AI</dt>
            <dd>{summary.ai_trust ?? "—"} / 5</dd>
          </div>
          <div>
            <dt>Net promoter score</dt>
            <dd title={`${summary.nps_responses} answers`}>{summary.nps ?? "—"}</dd>
          </div>
        </dl>
      )}

      <div className="trial-queue-filters" role="tablist" aria-label="Feedback">
        {FILTERS.map(([value, label, test]) => (
          <button
            key={value}
            role="tab"
            aria-selected={filter === value}
            className={filter === value ? "is-active" : ""}
            onClick={() => setFilter(value)}
          >
            {label} <span>{items.filter(test).length}</span>
          </button>
        ))}
      </div>

      {result && (
        <div className={`trial-queue-result is-${result.tone}`} role="status">
          <p>{result.text}</p>
        </div>
      )}

      {state === "error" ? (
        <p className="trial-queue-empty">Feedback could not be loaded. Refresh to try again.</p>
      ) : state === "loading" && !items.length ? (
        <p className="trial-queue-empty">Loading feedback…</p>
      ) : rows.length === 0 ? (
        <p className="trial-queue-empty">
          {filter === "PENDING" ? "Nothing is waiting for review." : "Nothing here yet."}
        </p>
      ) : (
        <Table
          caption="Trial feedback"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "Nothing here yet", detail: "Responses appear here as trial users send feedback." }}
          columns={[
            {
              key: "company",
              label: "Company",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.organization_name}</strong>
                  <small>{row.tenant_key ?? "—"}</small>
                </span>
              ),
            },
            {
              key: "overall",
              label: "Overall",
              render: (row) => (
                <span className="fb-stars" aria-label={`${row.rating_overall} of 5`}>
                  <Star size={14} aria-hidden="true" /> {row.rating_overall}/5
                </span>
              ),
            },
            { key: "recommend", label: "Recommend", render: (row) => (row.recommend_score ?? "—").toString() },
            { key: "consent", label: "Website consent", render: (row) => CONSENT[row.publish_consent] },
            { key: "sent", label: "Sent", render: (row) => new Date(row.created_at).toLocaleDateString() },
            {
              key: "actions",
              label: "",
              render: (row) => (
                <div className="trial-queue-actions">
                  <button
                    className="platform-admin-secondary"
                    aria-expanded={selected === row.id}
                    onClick={() => setSelected(selected === row.id ? null : row.id)}
                  >
                    {selected === row.id ? "Close" : "Read"}
                  </button>
                  {row.publish_consent !== "PRIVATE" && row.quote && row.publication_status !== "PUBLISHED" && (
                    <button
                      className="platform-admin-primary"
                      disabled={busy !== null}
                      onClick={() => void publication(row, "PUBLISH")}
                    >
                      <Eye size={14} /> Publish
                    </button>
                  )}
                  {row.publication_status === "PUBLISHED" && (
                    <button
                      className="platform-admin-secondary"
                      disabled={busy !== null}
                      onClick={() => void publication(row, "HIDE")}
                    >
                      <EyeOff size={14} /> Hide
                    </button>
                  )}
                </div>
              ),
            },
          ]}
        />
      )}

      {open && (
        <article className="fb-detail" aria-label={`Feedback from ${open.organization_name}`}>
          <h4>
            {open.organization_name}
            {open.job_title ? ` · ${open.job_title}` : ""}
            {open.role_area ? ` · ${titleCase(open.role_area)}` : ""}
          </h4>
          <dl>
            <div>
              <dt>Ratings</dt>
              <dd>
                Overall {score(open.rating_overall)} · ease {score(open.rating_ease)} · usefulness{" "}
                {score(open.rating_usefulness)} · AI trust {score(open.rating_ai_trust)} · speed{" "}
                {score(open.rating_speed)} · import {score(open.rating_import)} · recommend{" "}
                {open.recommend_score ?? "—"}/10
              </dd>
            </div>
            <div>
              <dt>Used</dt>
              <dd>
                {open.features_used.length
                  ? open.features_used.map((code) => FEATURES[code] ?? titleCase(code)).join(", ")
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>Would adopt</dt>
              <dd>{open.adoption ? ADOPTION[open.adoption] : "—"}</dd>
            </div>
            <div>
              <dt>Liked</dt>
              <dd>{open.liked ?? "—"}</dd>
            </div>
            <div>
              <dt>Improve</dt>
              <dd>{open.improve ?? "—"}</dd>
            </div>
            <div>
              <dt>Needs before daily use</dt>
              <dd>{open.missing ?? "—"}</dd>
            </div>
            <div>
              <dt>Quote</dt>
              <dd>{open.quote ? <q>{open.quote}</q> : "—"}</dd>
            </div>
            <div>
              <dt>Credited as</dt>
              <dd>{open.attribution ?? "Not shown (private)"}</dd>
            </div>
            <div>
              <dt>Consent given</dt>
              <dd>
                {open.consent_text} <small>({new Date(open.consent_at).toLocaleString()})</small>
              </dd>
            </div>
            <div>
              <dt>Contact</dt>
              <dd>{open.contact_ok ? "Agreed to be contacted" : "Did not ask to be contacted"}</dd>
            </div>
          </dl>
        </article>
      )}
    </section>
  );
}
