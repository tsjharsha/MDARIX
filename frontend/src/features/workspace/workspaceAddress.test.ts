import { describe, expect, it } from "vitest";
import {
  addressFor,
  isWorkspaceHistoryState,
  locationFromAddress,
  restoreKind,
  tabParam,
  withTabParam,
} from "./workspaceAddress";
import { VIEW_TO_SECTION } from "./UserWorkspace";
import { WORKSPACE_SECTIONS } from "./workspaceContext";
import { recordPlace, routeFor } from "../../app/linkTable";

const read = (address: string) => {
  const [pathname, query = ""] = address.split("?");
  return locationFromAddress(pathname, query ? `?${query}` : "", VIEW_TO_SECTION, WORKSPACE_SECTIONS);
};

/** A refresh, or the address opened in a new tab: the screen the workspace starts on (as UserWorkspace does). */
const reopen = (address: string) => {
  const [pathname] = address.split("?");
  const named = read(address);
  const [section, tab] = named ? [named.section, named.tab] : (VIEW_TO_SECTION[pathname.split("/")[2] ?? "home"] ?? []);
  return routeFor(section as string, tab, "mvp");
};

describe("workspace addresses", () => {
  it("names the case and its step on the case page, with what the step carries", () => {
    expect(addressFor({ section: "Investigations", tab: "Decision", caseRef: "INV000147" })).toBe(
      "/app/investigations?case=INV000147&step=Decision",
    );
    expect(addressFor({ section: "Investigations", tab: "Intelligence?view=Unknowns", caseRef: "INV000147" })).toBe(
      "/app/investigations?case=INV000147&step=Intelligence&view=Unknowns",
    );
    // The case page names its case itself: a tab's own "case" (a UUID from an approval) is not repeated.
    expect(addressFor({ section: "Investigations", tab: "Decision?case=8f1c&follow_up=FU1", caseRef: "INV9" })).toBe(
      "/app/investigations?case=INV9&step=Decision&follow_up=FU1",
    );
    expect(addressFor({ section: "Investigations", tab: "All investigations", caseRef: "INV000147" })).toBe(
      "/app/investigations?case=INV000147",
    );
    expect(addressFor({ section: "Investigations" })).toBe("/app/investigations");
  });

  it("gives every section a path of its own, the tab and the record and filters it carries (6.1, 6.2)", () => {
    expect(addressFor({ section: "Dashboard" })).toBe("/app");
    expect(addressFor({ section: "Signals", tab: "Trends" })).toBe("/app/signals?tab=Trends");
    expect(addressFor({ section: "Trust & Audit", tab: "Audit trail" })).toBe("/app/audit?tab=Audit+trail");
    expect(addressFor({ section: "Import data" })).toBe("/app/import-data");
    expect(addressFor({ section: "Import data", tab: "?report=IMP000004" })).toBe("/app/import-data?report=IMP000004");
    expect(addressFor({ section: "My Account", tab: "Security" })).toBe("/app/account?tab=Security");
    expect(addressFor({ section: "Getting started", tab: "Team" })).toBe("/app/getting-started?tab=Team");
    expect(addressFor({ section: "Share feedback" })).toBe("/app/feedback");
    expect(addressFor({ section: "Look ahead" })).toBe("/app/look-ahead");
    expect(addressFor({ section: "Complaints", tab: "Reports?complaint=c1&report=r1" })).toBe(
      "/app/complaints?tab=Reports&complaint=c1&report=r1",
    );
    expect(addressFor({ section: "Signals", tab: "Signal inbox?priority=HIGH%2CCRITICAL&signal=SIG000023" })).toBe(
      "/app/signals?tab=Signal+inbox&priority=HIGH%2CCRITICAL&signal=SIG000023",
    );
    // A case is named on the case page only.
    expect(addressFor({ section: "Signals", caseRef: "INV000147" })).toBe("/app/signals");
  });

  it("the same tab for a second record is a different address (each a history entry of its own)", () => {
    const first = addressFor({ section: "Complaints", tab: "Reports?complaint=c1" });
    const second = addressFor({ section: "Complaints", tab: "Reports?complaint=c2" });
    expect(first).not.toBe(second);
  });

  it("reads back the screen an address names, with what its tab carried", () => {
    expect(read("/app/investigations?case=INV000147&step=Decision")).toEqual({
      section: "Investigations",
      tab: "Decision",
    });
    expect(read("/app/investigations?case=INV9&step=Decision&follow_up=FU1")).toEqual({
      section: "Investigations",
      tab: "Decision?follow_up=FU1",
    });
    expect(read("/app/signals?tab=Trends")).toEqual({ section: "Signals", tab: "Trends" });
    expect(read("/app/audit?tab=Audit+trail")).toEqual({ section: "Trust & Audit", tab: "Audit trail" });
    expect(read("/app/complaints?tab=Reports&complaint=c1&report=r1")).toEqual({
      section: "Complaints",
      tab: "Reports?complaint=c1&report=r1",
    });
    // Before 0.10.67: ?section= named the screen; it still does.
    expect(read("/app?section=Import+data")).toEqual({ section: "Import data" });
    expect(read("/app?section=My+Account&tab=Security")).toEqual({ section: "My Account", tab: "Security" });
    // ?signal= alone (a link in an older e-mail or task) still opens that signal, and stays in the address.
    expect(read("/app/signals?signal=SIG000023")).toEqual({ section: "Signals", tab: "?signal=SIG000023" });
  });

  it("names nothing for a plain path or a case link alone, so the workspace starts as it always has", () => {
    expect(read("/app/investigations")).toBeNull();
    expect(read("/app/investigations?case=INV000147")).toBeNull();
    expect(read("/app")).toBeNull();
    expect(read("/app/feedback")).toBeNull();
    // An unknown section is ignored rather than trusted.
    expect(read("/app?section=Nowhere")).toBeNull();
  });

  it("refresh and a new tab keep the screen, tab, record, filter and open panel (6.10)", () => {
    const places = [
      { section: "Complaints", tab: "Reports?complaint=c1&report=r1" },
      { section: "Complaints", tab: "Triage?item=intake%3A42" },
      { section: "Complaints", tab: "Dispositions?complaint=c9" },
      { section: "Complaints", tab: "Communications?complaint=c1&communication=e7" },
      { section: "Complaints", tab: "Complaint list?country=US&lot=L7" },
      { section: "Complaints", tab: "First contact?check=k1" },
      { section: "Readiness", tab: "Oversight?event=c1" },
      { section: "Signals", tab: "Signal inbox?priority=HIGH&signal=SIG000023" },
      { section: "My Work", tab: "Evidence requests?request=REQ000003" },
      { section: "My Work", tab: "Assigned to me?task=t1" },
      { section: "Records", tab: "Effectiveness checks?capa=p1" },
      { section: "Records", tab: `Audit trail?${new URLSearchParams({ view: "Case timeline?case=x&label=INV9" })}` },
      { section: "Getting started", tab: "Team" },
      { section: "Look ahead", tab: "As your distributor sees it" },
      { section: "My Account", tab: "Security" },
    ];
    for (const place of places) expect(reopen(addressFor(place)), place.tab).toEqual(place);
    // The case page keeps its step and what it carries; the case itself comes from ?case= (savedContext.ts).
    expect(reopen("/app/investigations?case=INV9&step=Reviews&review=R1")).toEqual({
      section: "Investigations",
      tab: "Reviews?review=R1",
    });
  });

  it("Back and Forward change only what changed (6.10)", () => {
    // Closing or opening a panel, or a filter coming back: the same tab, only what it carries.
    expect(
      restoreKind({ section: "Complaints", tab: "Reports?report=r1" }, { section: "Complaints", tab: "Reports" }),
    ).toBe("carried");
    // Another tab or section: the screen opens afresh with the entry's tab.
    expect(restoreKind({ section: "Complaints", tab: "Reports" }, { section: "Complaints", tab: "Triage" })).toBe(
      "screen",
    );
    expect(restoreKind({ section: "Complaints", tab: "Reports" }, { section: "Records", tab: "Reports" })).toBe(
      "screen",
    );
    expect(restoreKind({ section: "Readiness" }, { section: "Readiness" })).toBe("nothing");
  });

  it("reads and sets one parameter of a tab, keeping the rest", () => {
    expect(tabParam("Reports?complaint=c1&report=r1", "report")).toBe("r1");
    expect(tabParam("Reports", "report")).toBeNull();
    expect(withTabParam("Reports?complaint=c1", "report", "r1")).toBe("Reports?complaint=c1&report=r1");
    expect(withTabParam("Reports?complaint=c1&report=r1", "report", null)).toBe("Reports?complaint=c1");
    expect(withTabParam(undefined, "report", "r1")).toBe("?report=r1");
  });

  it("opens every kind of record where it is worked (6.5)", () => {
    expect(recordPlace("complaint", "c1")).toEqual({ section: "Readiness", tab: "Oversight?event=c1" });
    expect(recordPlace("report", "r1")).toEqual({ section: "Complaints", tab: "Reports?report=r1" });
    expect(recordPlace("communication", "e1")).toEqual({
      section: "Complaints",
      tab: "Communications?communication=e1",
    });
    expect(recordPlace("disposition", "c1")).toEqual({ section: "Complaints", tab: "Dispositions?complaint=c1" });
    expect(recordPlace("capa", "p1")).toEqual({ section: "Records", tab: "Effectiveness checks?capa=p1" });
    expect(recordPlace("case", "INV9")).toEqual({ section: "Investigations", tab: "Workspace" });
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
