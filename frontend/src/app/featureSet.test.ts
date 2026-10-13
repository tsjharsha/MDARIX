import { describe, expect, it } from "vitest";

import {
  PARKED_SECTIONS,
  PARKED_VIEWS,
  adminAreasFor,
  featureSetOf,
  importTemplatesFor,
  offeredTab,
  recordsAuditView,
  routeFor,
  tabsFor,
  viewsForFeatureSet,
} from "./featureSet";
import { DOMAINS } from "../features/admin/consoleDomains";
import { customerAdminSections } from "../features/customer-admin/CustomerAdminControlPlane";
import { SECTIONS as CUSTOMER_ADMIN_SECTIONS } from "../features/customer-admin/context";
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

  it("sends links to a case's evidence to the one case page, and evidence requests to My Work, under mvp only", () => {
    for (const tab of [undefined, "Case evidence", "Case evidence?item=EV000012", "Evidence library", "Provenance"])
      expect(routeFor("Evidence", tab, "mvp")).toEqual({ section: "Investigations", tab: "Evidence" });
    expect(routeFor("Evidence", "Requests?request=RQ000003", "mvp")).toEqual({
      section: "My Work",
      tab: "Evidence requests?request=RQ000003",
    });
    expect(routeFor("Evidence", "Requests", "mvp")).toEqual({ section: "My Work", tab: "Evidence requests" });
    // Full changes nothing.
    expect(routeFor("Evidence", "Case evidence", "full")).toEqual({ section: "Evidence", tab: "Case evidence" });
    expect(routeFor("Evidence", undefined, "full")).toEqual({ section: "Evidence", tab: undefined });
    expect(routeFor("Signals", "Signal inbox", "mvp")).toEqual({ section: "Signals", tab: "Signal inbox" });
  });

  it("sends decisions to the case page, approvals to My Work and signature checks to Records under mvp only", () => {
    expect(routeFor("Decisions", "Decision center", "mvp")).toEqual({ section: "Investigations", tab: "Decision" });
    expect(routeFor("Decisions", undefined, "mvp")).toEqual({ section: "Investigations", tab: "Decision" });
    expect(routeFor("Decisions", "Approvals", "mvp")).toEqual({ section: "My Work", tab: "Approvals" });
    expect(routeFor("Decisions", "Verify a signature", "mvp")).toEqual({
      section: "Records",
      tab: "Verify a signature",
    });
    // The decision keeps what it should open (a follow-up, an assessment).
    expect(routeFor("Decisions", "Decision?follow_up=FU000004", "mvp")).toEqual({
      section: "Investigations",
      tab: "Decision?follow_up=FU000004",
    });
    expect(routeFor("Decisions", "Decision center", "full")).toEqual({ section: "Decisions", tab: "Decision center" });
    expect(routeFor("Decisions", "Approvals", "full")).toEqual({ section: "Decisions", tab: "Approvals" });
  });

  it("parks six sections under mvp, and every link into them opens a screen the MVP keeps", () => {
    expect(PARKED_SECTIONS).toEqual([
      "Dashboard",
      "Products",
      "Evidence",
      "Decisions",
      "Intelligence",
      "Trust & Audit",
    ]);
    const links: [string, string | undefined][] = [
      ["Dashboard", undefined],
      ["Products", "Version story"],
      ["Evidence", "Limitations"],
      ["Decisions", "Approvals"],
      ["Intelligence", "Ask MDARIX"],
      ["Intelligence", "Reports"],
      ["Intelligence", "Regulatory copilot"],
      ["Trust & Audit", "Case timeline?case=c1&label=INV000001"],
      ["Trust & Audit", "AI assurance"],
    ];
    for (const [section, tab] of links) expect(PARKED_SECTIONS).not.toContain(routeFor(section, tab, "mvp").section);
    expect(routeFor("Products", "Version story", "mvp")).toEqual({ section: "Readiness", tab: undefined });
    expect(routeFor("Intelligence", "Ask MDARIX", "mvp")).toEqual({ section: "Investigations", tab: "Ask MDARIX" });
    expect(routeFor("Intelligence", "Reports", "mvp")).toEqual({ section: "Records", tab: "Reports" });
    expect(routeFor("Intelligence", "Risk & traceability", "mvp")).toEqual({
      section: "Investigations",
      tab: "Reviews",
    });
    expect(routeFor("Trust & Audit", "AI assurance", "mvp")).toEqual({ section: "Records", tab: "Audit trail" });
    expect(routeFor("Trust & Audit", "Audit trail", "full")).toEqual({ section: "Trust & Audit", tab: "Audit trail" });
  });

  it("carries a case's timeline into Records › Audit trail with its case and label", () => {
    const routed = routeFor("Trust & Audit", "Case timeline?case=c1&label=INV000001", "mvp");
    expect(routed.section).toBe("Records");
    expect(recordsAuditView(routed.tab)).toBe("Case timeline?case=c1&label=INV000001");
    expect(recordsAuditView(routeFor("Trust & Audit", "Integrity", "mvp").tab)).toBe("Integrity");
    expect(recordsAuditView("Audit trail")).toBeNull();
    expect(recordsAuditView("Effectiveness checks?capa=CAPA000001")).toBeNull();
  });

  it("parks the platform's mapping chain, renewals, cells and developer API under mvp only", () => {
    const areas = DOMAINS.filter((area) => area[0] !== "Platform Overview");
    expect(adminAreasFor(areas, "full")).toEqual(areas);
    const mvp = adminAreasFor(areas, "mvp");
    const names = mvp.map((area) => area[0]);
    expect(names).not.toContain("Data & Integrations");
    expect(names).toContain("Customers & Tenants");
    const plans = mvp.find((area) => area[0] === "Plans & Licensing");
    expect(plans?.[3]).toEqual(["Plans", "Subscriptions"]);
    expect(plans?.[1]).toBe("Plans and subscriptions");
    const operations = mvp.find((area) => area[0] === "Operations");
    expect(operations?.[3]).toEqual(["System health", "Queues & jobs", "Email & notifications"]);
  });

  it("offers the six data types the MVP reads first, in loading order, and the rest on request", () => {
    const entities = ["products", "lots", "complaints", "components", "suppliers", "risks", "investigations", "capas"];
    const templates = entities.map((entity) => ({ entity }));
    expect(importTemplatesFor(templates, "full")).toEqual({ core: templates, more: [] });
    const { core, more } = importTemplatesFor(templates, "mvp");
    expect(core.map((item) => item.entity)).toEqual([
      "products",
      "lots",
      "complaints",
      "investigations",
      "capas",
      "risks",
    ]);
    expect(more.map((item) => item.entity)).toEqual(["components", "suppliers"]);
  });

  it("parks the customer's source-system connections and mapping under mvp only", () => {
    expect(customerAdminSections("full")).toEqual(CUSTOMER_ADMIN_SECTIONS);
    expect(customerAdminSections(undefined)).toEqual(CUSTOMER_ADMIN_SECTIONS);
    const mvp = customerAdminSections("mvp");
    expect(mvp).not.toContain("Integrations");
    expect(mvp).not.toContain("Data Mapping");
    expect(mvp).toContain("Users");
    expect(mvp).toContain("Audit");
  });

  it("opens Trust & Audit on the audit trail when AI assurance is parked", () => {
    expect(initialTrustTab(null, false)).toBe("AI assurance");
    expect(initialTrustTab(null, false, "Audit trail")).toBe("Audit trail");
    expect(initialTrustTab(null, true, "Audit trail")).toBe("Case timeline");
    expect(initialTrustTab("Integrity", false, "Audit trail")).toBe("Integrity");
  });
});
