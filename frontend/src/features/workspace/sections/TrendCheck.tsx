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
import { IMPORTED_SOURCE } from "../complaintList";
import { inData } from "../home";

/**
 * Signals › Trend check: every product version (or version and problem, or complaint type) against its own history,
 * the notable ones first. Every complaint counts, whatever its status. A check beside the count rule: it raises no
 * signal by itself; a triage lead raises one from a notable group in one click.
 */
export function TrendCheck({ onOpenSignal }: { onOpenSignal: (reference: string) => void }) {
  const { notify, open, session, work, dataSource } = useWorkspace();
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
  const navigation = useNavigation();
  // The Sample · Your data switch decides the groups shown (0.10.85, D3.5): your data never shows the sample's rise.
  const shownItems = (board.data?.items ?? []).filter((item) =>
    navigation === "new" ? inData(item.product.identifier, dataSource, false) : true,
  );
  const summary = board.data?.summary;
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
      {navigation === "new" ? (
        board.data && <TrendHeroes board={board.data} action={action} source={dataSource} />
      ) : (
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
      )}
      <InlineError text={error} />
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
          <TrendPerUnit items={shownItems} />
          <Table
            caption="Trend check"
            rows={shownItems}
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

/** The version before, or the group's own history, as complaints in the same window as the recent count. */
export function beforeRate(row: Pick<TrendItem, "history" | "history_days" | "recent_days">): number {
  return row.history_days > 0 ? (row.history / row.history_days) * row.recent_days : 0;
}

/**
 * Trends' hero on the new navigation (0.10.85, D3.5; the approved design): "Is a product problem rising?" answered per
 * group in one sentence, with three bars (observed, expected, the version before or its own history in the same
 * window) and "How we compared" folded. With nothing rising, the group closest to rising says so; a short history says
 * plainly what it can and cannot show.
 */
export function TrendHeroes({
  board,
  action,
  source,
}: {
  board: TrendBoard;
  action: (row: TrendItem) => React.ReactNode;
  /** The Sample · Your data switch: on your data, your products only (never the sample's rise). */
  source?: string;
}) {
  const yours = source === IMPORTED_SOURCE;
  const items = (board.items ?? []).filter((item) => inData(item.product.identifier, source, false));
  const rising = items.filter((item) => item.result === "SIGNIFICANT" || item.result === "ELEVATED");
  const assessed = items.filter((item) => item.result === "STEADY").sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0));
  const shown = rising.length ? rising : assessed.slice(0, 1);
  const tested = rising.length + assessed.length;
  const counted = items.reduce((sum, item) => sum + item.recent, 0);
  return (
    <div className="uw-trend-heroes">
      {shown.map((row) => {
        const top = Math.max(row.recent, row.expected, beforeRate(row), 0.01);
        const bars: Array<[string, number, string]> = [
          ["Observed", row.recent, row.result === "STEADY" ? "is-ok" : "is-over"],
          ["Expected", row.expected, "is-muted"],
          [row.baseline === "PREVIOUS_VERSION" ? "Version before" : "Its own history", beforeRate(row), "is-muted"],
        ];
        return (
          <section key={row.key} className="uw-card uw-trend-hero" aria-label={row.name}>
            <span className={`ms-chip uw-trend-verdict is-${row.result.toLowerCase()}`}>{trendResultLabel(row)}</span>
            <h2>{risingSentence(row)}</h2>
            <div
              className="uw-bars"
              role="img"
              aria-label={bars.map(([label, value]) => `${label} ${value.toFixed(1)}`).join(", ")}
            >
              {bars.map(([label, value, tone]) => (
                <div key={label} className="uw-bar-row">
                  <span>{label}</span>
                  <span className="uw-bar-track">
                    <span
                      className={`uw-bar-fill ${tone}`}
                      style={{ width: `${Math.max(3, Math.round((value / top) * 100))}%` }}
                    />
                  </span>
                  <b className="uw-num">{label === "Observed" ? value : value.toFixed(1)}</b>
                </div>
              ))}
            </div>
            <p className="uw-trend-note">
              Each bar counts complaints in the last {row.recent_days} days: the expected number and the earlier one
              come from {trendBaselineText(row).replace(/^Own history/, "its own history")}.
            </p>
            <details className="uw-more uw-trend-how">
              <summary>How we compared</summary>
              <p>{comparisonLine(row)}</p>
              <p>{chanceText(row)}</p>
              {perUnitHint(board) && <p>{perUnitHint(board)}</p>}
            </details>
            <div className="ca-action-row">{action(row)}</div>
          </section>
        );
      })}
      {!rising.length && (
        <section className="uw-card uw-trend-hero" aria-label="What the history can show">
          <span className="ms-chip uw-trend-verdict is-steady">
            {tested ? "No version is rising against its own history" : "Too early to compare"}
          </span>
          <h2>
            {tested
              ? `${tested} ${tested === 1 ? "group" : "groups"} compared with their own history: none rising.`
              : `${counted} recent ${counted === 1 ? "complaint" : "complaints"} across ${items.length} ${items.length === 1 ? "group" : "groups"}; none can be compared with a history yet.`}
          </h2>
          {!tested && items.length > 0 && (
            <div
              className="uw-bars"
              role="img"
              aria-label={items.map((item) => `${item.name}: ${item.recent}`).join(", ")}
            >
              {items.slice(0, 4).map((item) => (
                <div key={item.key} className="uw-bar-row">
                  <span>{item.problem ?? item.product_version?.version_identifier ?? item.name}</span>
                  <span className="uw-bar-track">
                    <span
                      className="uw-bar-fill is-muted"
                      style={{
                        width: `${Math.max(3, Math.round((item.recent / Math.max(...items.map((x) => x.recent), 1)) * 100))}%`,
                      }}
                    />
                  </span>
                  <b className="uw-num">{item.recent}</b>
                </div>
              ))}
            </div>
          )}
          {(yours || !tested) && (
            <p className="uw-trend-note">
              {yours ? "Your data" : "This data"} gives each group {board.recent_days} recent days to count. A rise is
              judged against a version's own history ({board.history_days} days before) or the version it replaced, and
              per unit in the field once your lots file gives quantities. A group with fewer than {board.min_complaints}{" "}
              complaints, or a younger history, is listed, counted and never called a rise: what it can show now is how
              many complaints each group has, and which lots they share.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
