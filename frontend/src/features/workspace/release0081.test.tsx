// 0.10.81: the functional, usability, security and navigation reviews' findings that show on screen.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HomeSection, LegalClocks } from "./sections/Home";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";

const workspace = (persona = "admin") =>
  ({
    session: { business_permissions: [], persona, current_tenant: { tenant_name: "Test" } },
    persona,
    open: vi.fn(),
    notify: vi.fn(),
    work: {},
  }) as unknown as WorkspaceApi;

describe("Home while it reads (U-07)", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app/my-work", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("never says all clear before the data has arrived", () => {
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={workspace()}>
        <HomeSection heading={{ current: null }} />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain("Reading…");
    expect(html).not.toContain("Nothing past its time");
    const clocks = renderToStaticMarkup(<LegalClocks clocks={[]} onOpen={() => undefined} reading />);
    expect(clocks).toContain("Reading the legal clocks…");
    expect(clocks).not.toContain("No legal clock is running.");
    expect(renderToStaticMarkup(<LegalClocks clocks={[]} onOpen={() => undefined} />)).toContain(
      "No legal clock is running.",
    );
  });
});
