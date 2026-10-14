import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UserWorkspace } from "./UserWorkspace";
import type { SessionContext } from "./workspaceContext";

const session = {
  display_name: "Priya Sharma",
  feature_set: "mvp",
  allowed_menu: ["home", "products", "investigations"],
  current_tenant: { tenant_name: "Orbit Medical Devices" },
} as unknown as SessionContext;

const heading = (markup: string) => /<h1[^>]*>([^<]*)<\/h1>/.exec(markup)?.[1] ?? null;

describe("the workspace's first screen", () => {
  // Rendered once, as the browser first paints it (effects do not run): the address is /app.
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("waits for the trial status before the default start screen, so a trial never flashes Readiness first", () => {
    const markup = renderToStaticMarkup(<UserWorkspace session={session} />);
    expect(markup).toContain("Opening your workspace…");
    expect(heading(markup)).toBeNull();
  });

  it("opens a screen the person asked for at once", () => {
    const markup = renderToStaticMarkup(<UserWorkspace session={session} initialView="signals" />);
    expect(markup).not.toContain("Opening your workspace…");
    expect(heading(markup)).toBe("Signals");
  });
});
