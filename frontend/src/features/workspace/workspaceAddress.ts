import { APP_ROUTES, viewFromPath, type AppView } from "../../app/router";
import { NEW_PLACES, OLD_VIEWS, PLACES, tabParts } from "../../app/linkTable";
import type { WorkspaceSection } from "./workspaceContext";

/**
 * The one address scheme of the workspace (quality plan stage 6): every screen, tab, record, open panel and filter
 * has an address, so Back, refresh and a new tab keep it, and links in e-mails open it.
 *
 *   /app/<section>?tab=<tab>&<what the tab carries>
 *   /app/complaints?tab=Reports&complaint=<id>&report=<id>      a complaint's reports, one report's panel open
 *   /app/signals?tab=Signal+inbox&priority=HIGH&signal=SIG000023 the inbox's filters and one signal
 *   /app/investigations?case=INV000147&step=Decision            the case page: the case and its step
 *   /app/complaints/RV-06?tab=History                            one complaint's page (new navigation, 0.10.68)
 *
 * A tab name carries its record, panel and filters after "?" ("Reports?complaint=<id>", see linkTable.ts recordPlace);
 * the address spells them out beside the tab. Each section's path is in app/linkTable.json; a former address (a path,
 * ?section=, a former section or tab name) is read through the same table.
 */

/** Parameters the address itself uses; a tab's own parameters never take these names. */
const RESERVED = ["section", "tab", "step", "case"];

/** The path of a section: its place's (linkTable.json), else the former view that named it, else the home. */
function pathOf(section: string, tab = ""): { path: string; own: boolean } {
  const place = PLACES[section] ?? NEW_PLACES[section];
  if (place) return { path: place.path, own: true };
  const views = Object.entries(OLD_VIEWS).filter(([, [name]]) => name === section);
  const view = (views.find(([, [, named]]) => named === tab) ??
    views.find(([, [, named]]) => !named) ??
    views[0])?.[0] as AppView | undefined;
  return view && APP_ROUTES[view] ? { path: APP_ROUTES[view], own: true } : { path: APP_ROUTES.home, own: false };
}

/** What the browser keeps with each workspace address, to restore the screen and its case on Back and Forward. */
export type WorkspaceHistoryState = {
  mdarixWorkspace: true;
  section: WorkspaceSection;
  tab?: string;
  caseId: string | null;
  productId: string | null;
};

export function isWorkspaceHistoryState(value: unknown): value is WorkspaceHistoryState {
  return (
    typeof value === "object" && value !== null && (value as { mdarixWorkspace?: unknown }).mdarixWorkspace === true
  );
}

/** The section of one complaint's page, and its path's prefix: /app/complaints/<ref>. */
export const COMPLAINT_PAGE = "Complaint";
const COMPLAINT_PATH = /^\/app\/complaints\/([^/]+)\/?$/;

export function addressFor(location: { section: string; tab?: string; caseRef?: string | null }): string {
  const { name, query } = tabParts(location.tab);
  if (location.section === COMPLAINT_PAGE) {
    // The complaint's reference is the path; its section (other than Summary) and what it carries follow.
    const carried = new URLSearchParams(query);
    const ref = carried.get("ref") ?? "";
    carried.delete("ref");
    const params = new URLSearchParams();
    if (name && name !== "Summary") params.set("tab", name);
    for (const [key, value] of carried) if (!RESERVED.includes(key)) params.append(key, value);
    const text = params.toString();
    return `/app/complaints/${encodeURIComponent(ref)}${text ? `?${text}` : ""}`;
  }
  const { path, own } = pathOf(location.section, name);
  const params = new URLSearchParams();
  if (!own) params.set("section", location.section);
  if (location.section === "Investigations") {
    if (location.caseRef) params.set("case", location.caseRef);
    // The list (classic: with its case kept; the new navigation, 0.10.74: no case) is named when no case is.
    if (name && (name !== "All investigations" || !location.caseRef)) params.set("step", name);
  } else if (name) params.set("tab", name);
  for (const [key, value] of new URLSearchParams(query)) if (!RESERVED.includes(key)) params.append(key, value);
  const text = params.toString();
  return `${path}${text ? `?${text}` : ""}`;
}

/**
 * The screen an address names, or null when it names no section, step, tab or record (then the workspace starts as
 * it always has: from the path, a case link or the saved context). The tab comes back with what it carried.
 */
export function locationFromAddress(
  pathname: string,
  search: string,
  viewToSection: Readonly<Record<string, [WorkspaceSection, string?]>>,
  sections: readonly string[],
): { section: WorkspaceSection; tab?: string } | null {
  const params = new URLSearchParams(search);
  const page = COMPLAINT_PATH.exec(pathname);
  if (page) {
    const carried = new URLSearchParams({ ref: decodeURIComponent(page[1]) });
    for (const [key, value] of params) if (!RESERVED.includes(key)) carried.append(key, value);
    return {
      section: COMPLAINT_PAGE as WorkspaceSection,
      tab: `${(params.get("tab") ?? "").trim() || "Summary"}?${carried}`,
    };
  }
  const named = params.get("section");
  if (named && !sections.includes(named)) return null;
  const [section, defaultTab] = named
    ? [named as WorkspaceSection]
    : (viewToSection[viewFromPath(pathname)] ?? ["Dashboard" as WorkspaceSection]);
  const carried = new URLSearchParams();
  for (const [key, value] of params) if (!RESERVED.includes(key)) carried.append(key, value);
  const step = (params.get("step") ?? "").trim();
  const tab = (params.get("tab") ?? "").trim();
  const chosen = (section === "Investigations" ? step : tab) || defaultTab || "";
  const rest = carried.toString();
  if (!named && !step && !tab && !rest) return null;
  const full = rest ? `${chosen}?${rest}` : chosen;
  return full ? { section, tab: full } : { section };
}

/** One parameter a tab carries ("Reports?report=<id>" -> report), or null. */
export function tabParam(tab: string | undefined | null, name: string): string | null {
  const value = new URLSearchParams(tabParts(tab).query).get(name);
  return value && value.trim() ? value.trim() : null;
}

/** The tab with one parameter set (or, with null, removed); the tab's name and its other parameters stay. */
export function withTabParam(tab: string | undefined | null, name: string, value: string | null): string {
  const { name: tabName, query } = tabParts(tab);
  const params = new URLSearchParams(query);
  if (value) params.set(name, value);
  else params.delete(name);
  const rest = params.toString();
  return rest ? `${tabName}?${rest}` : tabName;
}

/**
 * What Back or Forward to a history entry changes on screen: nothing (the same tab with the same record and filters),
 * only what the tab carries (the same tab: a panel closes or opens again, a filter comes back) or the whole screen
 * (another tab or section, opened afresh).
 */
export function restoreKind(
  now: { section: string; tab?: string },
  entry: { section: string; tab?: string },
): "nothing" | "carried" | "screen" {
  if (now.section !== entry.section || tabParts(now.tab).name !== tabParts(entry.tab).name) return "screen";
  return (now.tab ?? "") === (entry.tab ?? "") ? "nothing" : "carried";
}
