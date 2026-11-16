import { Activity, Gauge, ShieldCheck } from "lucide-react";
import { BarList, Empty, Panel, RingMeter, StatTile, ToneBadge } from "../console/charts";
import type { Slice, Tone } from "../console/dashboardModel";
import { formatDate, useResource } from "../../customer-admin/shared";
import "./trialAi.css";

/*
 * Story step 9: the Platform Administrator closes the loop on a trial's AI. This month's use against the trial's own
 * (lower) limit, the model calls by outcome and feature, the trial provider chain, and the latest switch changes from
 * the trial's audit trail. Counts and metadata only: the server sends no record or prompt text.
 */

export type ChainLink = {
  position: number;
  name: string;
  state: "READY" | "RESTING" | "NOT_USABLE";
  resting_until: string | null;
};
export type SwitchEvent = {
  action: string;
  at: string | null;
  actor: string;
  reason: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  details: Record<string, unknown>;
};
export type TrialAiMetricsData = {
  organization_on: boolean;
  usage: { month: string; tokens_used: number; limit: number; percent: number; requests: number; refused: number };
  calls: {
    total: number;
    by_outcome: Record<string, number>;
    by_feature: Record<string, number>;
    last_at: string | null;
  };
  chain: ChainLink[];
  switch_events: SwitchEvent[];
};

export const aiMetricsPath = (tenantId: string) =>
  `/api/v1/platform-admin/trial-organizations/${encodeURIComponent(tenantId)}/ai-metrics`;

const OUTCOME_TONE: Record<string, Tone> = { ANSWERED: "good", INVALID_OUTPUT: "warning", FAILED: "critical" };
const CHAIN_WORDS: Record<ChainLink["state"], [string, Tone]> = {
  READY: ["Ready", "good"],
  RESTING: ["Resting", "warning"],
  NOT_USABLE: ["Not usable here", "critical"],
};

const words = (code: string) => code.charAt(0).toUpperCase() + code.slice(1).toLowerCase().replace(/_/g, " ");

/** The use tone: plenty left, getting close (80%), or used up. */
export const usageTone = (percent: number): Tone => (percent >= 100 ? "critical" : percent >= 80 ? "warning" : "good");

export const slices = (counts: Record<string, number>, tone: (key: string) => Tone): Slice[] =>
  Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .map(([key, count]) => ({ key, label: words(key), count, tone: tone(key) }));

/** One switch change in plain words: what changed, from what to what. */
export function switchChange(event: SwitchEvent): string {
  const after = event.new_values ?? {};
  switch (event.action) {
    case "AI_PROCESSING_SETTING_CHANGED":
      return after.ai_processing_allowed === undefined
        ? "AI allowance changed"
        : `AI for the organization turned ${after.ai_processing_allowed ? "on" : "off"}`;
    case "AI_FEATURE_SETTING_CHANGED":
      return `${words(String(event.details.feature ?? "A feature"))} turned ${after.enabled ? "on" : "off"}`;
    case "TRIAL_USER_AI_ACCESS_CHANGED":
      return `A user's AI set ${after.ai_access ? "Active" : "Inactive"}${event.details.bulk ? " (set all)" : ""}`;
    case "TRIAL_AI_ACCESS_BULK_CHANGED":
      return `Everyone set ${event.details.value ? "Active" : "Inactive"}: ${Number(event.details.count ?? 0)} changed`;
    default:
      return words(event.action);
  }
}

export function TrialAiMetrics({ tenantId }: { tenantId: string }) {
  const metrics = useResource<TrialAiMetricsData>(aiMetricsPath(tenantId));
  const data = metrics.data;
  return (
    <Panel eyebrow="AI this month" title="AI use, provider chain and switch changes" source={metrics}>
      {data && (
        <>
          <div className="to-ai-metrics">
            <RingMeter value={data.usage.tokens_used} total={data.usage.limit} label="of the trial's AI limit" />
            <StatTile
              label="Tokens used"
              value={data.usage.tokens_used}
              detail={`of ${data.usage.limit.toLocaleString()} this month`}
              icon={<Gauge size={18} />}
              tone={usageTone(data.usage.percent)}
            />
            <StatTile
              label="Model calls"
              value={data.calls.total}
              detail={data.calls.last_at ? `last ${formatDate(data.calls.last_at)}` : "none this month"}
              icon={<Activity size={18} />}
            />
            <StatTile
              label="Answered from rules"
              value={data.usage.refused}
              detail="refused before any AI service was called"
              icon={<ShieldCheck size={18} />}
            />
          </div>
          <div className="to-ai-grid">
            <div>
              <h3 className="to-ai-sub">Calls by outcome</h3>
              {data.calls.total ? (
                <BarList items={slices(data.calls.by_outcome, (key) => OUTCOME_TONE[key] ?? "neutral")} />
              ) : (
                <Empty
                  title="No model calls yet"
                  detail="Calls appear here when trial users use AI on the sample data."
                />
              )}
              {data.calls.total > 0 && (
                <>
                  <h3 className="to-ai-sub">Calls by feature</h3>
                  <BarList items={slices(data.calls.by_feature, () => "neutral")} colour="series" />
                </>
              )}
            </div>
            <div>
              <h3 className="to-ai-sub">Trial provider chain</h3>
              {data.chain.length ? (
                <ol className="to-ai-chain" aria-label="Trial provider chain, in order">
                  {data.chain.map((link) => (
                    <li key={link.name}>
                      <span className="to-ai-chain-pos">{link.position}</span>
                      <code>{link.name}</code>
                      <ToneBadge tone={CHAIN_WORDS[link.state][1]} label={CHAIN_WORDS[link.state][0]} />
                      {link.resting_until && <small className="ac-muted">until {formatDate(link.resting_until)}</small>}
                    </li>
                  ))}
                </ol>
              ) : (
                <Empty
                  title="No trial provider chain"
                  detail="MDARIX has not set the AI services for free trials, so AI stays off for every trial."
                />
              )}
            </div>
          </div>
          <h3 className="to-ai-sub">Switch changes (audit trail)</h3>
          {data.switch_events.length ? (
            <ul className="to-ai-events">
              {data.switch_events.map((event, index) => (
                <li key={`${event.action}-${event.at}-${index}`}>
                  <strong>{switchChange(event)}</strong>
                  <span className="ac-muted">
                    {event.actor} · {event.at ? formatDate(event.at) : "—"}
                  </span>
                  {event.reason && <q>{event.reason}</q>}
                </li>
              ))}
            </ul>
          ) : (
            <Empty
              title="No switch changes yet"
              detail="Each AI switch change is listed here with who, when and why."
            />
          )}
        </>
      )}
    </Panel>
  );
}
