// Pure rules for Records › Risk file input: whether each product's post-market data has reached its risk file. The
// server (/api/v1/post-market/risk-file, backend/app/post_market/risk_file.py) reads the records; these only shape
// what the person sees.
import type { Tone } from "../admin/console/dashboardModel";

export type RiskFileState =
  "NOT_REVIEWED" | "REASSESSMENT_OVERDUE" | "REASSESSMENT_OPEN" | "NO_RISK_REGISTER" | "REVIEWED" | "QUIET";

export type RiskFileProduct = {
  product: { id: string | null; business_id: string | null; name: string };
  state: RiskFileState;
  label: string;
  post_market: {
    complaints: number;
    harm: number;
    malfunction: number;
    signals_raised: number;
    signals_decided: number;
    significant_rises: string[];
  };
  risk_file: {
    risks: number;
    risks_assessed: number;
    risk_reviews: number;
    last_review_at: string | null;
    outcomes: Record<string, number>;
    change_asked: number;
    reassessments_open: number;
    reassessments_overdue: number;
  };
};

export type RiskFileBoard = {
  period: { from: string; to: string; days: number };
  summary: {
    products: number;
    not_reviewed: number;
    reassessment_overdue: number;
    reassessment_open: number;
    no_risk_register: number;
    reviewed: number;
    quiet: number;
  };
  note: string;
  items: RiskFileProduct[];
};

export type RiskFileDetail = RiskFileProduct & {
  risks: Array<{
    id: string;
    business_id: string | null;
    risk_identifier: string | null;
    description: string;
    status: string | null;
    assessed: Array<{ review: string | null; case: string | null; outcome: string | null; at: string | null }>;
  }>;
  reviews: Array<{
    review: string | null;
    case: string | null;
    outcome: string | null;
    at: string | null;
    risks_assessed: number;
  }>;
  reassessments: Array<{
    follow_up: string | null;
    case: string | null;
    title: string;
    status: string;
    due_at: string | null;
  }>;
};

export const RISK_FILE_PERIODS = [
  { days: 180, label: "Last 6 months" },
  { days: 365, label: "Last 12 months" },
  { days: 730, label: "Last 2 years" },
] as const;

export const riskFilePath = (days: number) => `/api/v1/post-market/risk-file?period_days=${days}`;
export const riskFileProductPath = (productId: string, days: number) =>
  `/api/v1/post-market/risk-file/${encodeURIComponent(productId)}?period_days=${days}`;

export const RISK_FILE_STATE: Record<RiskFileState, { label: string; tone: Tone }> = {
  NOT_REVIEWED: { label: "Not reviewed against the risk file", tone: "critical" },
  REASSESSMENT_OVERDUE: { label: "Risk reassessment overdue", tone: "critical" },
  REASSESSMENT_OPEN: { label: "Risk reassessment open", tone: "warning" },
  NO_RISK_REGISTER: { label: "No risks in MDARIX", tone: "serious" },
  REVIEWED: { label: "Reviewed", tone: "good" },
  QUIET: { label: "Nothing for the risk file", tone: "neutral" },
};

export const riskFileStateOf = (state: string | null | undefined) =>
  RISK_FILE_STATE[(state ?? "") as RiskFileState] ?? { label: "—", tone: "neutral" as Tone };

/** "1 malfunction", "3 malfunctions". */
export const plural = (count: number, noun: string) => `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;

/** What reached the product's post-market data in the period, in one line. */
export function postMarketText(item: Pick<RiskFileProduct, "post_market">): string {
  const data = item.post_market;
  const parts = [
    plural(data.complaints, "complaint"),
    data.harm ? `${data.harm} with death or serious injury` : "",
    data.malfunction ? plural(data.malfunction, "malfunction") : "",
    data.significant_rises.length ? plural(data.significant_rises.length, "significant rise") : "",
    data.signals_decided ? `${plural(data.signals_decided, "signal")} decided` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

/** What the risk file shows of it, in one line. */
export function riskFileText(item: Pick<RiskFileProduct, "risk_file">): string {
  const data = item.risk_file;
  const parts = [
    data.risk_reviews ? plural(data.risk_reviews, "risk review") : "No risk review",
    data.risks ? `${data.risks_assessed} of ${plural(data.risks, "risk")} assessed` : "no risks in MDARIX",
    data.reassessments_open
      ? `${plural(data.reassessments_open, "reassessment")} open${data.reassessments_overdue ? ` (${data.reassessments_overdue} overdue)` : ""}`
      : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

export function riskFileHeadline(board: RiskFileBoard | null | undefined): {
  title: string;
  detail: string;
  tone: Tone;
} {
  if (!board) return { title: "Reading your products…", detail: "", tone: "neutral" };
  const { not_reviewed, reassessment_overdue, reassessment_open, no_risk_register, products } = board.summary;
  if (not_reviewed || reassessment_overdue)
    return {
      title: [
        not_reviewed ? `${plural(not_reviewed, "product")} with field data not reviewed against the risk file` : "",
        reassessment_overdue ? `${plural(reassessment_overdue, "product")} with a risk reassessment overdue` : "",
      ]
        .filter(Boolean)
        .join(" · "),
      detail: "Request a risk review on their investigations, and finish the reassessments signed decisions asked for.",
      tone: "critical",
    };
  if (reassessment_open || no_risk_register)
    return {
      title: reassessment_open
        ? `${plural(reassessment_open, "product")} with a risk reassessment open`
        : `${plural(no_risk_register, "product")} with no risks in MDARIX`,
      detail: no_risk_register
        ? "Import the risk register so post-market data can be linked to it."
        : "Reassessments asked for by signed decisions are still open.",
      tone: "warning",
    };
  return {
    title: products ? "Every product's field data reached its risk file" : "No products yet",
    detail: products ? "Risk reviews cover every product with harm, malfunctions or rising trends." : "",
    tone: "good",
  };
}
