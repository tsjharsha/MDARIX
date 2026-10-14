import { useState } from "react";
import { Activity, AlertTriangle, Plus, TrendingUp } from "lucide-react";
import { Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Table, errorText, send, useResource } from "../../customer-admin/shared";
import { sectionAllowed, useCan, useWorkspace } from "../workspaceContext";
import {
  TREND_GROUPS,
  canRaiseFromTrend,
  pValueText,
  signalFromTrend,
  trendCountText,
  trendHeadline,
  trendPath,
  trendResultOf,
  type TrendBoard,
  perUnitHint,
  trendBaselineText,
  trendBasisText,
  trendResultLabel,
  type TrendGroup,
  type TrendItem,
} from "../signalAi";
import { ChipFilter, Hero, InlineError, ProductFilter } from "./boardParts";

/**
 * Signals › Trend check: every product version (or version and problem, or complaint type) against its own history,
 * the notable ones first. Every complaint counts, whatever its status. A check beside the count rule: it raises no
 * signal by itself; a triage lead raises one from a notable group in one click.
 */
export function TrendCheck({ onOpenSignal }: { onOpenSignal: (reference: string) => void }) {
  const { notify, open, session } = useWorkspace();
  const canTriage = useCan("signal.triage");
  const [group, setGroup] = useState<TrendGroup>("version");
  const [product, setProduct] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const board = useResource<TrendBoard>(trendPath(group, product));
  const headline = trendHeadline(board.data);
  const summary = board.data?.summary;
  const raise = async (item: TrendItem) => {
    setBusy(item.key);
    setError("");
    try {
      const made = await send<{ id: string; business_id?: string }>(
        "/api/v1/triage/signals",
        "POST",
        signalFromTrend(item),
      );
      notify(`${made?.business_id ?? "A signal"} was raised from the trend check for ${item.name}.`);
      board.reload();
      if (made?.business_id || made?.id) onOpenSignal(String(made.business_id ?? made.id));
    } catch (failure) {
      setError(errorText(failure, "The signal was not raised."));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="ac-overview">
      <Hero
        tone={board.data ? headline.tone : "neutral"}
        icon={<TrendingUp size={28} />}
        eyebrow="Trend check · last 30 days against each version's own history"
        title={headline.title}
        detail={headline.detail}
      >
        {perUnitHint(board.data) && (
          <div className="uw-trend-hint" role="note">
            <p>{perUnitHint(board.data)}</p>
            {sectionAllowed("Import data", session?.allowed_menu, session?.business_permissions) && (
              <button type="button" className="ac-secondary" onClick={() => open("Import data")}>
                Add lot quantities
              </button>
            )}
          </div>
        )}
      </Hero>
      <div className="uw-cr-stats">
        <StatTile
          label="Significant rise"
          value={summary ? summary.significant : null}
          detail="Chance under 1% if nothing changed"
          icon={<AlertTriangle size={18} />}
          tone={summary?.significant ? "critical" : undefined}
        />
        <StatTile
          label="Higher than usual"
          value={summary ? summary.elevated : null}
          detail="Chance under 5%"
          icon={<TrendingUp size={18} />}
          tone={summary?.elevated ? "warning" : undefined}
        />
        <StatTile
          label="Groups checked"
          value={summary ? summary.groups : null}
          detail={summary ? `${summary.too_few + summary.short_history} not assessed (too few or too new)` : ""}
          icon={<Activity size={18} />}
        />
        <StatTile
          label="Complaints counted"
          value={summary ? summary.complaints_counted : null}
          detail="Every status; dismissed records left out"
          icon={<Activity size={18} />}
        />
      </div>
      <Panel eyebrow="Signals" title="Trend check" source={board}>
        <div className="uw-cr-toolbar">
          <ChipFilter label="Group complaints" options={TREND_GROUPS} value={group} onChange={setGroup} />
          <ProductFilter value={product} onChange={setProduct} />
        </div>
        <InlineError text={error} />
        <Table
          caption="Trend check"
          rows={board.data?.items ?? []}
          rowKey={(row) => row.key}
          empty={{ title: "No complaints in the period", detail: "Groups appear once complaints are recorded." }}
          columns={[
            { key: "name", label: "Group", render: (row: TrendItem) => <strong>{row.name}</strong> },
            {
              key: "result",
              label: "Result",
              render: (row: TrendItem) => {
                const result = trendResultOf(row.result);
                return <ToneBadge tone={result.tone} label={trendResultLabel(row)} />;
              },
            },
            {
              key: "recent",
              label: "Last 30 days",
              numeric: true,
              render: (row: TrendItem) => trendCountText(row),
            },
            {
              key: "history",
              label: "Compared with",
              render: (row: TrendItem) => trendBaselineText(row),
            },
            {
              key: "basis",
              label: "Counted",
              render: (row: TrendItem) => trendBasisText(row),
            },
            { key: "p_value", label: "Chance", render: (row: TrendItem) => pValueText(row.p_value) },
            {
              key: "signals",
              label: "",
              render: (row: TrendItem) =>
                row.open_signals.length ? (
                  <button
                    type="button"
                    className="ac-link"
                    onClick={() => onOpenSignal(String(row.open_signals[0].business_id ?? row.open_signals[0].id))}
                  >
                    {row.open_signals[0].business_id ?? "Open signal"}
                  </button>
                ) : canTriage && canRaiseFromTrend(row) ? (
                  <button
                    type="button"
                    className="ac-secondary"
                    disabled={busy === row.key}
                    onClick={() => void raise(row)}
                  >
                    <Plus size={14} aria-hidden="true" /> {busy === row.key ? "Raising…" : "Raise a signal"}
                  </button>
                ) : null,
            },
          ]}
        />
        <p className="ac-note">{board.data?.note}</p>
      </Panel>
    </div>
  );
}
