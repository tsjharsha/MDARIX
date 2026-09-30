import { useState } from "react";
import { Tabs } from "../../customer-admin/shared";
import { AskMdarixPage } from "../../ask/AskMdarixPage";
import { RegulatoryCopilot } from "../../regulatory/RegulatoryCopilot";
import { RiskTraceabilityWorkspace } from "../../risk/RiskTraceabilityWorkspace";
import { useWorkspace } from "../workspaceContext";
import { Embedded } from "./common";

const TABS = ["Ask MDARIX", "Regulatory copilot", "Risk & traceability"] as const;
type Tab = (typeof TABS)[number];

export function IntelligenceSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Ask MDARIX",
  );
  const { work } = useWorkspace();
  return (
    <>
      <p className="ca-lede">
        AI answers use only your organization's authorized records, show their sources and limits, and never make the
        decision for you.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Intelligence sections" />
      <Embedded>
        {active === "Ask MDARIX" && (
          <AskMdarixPage
            investigationId={work.investigationId || undefined}
            productVersionId={(work.view?.selected_version?.id as string | undefined) ?? undefined}
          />
        )}
        {active === "Regulatory copilot" && <RegulatoryCopilot />}
        {active === "Risk & traceability" && <RiskTraceabilityWorkspace />}
      </Embedded>
    </>
  );
}
