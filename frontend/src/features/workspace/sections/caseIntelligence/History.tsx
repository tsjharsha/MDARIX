/** The history of every judgement made on the case's intelligence. (Part of CaseIntelligence.tsx.) */
import { Empty, Panel } from "../../../admin/console/charts";
import { formatDate, useResource } from "../../../customer-admin/shared";
import { safeText } from "../../../../app/displayId";
import { roleLabel } from "../../../../app/roles";
import { historyEventText, historyEvents, intelligencePath } from "../../intelligence";

export function HistoryView({ investigationId, caseLabel }: { investigationId: string; caseLabel: string }) {
  const history = useResource<unknown>(intelligencePath(investigationId, "history"));
  const events = historyEvents(history.data);
  const total = (history.data as { total?: unknown } | null)?.total;
  return (
    <Panel eyebrow={caseLabel} title="Intelligence history" source={history}>
      <p className="ac-note">Every judgement on this case's intelligence: what changed, why, by whom and when.</p>
      {events.length ? (
        <>
          <ol className="ca-timeline uw-task-history">
            {events.map((event, index) => (
              <li key={event.id ?? `${event.created_at ?? ""}:${index}`}>
                <strong>{historyEventText(event)}</strong>
                <small className="ac-muted">
                  {safeText(event.actor_name) ?? "MDARIX"}
                  {event.actor_role ? ` (${roleLabel(event.actor_role)})` : ""} · {formatDate(event.created_at)}
                </small>
                {safeText(event.reason) && <p>{event.reason}</p>}
              </li>
            ))}
          </ol>
          {typeof total === "number" && total > events.length && (
            <p className="ac-muted">
              Showing the latest {events.length} of {total} events.
            </p>
          )}
        </>
      ) : (
        <Empty
          title="No history yet"
          detail="Judgements on hypotheses, unknowns, chains and observations appear here."
        />
      )}
    </Panel>
  );
}
