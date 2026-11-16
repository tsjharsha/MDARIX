import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import "./statement-kind.css";

/** Elapsed seconds as the waiting line shows them ("Writing the summary · 4 s"). */
export const waitingLine = (label: string, seconds: number) => `${label} · ${seconds} s`;

/**
 * The wait for a live AI answer (design rule R4): three skeleton lines the shape of the answer and a live counter, so a
 * call that takes seconds never looks stuck.
 */
export function AiWaiting({ label }: { label: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="ai-waiting" role="status" aria-live="polite">
      <p>
        <Loader2 size={16} className="uw-spin" aria-hidden="true" /> {waitingLine(label, seconds)}
      </p>
      <span className="ac-skeleton" aria-hidden="true" />
      <span className="ac-skeleton" aria-hidden="true" />
      <span className="ac-skeleton is-short" aria-hidden="true" />
    </div>
  );
}
