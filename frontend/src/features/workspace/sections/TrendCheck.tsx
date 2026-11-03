import { useEffect, useState } from "react";
import { Activity, AlertTriangle, Plus, TrendingUp } from "lucide-react";
import { Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { Table, errorText, send, useResource } from "../../customer-admin/shared";
import { sectionAllowed, useCan, useNavigation, useTabParam, useWorkspace } from "../workspaceContext";
import {
  TREND_GROUPS,
  canRaiseFromTrend,
  chanceText,
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
  TREND_BASIS,
  comparisonLine,
  risingSentence,
} from "../signalAi";
import { ChipFilter, Hero, InlineError, ProductFilter } from "./boardParts";
import { BasisLine } from "../../shared/Basis";
import { Bars, BarsTable, ChartOrTable, type BarRow } from "./WowCharts";

/**
 * Signals › Trend check: every product version (or version and problem, or complaint type) against its own history,
 * the notable ones first. Every complaint counts, whatever its status. A check beside the count rule: it raises no
 * signal by itself; a triage lead raises one from a notable group in one click.
 */
export function TrendCheck({ onOpenSignal }: { onOpenSignal: (reference: string) => void }) {
  const { notify, open, session, work } = useWorkspace();
  const canTriage = useCan("signal.triage");
  const [group, setGroup] = useState<TrendGroup>("version");
  const [product, setProduct] = useState("");
  // A story opens the trend check on its product, by the identifier people read (?product=SAMPLE-ORBIT-300, 0.10.71).
  const [named] = useTabParam("product", "replace");
  const namedId = named ? work?.products?.find((item) => item.product_identifier === named)?.id : undefined;
  useEffect(() => {
    if (namedId) setProduct(namedId);
  }, [namedId]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const board = useResource<TrendBoard>(trendPath(group, product));
  const headline = trendHeadline(board.data);
  const summary = board.data?.summary;
  const navigation = useNavigation();
  const rising = (board.data?.items ?? []).filter(
    (item) => item.result === "SIGNIFICANT" || item.result === "ELEVATED",
  );
  // The one action on a group: open its trend, or raise one (the table and the lead sentences share it).
  const action = (row: TrendItem) =>
    row.open_signals.length ? (
      <button
        type="button"
        className="ac-link"
        onClick={() => onOpenSignal(String(row.open_signals[0].business_id ?? row.open_signals[0].id))}
      >
        {row.open_signals[0].business_id ?? "Open trend"}
      </button>
    ) : canTriage && canRaiseFromTrend(row) ? (
      <button type="button" className="ac-secondary" disabled={busy === row.key} onClick={() => void raise(row)}>
        <Plus size={14} aria-hidden="true" /> {busy === row.key ? "Raising…" : "Raise a trend"}
      </button>
    ) : null;
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
      setError(errorText(failure, "The trend was not raised."));
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
            {sectionAllowed(
              "Import data",
              session?.allowed_menu,
              session?.business_permissions,
              session?.sample_only,
            ) && (
              <button type="button" className="ac-secondary" onClick={() => open("Import data")}>
                Add lot quantities
              </button>
            )}
          </div>
        )}
      </Hero>
      {navigation === "new" && board.data && (
        // One sentence per rising group, then its comparison basis in one line (0.10.72, B5).
        <section className="uw-trend-lead" aria-label="Rising groups">
          {rising.length ? (
            <ul>
              {rising.map((row) => (
                <li key={row.key}>
                  <p>
                    <strong>{risingSentence(row)}</strong>
                  </p>
                  <p className="uw-cr-meta">{comparisonLine(row)}</p>
                  {action(row)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="ac-muted">No group is rising against its own history.</p>
          )}
          <InlineError text={error} />
        </section>
      )}
      <Revealed when={navigation === "new"} summary="All groups, the method and the chart">
        <div className="uw-cr-stats">
          <StatTile
            label="Significant rise"
            value={summary ? summary.significant : null}
            detail="Chance under 1% if nothing changed, allowing for the groups assessed"
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
            detail={
              summary
                ? `${summary.groups_tested ?? summary.groups - summary.too_few - summary.short_history} assessed; ${summary.too_few + summary.short_history} too few or too new`
                : ""
            }
            icon={<Activity size={18} />}
          />
          <StatTile
            label="Complaints counted"
            value={summary ? summary.complaints_counted : null}
            detail={
              summary?.linked_records
                ? "Every status; dismissed records left out; an event linked from several records counts once"
                : "Every status; dismissed records left out"
            }
            icon={<Activity size={18} />}
          />
        </div>
        <Panel eyebrow="Trends" title="Trend check" source={board}>
          <div className="uw-cr-toolbar">
            <ChipFilter label="Group complaints" options={TREND_GROUPS} value={group} onChange={setGroup} />
            <ProductFilter value={product} onChange={setProduct} />
          </div>
          <InlineError text={error} />
          <TrendPerUnit items={board.data?.items ?? []} />
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
                render: (row: TrendItem) =>
                  row.recent_days < 30 ? `${trendCountText(row)} in ${row.recent_days} days` : trendCountText(row),
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
              { key: "p_value", label: "Chance", render: (row: TrendItem) => chanceText(row) },
              {
                key: "signals",
                label: "",
                render: (row: TrendItem) => action(row),
              },
            ]}
          />
          <p className="ac-note">{board.data?.note}</p>
          <BasisLine ids={TREND_BASIS} />
        </Panel>
      </Revealed>
    </div>
  );
}

/** On the new navigation the statistics, every group, the grouping controls and the chart are revealed on request. */
function Revealed({ when, summary, children }: { when: boolean; summary: string; children: React.ReactNode }) {
  return when ? (
    <details className="uw-more">
      <summary>{summary}</summary>
      {children}
    </details>
  ) : (
    <>{children}</>
  );
}

/**
 * The trend per unit (wow screen 3): each assessed group's complaints in the last 30 days beside what the earlier
 * average predicts for the units in the field (or the days, for a product counted by calendar). The groups that rose
 * come first and say so in words; at most eight, the table lists them all.
 */
export function TrendPerUnit({ items }: { items: TrendItem[] }) {
  const rank = (item: TrendItem) => (item.result === "SIGNIFICANT" ? 0 : item.result === "ELEVATED" ? 1 : 2);
  const assessed = items
    .filter((item) => item.expected > 0 && item.p_value !== null)
    .sort((a, b) => rank(a) - rank(b) || (b.ratio ?? 0) - (a.ratio ?? 0));
  const row = (item: TrendItem): BarRow => ({
    key: item.key,
    label: item.name,
    value: item.recent,
    valueText: `${item.recent} in the last ${item.recent_days} days`,
    reference: item.expected,
    referenceText: `the earlier average predicts ${item.expected.toLocaleString("en-US", { maximumFractionDigits: 2 })}${item.basis === "UNITS" ? " for its units in the field" : ""}`,
    flag: rank(item) < 2 ? trendResultLabel(item) : null,
  });
  if (!assessed.length) return null;
  return (
    <ChartOrTable
      title="Complaints against the earlier average"
      chart={<Bars rows={assessed.slice(0, 8).map(row)} label="Complaints against the earlier average" />}
      table={
        <BarsTable
          rows={assessed.map(row)}
          caption="Complaints against the earlier average"
          columns={["Group", "Last 30 days", "The earlier average predicts"]}
        />
      }
      note="The bar is what arrived; the marker is what the group's earlier average predicts. A rise counts only when it is unlikely to be chance."
    />
  );
}
