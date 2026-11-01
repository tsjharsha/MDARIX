// Lot impact on a case (T-G5; backend/app/lot_impact): types, paths and the pure rules the panel uses. MDARIX lists
// every lot that shares the suspect factor the person chooses; the person decides any field action in the QMS.

/** The Lot impact section's anchor on the case's Scope step (it is versioned with the case scope). */
export const LOT_IMPACT_ANCHOR = "lot-impact";
export const SIGNERS = ["decision.sign", "quality.review", "regulatory.approve"] as const;

export type FactorKind = "COMPONENT_LOT" | "SUPPLIER" | "PRODUCT_VERSION";
export type Factor = { kind: FactorKind; id: string; lot: string | null };
export type FactorOption = Factor & { kind_label: string; label: string; lots: number; case_lots: number };
export type Shipment = {
  consignee: string;
  consignee_type: string | null;
  consignee_reference: string | null;
  country: string;
  units: number;
  ship_date: string;
};
export type Country = { country: string; units: number };
export type ImpactLot = {
  id: string;
  business_id: string | null;
  lot_identifier: string;
  product: string | null;
  version: string | null;
  made_on: string | null;
  released: number | null;
  complaints: number;
  per_1000: number | null;
  distribution_imported: boolean;
  shipped: number | null;
  in_stock: number | null;
  over_shipped: boolean;
  by_country: Country[];
  shipments: Shipment[];
  evidence: string[];
  excluded: boolean;
  exclusion_reason: string | null;
};
export type Totals = {
  lots: number;
  with_complaints: number;
  without_complaints: number;
  excluded: number;
  complaints: number;
  released: number;
  released_unknown: number;
  shipped: number;
  in_stock: number;
  not_imported: number;
  by_country: Country[];
};
export type ImpactList = {
  factor: Factor & { label: string; kind_label?: string };
  lots: ImpactLot[];
  totals: Totals;
  fingerprint: string;
  truncated: boolean;
};
export type Signature = {
  signer_name: string;
  signer_role: string;
  signed_at: string;
  meaning: string;
  record_id: string;
  record_business_id: string | null;
  content_fingerprint: string;
  scope_version: number | null;
};
export type LotImpactView = {
  investigation: { id: string; business_id: string | null; closed: boolean };
  never_decides: string;
  not_imported: string;
  practice_label: string | null;
  reason_min: number;
  options: FactorOption[];
  suggestion: (Factor & { label: string; kind_label: string; why: string }) | null;
  case_lots: number;
  genealogy: boolean;
  saved: {
    factor: Factor & { label: string; kind_label: string };
    scope_version: number | null;
    saved_at: string | null;
    saved_by_name: string | null;
  } | null;
  source: "saved" | "suggested" | "preview" | null;
  list: ImpactList | null;
  signed: { list: ImpactList; signature: Signature; changed: boolean; changes: string[] } | null;
};

export const lotImpactBase = (caseId: string) => `/api/v1/investigations/${encodeURIComponent(caseId)}/lot-impact`;

/** The list for the saved factor, or a preview for another (nothing is saved by reading it). */
export function lotImpactPath(caseId: string, preview?: Factor | null): string {
  const base = lotImpactBase(caseId);
  if (!preview) return base;
  const query = new URLSearchParams({ kind: preview.kind, ref: preview.id });
  if (preview.lot) query.set("lot", preview.lot);
  return `${base}?${query}`;
}

export const factorKey = (factor: Pick<Factor, "kind" | "id" | "lot"> | null | undefined) =>
  factor ? `${factor.kind}|${factor.id}|${factor.lot ?? ""}` : "";

export function factorOf(key: string, options: readonly FactorOption[]): Factor | null {
  const found = options.find((item) => factorKey(item) === key);
  return found ? { kind: found.kind, id: found.id, lot: found.lot } : null;
}

export const KIND_GROUPS: readonly [FactorKind, string][] = [
  ["COMPONENT_LOT", "Component lots (from lot genealogy)"],
  ["SUPPLIER", "Suppliers"],
  ["PRODUCT_VERSION", "Product versions"],
];

/** "NS-SL-2417: 5 lots, 2 of this case's" for the factor picker. */
export function optionText(option: FactorOption): string {
  const lots = `${option.lots} ${option.lots === 1 ? "lot" : "lots"}`;
  return option.case_lots ? `${option.label}: ${lots}, ${option.case_lots} of this case's` : `${option.label}: ${lots}`;
}

/** "US 230 · IN 112", or the empty text when nothing shipped. */
export const countriesText = (countries: readonly Country[], empty = "—") =>
  countries.length
    ? countries.map((item) => `${item.country} ${item.units.toLocaleString("en-US")}`).join(" · ")
    : empty;

export const unitsText = (value: number | null | undefined) => (value == null ? "—" : value.toLocaleString("en-US"));

/** The lots in the panel's three groups, in the server's order (most complaints first). */
export function groupLots(lots: readonly ImpactLot[]) {
  return {
    withComplaints: lots.filter((lot) => !lot.excluded && lot.complaints > 0),
    withoutComplaints: lots.filter((lot) => !lot.excluded && lot.complaints === 0),
    excluded: lots.filter((lot) => lot.excluded),
  };
}

/** Why the exclusions cannot be kept yet: each lot left out needs a reason of ``min`` characters. */
export function exclusionProblem(excluded: Record<string, string>, lots: readonly ImpactLot[], min: number): string {
  for (const [id, reason] of Object.entries(excluded)) {
    if (reason.trim().replace(/\s+/g, " ").length < min) {
      const name = lots.find((lot) => lot.id === id)?.lot_identifier ?? "this lot";
      return `Say in at least ${min} characters why ${name} is left out.`;
    }
  }
  return "";
}

/** The exclusions as the server keeps them. */
export const exclusionBody = (excluded: Record<string, string>) =>
  Object.entries(excluded).map(([lot_id, reason]) => ({ lot_id, reason: reason.trim() }));

/** The saved exclusions of a list, as the panel edits them. */
export const exclusionsOf = (list: ImpactList | null): Record<string, string> =>
  Object.fromEntries(
    (list?.lots ?? []).filter((lot) => lot.excluded).map((lot) => [lot.id, lot.exclusion_reason ?? ""]),
  );
