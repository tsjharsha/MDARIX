import { ChevronRight } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { errorText, useResource } from "../../customer-admin/shared";
import { useTabParam, useWorkspace } from "../workspaceContext";
import { reportPlace } from "../authorityReports";

/** GET /api/v1/decision-trees (backend/app/decision_guides/trees.py). */
export type TreeMarket = {
  market: string;
  label: string;
  title: string;
  version: number;
  status: "APPROVED" | "STARTER";
  status_label: string;
  version_label: string;
  enabled: boolean;
  tests: { passed: number; total: number; current: boolean };
  questions: { id: string; text: string; clause: string; extra: boolean }[];
};
export type TreeNode = {
  id: string;
  text: string;
  clause: string;
  extra: boolean;
  answer: string | null;
  answer_label: string;
};
export type TreePath = {
  market: string;
  label: string;
  nodes: TreeNode[];
  outcome: {
    code: string;
    label: string;
    signed: boolean;
    report_type_label: string | null;
    due_on: string | null;
    signed_by: string | null;
    signed_at: string | null;
    version: number;
  };
  report: { id: string; state: string } | null;
  has_form: boolean;
};
export type Trees = {
  markets: TreeMarket[];
  complaints: { id: string; ref: string; description: string; markets: string[]; signed: string[] }[];
  complaint: { id: string; ref: string; description: string } | null;
  paths: Record<string, TreePath>;
  never_decides: string;
  starter_mark: string;
};

/** Where a complaint's path in one market opens: the Decision trees tab, the market and complaint in its address. */
export const treePlace = (market: string, complaint: string) => ({
  section: "Decision trees" as const,
  tab: `?${new URLSearchParams({ market, complaint })}`,
});

/** Each market's short name on its button (the approved design). */
export const TREE_NAMES: Record<string, string> = { US: "US MDR", IN: "India", EU_NI: "EU / NI", GB: "Great Britain" };

/** The complaint a market's tree shows first: the one asked for, else the first walked through it (signed first). */
export function chosenComplaint(trees: Trees | null, market: string, asked: string | null): string | null {
  if (!trees) return null;
  const walked = trees.complaints.filter((item) => item.markets.includes(market));
  return (walked.find((item) => item.id === asked) ?? walked[0])?.id ?? null;
}

/** What the tree's outcome leads to: the report, the filing on the conclusion, or nothing. */
export function nextAfter(path: TreePath | null): { title: string; detail: string } {
  if (!path) return { title: "No complaint walked through it yet", detail: "Assess a complaint for this market." };
  const reportable = path.outcome.code === "REPORTABLE";
  if (!path.outcome.signed)
    return {
      title: `Points to: ${path.outcome.label.toLowerCase()}`,
      detail: "Not signed yet. A person confirms or overrides it on the complaint's page and signs.",
    };
  if (!reportable) return { title: "No report", detail: "The rationale stays on the complaint's record, signed." };
  if (!path.has_form)
    return {
      title: "Reportable",
      detail: "Record where and when you reported on the market's signed conclusion.",
    };
  return {
    title: path.report ? "The report was created when the conclusion was signed" : "The report is created on signing",
    detail: "Its mandatory fields arrive filled from the complaint, the product, your organization and this tree.",
  };
}

const ANSWERS = ["YES", "NO"] as const;

/**
 * Decision trees (0.10.75, Release C part C3): one tree per market, built from the decision guides (their locked
 * wording and test matrix), with the path a complaint took: question, answer, clause, outcome. The address carries
 * the market and the complaint (/app/decision-trees?market=US&complaint=<id>), so a complaint's page opens its path.
 */
export function DecisionTreesSection() {
  const { open } = useWorkspace();
  const [marketParam, setMarket] = useTabParam("market");
  const [complaintParam, setComplaint] = useTabParam("complaint", "replace");
  const all = useResource<Trees>("/api/v1/decision-trees");
  const markets = all.data?.markets ?? [];
  const market = markets.find((item) => item.market === marketParam)?.market ?? markets[0]?.market ?? "US";
  const tree = markets.find((item) => item.market === market) ?? null;
  const complaint = chosenComplaint(all.data ?? null, market, complaintParam);
  const one = useResource<Trees>(complaint ? `/api/v1/decision-trees?complaint_id=${complaint}` : null);
  const path = one.data?.paths[market] ?? null;
  const walked = (all.data?.complaints ?? []).filter((item) => item.markets.includes(market));
  if (!all.data || !tree)
    return (
      <Panel eyebrow="Decision trees" title="Is it reportable, and by when?" source={all}>
        {all.state === "error" && <p className="ac-muted">{errorText(all.error, "The trees could not be read.")}</p>}
      </Panel>
    );
  const after = nextAfter(path);
  const nodes: TreeNode[] =
    path?.nodes ?? tree.questions.map((item) => ({ ...item, answer: null, answer_label: "Not answered" }));
  const reportable = path?.outcome.code === "REPORTABLE";
  return (
    <div className="uw-trees">
      <div className="uw-tree-markets" role="group" aria-label="Market">
        {markets.map((item) => (
          <button
            key={item.market}
            type="button"
            className={item.market === market ? "ac-primary" : "ac-secondary"}
            aria-pressed={item.market === market}
            onClick={() => setMarket(item.market)}
          >
            {TREE_NAMES[item.market] ?? item.label}
          </button>
        ))}
      </div>
      <div className="uw-rec">
        <section className="uw-card uw-rec-main" aria-label={`The ${tree.label} tree`}>
          <div className="uw-card-head">
            <div>
              <p className="ac-eyebrow">{tree.version_label}</p>
              <h2>{tree.title}</h2>
            </div>
            <ToneBadge tone={tree.status === "APPROVED" ? "good" : "neutral"} label={tree.status_label} />
          </div>
          <div className="uw-card-pad uw-tree-body">
            {walked.length > 0 ? (
              <label className="uw-lv uw-tree-for">
                <span>Path for</span>
                <select value={complaint ?? ""} onChange={(event) => setComplaint(event.target.value)}>
                  {walked.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.ref}
                      {item.signed.includes(market) ? "" : " (not signed yet)"}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <p className="ac-muted">No complaint has been walked through this tree yet: its questions, in order.</p>
            )}
            {complaintParam && complaintParam !== complaint && (
              <p className="ac-message tone-warning" role="status">
                The complaint you came from has no {tree.label} assessment yet: its answers start on its page.
              </p>
            )}
            {one.data?.complaint && path && <p className="uw-tree-what">{one.data.complaint.description}</p>}
            <ol className="uw-tree" aria-label="Question, answer, clause">
              {nodes.map((node, index) => (
                <li key={node.id} className={`uw-tnode${node.extra ? " is-extra" : ""}`}>
                  <span className="uw-tn" aria-hidden="true">
                    {index + 1}
                  </span>
                  <div className="uw-tq">
                    <b>{node.text}</b>
                    <small>
                      {node.clause}
                      {node.extra ? " · your extra question: recorded, never changes the conclusion" : ""}
                    </small>
                  </div>
                  <span className="uw-tans" aria-label={`Answer: ${node.answer_label}`}>
                    {(node.answer && !ANSWERS.includes(node.answer as "YES") ? [...ANSWERS, node.answer] : ANSWERS).map(
                      (answer) => (
                        <span key={answer} className={`uw-pill${node.answer === answer ? " is-on" : ""}`}>
                          {answer === node.answer ? node.answer_label : answer === "YES" ? "Yes" : "No"}
                        </span>
                      ),
                    )}
                  </span>
                </li>
              ))}
              <li className={`uw-tout${reportable ? " is-reportable" : ""}`}>
                <b>{path ? path.outcome.label : "Outcome"}</b>
                <span>
                  {path
                    ? [
                        path.outcome.report_type_label,
                        path.outcome.signed
                          ? `signed by ${path.outcome.signed_by ?? "a colleague"}, version ${path.outcome.version}`
                          : "suggested by the answers so far, not signed",
                      ]
                        .filter(Boolean)
                        .join(" · ")
                    : "Each complaint's answers lead to its outcome."}
                </span>
              </li>
            </ol>
            <p className="ac-note">{all.data.never_decides}</p>
          </div>
        </section>
        <aside className="uw-rail" aria-label="What happens next">
          <section className="uw-card uw-card-pad uw-rail-next">
            <h2>What happens next</h2>
            <b>{after.title}</b>
            <p className="ac-muted">{after.detail}</p>
            {path?.report ? (
              <button
                type="button"
                className="ac-primary"
                onClick={() => {
                  const place = reportPlace(path.report!.id);
                  open(place.section, place.tab);
                }}
              >
                Open the report <ChevronRight size={15} aria-hidden="true" />
              </button>
            ) : one.data?.complaint ? (
              <button
                type="button"
                className="ac-secondary"
                onClick={() => open("Complaint", `Summary?ref=${encodeURIComponent(one.data!.complaint!.ref)}`)}
              >
                Open {one.data.complaint.ref}
              </button>
            ) : null}
          </section>
          <section className="uw-card uw-card-pad">
            <h2>Tested before use</h2>
            <b>
              {tree.tests.passed} of {tree.tests.total} worked complaints pass
            </b>
            <p className="ac-muted">
              The regulation's wording is locked. Your explanation and examples sit beside it.
              {tree.status === "STARTER" ? " Starter rules, for your consultant to confirm." : ""}
            </p>
            <button type="button" className="ac-link" onClick={() => open("Settings", "Reportability guides")}>
              Open the guide in Settings
            </button>
          </section>
        </aside>
      </div>
    </div>
  );
}
