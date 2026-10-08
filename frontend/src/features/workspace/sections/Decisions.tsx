import { useEffect, useRef, useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { Tabs } from "../../customer-admin/shared";
import { DecisionCenterView } from "../../investigator/DecisionCenterView";
import { SignatureVerificationWorkspace } from "../../signature/SignatureVerificationWorkspace";
import { displayId } from "../../../app/displayId";
import { useCan, useWorkspace } from "../workspaceContext";
import { Embedded } from "./common";
import { NextStepsPanel } from "./NextSteps";
import { ApprovalsPanel } from "./DecisionApprovals";
import { CaseDecisionPanel } from "./CaseDecision";
import { parseDecisionTab, tabName } from "../decisionTabs";
import type { QueueRow } from "../humanDecision";

const TABS = ["Approvals", "Decision", "Decision center", "Verify a signature"] as const;
type Tab = (typeof TABS)[number];

export function DecisionsSection({ tab }: { tab?: string }) {
  const { work } = useWorkspace();
  // Approvals (the queue of briefs awaiting a signature) is for people who may sign; it is their first tab.
  const canSign = useCan("decision.sign");
  const tabs = TABS.filter((item) => item !== "Approvals" || canSign);
  const requested = tabName(tab);
  const [active, setActive] = useState<Tab>(() =>
    (tabs as readonly string[]).includes(requested) ? (requested as Tab) : canSign ? "Approvals" : "Decision center",
  );
  // A case opened from the approvals queue or the dashboard, which the context bar may not hold (another product).
  const [opened, setOpened] = useState<{ id: string; label: string | null } | null>(() => {
    const caseId = parseDecisionTab(tab).caseId;
    return caseId ? { id: caseId, label: null } : null;
  });
  // Choosing another case in the context bar shows that case's decision.
  const previous = useRef(work.investigationId);
  useEffect(() => {
    if (previous.current === work.investigationId) return;
    previous.current = work.investigationId;
    if (work.investigationId) setOpened((current) => (current && current.id !== work.investigationId ? null : current));
  }, [work.investigationId]);
  const decisionCase = opened?.id ?? work.investigationId;
  const selected = work.investigations.find((item) => String(item.id) === decisionCase);
  const caseLabel =
    opened?.label ?? (selected ? displayId(selected, "investigation_identifier") : "Selected investigation");
  const openFromQueue = (row: QueueRow) => {
    if (!row.investigationId) return;
    setOpened({ id: row.investigationId, label: row.caseId });
    // With its product (or when the context already lists it) the case also becomes the working context.
    if (row.productId) work.setInvestigationId(row.investigationId, row.productId);
    else if (work.investigations.some((item) => String(item.id) === row.investigationId))
      work.setInvestigationId(row.investigationId);
    setActive("Decision");
  };
  return (
    <>
      <Tabs tabs={tabs} active={active} onChange={setActive} label="Decision sections">
        {active === "Approvals" && <ApprovalsPanel onOpen={openFromQueue} />}
        {active === "Decision" &&
          (decisionCase ? (
            <>
              {opened && opened.id !== work.investigationId && (
                <p className="ac-note" role="status">
                  Opened from the approvals queue. The context bar above still shows another case.
                </p>
              )}
              <CaseDecisionPanel
                key={decisionCase}
                investigationId={decisionCase}
                caseLabel={caseLabel}
                onCaseChanged={() => work.refreshInvestigations()}
              />
            </>
          ) : (
            <Panel title="No investigation selected">
              <Empty
                title="Choose an investigation first"
                detail={
                  canSign
                    ? "Open a case from Approvals, or pick one in the context bar above."
                    : "Decisions belong to an investigation. Pick one in the context bar above."
                }
              />
            </Panel>
          ))}
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
