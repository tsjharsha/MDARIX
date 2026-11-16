import { useContext, useMemo, useState } from "react";
import { ResolutionWithCauses } from "./caseIntelligence/RootCause";
import { BarList, ColumnChart, Panel } from "../../admin/console/charts";
import { chartWindowEnd, dailyCounts, titleCase, type Slice } from "../../admin/console/dashboardModel";
import { Tabs, listOf, useResource } from "../../customer-admin/shared";
import { WorkspaceContext, useCan, useReportedTab } from "../workspaceContext";
import { Stage2Experience } from "../../stage2/Stage2Experience";
import { Embedded, NeedsProduct, RecordTable } from "./common";
import { SIGNALS_TABS, parseSignalsTab, signalsTab, type SignalsTab } from "../signals";
import { SignalInbox } from "./SignalInbox";
import { DetectionRules } from "./DetectionRules";
import { TrendCheck } from "./TrendCheck";
import { ComplaintList } from "./ComplaintList";

/**
 * Signals: the signal inbox (triage), the complaints behind signals, and their trends. `tab` may carry the inbox's
 * filters or a signal to open (see signalsTab in ../signals.ts); a former tab name opens the tab that replaced it.
 */
export function SignalsSection({ tab }: { tab?: string }) {
  const canTriage = useCan("signal.triage");
  const tabs = SIGNALS_TABS.filter((item) => item !== "Detection rules" || canTriage);
  const [target, setTarget] = useState(() => parseSignalsTab(tab));
  const report = useContext(WorkspaceContext)?.reportTab;
  // Each new target (from a link, a task, the rules' run result) opens the inbox afresh with it.
  const [targetKey, setTargetKey] = useState(0);
  const [active, setActive] = useReportedTab<SignalsTab>(() =>
    (tabs as readonly string[]).includes(target.tab) ? target.tab : "Signal inbox",
  );
  const openSignal = (signal: string) => {
    setTarget({ ...parseSignalsTab("Signal inbox"), signal });
    setTargetKey((value) => value + 1);
    setActive("Signal inbox");
    report?.(signalsTab({ signal }));
  };
  return (
    <>
      <Tabs tabs={tabs} active={active} onChange={setActive} label="Trend sections">
        {active === "Signal inbox" && (
          <SignalInbox
            key={targetKey}
            initialFilters={target.filters}
            initialSignal={target.signal}
            // Back on the list, the signal is not opened again when the person returns to this tab.
            onSignalClosed={() => setTarget((current) => ({ ...current, signal: null }))}
          />
        )}
        {active === "Product complaints" && (
          <NeedsProduct>
            {(view) => (
              <Panel eyebrow={view.product.name ?? "Product"} title="Complaints for the selected version">
                <RecordTable
                  caption="Complaints"
                  idLabel="Complaint ID"
                  rows={view.complaints}
                  columns={["complaint_identifier", "event_timestamp", "recorded_timestamp", "status"]}
                  labels={{ event_timestamp: "Event date", recorded_timestamp: "Recorded" }}
                  empty={{
                    title: "No complaints recorded",
                    detail: "Complaints for this product version appear here.",
                  }}
                />
              </Panel>
            )}
          </NeedsProduct>
        )}
        {active === "Recent complaints" && (
          <Embedded>
            <Stage2Experience mode="signals" />
          </Embedded>
        )}
        {active === "Complaint list" && <ComplaintList />}
        {active === "Trends" && <Trends />}
        {active === "Trend check" && <TrendCheck onOpenSignal={openSignal} />}
        {active === "By resolution" && <ResolutionWithCauses />}
        {active === "Detection rules" && <DetectionRules onOpenSignal={openSignal} />}
      </Tabs>
    </>
  );
}

export function Trends() {
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
        : "Trends by event date · last 30 days",
    };
  }, [signals.data]);
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Signals" title={model.title} source={signals}>
        <ColumnChart data={model.trend} unit="signals" caption="latest 100 recorded trends" />
      </Panel>
      <Panel eyebrow="Signals" title="By recorded severity" source={signals}>
        {model.severity.length ? (
          <BarList items={model.severity} colour="series" />
        ) : (
          <p className="ac-muted">No trends recorded yet.</p>
        )}
        <p className="ac-note">Severity is shown only when the source system recorded it.</p>
      </Panel>
    </div>
  );
}
