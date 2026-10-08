import { describe, expect, it } from "vitest";
import { APP_ROUTES, viewFromPath } from "./router";
import {
  AUTH_ENDPOINTS,
  allowedViewsForRole,
  apiErrorMessage,
  clearTenantScopedCache,
  isCustomerAdminRole,
  isPlatformAdminRole,
  MOBILE_FOCUS_ORDER,
  PLATFORM_ADMIN_VIEWS,
  WORKSPACE_VIEWS,
} from "./navigationPolicy";

describe("authentication and role navigation", () => {
  it("uses the session, signin, and signout API contracts", () => {
    expect(AUTH_ENDPOINTS).toEqual({
      session: "/api/v1/auth/session",
      signin: "/api/v1/auth/signin",
      signout: "/api/v1/auth/signout",
    });
  });

  it("recognizes platform and customer administrator roles", () => {
    expect(isPlatformAdminRole("Administrator")).toBe(true);
    expect(isPlatformAdminRole("Viewer")).toBe(false);
    expect(isCustomerAdminRole("CUSTOMER_ADMIN")).toBe(true);
    expect(isCustomerAdminRole("Administrator")).toBe(false);
  });

  it("routes each administrator to only its own protected area", () => {
    expect(allowedViewsForRole("Administrator")).toContain("admin");
    expect(allowedViewsForRole("Administrator")).not.toContain("customer-admin");
    expect(allowedViewsForRole("Customer Admin")).toContain("customer-admin");
    expect(allowedViewsForRole("Viewer")).toBeNull();
  });

  it("offers only the screens the deployment serves", () => {
    expect(allowedViewsForRole("Administrator", "MULTI")).toEqual(PLATFORM_ADMIN_VIEWS);
    const platform = allowedViewsForRole("Administrator", "PLATFORM") ?? [];
    expect(platform).toContain("admin");
    expect(platform).not.toContain("regulatory-copilot");
    expect(platform.some((view) => WORKSPACE_VIEWS.includes(view))).toBe(false);
    const cellAdmin = allowedViewsForRole("Customer Admin", "CELL") ?? [];
    expect(cellAdmin).toContain("customer-admin");
    expect(cellAdmin).toContain("investigations");
    // Platform staff cannot sign in to a cell; were a session to exist, no platform screen would be offered.
    const cellStaff = allowedViewsForRole("Administrator", "CELL") ?? [];
    expect(cellStaff).not.toContain("admin");
    expect(cellStaff.every((view) => WORKSPACE_VIEWS.includes(view))).toBe(true);
    expect(allowedViewsForRole("Viewer", "CELL")).toBeNull();
  });

  it("keeps every declared admin route addressable", () => {
    for (const [view, path] of Object.entries(APP_ROUTES)) expect(viewFromPath(path)).toBe(view);
  });

  it("lets a customer administrator switch into the Investigator workspace but not the platform console", () => {
    const allowed = allowedViewsForRole("CUSTOMER_ADMIN") ?? [];
    expect(allowed).toContain("customer-admin");
    for (const view of WORKSPACE_VIEWS) expect(allowed).toContain(view);
    for (const view of ["investigations", "evidence", "ask", "my-work"] as const) expect(allowed).toContain(view);
    for (const view of PLATFORM_ADMIN_VIEWS.filter((item) => !WORKSPACE_VIEWS.includes(item)))
      expect(allowed).not.toContain(view);
    expect(allowedViewsForRole("Customer Admin")).toEqual(allowed);
    expect(new Set(allowed).size).toBe(allowed.length);
  });

  it("exposes the regulatory co-pilot only to governed admin roles", () => {
    expect(allowedViewsForRole("Administrator")).toContain("regulatory-copilot");
    expect(allowedViewsForRole("CUSTOMER_ADMIN")).toContain("regulatory-copilot");
    expect(allowedViewsForRole("Viewer")).toBeNull();
  });
});

describe("tenant cache and API failure boundaries", () => {
  it("clears tenant and context cache entries while preserving unrelated settings", () => {
    const values = new Map([
      ["mdarix:tenant:a:products", "a"],
      ["mdarix:context:a", "a"],
      ["mdarix:ui:theme", "dark"],
    ]);
    const storage = {
      get length() {
        return values.size;
      },
      key: (index: number) => [...values.keys()][index] ?? null,
      removeItem: (key: string) => values.delete(key),
    };
    expect(clearTenantScopedCache(storage)).toBe(2);
    expect(values.has("mdarix:ui:theme")).toBe(true);
  });

  it("surfaces structured API errors and safe fallback errors", () => {
    expect(apiErrorMessage({ detail: { message: "Tenant denied" } })).toBe("Tenant denied");
    expect(apiErrorMessage({ detail: "Unavailable" })).toBe("Unavailable");
    expect(apiErrorMessage({})).toBe("The request could not be completed.");
  });
});

describe("Mapping Studio, onboarding, mobile and keyboard contracts", () => {
  it("keeps Mapping Studio and onboarding routes explicit", () => {
    expect(APP_ROUTES["admin-mapping"]).toBe("/app/admin/mapping-studio");
    expect(APP_ROUTES["admin-create-customer"]).toBe("/app/admin/customers/new");
  });

  it("defines a deterministic mobile keyboard focus order", () => {
    expect([...MOBILE_FOCUS_ORDER]).toEqual(["menu", "user-context", "primary-content", "logout"]);
  });
});
