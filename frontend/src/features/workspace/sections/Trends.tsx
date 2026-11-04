import { useState } from "react";
import { FileSearch } from "lucide-react";
import { Tabs } from "../../customer-admin/shared";
import { NEW_PLACES } from "../../../app/linkTable";
import { offeredTab } from "../../../app/featureSet";
import { renamed, useReportedTab, useWorkspace } from "../workspaceContext";
import { withTabParam } from "../workspaceAddress";
import { parseSignalsTab } from "../signals";
import { SignalInbox } from "./SignalInbox";
import { TrendCheck } from "./TrendCheck";
import { ResolutionTrend } from "./Dispositions";
import { Trends } from "./Signals";

export const TRENDS_TABS = NEW_PLACES.Trends.tabs;
type TrendsTab = (typeof TRENDS_TABS)[number];

/**
 * Trends on the new navigation (0.10.68): is a product problem rising? It opens on the trend check (each product
 * version against its own history), then the trends to review (the classic signal inbox), complaints over time and
 * by resolution. A trend opens an investigation; the list of investigations is one click away. The detection rules
 * are in Settings › Trend rules.
 */
export function TrendsSection({ tab }: { tab?: string }) {
  const { open, reportTab, personaTabs = [] } = useWorkspace();
  // The inbox's filters and the trend to open come in the address (Trends to review?priority=HIGH&signal=SIG000023).
  const [target, setTarget] = useState(() => parseSignalsTab(renamed(tab, "Signal inbox")));
  const [targetKey, setTargetKey] = useState(0);
  const [active, setActive] = useReportedTab<TrendsTab>(() => offeredTab(tab, TRENDS_TABS, "Trend check"));
  const openTrend = (signal: string) => {
    setTarget({ ...parseSignalsTab("Signal inbox"), signal });
    setTargetKey((value) => value + 1);
    setActive("Trends to review");
    reportTab?.(withTabParam("Trends to review", "signal", signal), "replace");
  };
  return (
    <>
      {/* The Investigations tab is one click away for a persona that has it (0.10.87). */}
      {!personaTabs.includes("investigations") && (
        <div className="ca-action-row uw-list-actions">
          <button type="button" className="ac-secondary" onClick={() => open("Investigations", "All investigations")}>
            <FileSearch size={15} aria-hidden="true" /> Investigations
          </button>
        </div>
      )}
      <Tabs tabs={TRENDS_TABS} active={active} onChange={setActive} label="Trend sections">
        {active === "Trend check" && <TrendCheck onOpenSignal={openTrend} />}
        {active === "Trends to review" && (
          <SignalInbox
            key={targetKey}
            initialFilters={target.filters}
            initialSignal={target.signal}
            onSignalClosed={() => setTarget((current) => ({ ...current, signal: null }))}
          />
        )}
        {active === "Over time" && <Trends />}
        {active === "By resolution" && <ResolutionTrend />}
      </Tabs>
    </>
  );
}
