import table from "./linkTable.json";
import type { FeatureSet } from "./featureSet";

/**
 * The old -> new link table (linkTable.json): every former address and section name, and the place that holds it now.
 * It is applied when the workspace starts (the address it was opened on) and on every navigation (open()), and it is
 * kept permanently, so e-mails already sent, bookmarks, videos and guides keep working. Stage 7 changes the places.
 */
export type Place = { section: string; tab?: string };

/** The workspace screens of the MVP feature set: each one's address and its tabs. */
export const PLACES: Readonly<Record<string, { path: string; tabs: readonly string[] }>> = table.places;

/** Where each kind of record opens, and the address parameter that names it. */
export type RecordKind = keyof typeof table.records;
export const RECORD_PLACES: Readonly<Record<RecordKind, { section: string; tab: string; param: string }>> =
  table.records;

/** Former addresses (/app/<view>): the section, and tab, each one opened. */
export const OLD_VIEWS = table.oldViews as unknown as Readonly<Record<string, [string, string?]>>;

/** Former tab names, by section: the tab that replaced each. */
export const OLD_TABS: Readonly<Record<string, Readonly<Record<string, string>>>> = table.oldTabs;

/** My Work's approvals tab under the MVP (the queue of decisions awaiting a signature, for people who may sign). */
export const MY_WORK_APPROVALS_TAB = "Approvals";

type OldSection = { section: string; tab?: string; to: Place; keep?: "query" | "view" };
const OLD_SECTIONS: readonly OldSection[] = table.oldSections as OldSection[];

/** A tab's name and what it carries after "?" (a case, a request, a view). */
export function tabParts(tab: string | undefined | null): { name: string; query: string } {
  const text = tab ?? "";
  const mark = text.indexOf("?");
  return mark < 0 ? { name: text, query: "" } : { name: text.slice(0, mark), query: text.slice(mark + 1) };
}

/** A tab named by its former name opens the tab that replaced it; what it carries comes along. */
export function currentTab(section: string, tab: string | undefined): string | undefined {
  const { name, query } = tabParts(tab);
  const now = OLD_TABS[section]?.[name];
  return now ? (query ? `${now}?${query}` : now) : tab;
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
 * The first row of the table that names the section (and the tab, where it names one) decides.
 */
export function routeFor(
  section: string,
  tab: string | undefined,
  featureSet: FeatureSet,
): { section: string; tab: string | undefined } {
  if (featureSet !== "mvp") return { section, tab };
  const { name, query } = tabParts(tab);
  const row = OLD_SECTIONS.find((item) => item.section === section && (item.tab === undefined || item.tab === name));
  if (!row) return { section, tab: currentTab(section, tab) };
  const to = row.to;
  if (row.keep === "query") return { section: to.section, tab: query ? `${to.tab}?${query}` : to.tab };
  if (row.keep === "view") return { section: to.section, tab: `${to.tab}?${new URLSearchParams({ view: tab ?? "" })}` };
  return { section: to.section, tab: to.tab };
}

/** The place a record opens: its section and tab, the record named by its parameter (Reports?report=<id>). */
export function recordPlace(kind: RecordKind, id: string, extra: Record<string, string> = {}): Place {
  const place = RECORD_PLACES[kind];
  const params = new URLSearchParams(kind === "case" ? extra : { [place.param]: id, ...extra });
  const query = params.toString();
  return { section: place.section, tab: query ? `${place.tab}?${query}` : place.tab };
}

/** A place as the server names it (backend/app/links.py): a section, a tab, a record and a panel. */
export type Target = {
  section: string;
  tab?: string | null;
  record?: { kind: string; id: string } | null;
  panel?: string | null;
};

/** What a server answer says a button opens: the section and tab older answers carry, and the target beside them. */
export type Opens = { section: string; tab?: string | null; target?: Target | null };

/**
 * The one resolver for server-sent links: the structured target where the answer has one (a record named by its own
 * parameter on its own place, `event` on Oversight, else by its kind: Reports?complaint=<id>), else the section and
 * tab an answer from before 0.10.67 (an alert raised then, a tab left open across an upgrade) carries.
 */
export function placeOf(opens: Opens): Place {
  const target = opens.target;
  if (!target) return { section: opens.section, tab: opens.tab ?? undefined };
  const record = target.record;
  if (!record || record.kind === "case") return { section: target.section, tab: target.tab ?? undefined };
  const home = RECORD_PLACES[record.kind as RecordKind];
  const own = !!home && home.section === target.section && home.tab === target.tab;
  const tab = target.tab ?? "";
  const param = own ? home.param : record.kind;
  return { section: target.section, tab: `${tab}?${new URLSearchParams({ [param]: record.id })}` };
}
