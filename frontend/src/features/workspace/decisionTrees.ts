// The Decision trees tab's data (GET /api/v1/decision-trees, backend/app/decision_guides/trees.py), its address and
// its market names: shared by the tab, a complaint's page and the Reportability watch.

/** GET /api/v1/decision-trees (backend/app/decision_guides/trees.py). */
export type TreeMarket = {
  market: string;
  label: string;
  title: string;
  version: number;
  status: "APPROVED" | "STARTER";
  status_label: string;
  version_label: string;
  enabled: boolean;
  tests: { passed: number; total: number; current: boolean };
  questions: { id: string; text: string; clause: string; extra: boolean }[];
  /** The report a reportable outcome creates (0.10.76: the EU, GB and Canada forms are starters). */
  form?: { title: string; starter: boolean } | null;
  /** 0.10.83 (D2.5): where this market's reporting may also apply to an incident elsewhere; advice only, starter. */
  foreign?: string;
};
export type TreeNode = {
  id: string;
  text: string;
  clause: string;
  extra: boolean;
  answer: string | null;
  answer_label: string;
  /** 0.10.83 (D2): why earlier answers made this question unnecessary, when they did. */
  not_asked?: string | null;
};
export type TreePath = {
  market: string;
  label: string;
  nodes: TreeNode[];
  outcome: {
    code: string;
    label: string;
    signed: boolean;
    report_type_label: string | null;
    due_on: string | null;
    signed_by: string | null;
    signed_at: string | null;
    version: number;
  };
  report: { id: string; state: string } | null;
  has_form: boolean;
};
export type Trees = {
  markets: TreeMarket[];
  complaints: { id: string; ref: string; description: string; markets: string[]; signed: string[] }[];
  complaint: { id: string; ref: string; description: string } | null;
  paths: Record<string, TreePath>;
  never_decides: string;
  starter_mark: string;
};

/** Where a complaint's path in one market opens: the Decision trees tab, the market and complaint in its address. */
export const treePlace = (market: string | null, complaint: string) => ({
  section: "Decision trees" as const,
  tab: `?${new URLSearchParams(market ? { market, complaint } : { complaint })}`,
});

/** Each market's short name on its button (the approved design). */
export const TREE_NAMES: Record<string, string> = {
  US: "US MDR",
  IN: "India",
  EU_NI: "EU / NI",
  GB: "Great Britain",
  CA: "Canada",
};
