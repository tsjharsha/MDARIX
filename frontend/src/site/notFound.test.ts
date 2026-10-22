import { describe, expect, it } from "vitest";
import caddyfile from "../../../infrastructure/docker/Caddyfile?raw";
import securityTxt from "../../public/.well-known/security.txt?raw";
import { LEGACY_PAGES, resolveSitePath } from "../PublicMegaSite";
import { TRIAL_GUIDE_PATH, USER_GUIDE_PATH } from "../features/help/paths";

// WEB-17: the web server (infrastructure/docker/Caddyfile) answers an address that is no page with the website's
// "Page not found" page and a real 404 status. Built files and pre-rendered pages are served as they are; the addresses
// the browser routes itself get the application shell. This keeps the server's list of those addresses in step with
// the browser's routing (app/App.tsx, PublicMegaSite.tsx resolveSitePath).

const shellPattern = () => {
  const line = caddyfile.split("\n").find((text) => text.trim().startsWith("@shell path_regexp shell "));
  if (!line) throw new Error("The Caddyfile has no @shell matcher");
  return new RegExp(line.trim().slice("@shell path_regexp shell ".length));
};

// Routed in the browser by app/App.tsx: sign-in and account screens, the guides and the signed-in application.
const APPLICATION_ADDRESSES = [
  "/signin",
  "/forgot-password",
  "/activate-account",
  "/reset-password",
  "/mfa",
  "/request-demo",
  "/help/pilot-guide",
  TRIAL_GUIDE_PATH,
  USER_GUIDE_PATH,
  "/app",
  "/app/",
  "/app/next-steps",
  "/app/customer-admin",
  "/platform-admin",
  "/platform-admin/onboarding",
];

describe("addresses that are no page get a real 404", () => {
  it("serves the application shell for every address the browser routes itself", () => {
    const shell = shellPattern();
    for (const path of APPLICATION_ADDRESSES) expect(shell.test(path), path).toBe(true);
    // The website's former page addresses and capability pages open the page that now holds them.
    for (const path of [...Object.keys(LEGACY_PAGES), "/platform/product-version", "/platform/challenger"]) {
      expect(shell.test(path), path).toBe(true);
      expect(resolveSitePath(path, "").page, path).not.toBe("not-found");
    }
    expect(shell.test("/why-mdarix/")).toBe(true);
  });

  it("sends anything else to the not-found page with status 404", () => {
    const shell = shellPattern();
    for (const path of [
      "/nope",
      "/apps",
      "/platform-adminx",
      "/signin/extra",
      "/wp-login.php",
      "/.env",
      "/platformx",
      // The questions are pre-rendered files (served as built); an address that is no question is no page.
      "/questions/no-such-question",
      "/questionsx",
    ]) {
      expect(shell.test(path), path).toBe(false);
      expect(resolveSitePath(path, "").page, path).toBe("not-found");
    }
    expect(caddyfile).toContain("rewrite * /404.html");
    expect(caddyfile).toMatch(/file_server \{\s*status 404\s*\}/);
    // Built files and pre-rendered pages come first, except the not-found page itself: /404.html opened by its own
    // name answered 200 before 0.10.43, and now gets the 404 like any address that is no page.
    expect(caddyfile).toMatch(/@built \{\s*file \{path\} \{path\}\/index\.html\s*not path \/404\.html\s*\}/);
    expect(shell.test("/404.html")).toBe(false);
    // The API, assets and videos keep their own handlers above.
    expect(caddyfile.indexOf("@built {")).toBeLessThan(caddyfile.indexOf("@shell"));
    for (const handler of ["handle /api/*", "handle /assets/*", "handle_path /media/videos/*"])
      expect(caddyfile.indexOf(handler), handler).toBeLessThan(caddyfile.indexOf("@built"));
  });
});

describe("security.txt (RFC 9116)", () => {
  it("names the contact, the expiry in UTC, the language and its canonical address", () => {
    const fields = Object.fromEntries(
      securityTxt
        .trim()
        .split(/\r?\n/)
        .map((line) => [line.slice(0, line.indexOf(":")), line.slice(line.indexOf(":") + 1).trim()]),
    );
    expect(fields).toEqual({
      Contact: "mailto:support@mdarix.in",
      Expires: fields.Expires,
      "Preferred-Languages": "en",
      Canonical: "https://mdarix.com/.well-known/security.txt",
    });
    expect(fields.Expires).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
    expect(new Date(fields.Expires).toISOString().replace(".000", "")).toBe(fields.Expires);
  });
});
