import { Printer } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { type BriefVersion } from "../decisionBrief";
import { NOT_RECORDED, decisionSummaryPath, type DecisionSummary } from "../decisionSummary";
import { lotImpactBase, type LotImpactView } from "../lotImpact";
import { briefPage } from "../investigationBrief";

/** Print only the brief, the way the intake summary prints (body class + print stylesheet): the browser saves a PDF. */
export function printBrief() {
  document.body.classList.add("uw-print-brief");
  window.print();
  document.body.classList.remove("uw-print-brief");
}

/**
 * W1c: the Investigation Brief as one page a Quality or Regulatory leader reads, readable on a projector at 1280×720
 * and printable. Each part comes from the records (investigationBrief.ts); a part with none says "Not recorded".
 */
export function InvestigationBriefPage({
  investigationId,
  caseLabel,
  version,
}: {
  investigationId: string;
  caseLabel: string;
  version: BriefVersion;
}) {
  const summary = useResource<DecisionSummary>(decisionSummaryPath(investigationId));
  const lots = useResource<LotImpactView>(lotImpactBase(investigationId));
  const parts = briefPage(version, summary.data, lots.data);
  const question = safeText((version.content?.investigation as Record<string, unknown> | undefined)?.question);
  return (
    <Panel
      eyebrow={caseLabel}
      title="Investigation Brief"
      className="uw-ibrief"
      action={
        <button type="button" className="ac-secondary uw-no-print" onClick={printBrief}>
          <Printer size={15} aria-hidden="true" /> Print or save as PDF
        </button>
      }
    >
      {question && <p className="uw-case-question">{question}</p>}
      <div className="uw-ibrief-grid">
        {parts.map((part, index) => (
          <section key={part.key} className={`uw-ibrief-part part-${part.key}`} aria-label={part.title}>
            <h3>
              <span className="uw-num">{index + 1}</span> {part.title}
            </h3>
            {part.lines.length ? (
              <ul>
                {part.lines.map((line, at) => (
                  <li key={at}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">{NOT_RECORDED}</p>
            )}
          </section>
        ))}
      </div>
    </Panel>
  );
}
