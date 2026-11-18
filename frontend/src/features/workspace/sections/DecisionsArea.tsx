import { useState } from "react";
import { chooseCase, useWorkspace } from "../workspaceContext";
import { tabParam } from "../workspaceAddress";
import type { QueueRow } from "../humanDecision";
import { ApprovalsPanel } from "./DecisionApprovals";
import { ApprovalsCard, DECISION_PLACE } from "./HomeWork";
import { ReportabilityWatch } from "./ReportabilityWatch";
import { ReportsSection } from "./ReportsTab";

/**
 * Decisions & Reports (UX2, Persona Blueprint wave D): approvals, decision trees and authority reports in one area,
 * instead of three places (Complaints' Reporting and Authority reports views, the Reports and Decision trees tabs, and
 * the classic Decision / Decision center). The screens keep their own components; this file only gives the area its
 * Approvals screen and gives Reports what Complaints › Reporting showed.
 */

/** Approvals, /app/approvals: the briefs waiting for this person's signature; a row opens the investigation's decision.
 * Shown to whoever may sign a decision or approve a report (workspaceContext SECTION_PERMISSIONS); the queue's read
 * and the signature check again on the server. Its first brief's one-page summary is Today's Approvals card (UX1),
 * read from the same queue (GET /api/v1/decisions/queue), so Today and Approvals show the same waiting items (UX3). */
export function ApprovalsSection() {
  const { work, open, notify } = useWorkspace();
  const openApproval = async (row: QueueRow) => {
    if (!row.investigationId) return;
    if (row.productId) work.setInvestigationId(row.investigationId, row.productId);
    else if (!(row.caseId && (await chooseCase(work, row.caseId)))) {
      notify(
        `${row.caseId ?? "This investigation"} could not be opened right now. Open it from Investigations.`,
        "critical",
      );
      return;
    }
    open("Investigations", DECISION_PLACE);
  };
  return (
    <>
      <ApprovalsCard />
      <ApprovalsPanel onOpen={openApproval} />
    </>
  );
}

/** Reports, /app/reports: every authority report and, as Complaints › Reporting showed, the reportability watch (a
 * complaint's market assessment, part=assess, opens that complaint's). */
export function ReportingSection({ tab }: { tab?: string }) {
  const { open } = useWorkspace();
  const [carried] = useState(() => tab);
  const complaint = tabParam(carried, "complaint");
  return (
    <>
      {(!complaint || tabParam(carried, "part") === "assess") && (
        <ReportabilityWatch onOpenTab={(classic) => open("Complaints", classic)} />
      )}
      <ReportsSection complaintId={complaint} />
    </>
  );
}
