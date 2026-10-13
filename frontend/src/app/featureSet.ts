import type { AppView } from "./router";

/**
 * Which features the server offers (session context `feature_set`, backend/app/feature_set.py): everything as built
 * (`full`, the default) or the lightweight MVP (`mvp`). Under `mvp` the parked areas below are hidden here and their
 * API routes answer 404 on the server; their code is kept and comes back with `full`.
 */
export type FeatureSet = "full" | "mvp";

/** Anything other than "mvp" (missing, older servers, an unexpected value) is the full product. */
export function featureSetOf(value: unknown): FeatureSet {
  return typeof value === "string" && value.trim().toLowerCase() === "mvp" ? "mvp" : "full";
}

/** Screens (addresses) the MVP parks. An old link to one opens the nearest screen the MVP keeps. */
export const PARKED_VIEWS: readonly AppView[] = [
  "story",
  "persona",
  "assurance",
  "regulatory-copilot",
  "risk-traceability",
  "admin-stage2",
  "admin-product-configuration",
  "admin-subscriptions",
  "admin-mapping",
  "platform-licenses",
];

/** Tabs the MVP parks, by workspace section. */
export const PARKED_TABS: Readonly<Record<string, readonly string[]>> = {
  Investigations: ["Story"],
  Intelligence: ["Regulatory copilot", "Risk & traceability"],
  Decisions: ["Decision center"],
  "Trust & Audit": ["AI assurance"],
};

export function viewsForFeatureSet(
  views: readonly AppView[] | null,
  featureSet: FeatureSet,
): readonly AppView[] | null {
  if (!views || featureSet !== "mvp") return views;
  return views.filter((view) => !PARKED_VIEWS.includes(view));
}

/** A section's tabs for this feature set, in their order. */
export function tabsFor<T extends string>(section: string, tabs: readonly T[], featureSet: FeatureSet): readonly T[] {
  if (featureSet !== "mvp") return tabs;
  const parked = PARKED_TABS[section] ?? [];
  return tabs.filter((tab) => !parked.includes(tab));
}

/** The requested tab when the section offers it, else the fallback when offered, else the first tab. */
export function offeredTab<T extends string>(requested: string | null | undefined, tabs: readonly T[], fallback: T): T {
  if (requested && (tabs as readonly string[]).includes(requested)) return requested as T;
  return tabs.includes(fallback) ? fallback : tabs[0];
}
