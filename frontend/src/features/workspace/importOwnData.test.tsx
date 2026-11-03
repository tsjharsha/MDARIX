// 0.10.79: "Import your data" on the new navigation's top bar (beside the Sample data label) and, at phone width, in
// the avatar menu; the Complaints header offers it in a trial too. Every path opens the trial import that Help › Try
// your own data opens: Getting started › Your data until 0.10.80, its own page Import your data since. A sample-only trial and a person who may not change records do
// not see it. The classic navigation is unchanged.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext, canImportOwnData, openImport, type WorkspaceApi } from "./workspaceContext";
import { AvatarMenu, ImportOwnData, importOwnDataAction } from "./HybridShell";
import { ComplaintViews } from "./sections/ComplaintViews";
import { UserWorkspace } from "./UserWorkspace";

vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: () => ({ state: "ready", data: null, reload: () => undefined }),
}));

const MENU = ["home", "products", "investigations"];
const OWNER = { allowed_menu: MENU, business_permissions: ["records.write", "signal.triage", "quality.review"] };
const SAMPLE_ONLY = { ...OWNER, sample_only: true };
// A locked Regulatory Leader: no records.write.
const REGULATORY = { allowed_menu: MENU, business_permissions: ["regulatory.review", "regulatory.approve"] };

const api = (session: Record<string, unknown>, overrides: Partial<WorkspaceApi> = {}) =>
  ({
    session,
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    ...overrides,
  }) as unknown as WorkspaceApi;
const render = (node: ReactNode, value: WorkspaceApi) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={value}>{node}</WorkspaceContext.Provider>);

describe("Import your data on the top bar", () => {
  it("is offered to the trial owner and opens the trial import (Import your data since 0.10.80)", () => {
    expect(canImportOwnData(OWNER as never)).toBe(true);
    const open = vi.fn();
    const action = importOwnDataAction(true, OWNER as never, open);
    expect(action).toBeTypeOf("function");
    action?.();
    expect(open).toHaveBeenCalledWith("Import your data");
    const button = renderToStaticMarkup(<ImportOwnData onOpen={() => undefined} />);
    expect(button).toContain("Import your data");
    expect(button).toContain("<svg"); // the upload icon
  });

  it("is absent for a sample-only trial and for a colleague who may not change records", () => {
    expect(importOwnDataAction(true, SAMPLE_ONLY as never, vi.fn())).toBeUndefined();
    expect(importOwnDataAction(true, REGULATORY as never, vi.fn())).toBeUndefined();
    // Not a trial: no Sample data label, so nothing beside it (a pilot imports from its own menu).
    expect(importOwnDataAction(false, OWNER as never, vi.fn())).toBeUndefined();
  });

  it("is in the avatar menu, for the phone, only when offered", () => {
    const shown = renderToStaticMarkup(
      <AvatarMenu session={null} current="Home" open={vi.fn()} showSettings onImport={() => undefined} defaultOpen />,
    );
    expect(shown).toContain("Import your data");
    const none = renderToStaticMarkup(
      <AvatarMenu session={null} current="Home" open={vi.fn()} showSettings defaultOpen />,
    );
    expect(none).not.toContain("Import your data");
  });
});

describe("Import your data on the Complaints header", () => {
  it("is offered in a trial by the same rule, and opens the same flow", () => {
    expect(render(<ComplaintViews />, api(OWNER))).toContain("Import your data");
    expect(render(<ComplaintViews />, api(SAMPLE_ONLY))).not.toContain("Import your data");
    expect(render(<ComplaintViews />, api(REGULATORY))).not.toContain("Import your data");
    const open = vi.fn();
    openImport(open, true);
    expect(open).toHaveBeenLastCalledWith("Import your data");
    // A pilot keeps its Import data screen.
    expect(render(<ComplaintViews />, api(OWNER, { isTrial: false }))).toContain("Import your data");
    openImport(open, false);
    expect(open).toHaveBeenLastCalledWith("Import data");
  });
});

describe("the classic navigation", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app/my-work", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("draws no Import your data on its bar", () => {
    const session = {
      ...OWNER,
      display_name: "Asha Quality",
      feature_set: "mvp",
      navigation: "classic",
      current_tenant: { tenant_name: "Medisynth Devices (Sample)" },
    };
    const markup = renderToStaticMarkup(<UserWorkspace session={session as never} initialView="my-work" />);
    expect(markup).not.toContain("uw-top-import");
  });
});
