import { describe, expect, it } from "vitest";
import { resolveSitePath } from "../PublicMegaSite";

describe("website addresses", () => {
  it("opens the legal, security and contact pages", () => {
    for (const path of ["/privacy", "/terms", "/trial-agreement", "/security", "/contact"])
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
});
