import { useState } from "react";
import { Sparkles, TrendingUp } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { useCanRunAi, useWorkspace } from "../workspaceContext";
import {
  aiSummaryNote,
  insightPath,
  chanceText,
  summaryPath,
  trendBasisText,
  trendCountText,
  trendResultOf,
  type SignalInsight,
  type SignalSummary,
  type TrendItem,
} from "../signalAi";
import { InlineError } from "./boardParts";
import { TrustBadge } from "./TrustBadge";

/**
 * What a signal's complaints have in common (from their records, or written by AI and checked sentence by sentence;
 * every sentence names the complaints it rests on) and the trend check of its product version.
 */
export function SignalInsightPanel({ signalId }: { signalId: string }) {
  const insight = useResource<SignalInsight>(insightPath(signalId));
  const { notify } = useWorkspace();
  const canRunAi = useCanRunAi();
  const [ai, setAi] = useState<SignalSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const write = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await send<SignalSummary>(summaryPath(signalId), "POST");
      setAi(result ?? null);
      if (result?.author === "AI")
        notify("The AI summary is ready; every sentence was checked against the complaints.");
    } catch (failure) {
      setError(errorText(failure, "The AI summary could not be written."));
    } finally {
      setBusy(false);
    }
  };
  const summary = ai ?? insight.data?.summary ?? null;
  return (
    <Panel
      eyebrow="What the complaints have in common"
      title={summary?.author === "AI" ? "AI summary" : "Summary from the records"}
      source={insight}
      action={
        canRunAi ? (
          <button type="button" className="ac-secondary" disabled={busy} onClick={() => void write()}>
            <Sparkles size={15} aria-hidden="true" /> {busy ? "Writing…" : ai ? "Write again" : "Write an AI summary"}
          </button>
        ) : undefined
      }
    >
      {summary && <SummaryView summary={summary} />}
      <InlineError text={error} />
      {insight.data && <TrendLine trend={insight.data.trend} />}
    </Panel>
  );
}

/** The summary's sentences with the complaints each cites (exported for its unit test). */
export function SummaryView({ summary }: { summary: SignalSummary }) {
  const note = aiSummaryNote(summary);
  if (!summary.sentences.length) return <p className="ac-muted">The signal has no complaints to summarize.</p>;
  return (
    <>
      {summary.author === "AI" && summary.ai?.label && (
        <p className="uw-ai-label">
          <Sparkles size={14} aria-hidden="true" /> {summary.ai.label}
        </p>
      )}
      {summary.author === "AI" && summary.ai?.trust && (
        <div className="uw-ai-head">
          <TrustBadge trust={summary.ai.trust} />
        </div>
      )}
      <ul className="uw-sum-list">
        {summary.sentences.map((sentence, index) => (
          <li key={index}>
            <span>{sentence.text}</span>
            <span className="uw-sum-cites" aria-label="Complaints cited">
              {sentence.complaints.map((ref) => (
                <code key={ref}>{ref}</code>
              ))}
            </span>
          </li>
        ))}
      </ul>
      {summary.author === "AI" && (summary.ai?.dropped?.length ?? 0) > 0 && (
        <p className="ac-muted">
          {summary.ai!.dropped!.length} sentence{summary.ai!.dropped!.length === 1 ? "" : "s"} left out: not backed by
          the signal&apos;s complaints, or claiming a cause.
        </p>
      )}
      {note && <p className="ac-muted">{note}</p>}
    </>
  );
}

/** The trend check of the signal's own version and problem (exported for its unit test). */
export function TrendLine({ trend }: { trend: TrendItem | null }) {
  if (!trend) return <p className="ac-muted">No trend check for this signal: it names no product.</p>;
  const result = trendResultOf(trend.result);
  return (
    <section className="ca-drawer-section uw-trend-line" aria-label="Trend check">
      <h3>
        <TrendingUp size={16} aria-hidden="true" /> Trend check
      </h3>
      <p>
        <ToneBadge tone={result.tone} label={result.label} /> <strong>{trendCountText(trend)}</strong>{" "}
        {trend.recent_days < 30
          ? `in the ${trend.recent_days} days since its release`
          : `in the last ${trend.recent_days} days`}{" "}
        · {trendBasisText(trend)} · {chanceText(trend)}
      </p>
      <p className="ac-muted">{trend.sentence}</p>
    </section>
  );
}
