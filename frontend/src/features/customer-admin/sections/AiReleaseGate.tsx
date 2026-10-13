import { CheckCircle2, CircleDashed } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";

/**
 * The AI release gate (backend/app/ai_release_gate.py): the four bars AI must pass before it is switched on for a pilot
 * (a contracted provider with zero data retention, the golden dataset signed off by a person, the golden evaluation at
 * 15 of 15 with the configured model, every AI result checked automatically). Production refuses to switch AI on
 * until every bar is met.
 */
export type ReleaseGateBar = {
  code: string;
  title: string;
  status: "MET" | "NOT_MET";
  detail: string;
  action?: string | null;
};
export type ReleaseGate = {
  ready: boolean;
  met: number;
  total: number;
  enforced: boolean;
  bars: ReleaseGateBar[];
  message: string;
};

/** Whether the server refuses to switch AI on now (production, a bar not met). */
export const gateBlocksSwitchOn = (gate: ReleaseGate | null | undefined) => Boolean(gate?.enforced && !gate.ready);

/** The gate's bars; ``showActions`` adds what to do for each open bar (for MDARIX staff, who operate the server). */
export function AiReleaseGate({
  gate,
  showActions = false,
}: {
  gate: ReleaseGate | null | undefined;
  showActions?: boolean;
}) {
  if (!gate) return null;
  return (
    <Panel eyebrow="Before AI goes to a pilot" title={`AI release gate: ${gate.met} of ${gate.total} met`}>
      <p>
        {gate.message}
        {gate.enforced && !gate.ready ? " This server will not switch AI on until every bar is met." : ""}
      </p>
      <ol className="ca-gate" aria-label="AI release gate">
        {gate.bars.map((bar) => {
          const met = bar.status === "MET";
          return (
            <li key={bar.code} className={`ca-gate-bar ${met ? "is-met" : "is-open"}`}>
              {met ? (
                <CheckCircle2 size={18} className="ac-tone-icon tone-good" aria-hidden="true" />
              ) : (
                <CircleDashed size={18} className="ac-tone-icon tone-warning" aria-hidden="true" />
              )}
              <div>
                <strong>{bar.title}</strong>
                <span>{bar.detail}</span>
                {showActions && !met && bar.action && <small>{bar.action}</small>}
              </div>
              <ToneBadge tone={met ? "good" : "warning"} label={met ? "Met" : "Not met"} />
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
