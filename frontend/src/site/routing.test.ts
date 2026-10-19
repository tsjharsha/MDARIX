import { describe, expect, it } from "vitest";
import { resolveSitePath } from "../PublicMegaSite";

// The 19 former Platform pages and the page and section that now hold each one.
const FORMER_PLATFORM_PAGES: Record<string, [string, string]> = {
  "/platform/product-360": ["/platform/product-360", ""],
  "/platform/reality-graph": ["/platform/product-360", "reality-graph"],
  "/platform/product-version": ["/platform/product-360", "product-version"],
  "/platform/timeline": ["/platform/product-360", "timeline"],
  "/platform/ask-mdarix": ["/platform/investigations", "ask-mdarix"],
  "/platform/investigation": ["/platform/investigations", "investigation"],
  "/platform/evidence": ["/platform/investigations", "evidence"],
  "/platform/hypotheses": ["/platform/investigations", "hypotheses"],
  "/platform/challenger": ["/platform/investigations", "challenger"],
  "/platform/unknowns": ["/platform/investigations", "unknowns"],
  "/platform/failure-chain": ["/platform/decisions", "failure-chain"],
  "/platform/counterfactual": ["/platform/decisions", "counterfactual"],
  "/platform/decision-center": ["/platform/decisions", "decision-center"],
  "/platform/investigation-brief": ["/platform/decisions", "investigation-brief"],
  "/platform/ai-assurance": ["/platform/trust", "ai-assurance"],
  "/platform/ai-provenance": ["/platform/trust", "ai-provenance"],
  "/platform/human-review": ["/platform/trust", "human-review"],
  "/platform/audit-trail": ["/platform/trust", "audit-trail"],
  "/platform/enterprise-administration": ["/platform/trust", "enterprise-administration"],
};

describe("website addresses", () => {
  it("opens the legal, security and contact pages", () => {
    for (const path of ["/privacy", "/terms", "/trial-agreement", "/security", "/accessibility", "/contact"])
      expect(resolveSitePath(path, "")).toEqual({ page: path, hash: "" });
  });

  it("opens the Platform pages, the roadmap and the regulations", () => {
    for (const path of [
      "/platform",
      "/platform/product-360",
      "/platform/investigations",
      "/platform/decisions",
      "/platform/trust",
      "/roadmap",
      "/trust/regulations",
    ])
      expect(resolveSitePath(path, "")).toEqual({ page: path, hash: "" });
  });

  it("shows a not-found page for unknown addresses instead of the home page", () => {
    expect(resolveSitePath("/no-such-page", "")).toEqual({ page: "not-found", hash: "" });
    expect(resolveSitePath("/privacy-policy", "x")).toEqual({ page: "not-found", hash: "" });
  });

  it("sends former pricing pages to the contact page and keeps other former pages working", () => {
    expect(resolveSitePath("/pricing", "")).toEqual({ page: "/contact", hash: "" });
    expect(resolveSitePath("/plans/", "")).toEqual({ page: "/contact", hash: "" });
    expect(resolveSitePath("/ai-trust", "")).toEqual({ page: "/trust", hash: "ai" });
    expect(resolveSitePath("/", "")).toEqual({ page: "/", hash: "" });
  });

  it("sends each of the 19 former Platform pages to its section on the page that holds it", () => {
    expect(Object.keys(FORMER_PLATFORM_PAGES)).toHaveLength(19);
    for (const [path, [page, hash]] of Object.entries(FORMER_PLATFORM_PAGES)) {
      expect(resolveSitePath(path, ""), path).toEqual({ page, hash });
      expect(resolveSitePath(`${path}/`, ""), path).toEqual({ page, hash });
    }
  });

  it("sends the former single Platform page's anchors to the page that holds them", () => {
    expect(resolveSitePath("/platform", "challenger")).toEqual({
      page: "/platform/investigations",
      hash: "challenger",
    });
    expect(resolveSitePath("/platform", "audit-trail")).toEqual({ page: "/platform/trust", hash: "audit-trail" });
    // The former group anchors (the old menu and footer) open their page at the top.
    expect(resolveSitePath("/platform", "product-intelligence")).toEqual({ page: "/platform/product-360", hash: "" });
    expect(resolveSitePath("/platform", "decision-intelligence")).toEqual({ page: "/platform/decisions", hash: "" });
    expect(resolveSitePath("/platform", "trust-governance")).toEqual({ page: "/platform/trust", hash: "" });
    expect(resolveSitePath("/platform", "no-such-section")).toEqual({ page: "/platform", hash: "no-such-section" });
  });

  it("keeps lifecycle addresses on the lifecycle page", () => {
    expect(resolveSitePath("/platform/strategy", "")).toEqual({ page: "/product-lifecycle", hash: "strategy" });
    expect(resolveSitePath("/roadmap", "capa")).toEqual({ page: "/product-lifecycle", hash: "capa" });
  });

  it("sends the moved standards and roadmap sections to their own pages", () => {
    expect(resolveSitePath("/", "standards")).toEqual({ page: "/trust/regulations", hash: "" });
    expect(resolveSitePath("/trust", "trust-standards")).toEqual({ page: "/trust/regulations", hash: "" });
    expect(resolveSitePath("/regulations", "")).toEqual({ page: "/trust/regulations", hash: "" });
    expect(resolveSitePath("/", "scope-title")).toEqual({ page: "/roadmap", hash: "" });
  });
});
