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

/**
 * Workspace sections the MVP parks. The MVP is five screens (Readiness, Complaints, Signals, the one case page,
 * Records) plus My Work, Import data and My Account: Readiness is the home instead of the Dashboard; a case's evidence,
 * Ask MDARIX and decision are steps of the case page; approvals are in My Work; the audit trail, reports and signature
 * verification are in Records; products are read through Readiness, Complaints and Signals.
 */
export const PARKED_SECTIONS: readonly string[] = [
  "Dashboard",
  "Products",
  "Evidence",
  "Decisions",
  "Intelligence",
  "Trust & Audit",
];

/** Records' tabs under the MVP: the inspector's records, then what moved there from the parked sections. */
export const MVP_RECORDS_TABS = [
  "Effectiveness checks",
  "Risk file input",
  "Audit trail",
  "Reports",
  "Verify a signature",
] as const;
export type MvpRecordsTab = (typeof MVP_RECORDS_TABS)[number];

/** My Work's approvals tab under the MVP (the queue of decisions awaiting a signature, for people who may sign). */
export const MY_WORK_APPROVALS_TAB = "Approvals";

/**
 * Customer administration sections the MVP parks: the source-system connections and their sync runs (nothing should
 * look like a live QMS or ERP integration until one exists) and the field mapping studio. Data comes in through
 * Import data.
 */
export const PARKED_CUSTOMER_ADMIN_SECTIONS: readonly string[] = ["Integrations", "Data Mapping"];

/**
 * Platform administration the MVP parks: Data & Integrations (connectors, schemas, mappings, releases and runs: the
 * mapping chain a pilot on CSV imports does not use), renewals and their reminder emails (pilots are invoiced by hand),
 * tenant cells and the developer API reference. A link to a parked section opens the one named here, or its area's
 * first section.
 */
export const PARKED_ADMIN_AREAS: readonly string[] = ["Data & Integrations"];
export const PARKED_ADMIN_SECTIONS: Readonly<Record<string, readonly string[]>> = {
  "Plans & Licensing": ["Renewals", "Reminders"],
  Operations: ["Tenant cells", "Developer API"],
};
/** The one-line purpose of an area whose parked sections it no longer names. */
const MVP_ADMIN_PURPOSE: Readonly<Record<string, string>> = {
  "Plans & Licensing": "Plans and subscriptions",
  Operations: "Health, queues, email and problem reports",
};
export const PARKED_ADMIN_FALLBACK: Readonly<Record<string, string>> = {
  Renewals: "Subscriptions",
  Reminders: "Subscriptions",
};

/** The platform administration areas this feature set offers, each with the sections it keeps, in order. */
export function adminAreasFor<T extends readonly [string, string, unknown, readonly string[]]>(
  areas: readonly T[],
  featureSet: FeatureSet,
): T[] {
  if (featureSet !== "mvp") return [...areas];
  return areas
    .filter((area) => !PARKED_ADMIN_AREAS.includes(area[0]))
    .map((area) => {
      const parked = PARKED_ADMIN_SECTIONS[area[0]];
      if (!parked) return area;
      const items = area[3].filter((item) => !parked.includes(item));
      return [area[0], MVP_ADMIN_PURPOSE[area[0]] ?? area[1], area[2], items] as unknown as T;
    });
}

/**
 * The data the MVP's screens read, in loading order: products, lots (with quantities, for per-unit trends), complaints,
 * then the investigations, CAPAs and risks that refer to them (the readiness checks, effectiveness checks and risk file
 * input). Under mvp the other templates (components, suppliers, bill of materials…) are offered on request only.
 */
export const MVP_IMPORT_ENTITIES: readonly string[] = [
  "products",
  "lots",
  "complaints",
  "investigations",
  "capas",
  "risks",
];

/** The import templates to show first, and the ones offered on request, for this feature set. */
export function importTemplatesFor<T extends { entity: string }>(
  templates: readonly T[],
  featureSet: FeatureSet,
): { core: T[]; more: T[] } {
  if (featureSet !== "mvp") return { core: [...templates], more: [] };
  const rank = (item: T) => MVP_IMPORT_ENTITIES.indexOf(item.entity);
  return {
    core: templates.filter((item) => rank(item) >= 0).sort((left, right) => rank(left) - rank(right)),
    more: templates.filter((item) => rank(item) < 0),
  };
}

/** A tab's name and what it carries after "?" (a case, a request, a view). */
function tabParts(tab: string | undefined): { name: string; query: string } {
  const text = tab ?? "";
  const mark = text.indexOf("?");
  return mark < 0 ? { name: text, query: "" } : { name: text.slice(0, mark), query: text.slice(mark + 1) };
}

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

/**
 * Where a workspace link goes under this feature set. Under `mvp` every link into a parked section (a task, a case
 * step, an old bookmark, a story chapter) opens the screen that now holds that work, so nothing is a dead end:
 * - Dashboard and Products: Readiness, the home.
 * - Evidence: a case's evidence is a step of the case page; evidence requests are in My Work.
 * - Decisions: a decision is the case page's Decision step; approvals are in My Work; signature verification is in
 *   Records.
 * - Intelligence: Ask MDARIX is a step of the case page (it answers without a case too); risk and regulatory reviews
 *   are the case's Reviews step; reports are in Records.
 * - Trust & Audit: Records › Audit trail, with the case timeline, replay, AI runs, integrity and the audit trail.
 */
export function routeFor(
  section: string,
  tab: string | undefined,
  featureSet: FeatureSet,
): { section: string; tab: string | undefined } {
  if (featureSet !== "mvp") return { section, tab };
  const { name, query } = tabParts(tab);
  // Readiness is the MVP's home: links to the Dashboard and the parked Products section open it.
  if (section === "Dashboard" || section === "Products") return { section: "Readiness", tab: undefined };
  if (section === "Evidence") {
    if (name === "Requests")
      return { section: "My Work", tab: query ? `Evidence requests?${query}` : "Evidence requests" };
    return { section: "Investigations", tab: "Evidence" };
  }
  if (section === "Decisions") {
    if (name === MY_WORK_APPROVALS_TAB) return { section: "My Work", tab: MY_WORK_APPROVALS_TAB };
    if (name === "Verify a signature") return { section: "Records", tab: "Verify a signature" };
    // The decision of a case (with a follow-up or assessment to open); the legacy Decision center is parked.
    if (name === "Decision") return { section: "Investigations", tab };
    return { section: "Investigations", tab: "Decision" };
  }
  if (section === "Intelligence") {
    if (name === "Reports") return { section: "Records", tab: "Reports" };
    if (name === "Risk & traceability" || name === "Regulatory copilot")
      return { section: "Investigations", tab: "Reviews" };
    return { section: "Investigations", tab: "Ask MDARIX" };
  }
  if (section === "Trust & Audit") {
    // AI assurance is parked; every other view keeps its case and label (see recordsAuditView).
    if (!name || name === "AI assurance") return { section: "Records", tab: "Audit trail" };
    return { section: "Records", tab: `Audit trail?${new URLSearchParams({ view: tab ?? "" })}` };
  }
  return { section, tab };
}

/** The Trust & Audit view a Records › Audit trail tab carries ("Audit trail?view=Case timeline?case=…"), or null. */
export function recordsAuditView(tab: string | undefined): string | null {
  const { name, query } = tabParts(tab);
  if (name !== "Audit trail" || !query) return null;
  const view = new URLSearchParams(query).get("view");
  return view && view.trim() ? view : null;
}

/** The requested tab when the section offers it, else the fallback when offered, else the first tab. */
export function offeredTab<T extends string>(requested: string | null | undefined, tabs: readonly T[], fallback: T): T {
  if (requested && (tabs as readonly string[]).includes(requested)) return requested as T;
  return tabs.includes(fallback) ? fallback : tabs[0];
}
