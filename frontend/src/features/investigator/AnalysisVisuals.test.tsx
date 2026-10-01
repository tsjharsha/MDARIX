import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { HypothesisSet, InvestigationAnalysis } from "../../app/types";
import { AnalysisVisual, AuthorBadge, ForAgainstBar, HypothesisBoard } from "./AnalysisVisuals";

const ref = (id: string) => ({ reference_type: "EVIDENCE", evidence_identifier: id });
const item = (statement: string, ids: string[] = []) => ({
  item_id: statement,
  semantic_type: "OBSERVATION",
  statement,
  grounding_status: "ACCEPTED",
  source_references: ids.map(ref),
});

const analysis = {
  analysis_id: "a1",
  status: "COMPLETED_WITH_LIMITATIONS",
  analysis_author: "LANGUAGE_MODEL",
  summary: "Complaints rose after Rev D; lot data is missing.",
  observations: [item("Supplier changed its process.", ["EV-VS001-001", "EV-VS001-001"])],
  temporal_patterns: [],
  evidence_relationships: [],
  possible_explanations: [],
  contradictions: [item("Validation passed despite complaints.", ["EV-VS001-005", "EV-VS001-004"])],
  missing_information: [item("Lot-level rates.")],
  questions_to_investigate: [],
  limitations: [],
  validation_summary: { model_statements_dropped_by_checks: 2 },
  model_provenance: {},
} as InvestigationAnalysis;

describe("AnalysisVisual", () => {
  it("shows the summary, counts, evidence chips and what the checks removed", () => {
    const html = renderToStaticMarkup(<AnalysisVisual analysis={analysis} />);
    expect(html).toContain("Written by AI · checked by MDARIX rules");
    expect(html).toContain("Complaints rose after Rev D; lot data is missing.");
    expect(html.match(/EV-VS001-001<\/span>/g)).toHaveLength(1); // duplicates collapse into one chip
    expect(html).toContain("EV-VS001-005");
    expect(html).toContain("2 AI statements removed by the checks");
  });

  it("names the rules as the author when the AI was not used", () => {
    const html = renderToStaticMarkup(<AuthorBadge author="RULES" reason="MODEL_CALL_FAILED" />);
    expect(html).toContain("Written by MDARIX rules");
    expect(html).toContain("AI not used: the AI service was busy or unreachable");
    expect(renderToStaticMarkup(<AuthorBadge author="RULES" reason="MODEL_NOT_CONFIGURED" />)).not.toContain(
      "AI not used",
    );
  });
});

describe("ForAgainstBar", () => {
  it("splits the bar by supporting and contradicting evidence, with a text label", () => {
    const html = renderToStaticMarkup(<ForAgainstBar support={3} against={1} />);
    expect(html).toContain('aria-label="3 supporting, 1 contradicting evidence"');
    expect(html).toContain("width:75%");
    expect(html).toContain("width:25%");
  });
});

describe("HypothesisBoard", () => {
  it("shows each hypothesis with its for and against evidence", () => {
    const set = {
      hypothesis_set_id: "s1",
      status: "MIXED_EVIDENCE",
      provenance: { author: "LANGUAGE_MODEL" },
      comparison: [],
      validation_summary: {},
      guardrails: {},
      hypotheses: [
        {
          hypothesis_id: "h1",
          statement: "Hypothesis: the supplier change may be associated with the shutdowns.",
          scope: "supplier",
          status: "MIXED_EVIDENCE",
          supporting_evidence: [
            { relationship_type: "SUPPORTS", rationale: "came first", source_references: [ref("EV-1")] },
          ],
          contradicting_evidence: [
            { relationship_type: "CONTRADICTS", rationale: "earlier complaints", source_references: [ref("EV-2")] },
          ],
          contextual_evidence: [],
          assumptions: [],
          evidence_gaps: [],
          falsification_conditions: ["Compare lots with and without the new process."],
          temporal_consistency: {},
        },
      ],
    } as HypothesisSet;
    const html = renderToStaticMarkup(<HypothesisBoard set={set} />);
    expect(html).toContain("the supplier change may be associated with the shutdowns.");
    expect(html).not.toContain("Hypothesis: the");
    expect(html).toContain("av-chip-for");
    expect(html).toContain("av-chip-against");
    expect(html).toContain("How to rule it out (1)");
    expect(html).toContain("earlier complaints");
  });
});
