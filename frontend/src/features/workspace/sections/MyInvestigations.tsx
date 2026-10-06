import { ChevronRight } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { sectionAllowed, useCan, useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { MY_CASES_SUMMARY_PATH, myCaseTiles, rankMyCases, type MyCase, type MyCasesSummary } from "../caseWorkflow";
import { CaseDue, CasePriority, CaseStateBadge } from "./CaseHeader";

/** Dashboard: the cases the person works, for people who work investigations (investigation.work). */
export function MyInvestigationsPanel() {
  const { session } = useWorkspace();
  const canWork = useCan("investigation.work");
  const allowed = sectionAllowed("Investigations", session?.allowed_menu, session?.business_permissions);
  if (!canWork || !allowed) return null;
  return <MyInvestigations />;
}

function MyInvestigations() {
  const { session, work, open } = useWorkspace();
  const summary = useResource<MyCasesSummary>(MY_CASES_SUMMARY_PATH);
  const ready = summary.state === "ready";
  const tiles = myCaseTiles(summary.data);
  const cases = rankMyCases(summary.data?.cases).slice(0, 8);
  const can = (section: WorkspaceSection) =>
    sectionAllowed(section, session?.allowed_menu, session?.business_permissions);
  // A role that may not read the summary simply does not see the panel.
  if (summary.state === "forbidden") return null;
  const go = (row: MyCase, section: WorkspaceSection, tab: string) => () => {
    work.setInvestigationId(String(row.id), row.product?.id ? String(row.product.id) : null);
    open(section, tab);
  };
  return (
    <Panel
      eyebrow="Investigations"
      title="My investigations"
      source={summary}
      action={
        <button type="button" className="ac-link" onClick={() => open("Investigations", "All investigations")}>
          Open <ChevronRight size={14} aria-hidden="true" />
        </button>
      }
    >
      <div className="uw-task-counts" role="group" aria-label="Your investigation counts">
        {tiles
          .filter((tile) => can(tile.target.section))
          .map((tile) => (
            <button
              type="button"
              key={tile.key}
              className={`uw-task-count ${tile.urgent && (tile.value ?? 0) > 0 ? "urgent" : ""}`}
              onClick={() => open(tile.target.section, tile.target.tab)}
            >
              <strong>{ready ? (tile.value ?? 0) : "…"}</strong>
              <span>{tile.label}</span>
            </button>
          ))}
      </div>
      {ready && cases.length > 0 && (
        <ul className="uw-list uw-my-cases" aria-label="Your cases">
          {cases.map((row) => {
            const name = safeText(row.business_id) ?? "Case";
            const extras = [
              row.unreviewed_evidence ? `${row.unreviewed_evidence} to review` : "",
              row.open_requests ? `${row.open_requests} open ${row.open_requests === 1 ? "request" : "requests"}` : "",
              row.open_unknowns ? `${row.open_unknowns} open ${row.open_unknowns === 1 ? "unknown" : "unknowns"}` : "",
            ].filter(Boolean);
            return (
              <li key={row.id}>
                <span>
                  <strong>
                    {name}
                    {safeText(row.product?.name) ? ` · ${row.product?.name}` : ""}
                  </strong>
                  <small>{safeText(row.question) ?? "No question recorded"}</small>
                  {extras.length > 0 && <small className="ac-muted">{extras.join(" · ")}</small>}
                </span>
                <span className="uw-case-meta">
                  <CaseStateBadge row={row} />
                  <CasePriority priority={row.priority} />
                  <small>
                    <CaseDue row={row} />
                  </small>
                </span>
                <span className="uw-task-actions">
                  {can("Investigations") && (
                    <button
                      type="button"
                      className="ac-link"
                      aria-label={`Open the workspace of ${name}`}
                      onClick={go(row, "Investigations", "Workspace")}
                    >
                      Workspace
                    </button>
                  )}
                  {can("Evidence") && (
                    <button
                      type="button"
                      className="ac-link"
                      aria-label={`Open the case evidence of ${name}`}
                      onClick={go(row, "Evidence", "Case evidence")}
                    >
                      Case evidence
                    </button>
                  )}
                  {can("Investigations") && (
                    <button
                      type="button"
                      className="ac-link"
                      aria-label={`Open the scope of ${name}`}
                      onClick={go(row, "Investigations", "Scope")}
                    >
                      Scope
                    </button>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {ready && !cases.length && (
        <Empty title="No cases assigned to you" detail="Investigations you own or work on appear here." />
      )}
    </Panel>
  );
}
