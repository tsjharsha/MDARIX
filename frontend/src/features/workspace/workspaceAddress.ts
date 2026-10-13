import { APP_ROUTES, viewFromPath, type AppView } from "../../app/router";
import type { WorkspaceSection } from "./workspaceContext";

/**
 * The address of a workspace screen under the MVP feature set (app/featureSet.ts), so the browser's Back and Forward,
 * bookmarks and links in emails open the same screen: a section's own path (router.ts), and for the one case page the
 * case and its step, e.g. /app/investigations?case=INV000147&step=Decision. Sections without a path of their own are
 * named by ?section=.
 */
const SECTION_VIEW: Readonly<Record<string, AppView>> = {
  Dashboard: "home",
  "My Work": "my-work",
  Products: "products",
  Signals: "signals",
  Investigations: "investigations",
  Evidence: "evidence",
  Decisions: "decision",
  Intelligence: "ask",
  "Trust & Audit": "audit",
};

/** A tab's name without what it carries after "?" (a request, a view): the address names the tab only. */
const tabName = (tab: string | null | undefined) => (tab ?? "").split("?")[0].trim();

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

export function addressFor(location: { section: string; tab?: string; caseRef?: string | null }): string {
  const view = SECTION_VIEW[location.section];
  const params = new URLSearchParams();
  if (!view) params.set("section", location.section);
  const tab = tabName(location.tab);
  if (location.section === "Investigations") {
    if (location.caseRef) params.set("case", location.caseRef);
    if (tab && tab !== "All investigations") params.set("step", tab);
  } else if (view && tab) params.set("tab", tab);
  const query = params.toString();
  return `${APP_ROUTES[view ?? "home"]}${query ? `?${query}` : ""}`;
}

/**
 * The screen an address names, or null when it names no section, step or tab (then the workspace starts as it
 * always has: from the path, a case link or the saved context).
 */
export function locationFromAddress(
  pathname: string,
  search: string,
  viewToSection: Readonly<Record<string, [WorkspaceSection, string?]>>,
  sections: readonly string[],
): { section: WorkspaceSection; tab?: string } | null {
  const params = new URLSearchParams(search);
  const named = params.get("section");
  const step = tabName(params.get("step"));
  const tab = tabName(params.get("tab"));
  if (!named && !step && !tab) return null;
  if (named) return sections.includes(named) ? { section: named as WorkspaceSection } : null;
  const [section, defaultTab] = viewToSection[viewFromPath(pathname)] ?? ["Dashboard"];
  const chosen = section === "Investigations" ? step : tab;
  return { section, tab: chosen || defaultTab };
}
