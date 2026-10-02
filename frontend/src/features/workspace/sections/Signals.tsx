import { useMemo, useState } from "react";
import { BarList, ColumnChart, Panel } from "../../admin/console/charts";
import { chartWindowEnd, dailyCounts, titleCase, type Slice } from "../../admin/console/dashboardModel";
import { Tabs, listOf, useResource } from "../../customer-admin/shared";
import { Stage2Experience } from "../../stage2/Stage2Experience";
import { Embedded, NeedsProduct, RecordTable } from "./common";

const TABS = ["Product complaints", "All signals", "Trends"] as const;
type Tab = (typeof TABS)[number];

export function SignalsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Product complaints",
  );
  return (
    <>
      <p className="ca-lede">Signals are recorded observations. They are not conclusions about cause.</p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Signal sections" />
      {active === "Product complaints" && (
        <NeedsProduct>
          {(view) => (
            <Panel eyebrow={view.product.name ?? "Product"} title="Complaints for the selected version">
              <RecordTable
                caption="Complaints"
                rows={view.complaints}
                columns={["complaint_identifier", "event_timestamp", "recorded_timestamp", "status"]}
                empty={{ title: "No complaints recorded", detail: "Complaints for this product version appear here." }}
              />
            </Panel>
          )}
        </NeedsProduct>
      )}
      {active === "All signals" && (
        <Embedded>
          <Stage2Experience mode="signals" />
        </Embedded>
      )}
      {active === "Trends" && <Trends />}
    </>
  );
}

function Trends() {
  const signals = useResource<any>("/api/v1/analytics/signals");
  const rows = listOf(signals.data?.signals);
  const model = useMemo(() => {
    const bySeverity = new Map<string, number>();
    for (const row of rows) {
      const key = row.severity ? titleCase(String(row.severity)) : "Not recorded";
      bySeverity.set(key, (bySeverity.get(key) ?? 0) + 1);
    }
    const severity: Slice[] = [...bySeverity.entries()]
      .map(([label, count]) => ({ key: label, label, count, tone: "neutral" as const }))
      .sort((a, b) => b.count - a.count);
    const timestamps = rows.map((row) => row.event_timestamp);
    const span = chartWindowEnd(timestamps, 30);
    return {
      severity,
      trend: dailyCounts(timestamps, 30, span.end),
      // Older data: show the 30 days up to the latest signal, and say so in the title.
      title: span.shifted
        ? `Signals by event date · 30 days to ${span.end.toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
            timeZone: "UTC",
          })} (latest signal)`
        : "Signals by event date · last 30 days",
    };
  }, [signals.data]);
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Signals" title={model.title} state={signals.state} error={signals.error}>
        <ColumnChart data={model.trend} unit="signals" caption="latest 100 recorded signals" />
      </Panel>
      <Panel eyebrow="Signals" title="By recorded severity" state={signals.state} error={signals.error}>
        {model.severity.length ? (
          <BarList items={model.severity} colour="series" />
        ) : (
          <p className="ac-muted">No signals recorded yet.</p>
        )}
        <p className="ac-note">Severity is shown only when the source system recorded it.</p>
      </Panel>
    </div>
  );
}
