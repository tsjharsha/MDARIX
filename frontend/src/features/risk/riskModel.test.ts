import { describe, expect, it } from "vitest";
import {
  NOT_CAPTURED,
  fieldOrNotCaptured,
  filterChains,
  missingLinks,
  notCapturedLabels,
  pageSummary,
  registerPath,
  residualLabel,
  reviewReasonValid,
  reviewRequestPath,
  traceabilityGaps,
  type Chain,
} from "./riskModel";

const chain = (overrides: Partial<Chain>): Chain => ({
  risk_id: "r1",
  risk_identifier: "RISK-001",
  product: "PUMP-X",
  requirements: ["REQ-1"],
  failure_modes: ["FM-1"],
  controls: ["CTL-1"],
  verification_evidence: ["EV-1"],
  residual_risk: "CONTROLLED_WITH_VERIFICATION_EVIDENCE",
  complete: true,
  ...overrides,
});

describe("risk register", () => {
  it("never invents a value the records do not hold", () => {
    expect(fieldOrNotCaptured(null)).toBe(NOT_CAPTURED);
    expect(fieldOrNotCaptured("  ")).toBe(NOT_CAPTURED);
    expect(fieldOrNotCaptured(4)).toBe("4");
    expect(notCapturedLabels(["hazard", "risk_level"])).toEqual(["Hazard", "Risk level"]);
  });

  it("describes residual risk from linked controls only, with a tone", () => {
    expect(residualLabel("NO_CONTROLS_LINKED")).toEqual({ label: "No control linked", tone: "serious" });
    expect(residualLabel("CONTROLLED_WITH_VERIFICATION_EVIDENCE").tone).toBe("good");
    expect(residualLabel(undefined)).toEqual({ label: "Unknown", tone: "neutral" });
  });

  it("pages the register and says where the page is", () => {
    expect(registerPath(50)).toBe("/api/v1/risk/register?limit=25&offset=50");
    expect(registerPath(-5)).toBe("/api/v1/risk/register?limit=25&offset=0");
    expect(pageSummary(61, 25, 25)).toBe("Risks 26–50 of 61");
    expect(pageSummary(0, 0, 0)).toBe("0 risks");
  });

  it("asks for a review only with a reason the server accepts", () => {
    expect(reviewReasonValid("too short")).toBe(false);
    expect(reviewReasonValid("  New complaint trend on lot 7  ")).toBe(true);
    expect(reviewRequestPath("a/b")).toBe("/api/v1/risk/a%2Fb/review-request");
  });
});

describe("traceability", () => {
  it("lists only the gaps that exist, most consequential first, with what to do", () => {
    const gaps = traceabilityGaps({
      requirements_without_risk: ["REQ-9"],
      risks_without_control: ["RISK-002"],
      controls_without_risk: [],
    });
    expect(gaps.map((gap) => gap.key)).toEqual(["risks_without_control", "requirements_without_risk"]);
    expect(gaps[0]).toMatchObject({ risks: true, items: ["RISK-002"] });
    expect(gaps[0].fix).toMatch(/control/);
    expect(traceabilityGaps(undefined)).toEqual([]);
  });

  it("finds chains by any linked identifier and can hide complete ones", () => {
    const chains = [
      chain({}),
      chain({ risk_id: "r2", risk_identifier: "RISK-002", controls: [], verification_evidence: [], complete: false }),
    ];
    expect(filterChains(chains, "ev-1", false).map((item) => item.risk_id)).toEqual(["r1"]);
    expect(filterChains(chains, "", true).map((item) => item.risk_id)).toEqual(["r2"]);
    expect(filterChains(chains, "pump", false)).toHaveLength(2);
  });

  it("names what a chain is missing", () => {
    expect(missingLinks(chain({}))).toEqual([]);
    expect(missingLinks(chain({ requirements: [], verification_evidence: [], complete: false }))).toEqual([
      "requirement",
      "verification evidence",
    ]);
  });
});
