// The working context (product, version, investigation, time view) is kept by the server for each person
// (GET/PUT /api/v1/workspace/context), so it survives a reload and a new sign-in. These pure rules translate between
// the server's record and the workspace's own state, and read a case link (?case=INV000147).
import type { TemporalMode } from "../../app/types";
import type { WorkspaceSection } from "./workspaceContext";

/** The saved context as GET/PUT /api/v1/workspace/context return it (only the fields the workspace uses). */
export type SavedContext = {
  product_id?: string | null;
  product_version_id?: string | null;
  investigation_id?: string | null;
  temporal_mode?: string | null;
  temporal_cutoff?: string | null;
  product_business_id?: string | null;
  investigation_business_id?: string | null;
};

/** GET /api/v1/workspace/context/resolve?investigation=<business id>. */
export type ResolvedCase = {
  investigation_id: string;
  investigation_business_id?: string | null;
  product_id: string;
  product_business_id?: string | null;
};

/** What the workspace holds: a product and investigation by id, a version by its UUID, and the time view. */
export type ContextChoice = {
  productId: string;
  versionId: string | null;
  investigationId: string;
  mode: TemporalMode;
  asOf: string;
};

const MODE_TO_SERVER: Record<TemporalMode, string> = {
  current: "CURRENT",
  event: "EVENT_AS_OF",
  known: "KNOWN_AS_OF",
};

/** The workspace's time view for the server's temporal mode; null when the value is unknown. */
export function modeFromServer(value: unknown): TemporalMode | null {
  const code = String(value ?? "")
    .trim()
    .toUpperCase();
  const match = (Object.entries(MODE_TO_SERVER) as Array<[TemporalMode, string]>).find(([, server]) => server === code);
  return match?.[0] ?? null;
}

const DAY = /^(\d{4}-\d{2}-\d{2})/;

/**
 * The body of PUT /api/v1/workspace/context. The point in time is saved only for a historical view: "Current" always
 * opens on today, so an old date is never brought back with it.
 */
export function contextBody(choice: ContextChoice) {
  return {
    product_id: choice.productId || null,
    product_version_id: choice.versionId || null,
    investigation_id: choice.investigationId || null,
    temporal_mode: MODE_TO_SERVER[choice.mode] ?? "CURRENT",
    temporal_cutoff: choice.mode !== "current" && DAY.test(choice.asOf) ? `${choice.asOf}T00:00:00Z` : null,
  };
}

/**
 * The saved context to start from, when it still holds: its product must still be one of the organization's
 * products. The version and the investigation are applied once that product's versions and cases are known (and only
 * when they are still among them); the time view only when it is a historical one with its date.
 */
export function restoredChoice(
  saved: SavedContext | null | undefined,
  products: Array<{ id: string }>,
): {
  productId: string;
  versionId: string | null;
  investigationId: string | null;
  mode: TemporalMode | null;
  asOf: string | null;
} | null {
  const productId = saved?.product_id ? String(saved.product_id) : "";
  if (!productId || !products.some((product) => product.id === productId)) return null;
  const mode = modeFromServer(saved?.temporal_mode);
  const day = DAY.exec(String(saved?.temporal_cutoff ?? ""))?.[1] ?? null;
  const historical = mode && mode !== "current" && day;
  return {
    productId,
    versionId: saved?.product_version_id ? String(saved.product_version_id) : null,
    investigationId: saved?.investigation_id ? String(saved.investigation_id) : null,
    mode: historical ? mode : null,
    asOf: historical ? day : null,
  };
}

/** The version identifier ("B") of the product version with this id, among a Product 360 response's versions. */
export function versionIdentifierFor(
  versions: Array<Record<string, unknown>> | null | undefined,
  versionId: string | null | undefined,
): string | null {
  if (!versionId) return null;
  const match = (versions ?? []).find((version) => String(version?.id ?? "") === versionId);
  const identifier = match?.version_identifier;
  return typeof identifier === "string" && identifier.trim() ? identifier : null;
}

// A business ID as people quote it (INV000147); anything else in the address is ignored.
const CASE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

/** The case a link names (?case=INV000147), or null when the address names none (or something that is not an ID). */
export function caseFromSearch(search: string | null | undefined): string | null {
  const value = new URLSearchParams(search ?? "").get("case")?.trim() ?? "";
  return CASE_ID.test(value) ? value : null;
}

/** The address's query without its case link (so a reload starts from the saved context, not the old link). */
export function searchWithoutCase(search: string | null | undefined): string {
  const params = new URLSearchParams(search ?? "");
  params.delete("case");
  const rest = params.toString();
  return rest ? `?${rest}` : "";
}

/** Where a case link opens: the case's workspace or its decision; any other address opens as it would without one. */
export function caseLinkStart(
  view: string | undefined,
  start: [WorkspaceSection, string?],
): [WorkspaceSection, string?] {
  if (view === "investigations") return ["Investigations", "Workspace"];
  if (view === "decision") return ["Decisions", "Decision center"];
  return start;
}
