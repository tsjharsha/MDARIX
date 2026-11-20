import { describe, expect, it } from "vitest";
import { VIGILANCE_URL } from "../PublicMegaSite";
import { renderPage } from "./prerender";

describe("the website header", () => {
  it("offers Vigilance AI right after Sign in, on every page", () => {
    for (const path of ["/", "/platform", "/trust"] as const) {
      const html = renderPage(path);
      const signIn = html.indexOf('href="/signin">Sign in</a>');
      const vigilance = html.indexOf(`href="${VIGILANCE_URL}">Vigilance AI</a>`);
      expect(signIn, path).toBeGreaterThan(-1);
      expect(vigilance, path).toBeGreaterThan(signIn);
    }
    expect(VIGILANCE_URL).toMatch(/^https:\/\/vigilance-[0-9]+\.asia-south1\.run\.app\/$/);
  });
});
