// Keyboard use of the website header's menus (WEB-10, WCAG 2.4.3 focus order). A menu's panel follows the whole
// navigation in the page, so the browser's own Tab order would reach its links only after the rest of the header.
// These rules give the order a reader expects: the button, then its links, then the next item of the header.

/** Where the focus is in an open menu: on its button, or on one of its links (by position, of `count`). */
export type MenuFocus = { at: "button" } | { at: "link"; index: number; count: number };

/** What a key does there: move to the first link, back to the button, close the menu and move to the header item
 * after the button, close it and return to the button, or nothing (the browser's own behaviour). */
export type MenuMove = "first-link" | "button" | "close-and-continue" | "close-to-button" | null;

export function menuMove(key: string, shift: boolean, focus: MenuFocus): MenuMove {
  if (key === "Escape") return "close-to-button";
  if (key !== "Tab") return null;
  if (focus.at === "button") return shift ? null : "first-link";
  if (shift) return focus.index === 0 ? "button" : null;
  return focus.index === focus.count - 1 ? "close-and-continue" : null;
}

/** The id of a menu's panel, for its button's aria-controls. */
export const menuPanelId = (name: string) => `ms-menu-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
