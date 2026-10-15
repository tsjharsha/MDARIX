import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  aiSummaryNote,
  canRaiseFromTrend,
  isRunning,
  oneClickQuestion,
  pValueText,
  runAuthor,
  runHeadline,
  runProgress,
  signalFromTrend,
  trendCountText,
  trendHeadline,
  trendPath,
  trendResultOf,
  type CaseAiRun,
  type TrendBoard,
  type TrendItem,
} from "./signalAi";
import { followUpTypesOf, followUpsFromActions } from "./humanDecision";
import { SummaryView, TrendLine } from "./sections/SignalInsight";
import { RunView, cardShown, startsByItself } from "./sections/CaseAiRun";
import { SIGNALS_TABS } from "./signals";
import { taskDestination } from "./tasks";

const item = (overrides: Partial<TrendItem> = {}): TrendItem => ({
  key: "p|v|",
  product: { id: "p-1", business_id: "PRD000001", name: "FlowSure 200" },
  product_version: { id: "v-1", business_id: "PVR000002", version_identifier: "Rev B" },
  problem: null,
  name: "FlowSure 200 Rev B",
  recent: 6,
  recent_days: 30,
  history: 6,
  history_days: 180,
  expected: 1,
  p_value: 0.0006,
  ratio: 6,
  result: "SIGNIFICANT",
  label: "Rate significantly higher than its history",
  sentence: "FlowSure 200 Rev B: 6 complaints in the last 30 days against 1.0 expected",
  recent_complaints: [
    { id: "c-1", business_id: "CMP000001" },
    { id: "c-2", business_id: "CMP000002" },
  ],
  open_signals: [],
  ...overrides,
});

describe("the trend check", () => {
  it("asks for a grouping and a product", () => {
    expect(trendPath("version")).toBe("/api/v1/triage/trends?group=version");
    expect(trendPath("problem", "p-1")).toBe("/api/v1/triage/trends?group=problem&product_id=p-1");
  });

  it("reads results, chances and counts in plain words", () => {
    expect(trendResultOf("SIGNIFICANT")).toEqual({ label: "Significant rise", tone: "critical" });
    expect(trendResultOf("STEADY").tone).toBe("good");
    expect(trendResultOf("ODD").label).toBe("—");
    expect(pValueText(0.0004)).toBe("p < 0.001");
    expect(pValueText(0.0166)).toBe("p 0.017");
    expect(pValueText(null)).toBe("—");
    expect(trendCountText(item())).toBe("6 against 1.0 expected (6.0×)");
    expect(trendCountText(item({ result: "SHORT_HISTORY" }))).toBe("6 in 30 days");
  });

  it("leads with significant rises, then elevated ones", () => {
    const board = (summary: Partial<TrendBoard["summary"]>) =>
      ({
        summary: {
          groups: 4,
          complaints_counted: 120,
          significant: 0,
          elevated: 0,
          steady: 4,
          too_few: 0,
          short_history: 0,
          ...summary,
        },
      }) as TrendBoard;
    expect(trendHeadline(board({ significant: 1 }))).toMatchObject({
      title: "1 group rising significantly against their own history",
      tone: "critical",
    });
    expect(trendHeadline(board({ elevated: 2 })).tone).toBe("warning");
    expect(trendHeadline(board({})).title).toBe("No version is rising against its own history");
    expect(trendHeadline(board({})).detail).toContain("120 complaints counted across 4 groups, whatever their status.");
  });

  it("raises a signal only from a notable group without one, with its recent complaints", () => {
    expect(canRaiseFromTrend(item())).toBe(true);
    expect(canRaiseFromTrend(item({ result: "STEADY" }))).toBe(false);
    expect(canRaiseFromTrend(item({ open_signals: [{ id: "s", business_id: "SIG000001", status: "NEW" }] }))).toBe(
      false,
    );
    expect(signalFromTrend(item())).toEqual({
      title: "Trend check: FlowSure 200 Rev B",
      description: item().sentence,
      product_id: "p-1",
      product_version_id: "v-1",
      complaint_ids: ["c-1", "c-2"],
      reason: "Raised from the trend check: rate significantly higher than its history (p < 0.001)",
    });
  });

  it("is a tab of Signals", () => {
    expect(SIGNALS_TABS).toContain("Trend check");
  });

  it("shows a signal's own check", () => {
    const markup = renderToStaticMarkup(<TrendLine trend={item()} />);
    expect(markup).toContain("Significant rise");
    expect(markup).toContain("6 against 1.0 expected (6.0×)");
    expect(markup).toContain("p &lt; 0.001");
    expect(renderToStaticMarkup(<TrendLine trend={null} />)).toContain("it names no product");
  });
});

describe("the signal summary", () => {
  it("shows each sentence with the complaints it cites, and the AI label when AI wrote it", () => {
    const records = renderToStaticMarkup(
      <SummaryView
        summary={{
          author: "RECORDS",
          complaints: 3,
          sentences: [{ text: "3 complaints about occlusion.", complaints: ["CMP000001", "CMP000002"] }],
          ai: { status: "NO_ANSWER", reason: "PROVIDER_NOT_CONFIGURED" },
        }}
      />,
    );
    expect(records).toContain("3 complaints about occlusion.");
    expect(records).toContain("<code>CMP000001</code>");
    expect(records).toContain("No AI provider is set up yet");
    const ai = renderToStaticMarkup(
      <SummaryView
        summary={{
          author: "AI",
          complaints: 3,
          sentences: [{ text: "Two describe a clear line.", complaints: ["CMP000001"] }],
          ai: {
            status: "COMPLETED",
            label: "AI interpretation: written by AI",
            dropped: [{ text: "x", reason: "CAUSAL_OR_DECISION_CLAIM" }],
          },
        }}
      />,
    );
    expect(ai).toContain("AI interpretation: written by AI");
    expect(ai).toContain("1 sentence left out");
  });

  it("says why AI did not write it", () => {
    expect(
      aiSummaryNote({
        author: "RECORDS",
        complaints: 1,
        sentences: [],
        ai: { status: "REFUSED", message: "AI is off." },
      }),
    ).toBe("AI is off.");
    expect(aiSummaryNote({ author: "AI", complaints: 1, sentences: [], ai: { status: "COMPLETED" } })).toBeNull();
    expect(aiSummaryNote(null)).toBeNull();
  });
});

describe("one click to a case", () => {
  it("starts from the signal's question, else one from its product and problem", () => {
    expect(oneClickQuestion("What is the root cause of occlusion alarms?", {})).toBe(
      "What is the root cause of occlusion alarms?",
    );
    expect(oneClickQuestion("", { problem_key: "FLOW_INTERRUPTION", product: { name: "FlowSure 300" } })).toBe(
      "What explains flow interruption on FlowSure 300?",
    );
    expect(oneClickQuestion("short", { problem_key: "UNSPECIFIED" })).toBe("What explains these complaints?");
  });
});

const run = (overrides: Partial<CaseAiRun> = {}): CaseAiRun => ({
  id: "r-1",
  status: "COMPLETED",
  trigger: "AUTO",
  as_of: null,
  requested_at: null,
  started_at: null,
  finished_at: null,
  error: null,
  steps: [
    { step: "ANALYSIS", label: "Analysis of the evidence", status: "DONE", author: "RULES" },
    { step: "HYPOTHESES", label: "Competing explanations", status: "DONE", author: "RULES" },
    { step: "BRIEF", label: "Investigation brief", status: "PENDING" },
  ],
  ...overrides,
});

describe("the case AI run", () => {
  it("reads progress, author and headline", () => {
    expect(isRunning(run({ status: "RUNNING" }))).toBe(true);
    expect(isRunning(run())).toBe(false);
    expect(runProgress(run())).toEqual({ done: 2, total: 3 });
    expect(runAuthor(run())).toBe("RULES");
    expect(runAuthor(run({ steps: [{ step: "A", label: "A", status: "DONE", author: "AI" }, ...run().steps] }))).toBe(
      "MIXED",
    );
    expect(runHeadline(null).title).toBe("The AI analysis has not run yet");
    expect(runHeadline(run({ status: "RUNNING" })).title).toBe("Analysing the case… 2 of 3 steps done");
    expect(runHeadline(run())).toMatchObject({
      title: "AI analysis ready: judge each explanation below",
      tone: "good",
    });
    expect(runHeadline(run()).detail).toContain("AI is off or unavailable");
    expect(runHeadline(run({ status: "PARTIAL", error: "Investigation brief failed: X" })).tone).toBe("warning");
  });

  it("shows each step with who wrote it, and a way to run it again", () => {
    const markup = renderToStaticMarkup(
      <RunView run={run()} running={false} canRun busy={false} error="" onRun={vi.fn()} />,
    );
    expect(markup).toContain("started by itself");
    expect(markup).toContain("Analysis of the evidence");
    expect(markup).toContain("From the rules");
    expect(markup).toContain("Run the analysis again");
    expect(markup).toContain("never decides the cause, reportability or closure");
    const viewer = renderToStaticMarkup(
      <RunView run={run()} running={false} canRun={false} busy={false} error="" onRun={vi.fn()} />,
    );
    expect(viewer).not.toContain("Run the analysis again");
  });

  it("starts by itself and shows only while AI answers for the organization", () => {
    const at = { canRun: true, aiReady: true as boolean | null, loaded: true, run: null as CaseAiRun | null };
    expect(startsByItself(at)).toBe(true);
    // AI off, not available or used up, or its status still loading: opening the case starts nothing.
    expect(startsByItself({ ...at, aiReady: false })).toBe(false);
    expect(startsByItself({ ...at, aiReady: null })).toBe(false);
    expect(startsByItself({ ...at, canRun: false })).toBe(false);
    expect(startsByItself({ ...at, loaded: false })).toBe(false);
    expect(startsByItself({ ...at, run: run() })).toBe(false);
    expect(cardShown(true, false)).toBe(true);
    expect(cardShown(false, false)).toBe(false);
    expect(cardShown(null, false)).toBe(false);
    expect(cardShown(false, true)).toBe(true);
  });
});

describe("follow-ups from the brief's recommended actions", () => {
  it("reads which follow-up an action names", () => {
    expect(followUpTypesOf("Open a CAPA for the sensor adhesive")).toEqual(["CAPA_REQUIRED"]);
    expect(followUpTypesOf("Update the risk file for under-infusion")).toEqual(["RISK_REASSESSMENT_REQUIRED"]);
    expect(followUpTypesOf("Assess whether an MDR is needed")).toEqual(["REGULATORY_ACTION_REQUIRED"]);
    expect(followUpTypesOf("Quarantine lot L-0101 and review a field action")).toEqual([
      "FIELD_ACTION_REVIEW_REQUIRED",
    ]);
    expect(followUpTypesOf("Release a firmware fix")).toEqual(["PRODUCT_CHANGE_REQUIRED"]);
    expect(followUpTypesOf("Interview the night shift")).toEqual([]);
  });

  it("ticks them with the actions as titles, joining actions of one kind", () => {
    const found = followUpsFromActions([
      "Open a CAPA for the sensor adhesive",
      "  Corrective action on the moulding tool ",
      "Interview the night shift",
    ]);
    expect(Object.keys(found)).toEqual(["CAPA_REQUIRED"]);
    expect(found.CAPA_REQUIRED).toMatchObject({
      selected: true,
      title: "Open a CAPA for the sensor adhesive; Corrective action on the moulding tool",
    });
    expect(followUpsFromActions([])).toEqual({});
    expect(followUpsFromActions(["CAPA " + "x".repeat(400)]).CAPA_REQUIRED.title.length).toBe(300);
  });
});

describe("tasks", () => {
  it("still open their screens", () => {
    expect(taskDestination({ task_type: "REPORTABILITY_DECISION", investigation: null }).section).toBe("Complaints");
  });
});

describe("a case's regulatory review", () => {
  it("shows each complaint's reporting clock and leads to the watch", async () => {
    const { ReportingClocks } = await import("./sections/CaseReviews");
    const { WorkspaceContext } = await import("./workspaceContext");
    const api = { session: null, open: vi.fn(), notify: vi.fn(), work: {} } as never;
    const markup = renderToStaticMarkup(
      <WorkspaceContext.Provider value={api}>
        <ReportingClocks
          context={{
            reporting_clocks: [
              {
                complaint: { id: "c-1", business_id: "CMP000031" },
                state: "DUE_SOON",
                binding: {
                  window: "FDA MDR (30 calendar days)",
                  days: 30,
                  day_basis: "CALENDAR",
                  due_date: "2026-10-15",
                  state: "DUE_SOON",
                  days_left: 2,
                  triggers: ["DEATH"],
                },
                decision: null,
              },
              {
                complaint: { id: "c-2", business_id: "CMP000032" },
                state: "DECIDED",
                binding: null,
                decision: "REPORTED",
              },
            ],
          }}
        />
      </WorkspaceContext.Provider>,
    );
    expect(markup).toContain("CMP000031");
    expect(markup).toContain("Due in 2 days");
    expect(markup).toContain("FDA MDR (30 calendar days) · due 2026-10-15");
    expect(markup).toContain("Reported");
    expect(markup).toContain("Record decisions on the reportability watch");
    expect(
      renderToStaticMarkup(
        <WorkspaceContext.Provider value={api}>
          <ReportingClocks context={{}} />
        </WorkspaceContext.Provider>,
      ),
    ).toBe("");
  });
});
