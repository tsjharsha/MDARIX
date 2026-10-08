import { describe, expect, it } from "vitest";
import { canSwitchToWorkspace, customerAdminDestination, rememberMode, rememberedMode } from "./consoleChoice";
import type { AppView } from "./router";

const ALLOWED: AppView[] = ["customer-admin", "home", "investigations", "signals", "decision"];

describe("customer administrator: console or workspace", () => {
  it("opens the console on its own address and on /app by default", () => {
    expect(customerAdminDestination("customer-admin", "workspace", ALLOWED)).toEqual({
      mode: "console",
      view: "customer-admin",
    });
    expect(customerAdminDestination("home", "console", ALLOWED)).toEqual({ mode: "console", view: "customer-admin" });
  });

  it("opens the workspace on a workspace address, and on /app once the person switched to it", () => {
    expect(customerAdminDestination("investigations", "console", ALLOWED)).toEqual({
      mode: "workspace",
      view: "investigations",
    });
    expect(customerAdminDestination("home", "workspace", ALLOWED)).toEqual({ mode: "workspace", view: "home" });
  });

  it("returns to the console for an address the role may not open", () => {
    expect(customerAdminDestination("admin", "workspace", ALLOWED)).toEqual({
      mode: "console",
      view: "customer-admin",
    });
    expect(customerAdminDestination("investigations", "workspace", ["customer-admin"])).toEqual({
      mode: "console",
      view: "customer-admin",
    });
  });

  it("offers the switch only when the role's views include the workspace", () => {
    expect(canSwitchToWorkspace(ALLOWED)).toBe(true);
    expect(canSwitchToWorkspace(["customer-admin"])).toBe(false);
    expect(canSwitchToWorkspace(null)).toBe(false);
  });

  it("remembers the choice for the browser session, and falls back to the console", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (k: string, v: string) => void values.set(k, v),
    };
    expect(rememberedMode(storage)).toBe("console");
    rememberMode("workspace", storage);
    expect(rememberedMode(storage)).toBe("workspace");
    expect(
      rememberedMode({
        getItem: () => {
          throw new Error("blocked");
        },
      }),
    ).toBe("console");
  });
});
