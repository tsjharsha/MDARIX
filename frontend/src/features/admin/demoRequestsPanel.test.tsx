import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { websiteDemoRequestsOffered } from "../../app/featureSet";
import { DEMO_REQUESTS_OFFERED } from "../../site/offer";
import { DemoRequestsWorkspace, shownDemoRequests } from "./DemoRequestsWorkspace";
import { Onboarding } from "./areas/IdentityAccess";
import { sectionGuide } from "./areas/sections";

// 0.10.44: Platform Admin › Identity & Access › Onboarding showed an empty "Website visitors who asked for a demo"
// panel. The website has offered only the free trial since 0.10.5 (site/offer.ts), and the MVP feature set parks
// POST /api/v1/public/demo-requests (backend/app/feature_set.py). The website's demo requests are shown only where both
// offer them; a free trial's own one-to-one demo (Getting started) is still listed, once one is booked.

describe("website demo requests in Platform Admin", () => {
  it("are offered only where the website offers them and the feature set serves their route", () => {
    expect(websiteDemoRequestsOffered("mvp")).toBe(false);
    expect(websiteDemoRequestsOffered("full")).toBe(DEMO_REQUESTS_OFFERED);
    // The website offers no demo request in any mode today, so neither feature set lists them.
    expect(DEMO_REQUESTS_OFFERED).toBe(false);
    expect(websiteDemoRequestsOffered("full")).toBe(false);
  });

  it("leaves out the panel and every mention of a website demo while they are not offered", () => {
    const html = renderToStaticMarkup(<Onboarding websiteDemos={false} />);
    expect(html).not.toContain("Website visitors who asked for a demo");
    expect(html).not.toContain("Demo and trial requests");
    expect(html).not.toContain("asked for a demo,");
    expect(html).toContain("<h2>Trial requests</h2>");
    expect(html).toContain("for a pilot conversation or a one-to-one demo");
    expect(sectionGuide("Identity & Access", "Onboarding")).not.toMatch(/^Demo/);
    expect(sectionGuide("Identity & Access", "Onboarding")).toContain("Free-trial requests");
  });

  it("keeps the website's panel where the website offers demo requests", () => {
    const html = renderToStaticMarkup(<Onboarding websiteDemos />);
    expect(html).toContain("<h2>Demo and trial requests</h2>");
    expect(html).toContain("Website visitors who asked for a demo");
    expect(sectionGuide("Identity & Access", "Onboarding", true)).toBe(
      "Demo and trial requests from prospective customers.",
    );
    // Until a request is read, the trials-only panel shows nothing (it appears once a free trial books a demo).
    expect(renderToStaticMarkup(<DemoRequestsWorkspace websiteRequests={false} />)).toBe("");
  });

  it("lists only the trials' one-to-one demo requests, with their own counts, while website requests are not offered", () => {
    const items = [
      { id: "1", source: "WEBSITE", status: "NEW" },
      { id: "2", source: "TRIAL", status: "NEW" },
      { id: "3", source: "TRIAL", status: "CONTACTED" },
      { id: "4", source: undefined, status: "CLOSED" },
    ];
    const trials = shownDemoRequests(items, false);
    expect(trials.items.map((item) => item.id)).toEqual(["2", "3"]);
    expect(trials.counts).toEqual({ NEW: 1, CONTACTED: 1 });
    expect(shownDemoRequests(items, true).items).toHaveLength(4);
  });
});
