import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  postMarketText,
  riskFileHeadline,
  riskFilePath,
  riskFileProductPath,
  riskFileStateOf,
  riskFileText,
  type RiskFileBoard,
  type RiskFileDetail,
  type RiskFileProduct,
} from "./riskFile";
import { ProductDetail, RiskFileCard } from "./sections/RiskFile";
import { RECORDS_TABS, parseRecordsTab } from "./effectiveness";

const product = (overrides: Partial<RiskFileProduct> = {}): RiskFileProduct => ({
  product: { id: "p-1", business_id: "PRD000001", name: "FlowSure 200" },
  state: "NOT_REVIEWED",
  label: "Post-market data not reviewed against the risk file",
  post_market: {
    complaints: 12,
    harm: 2,
    malfunction: 3,
    signals_raised: 1,
    signals_decided: 1,
    significant_rises: ["FlowSure 200 Rev B · occlusion"],
  },
  risk_file: {
    risks: 4,
    risks_assessed: 1,
    risk_reviews: 0,
    last_review_at: null,
    outcomes: {},
    change_asked: 0,
    reassessments_open: 1,
    reassessments_overdue: 1,
  },
  ...overrides,
});

const board = (summary: Partial<RiskFileBoard["summary"]>): RiskFileBoard => ({
  period: { from: "2025-10-14", to: "2026-10-13", days: 365 },
  summary: {
    products: 3,
    not_reviewed: 0,
    reassessment_overdue: 0,
    reassessment_open: 0,
    no_risk_register: 0,
    reviewed: 3,
    quiet: 0,
    ...summary,
  },
  note: "",
  items: [],
});

describe("risk file input rules", () => {
  it("asks for a period and a product", () => {
    expect(riskFilePath(365)).toBe("/api/v1/post-market/risk-file?period_days=365");
    expect(riskFileProductPath("p 1", 180)).toBe("/api/v1/post-market/risk-file/p%201?period_days=180");
  });

  it("reads every state with a label and a tone", () => {
    expect(riskFileStateOf("NOT_REVIEWED")).toEqual({ label: "Not reviewed against the risk file", tone: "critical" });
    expect(riskFileStateOf("REASSESSMENT_OPEN").tone).toBe("warning");
    expect(riskFileStateOf("REVIEWED").tone).toBe("good");
    expect(riskFileStateOf("ODD").label).toBe("—");
  });

  it("says what reached the post-market data and the risk file", () => {
    expect(postMarketText(product())).toBe(
      "12 complaints · 2 with death or serious injury · 3 malfunctions · 1 significant rise · 1 signal decided",
    );
    expect(riskFileText(product())).toBe("No risk review · 1 of 4 risks assessed · 1 reassessment open (1 overdue)");
    expect(
      riskFileText(
        product({
          risk_file: {
            ...product().risk_file,
            risks: 0,
            risk_reviews: 2,
            reassessments_open: 0,
            reassessments_overdue: 0,
          },
        }),
      ),
    ).toBe("2 risk reviews · no risks in MDARIX");
  });

  it("leads with what an inspector would cite", () => {
    expect(riskFileHeadline(board({ not_reviewed: 1, reassessment_overdue: 2 }))).toMatchObject({
      title:
        "1 product with field data not reviewed against the risk file · 2 products with a risk reassessment overdue",
      tone: "critical",
    });
    expect(riskFileHeadline(board({ no_risk_register: 1 })).detail).toContain("Import the risk register");
    expect(riskFileHeadline(board({})).title).toBe("Every product's field data reached its risk file");
  });

  it("is a tab of Records", () => {
    expect(RECORDS_TABS).toContain("Risk file input");
    expect(parseRecordsTab("Risk file input").tab).toBe("Risk file input");
  });
});

describe("risk file input screens", () => {
  it("a product card shows both sides and opens its risks", () => {
    const markup = renderToStaticMarkup(<RiskFileCard item={product()} onOpen={vi.fn()} />);
    expect(markup).toContain("FlowSure 200");
    expect(markup).toContain("Not reviewed against the risk file");
    expect(markup).toContain("12 complaints");
    expect(markup).toContain("1 of 4 risks assessed");
    expect(markup).toContain("Rising: FlowSure 200 Rev B · occlusion");
    expect(markup).toContain("Risks and reviews");
  });

  it("the detail shows each risk, assessed or not", () => {
    const detail: RiskFileDetail = {
      ...product({ state: "REVIEWED" }),
      risks: [
        {
          id: "r1",
          business_id: "RSK000001",
          risk_identifier: "R-1",
          description: "Delayed therapy",
          status: "active",
          assessed: [],
        },
        {
          id: "r2",
          business_id: "RSK000002",
          risk_identifier: "R-2",
          description: "Under-infusion",
          status: "active",
          assessed: [{ review: "REV000003", case: "INV000147", outcome: "NO_CHANGE_REQUIRED", at: null }],
        },
      ],
      reviews: [{ review: "REV000003", case: "INV000147", outcome: "NO_CHANGE_REQUIRED", at: null, risks_assessed: 1 }],
      reassessments: [],
    };
    const markup = renderToStaticMarkup(<ProductDetail detail={detail} />);
    expect(markup).toContain("Not assessed in the period");
    expect(markup).toContain("Assessed in INV000147");
    expect(markup).toContain("no change required");
  });
});
