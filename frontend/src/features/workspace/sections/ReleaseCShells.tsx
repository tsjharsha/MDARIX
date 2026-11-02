import { ChevronRight } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { useWorkspace } from "../workspaceContext";

/** What MDARIX does with an authority report, said once where it matters (Release C guardrail 3). */
export const NEVER_SUBMITS =
  "MDARIX prepares each report, gets it approved and records the submission you make through the authority's own " +
  "channel: eMDR for the FDA, EUDAMED or the national authority for the EU, MHRA's portal for Great Britain, Health " +
  "Canada, and MvPI for India. MDARIX never submits to an authority.";

/**
 * Decision trees (0.10.73, C1): the tab's place on the new navigation. One tree per market, with the path each
 * complaint took, comes with Release C's part C3; until then the page says where the questions are today.
 */
export function DecisionTreesSection() {
  const { open } = useWorkspace();
  return (
    <Panel eyebrow="Is it reportable, and by when?" title="One decision tree per market">
      <p>
        Each market's questions are asked on the complaint's page, in its market assessment: did a death or serious
        injury occur, did the device malfunction, would it be likely to cause harm if it recurred. Each question set has
        its version, its locked regulation wording and its worked complaints.
      </p>
      <p className="ac-muted">
        This page will show each market's tree, its version and test result, and the path each complaint took through
        it: question, answer, clause, outcome.
      </p>
      <div className="ca-action-row">
        <button type="button" className="ac-primary" onClick={() => open("Settings", "Reportability guides")}>
          Open the reportability guides <ChevronRight size={15} aria-hidden="true" />
        </button>
        <button type="button" className="ac-secondary" onClick={() => open("Complaints", "Reporting")}>
          Complaints to assess
        </button>
      </div>
    </Panel>
  );
}

/**
 * Reports (0.10.73, C1): the tab's place on the new navigation. The list of authority reports with its views comes
 * with part C3; today each report is under Complaints › Reporting.
 */
export function ReportsSection() {
  const { open } = useWorkspace();
  return (
    <Panel eyebrow="Authority reports" title="Your reports are under Complaints › Reporting">
      <p>
        Each report MDARIX prepares lists its form's fields in the form's order, filled from the complaint, the product
        and your organization, with its approval and its PDF. This page will list every report, with views for the open
        ones, those waiting for your approval and those submitted this month.
      </p>
      <p className="uw-never-submits">{NEVER_SUBMITS}</p>
      <div className="ca-action-row">
        <button type="button" className="ac-primary" onClick={() => open("Complaints", "Reporting")}>
          Open the reports <ChevronRight size={15} aria-hidden="true" />
        </button>
      </div>
    </Panel>
  );
}
