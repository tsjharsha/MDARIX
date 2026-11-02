import table from "../../app/linkTable.json";

/**
 * The stable id under which a workspace screen remembers its lists' column choices (app/linkTable.json viewIds), so
 * a screen that moves or is renamed keeps them. Until 0.10.67 they were kept under the section's name
 * ("workspace:Complaints:<list>"); carryOverColumnChoices moves those keys to the id once.
 */
const VIEW_IDS: Readonly<Record<string, string>> = table.viewIds;

export const columnScopeFor = (section: string) =>
  `view:${VIEW_IDS[section] ?? section.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

const PREFIXES = ["mdarix.columns.", "mdarix.columnLayout."];

/**
 * Move every list's saved columns from the section's name to its view id (a newer choice under the id wins). Storage
 * may be missing or refuse (a private window, blocked site data): then nothing moves and nothing breaks. Returns how
 * many keys moved.
 */
export function carryOverColumnChoices(
  storage: Pick<Storage, "length" | "key" | "getItem" | "setItem" | "removeItem">,
) {
  let moved = 0;
  try {
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key) keys.push(key);
    }
    for (const key of keys) {
      const prefix = PREFIXES.find((item) => key.startsWith(`${item}workspace:`));
      if (!prefix) continue;
      const rest = key.slice(prefix.length + "workspace:".length);
      const section = Object.keys(VIEW_IDS).find((name) => rest.startsWith(`${name}:`));
      if (!section) continue;
      const target = `${prefix}${columnScopeFor(section)}${rest.slice(section.length)}`;
      const value = storage.getItem(key);
      if (value !== null && storage.getItem(target) === null) storage.setItem(target, value);
      storage.removeItem(key);
      moved += 1;
    }
  } catch {
    // Storage unavailable: the lists show their default columns, as in a new browser.
  }
  return moved;
}
