import { Settings2 } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { rolesSummary } from "../../../app/roles";
import { useWorkspace } from "../workspaceContext";
import { TeamPanel } from "./TrialTeam";

/**
 * Team on the new navigation (0.10.68). A free trial invites and manages its colleagues here (the classic Getting
 * started › Team). In a pilot the customer administrator manages people in the admin console, as before: this screen
 * says so and, for an administrator, opens it.
 */
export function TeamSection({ onAdminConsole }: { onAdminConsole?: () => void }) {
  const { isTrial, session } = useWorkspace();
  if (isTrial) return <TeamPanel onChanged={() => undefined} />;
  return (
    <Panel eyebrow="Team" title="Your team is managed in the admin console">
      <p>
        In a pilot your customer administrator invites people, gives them their roles and removes them, in the admin
        console. You hold: <strong>{rolesSummary(session)}</strong>.
      </p>
      {onAdminConsole ? (
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={onAdminConsole}>
            <Settings2 size={16} aria-hidden="true" /> Open the admin console
          </button>
        </div>
      ) : (
        <p className="ac-muted">To add a colleague or change a role, ask your customer administrator.</p>
      )}
    </Panel>
  );
}
