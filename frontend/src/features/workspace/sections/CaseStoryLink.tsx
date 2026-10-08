import { useContext } from "react";
import { History } from "lucide-react";
import { safeText } from "../../../app/displayId";
import { WorkspaceContext, sectionAllowed } from "../workspaceContext";
import { trustTab } from "../caseAudit";

/**
 * "See the full case story in Trust & Audit": opens the case's timeline. Shown only inside the workspace and when the
 * person's menu has Trust & Audit; a case the context bar lists becomes the working case as well.
 */
export function CaseStoryLink({
  investigationId,
  caseLabel,
  className = "ac-secondary",
}: {
  investigationId: string | null | undefined;
  caseLabel?: string | null;
  className?: string;
}) {
  const workspace = useContext(WorkspaceContext);
  const id = typeof investigationId === "string" ? investigationId.trim() : "";
  if (!workspace || !id) return null;
  const { session, work, open } = workspace;
  if (!sectionAllowed("Trust & Audit", session?.allowed_menu, session?.business_permissions)) return null;
  const go = () => {
    if (id !== work.investigationId && work.investigations.some((item) => String(item.id) === id))
      work.setInvestigationId(id);
    open("Trust & Audit", trustTab({ tab: "Case timeline", caseId: id, caseLabel: safeText(caseLabel) }));
  };
  return (
    <button type="button" className={className} onClick={go}>
      <History size={15} aria-hidden="true" /> See the full case story in Trust &amp; Audit
    </button>
  );
}
