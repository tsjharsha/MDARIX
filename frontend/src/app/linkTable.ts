import table from "./linkTable.json";
import type { FeatureSet } from "./featureSet";

/**
 * The old -> new link table (linkTable.json): every former address and section name, and the place that holds it now.
 * It is applied when the workspace starts (the address it was opened on) and on every navigation (open()), and it is
 * kept permanently, so e-mails already sent, bookmarks, videos and guides keep working. Stage 7 changes the places.
 */
export type Place = { section: string; tab?: string | undefined };

/** The workspace screens of the MVP feature set: each one's address and its tabs. */
export const PLACES: Readonly<Record<string, { path: string; tabs: readonly string[] }>> = table.places;

/** An organization's navigation (session context `navigation`, tenants.navigation): today's menu or the new one. */
export type Navigation = "classic" | "new";
export const navigationOf = (value: unknown): Navigation => (value === "new" ? "new" : "classic");

/** The screens of the new navigation (stage 7): each one's address, its name in the menu, its tabs and views. */
export type NewPlace = {
  path: string;
  label?: string;
  tabs: readonly string[];
  views?: Readonly<Record<string, readonly string[]>>;
};
export const NEW_PLACES: Readonly<Record<string, NewPlace>> = table.newPlaces;

/** The new navigation's menu: the four main screens, and Settings, Team and Account at the top right. */
export const NEW_MENU: { main: readonly string[]; top: readonly string[] } = table.newMenu;

/** The screens of a navigation. */
export const placesFor = (
  navigation: Navigation,
): Readonly<Record<string, { path: string; tabs: readonly string[] }>> => (navigation === "new" ? NEW_PLACES : PLACES);

/** A screen's name as its menu and heading say it: "My work", "Account" on the new navigation. */
export const placeLabel = (section: string, navigation: Navigation): string =>
  (navigation === "new" && NEW_PLACES[section]?.label) || section;

/** Where each kind of record opens, and the address parameter that names it. */
export type RecordKind = keyof typeof table.records;
export const RECORD_PLACES: Readonly<Record<RecordKind, { section: string; tab: string; param: string }>> =
  table.records;
/** Where each kind of record opens on the new navigation: a complaint on its own page. */
export const NEW_RECORD_PLACES: Readonly<Record<RecordKind, { section: string; tab: string; param: string }>> =
  table.newRecords;

/** Former addresses (/app/<view>): the section, and tab, each one opened. */
export const OLD_VIEWS = table.oldViews as unknown as Readonly<Record<string, [string, string?]>>;

/** Former tab names, by section: the tab that replaced each. */
export const OLD_TABS: Readonly<Record<string, Readonly<Record<string, string>>>> = table.oldTabs;

/** My Work's approvals tab under the MVP (the queue of decisions awaiting a signature, for people who may sign). */
export const MY_WORK_APPROVALS_TAB = "Approvals";

type OldSection = { section: string; tab?: string; to: Place; keep?: "query" | "view" };
const OLD_SECTIONS: readonly OldSection[] = table.oldSections as OldSection[];

/**
 * A row of newHomes (classic place -> its home on the new navigation) or classicHomes (the reverse, for an address of
 * the new navigation opened by an organization on the classic one): `has` names a parameter the tab must carry,
 * `keep` keeps what it carries, `rename` renames a parameter (Oversight?event=<id> -> Complaint?ref=<id>), `add`
 * sets one (the view a former tab is now).
 */
type HomeRow = {
  section: string;
  tab?: string;
  has?: string;
  to: Place;
  keep?: "query";
  rename?: Record<string, string>;
  add?: Record<string, string>;
};
export const NEW_HOMES: readonly HomeRow[] = table.newHomes as HomeRow[];
const CLASSIC_HOMES: readonly HomeRow[] = table.classicHomes as HomeRow[];

/** A place through one table of homes: the first row that names its section (and tab, and parameter) decides. */
function homeOf(
  rows: readonly HomeRow[],
  section: string,
  tab: string | undefined,
): { section: string; tab: string | undefined } {
  const { name, query } = tabParts(tab);
  const carried = new URLSearchParams(query);
  const row = rows.find(
    (item) =>
      item.section === section && (item.tab === undefined || item.tab === name) && (!item.has || carried.has(item.has)),
  );
  if (!row) return { section, tab };
  const params = new URLSearchParams();
  if (row.keep === "query") for (const [key, value] of carried) params.append(row.rename?.[key] ?? key, value);
  for (const [key, value] of Object.entries(row.add ?? {})) if (!params.has(key)) params.set(key, value);
  const rest = params.toString();
  const to = row.to.tab ?? "";
  return { section: row.to.section, tab: rest ? `${to}?${rest}` : row.to.tab };
}

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
  navigation: Navigation = "classic",
): { section: string; tab: string | undefined } {
  if (featureSet !== "mvp") return { section, tab };
  const classic = classicRoute(section, tab);
  // The new navigation (stage 7) moves every classic place to its new home; a place already on it stays. A parked
  // section with a home of its own there (Products: Product 360, 0.10.94) goes there before its classic parking.
  if (navigation === "new") {
    if (onNewPlace(section, tab)) return { section, tab };
    return NEW_HOMES.some((row) => row.section === section && row.section !== classic.section)
      ? homeOf(NEW_HOMES, section, tab)
      : homeOf(NEW_HOMES, classic.section, classic.tab);
  }
  return CLASSIC_HOMES.some((row) => row.section === classic.section)
    ? homeOf(CLASSIC_HOMES, classic.section, classic.tab)
    : classic;
}

/** Whether a place is one of the new navigation's own: its screen, and its tab when it names one. */
function onNewPlace(section: string, tab: string | undefined): boolean {
  const place = NEW_PLACES[section];
  const name = tabParts(tab).name;
  return !!place && (!name || place.tabs.includes(name));
}

/** The classic place of a link: a parked section's screen, a former tab's new name. */
function classicRoute(section: string, tab: string | undefined): { section: string; tab: string | undefined } {
  const { name, query } = tabParts(tab);
  const row = OLD_SECTIONS.find((item) => item.section === section && (item.tab === undefined || item.tab === name));
  if (!row) return { section, tab: currentTab(section, tab) };
  const to = row.to;
  if (row.keep === "query") return { section: to.section, tab: query ? `${to.tab}?${query}` : to.tab };
  if (row.keep === "view")
    return { section: to.section, tab: `${to.tab}?${new URLSearchParams({ view: currentTab(section, tab) ?? "" })}` };
  return { section: to.section, tab: to.tab };
}

/** The place a record opens: its section and tab, the record named by its parameter (Reports?report=<id>). */
export function recordPlace(
  kind: RecordKind,
  id: string,
  extra: Record<string, string> = {},
  navigation: Navigation = "classic",
): Place {
  const place = (navigation === "new" ? NEW_RECORD_PLACES : RECORD_PLACES)[kind];
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

/**
 * Words that point somewhere (7.10): a text's "A › B" paths (the user guide, the trial guide) as an organization on the
 * new navigation reads them, through the same table: "Complaints › Reports" reads "Complaints › Reporting",
 * "Readiness › Oversight" "My work › Team overview". A path the table does not know stays as written.
 */
export function newPathText(text: string): string {
  const longest = (items: readonly string[]) => [...items].sort((a, b) => b.length - a.length).join("|");
  // Screen and tab names are words, spaces and "&" only (linkTable.json), so they need no escaping in the pattern.
  const tabs = longest([...new Set(Object.values(PLACES).flatMap((place) => place.tabs))]);
  const pattern = new RegExp(`(?<![A-Za-z])(${longest(Object.keys(PLACES))}) › (${tabs})?`, "g");
  return text.replace(pattern, (whole, section: string, tab: string | undefined) => {
    const own = !!tab && PLACES[section].tabs.includes(tab);
    if (!own && PLACES[section].tabs.length) return whole;
    const place = routeFor(section, own ? tab : undefined, "mvp", "new");
    const label = placeLabel(place.section, "new");
    if (!own) return `${label} › ${tab ?? ""}`;
    const now = tabParts(place.tab);
    const view = new URLSearchParams(now.query).get("view");
    return [label, now.name, view].filter(Boolean).join(" › ");
  });
}
