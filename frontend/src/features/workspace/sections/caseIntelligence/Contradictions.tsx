/** Where the case's evidence contradicts a hypothesis (read only). (Part of CaseIntelligence.tsx.) */
import { Empty, Panel, ToneBadge } from "../../../admin/console/charts";
import { listOf, useResource } from "../../../customer-admin/shared";
import { StatementKind } from "../../../shared/StatementKind";
import { contradictionView, intelligencePath, type IntelligenceView } from "../../intelligence";

export function ContradictionsView({
  investigationId,
  caseLabel,
  onView,
}: {
  investigationId: string;
  caseLabel: string;
  onView: (view: IntelligenceView) => void;
}) {
  const contradictions = useResource<any>(intelligencePath(investigationId, "contradictions"));
  const rows = listOf(contradictions.data?.items ?? contradictions.data).map(contradictionView);
  return (
    <Panel eyebrow={caseLabel} title="Contradictions" source={contradictions}>
      <p className="ac-note">
        Evidence that speaks against a hypothesis. A contradiction is documented when a person has judged the hypothesis
        with it in view.
      </p>
      {rows.length ? (
        <ul className="uw-intel-list">
          {rows.map((row) => (
            <li key={row.key} className="uw-intel-card">
              <header>
                <ToneBadge tone="critical" label={row.label} />
                <StatementKind kind={row.kind} origin={row.origin} kindLabel={row.kindLabel} />
              </header>
              <p>
                <strong>{row.evidence ?? "Evidence"}</strong>
                {row.evidenceTitle ? ` · ${row.evidenceTitle}` : ""} contradicts{" "}
                <strong>{row.hypothesis ?? "a hypothesis"}</strong>
                {row.hypothesisStatement ? `: ${row.hypothesisStatement}` : ""}
              </p>
              {row.rationale && <p className="uw-intel-reason">{row.rationale}</p>}
              {row.addedBy && <small className="ac-muted">Added by {row.addedBy}</small>}
              {row.judgedSince === true && <ToneBadge tone="good" label="A person has judged the hypothesis since" />}
              {row.judgedSince === false && (
                <ToneBadge tone="warning" label="Not judged by a person since: review the hypothesis" />
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Empty
          title="No contradictions recorded"
          detail="Link contradicting evidence to a hypothesis and it is listed here."
        />
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-link" onClick={() => onView("Hypotheses")}>
          Open hypotheses
        </button>
      </div>
    </Panel>
  );
}
