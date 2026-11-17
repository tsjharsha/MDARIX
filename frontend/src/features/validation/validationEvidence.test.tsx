import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  NO_RUN,
  VALIDATION_EVIDENCE_PATH,
  ValidationEvidence,
  filterRows,
  resultTone,
  runLine,
  type EvidenceRow,
  type ValidationEvidenceData,
} from "./ValidationEvidence";
import { SECURITY_SECTIONS } from "../admin/areas/sections";

// E2: the validation evidence screen shows the server's mapping, its gaps and "No run recorded" without a run.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path]) ?? null,
    reload: () => undefined,
  }),
}));

const row = (extra: Partial<EvidenceRow>): EvidenceRow => ({
  req_id: "REQ-RPT-001",
  class: "A",
  text: "The system shall refuse not reportable while an Unknown answer could make the event reportable.",
  named_tests: [{ file: "tests/test_market_assessment_rules.py", result: NO_RUN, tests: 0 }],
  linked_tests: [],
  scenarios_passed: "0/5",
  result: NO_RUN,
  gap: false,
  ...extra,
});

const evidence = (extra: Partial<ValidationEvidenceData> = {}): ValidationEvidenceData => ({
  requirements: [row({}), row({ req_id: "REQ-RPT-003", named_tests: [], result: "No test", gap: true })],
  counts: { requirements: 2, with_tests: 1, gaps: 1, passed: 0, failed: 0, not_run: 1 },
  protocol: { id: "MDX-VAL-007-P", signed: false, expected_results: 181, expected_confirmed: 0 },
  release: "0.11.0",
  run: null,
  framing: "Risk-based: this evidence supports your Computer Software Assurance and validation of MDARIX.",
  ...extra,
});

describe("Validation evidence", () => {
  it("maps each requirement to its tests, shows a gap plainly and says No run recorded without a run", () => {
    resources.data[VALIDATION_EVIDENCE_PATH] = evidence();
    const html = renderToStaticMarkup(<ValidationEvidence />);
    expect(html).toContain("Evidence to support your validation");
    expect(html).toContain("REQ-RPT-001");
    expect(html).toContain("test_market_assessment_rules.py");
    expect(html).toContain("Gap: no test");
    expect(html).toContain("No test covers this requirement yet");
    expect(html).toContain(NO_RUN);
    expect(html).toContain("Not yet signed");
    expect(html).toContain("supports your Computer Software Assurance");
    expect(html).toContain("Download the release validation pack (0.11.0)");
    // Honest wording: never a compliance or certification claim, and no recording button for a customer.
    expect(html).not.toMatch(/validated|compliant|certified/i);
    expect(html).not.toContain("Record a test run");
    expect(html).not.toMatch(/gradient|glass|glow/);
  });

  it("names the recorded run and offers the platform administrator to record one", () => {
    const run = {
      commit: "a".repeat(40),
      tree: "clean",
      ran_at: "2026-11-17T10:00:00+00:00",
      uploaded_at: "2026-11-17T10:05:00+00:00",
      passed: 1,
      failed: 1,
      skipped: 1,
      file_name: "junit.xml",
    };
    resources.data[VALIDATION_EVIDENCE_PATH] = evidence({ run });
    const html = renderToStaticMarkup(<ValidationEvidence canRecord />);
    expect(html).toContain("Record a test run (JUnit XML)");
    expect(runLine(run)).toContain("commit aaaaaaaa");
    expect(runLine(run)).toContain("1 passed, 1 failed, 1 skipped");
    expect(runLine(null)).toBe(NO_RUN);
  });

  it("filters gaps and failures, and never shows a result by colour alone", () => {
    const rows = [row({}), row({ req_id: "B", gap: true, result: "No test" }), row({ req_id: "C", result: "Failed" })];
    expect(filterRows(rows, "Gaps").map((item) => item.req_id)).toEqual(["B"]);
    expect(filterRows(rows, "Failed").map((item) => item.req_id)).toEqual(["C"]);
    expect(filterRows(rows, "All")).toHaveLength(3);
    expect(resultTone("Passed")).toBe("good");
    expect(resultTone("Failed")).toBe("critical");
    expect(resultTone(NO_RUN)).toBe("neutral");
  });

  it("is a section of the platform administrator's Security area", () => {
    expect(SECURITY_SECTIONS).toContain("Validation evidence");
  });
});
