import { useEffect } from "react";
import { ChevronRight } from "lucide-react";
import { useResource } from "../../customer-admin/shared";
import { useOpenTarget, useWorkspace } from "../workspaceContext";
import { eventPath, type EventView } from "../oversight";
import { nextStep } from "./ComplaintPage";

/**
 * The next step, always (stage 8, 8.7): at the end of each step done on another screen (triage, a market's
 * assessment, the report, the disposition), the complaint's next action is the main button, and its page one click
 * away. `first` puts a step of the story under way before it (the flagship asks for India too). New navigation only;
 * the classic screens are unchanged.
 */
export function ComplaintNextStep({
  complaintId,
  refreshKey,
  first,
}: {
  complaintId: string;
  /** Changes when the step was saved or signed here, so the next action is read again. */
  refreshKey: string;
  first?: { label: string; run: () => void } | null;
}) {
  const { navigation, open } = useWorkspace();
  const go = useOpenTarget();
  const view = useResource<EventView>(navigation === "new" ? eventPath(complaintId) : null);
  useEffect(() => {
    if (navigation === "new") view.reload();
  }, [refreshKey]);
  if (navigation !== "new" || !view.data) return null;
  const step = nextStep(view.data);
  const ref = view.data.event.ref;
  const page = (tab = "Summary") => open("Complaint", `${tab}?ref=${encodeURIComponent(ref)}`);
  const main =
    first ??
    (step ? { label: step.label, run: () => (step.opens ? go(step.opens) : page("Decisions & actions")) } : null);
  return (
    <section className="uw-next-after" aria-label="The next step">
      <span className="ac-eyebrow">Next step on {ref}</span>
      {main ? (
        <button type="button" className="ac-primary" onClick={main.run}>
          {main.label} <ChevronRight size={15} aria-hidden="true" />
        </button>
      ) : (
        <span className="ac-muted">Nothing left to do on it in MDARIX.</span>
      )}
      <button type="button" className="ac-link" onClick={() => page()}>
        Open {ref}'s page
      </button>
    </section>
  );
}
