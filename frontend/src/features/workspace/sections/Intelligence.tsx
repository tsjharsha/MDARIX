import { useState } from "react";
import { Tabs } from "../../customer-admin/shared";
import { AskMdarixPage } from "../../ask/AskMdarixPage";
import { RegulatoryCopilot } from "../../regulatory/RegulatoryCopilot";
import { RiskTraceabilityWorkspace } from "../../risk/RiskTraceabilityWorkspace";
import { ReportsPanel } from "../../reports/ReportsPanel";
import { useFeatureSet, useWorkspace } from "../workspaceContext";
import { offeredTab, tabsFor } from "../../../app/featureSet";
import { Embedded } from "./common";

const TABS = ["Ask MDARIX", "Regulatory copilot", "Risk & traceability", "Reports"] as const;
type Tab = (typeof TABS)[number];

export function IntelligenceSection({ tab }: { tab?: string }) {
  // Under the MVP feature set the regulatory copilot and risk & traceability are parked (featureSet.ts).
  const tabs = tabsFor("Intelligence", TABS, useFeatureSet());
  const [active, setActive] = useState<Tab>(() => offeredTab(tab, tabs, "Ask MDARIX"));
  const { work } = useWorkspace();
  return (
    <>
      <Tabs tabs={tabs} active={active} onChange={setActive} label="Intelligence sections">
        <Embedded>
          {active === "Ask MDARIX" && (
            <AskMdarixPage
              investigationId={work.investigationId || undefined}
              productVersionId={(work.view?.selected_version?.id as string | undefined) ?? undefined}
            />
          )}
          {active === "Regulatory copilot" && <RegulatoryCopilot />}
          {active === "Risk & traceability" && <RiskTraceabilityWorkspace />}
          {active === "Reports" && <ReportsPanel />}
        </Embedded>
      </Tabs>
    </>
  );
}
