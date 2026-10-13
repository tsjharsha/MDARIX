import { describe, expect, it } from "vitest";

import { PARKED_VIEWS, featureSetOf, offeredTab, routeFor, tabsFor, viewsForFeatureSet } from "./featureSet";
import { allowedViewsForRole } from "./navigationPolicy";
import { initialTrustTab, TRUST_TABS } from "../features/workspace/caseAudit";

describe("feature set", () => {
  it("is mvp only when the server says so; anything else is the full product", () => {
    expect(featureSetOf("mvp")).toBe("mvp");
    expect(featureSetOf(" MVP ")).toBe("mvp");
    for (const value of ["full", "", null, undefined, "lite", 3]) expect(featureSetOf(value)).toBe("full");
  });

  it("keeps every tab under full and parks the MVP's tabs under mvp, in order", () => {
    const investigations = ["All investigations", "Workspace", "Decision", "Story", "CAPAs"] as const;
    expect(tabsFor("Investigations", investigations, "full")).toEqual(investigations);
    expect(tabsFor("Investigations", investigations, "mvp")).toEqual([
      "All investigations",
      "Workspace",
      "Decision",
      "CAPAs",
    ]);
    const intelligence = ["Ask MDARIX", "Regulatory copilot", "Risk & traceability", "Reports"] as const;
    expect(tabsFor("Intelligence", intelligence, "mvp")).toEqual(["Ask MDARIX", "Reports"]);
    expect(tabsFor("Decisions", ["Approvals", "Decision", "Decision center"], "mvp")).toEqual([
      "Approvals",
      "Decision",
    ]);
    expect(tabsFor("Trust & Audit", TRUST_TABS, "mvp")).not.toContain("AI assurance");
    // A section with nothing parked keeps all of its tabs.
    expect(tabsFor("Signals", ["Signal inbox", "Trends"], "mvp")).toEqual(["Signal inbox", "Trends"]);
  });

  it("opens the requested tab when offered, else the fallback, else the first tab", () => {
    const tabs = ["Ask MDARIX", "Reports"] as const;
    expect(offeredTab("Reports", tabs, "Ask MDARIX")).toBe("Reports");
    expect(offeredTab("Regulatory copilot", tabs, "Ask MDARIX")).toBe("Ask MDARIX");
    expect(offeredTab(null, ["Approvals", "Decision"] as const, "Decision center" as never)).toBe("Approvals");
  });

  it("leaves the parked views out of an administrator's views only under mvp", () => {
    const full = allowedViewsForRole("PLATFORM_ADMIN", "MULTI", "full") ?? [];
    const mvp = allowedViewsForRole("PLATFORM_ADMIN", "MULTI", "mvp") ?? [];
    expect(full).toContain("admin-stage2");
    expect(full).toContain("regulatory-copilot");
    expect(mvp).not.toContain("admin-stage2");
    expect(mvp).not.toContain("regulatory-copilot");
    expect(mvp).toContain("admin");
    expect(mvp).toContain("signature-verification");
    const customerAdmin = allowedViewsForRole("CUSTOMER_ADMIN", "MULTI", "mvp") ?? [];
    expect(customerAdmin).toContain("customer-admin");
    expect(customerAdmin).toContain("investigations");
    expect(customerAdmin).not.toContain("story");
    // Without a feature set (older servers) nothing changes; business roles still get null.
    expect(allowedViewsForRole("PLATFORM_ADMIN", "MULTI")).toEqual(full);
    expect(allowedViewsForRole("INVESTIGATOR", "MULTI", "mvp")).toBeNull();
    expect(viewsForFeatureSet(null, "mvp")).toBeNull();
    expect(PARKED_VIEWS.every((view) => !mvp.includes(view))).toBe(true);
  });

  it("sends links to a case's evidence to the one case page under mvp only", () => {
    for (const tab of [undefined, "Case evidence", "Case evidence?item=EV000012"])
      expect(routeFor("Evidence", tab, "mvp")).toEqual({ section: "Investigations", tab: "Evidence" });
    // The Evidence section's other tabs stay where they are, and full changes nothing.
    expect(routeFor("Evidence", "Requests?request=RQ000003", "mvp")).toEqual({
      section: "Evidence",
      tab: "Requests?request=RQ000003",
    });
    expect(routeFor("Evidence", "Evidence library", "mvp")).toEqual({ section: "Evidence", tab: "Evidence library" });
    expect(routeFor("Evidence", "Case evidence", "full")).toEqual({ section: "Evidence", tab: "Case evidence" });
    expect(routeFor("Evidence", undefined, "full")).toEqual({ section: "Evidence", tab: undefined });
    expect(routeFor("Signals", "Signal inbox", "mvp")).toEqual({ section: "Signals", tab: "Signal inbox" });
  });

  it("opens Trust & Audit on the audit trail when AI assurance is parked", () => {
    expect(initialTrustTab(null, false)).toBe("AI assurance");
    expect(initialTrustTab(null, false, "Audit trail")).toBe("Audit trail");
    expect(initialTrustTab(null, true, "Audit trail")).toBe("Case timeline");
    expect(initialTrustTab("Integrity", false, "Audit trail")).toBe("Integrity");
  });
});
