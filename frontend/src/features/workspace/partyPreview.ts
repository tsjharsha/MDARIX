// The distributor and authorised-representative preview (T-G37P; backend/app/party_views): three read-only pages with
// the sample parties, in free-trial workspaces only. Each opening is in the audit trail; nothing can be sent or changed.

/** The workspace section and its three pages, in the order the story opens them. */
export const LOOK_AHEAD_SECTION = "Look ahead";
export const LOOK_AHEAD_TABS = [
  "How a distributor reports",
  "As your distributor sees it",
  "As your authorised representative sees it",
] as const;
export type LookAheadTab = (typeof LOOK_AHEAD_TABS)[number];

export const LOOK_AHEAD_SUBTITLE = "Distributors and your EU representative";
export const LOOK_AHEAD_SUMMARY =
  "A read-only preview, with sample data, of how a distributor reports a complaint and follows it, and what your EU authorised representative sees.";

/** Each page's API path (GET only). */
export const PREVIEW_PATHS: Record<LookAheadTab, string> = {
  "How a distributor reports": "/api/v1/trial/preview/intake",
  "As your distributor sees it": "/api/v1/trial/preview/distributor",
  "As your authorised representative sees it": "/api/v1/trial/preview/authorised-representative",
};

/** The tab a link names, else the first. */
export const lookAheadTab = (name?: string): LookAheadTab =>
  LOOK_AHEAD_TABS.find((tab) => tab === name) ?? LOOK_AHEAD_TABS[0];

type Frame = { page: string; banner: string; read_only: true; party: string; empty?: string | null };

export type IntakePreview = Frame & {
  submission: {
    reference: string;
    product: string;
    lot: string | null;
    first_knowledge: string | null;
    words: string;
    becomes: string;
  } | null;
};

export type SubmitterStatus = "RECEIVED" | "UNDER_ASSESSMENT" | "CLOSED";
export type DistributorPreview = Frame & {
  statuses: { code: SubmitterStatus; label: string }[];
  items: {
    reference: string;
    complaint: string;
    status: SubmitterStatus;
    status_label: string;
    received: string | null;
    last_change: string | null;
    closing_note: string | null;
  }[];
};

export type PortfolioComplaint = {
  id: string;
  ref: string;
  identifier: string;
  product: string | null;
  country: string | null;
  status: SubmitterStatus;
  state: string;
  received: string | null;
  last_change: string | null;
  eu_assessment: { state: string; label: string; date?: string | null; due_on?: string | null };
};
export type RepresentativePreview = Frame & {
  prrc_note: string;
  products: string[];
  complaints: PortfolioComplaint[];
  high_risk: (Pick<PortfolioComplaint, "id" | "ref" | "identifier" | "product" | "country"> & {
    codes: string[];
    reasons: string[];
  })[];
  recurring: {
    signals: {
      id: string;
      ref: string;
      title: string;
      product: string | null;
      complaints: number;
      status: string;
      last_event: string | null;
    }[];
    service_level: {
      product_id: string;
      product_name: string | null;
      problem_code: string;
      count: number;
      complaints: string[];
    }[];
    rule: string;
  };
};

/** The tone of a submitter status. */
export const statusTone = (status: SubmitterStatus) =>
  status === "CLOSED" ? "good" : status === "UNDER_ASSESSMENT" ? "warning" : "neutral";
