import { useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { Tabs } from "../../customer-admin/shared";
import { DecisionCenterView } from "../../investigator/DecisionCenterView";
import { SignatureVerificationWorkspace } from "../../signature/SignatureVerificationWorkspace";
import { useWorkspace } from "../workspaceContext";
import { Embedded } from "./common";
import { NextStepsPanel } from "./NextSteps";

const TABS = ["Decision center", "Verify a signature"] as const;
type Tab = (typeof TABS)[number];

export function DecisionsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Decision center",
  );
  const { work } = useWorkspace();
  return (
    <>
      <p className="ca-lede">
        Only people with approval authority can sign. Signing asks you to confirm your identity and is recorded with the
        exact content you approved.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Decision sections">
        {active === "Decision center" &&
          (work.investigationId ? (
            <Embedded>
              <DecisionCenterView
                investigationId={work.investigationId}
                temporalMode={work.mode}
                asOf={work.asOf}
                nextSteps={<NextStepsPanel key={work.investigationId} investigationId={work.investigationId} />}
              />
            </Embedded>
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation first"
                detail="Decisions belong to an investigation. Pick one in the context bar above."
              />
            </Panel>
          ))}
        {active === "Verify a signature" && (
          <Embedded>
            <SignatureVerificationWorkspace />
          </Embedded>
        )}
      </Tabs>
    </>
  );
}
