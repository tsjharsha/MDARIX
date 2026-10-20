import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { menuMove, menuPanelId } from "./menuKeys";
import { PublicMegaSite } from "../PublicMegaSite";

// WEB-10: the keyboard order of the website header's menus (WCAG 2.4.3).
describe("header menu keys", () => {
  it("moves from an open menu's button into its first link", () => {
    expect(menuMove("Tab", false, { at: "button" })).toBe("first-link");
    expect(menuMove("Tab", true, { at: "button" })).toBeNull();
  });

  it("goes back to the button from the first link, and on past the last link", () => {
    expect(menuMove("Tab", true, { at: "link", index: 0, count: 5 })).toBe("button");
    expect(menuMove("Tab", false, { at: "link", index: 2, count: 5 })).toBeNull();
    expect(menuMove("Tab", true, { at: "link", index: 2, count: 5 })).toBeNull();
    expect(menuMove("Tab", false, { at: "link", index: 4, count: 5 })).toBe("close-and-continue");
  });

  it("closes on Escape and returns to the button", () => {
    expect(menuMove("Escape", false, { at: "button" })).toBe("close-to-button");
    expect(menuMove("Escape", false, { at: "link", index: 1, count: 3 })).toBe("close-to-button");
    expect(menuMove("Enter", false, { at: "link", index: 1, count: 3 })).toBeNull();
  });

  it("names each panel for its button's aria-controls, set only while the menu is open", () => {
    expect(menuPanelId("Product Lifecycle")).toBe("ms-menu-product-lifecycle");
    const scope = globalThis as unknown as { window?: unknown };
    scope.window = { location: { pathname: "/", search: "", hash: "", origin: "https://mdarix.in" } };
    try {
      const html = renderToStaticMarkup(createElement(PublicMegaSite, { path: "/" }));
      expect(html).toContain('aria-expanded="false"');
      // No menu is open on a page's first draw, so no button points at a panel that is not there.
      expect(html).not.toContain('aria-controls="ms-menu-');
    } finally {
      delete scope.window;
    }
  });
});
