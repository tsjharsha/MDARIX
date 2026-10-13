import { describe, expect, it } from "vitest";
import { addressFor, isWorkspaceHistoryState, locationFromAddress } from "./workspaceAddress";
import { VIEW_TO_SECTION } from "./UserWorkspace";
import { WORKSPACE_SECTIONS } from "./workspaceContext";

const read = (address: string) => {
  const [pathname, query = ""] = address.split("?");
  return locationFromAddress(pathname, query ? `?${query}` : "", VIEW_TO_SECTION, WORKSPACE_SECTIONS);
};

describe("workspace addresses", () => {
  it("names the case and its step on the case page", () => {
    expect(addressFor({ section: "Investigations", tab: "Decision", caseRef: "INV000147" })).toBe(
      "/app/investigations?case=INV000147&step=Decision",
    );
    // A tab carrying a view or a request is named by the tab alone.
    expect(addressFor({ section: "Investigations", tab: "Intelligence?view=Unknowns", caseRef: "INV000147" })).toBe(
      "/app/investigations?case=INV000147&step=Intelligence",
    );
    expect(addressFor({ section: "Investigations", tab: "All investigations", caseRef: "INV000147" })).toBe(
      "/app/investigations?case=INV000147",
    );
    expect(addressFor({ section: "Investigations" })).toBe("/app/investigations");
  });

  it("uses each section's own path, and names the others", () => {
    expect(addressFor({ section: "Dashboard" })).toBe("/app");
    expect(addressFor({ section: "Signals", tab: "Trends" })).toBe("/app/signals?tab=Trends");
    expect(addressFor({ section: "Trust & Audit", tab: "Audit trail" })).toBe("/app/audit?tab=Audit+trail");
    expect(addressFor({ section: "Import data" })).toBe("/app?section=Import+data");
    expect(addressFor({ section: "My Account", tab: "Security" })).toBe("/app?section=My+Account");
    // A case is named on the case page only.
    expect(addressFor({ section: "Signals", caseRef: "INV000147" })).toBe("/app/signals");
  });

  it("reads back the screen an address names", () => {
    expect(read("/app/investigations?case=INV000147&step=Decision")).toEqual({
      section: "Investigations",
      tab: "Decision",
    });
    expect(read("/app/signals?tab=Trends")).toEqual({ section: "Signals", tab: "Trends" });
    expect(read("/app?section=Import+data")).toEqual({ section: "Import data" });
    expect(read("/app/audit?tab=Audit+trail")).toEqual({ section: "Trust & Audit", tab: "Audit trail" });
    for (const address of [
      addressFor({ section: "Investigations", tab: "Record", caseRef: "INV9" }),
      addressFor({ section: "Products", tab: "Timeline" }),
      addressFor({ section: "Share feedback" }),
    ])
      expect(read(address)).not.toBeNull();
  });

  it("names nothing for a plain path or a case link alone, so the workspace starts as it always has", () => {
    expect(read("/app/investigations")).toBeNull();
    expect(read("/app/investigations?case=INV000147")).toBeNull();
    expect(read("/app")).toBeNull();
    // An unknown section is ignored rather than trusted.
    expect(read("/app?section=Nowhere")).toBeNull();
  });

  it("recognizes only the workspace's own history entries", () => {
    expect(
      isWorkspaceHistoryState({
        mdarixWorkspace: true,
        section: "Investigations",
        tab: "Decision",
        caseId: "c1",
        productId: null,
      }),
    ).toBe(true);
    for (const state of [null, undefined, { view: "home" }, "x"]) expect(isWorkspaceHistoryState(state)).toBe(false);
  });
});
