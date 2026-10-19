import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SimplifiedPlatformAdminScreen } from "./SimplifiedPlatformAdminScreen";
import { DOMAINS } from "./consoleDomains";

const context = { display_name: "Platform Admin", active_role: "Platform Administrator" };

// The text of each area button in the left menu (<strong>name</strong><small>description</small>).
const menu = (markup: string) => {
  const nav = /<nav[^>]*aria-label="Administrator navigation"[^>]*>([\s\S]*?)<\/nav>/.exec(markup)?.[1] ?? "";
  return [...nav.matchAll(/<strong>([^<]*)<\/strong><small>([^<]*)<\/small>/g)].map(([, name, text]) => [name, text]);
};

describe("the Platform Admin menu", () => {
  // Rendered once, as the browser first paints it (effects do not run).
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app/admin", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("describes each area in words only, without the number of its tabs", () => {
    const items = menu(renderToStaticMarkup(<SimplifiedPlatformAdminScreen securityContext={context} />));
    const security = DOMAINS.find((domain) => domain[0] === "Security");
    expect(items).toContainEqual(["Security", security?.[1]]);
    expect(items).toContainEqual(["Dashboard", "Live platform status"]);
    expect(items.length).toBeGreaterThan(3);
    for (const [, text] of items) expect(text).not.toMatch(/·\s*\d+\s*$/);
  });

  it("shows the administration areas on the dashboard without a count of sections", () => {
    const markup = renderToStaticMarkup(<SimplifiedPlatformAdminScreen securityContext={context} />);
    const areas = /<section[^>]*aria-label="Administration areas"[^>]*>([\s\S]*?)<\/section>/.exec(markup)?.[1] ?? "";
    expect(areas).toContain("Isolation, audit, support access and retention");
    expect(areas).not.toMatch(/\d+ sections/);
  });
});
