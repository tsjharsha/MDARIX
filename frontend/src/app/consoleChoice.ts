import type { AppView } from "./router";
import { featureSetOf } from "./featureSet";
import { navigationOf } from "./linkTable";

/*
 * A customer administrator has one account and two places to work: the customer-admin console and, with an
 * Investigator's rights, the investigation workspace. Which one a given address opens is decided here; the server
 * still authorizes every call either way.
 */

export type CustomerAdminMode = "console" | "workspace";

const MODE_KEY = "mdarix:ui:customer-admin-mode";

/** The place the person chose last in this browser session (sign-out clears it). */
export function rememberedMode(storage: Pick<Storage, "getItem"> | null = safeSession()): CustomerAdminMode {
  try {
    return storage?.getItem(MODE_KEY) === "workspace" ? "workspace" : "console";
  } catch {
    return "console";
  }
}

export function rememberMode(mode: CustomerAdminMode, storage: Pick<Storage, "setItem"> | null = safeSession()) {
  try {
    storage?.setItem(MODE_KEY, mode);
  } catch {
    // Without storage the console stays the starting point; the switch itself still works.
  }
}

function safeSession(): Storage | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Where an address takes a customer administrator. The console's own address opens the console; a workspace address
 * the role may open opens the workspace, except the bare /app, which opens whichever place they chose last
 * (the console by default). Anything else returns to the console.
 */
export function customerAdminDestination(
  current: AppView,
  remembered: CustomerAdminMode,
  allowed: readonly AppView[] | null,
): { mode: CustomerAdminMode; view: AppView } {
  if (current === "customer-admin") return { mode: "console", view: "customer-admin" };
  const workspaceAllowed = !!allowed?.includes(current);
  if (workspaceAllowed && (current !== "home" || remembered === "workspace"))
    return { mode: "workspace", view: current };
  return { mode: "console", view: "customer-admin" };
}

/** Whether the role may switch into the workspace at all (navigationPolicy decides the views). */
export const canSwitchToWorkspace = (allowed: readonly AppView[] | null) => !!allowed?.includes("home");

/** Whether customer administration opens inside the workspace's shell (UX2, Persona Blueprint wave D): on the new
 * navigation, every organization's from ux2navigationnew. Then Avatar › Administration opens it and /app/customer-admin
 * is the workspace's Administration screen; on the classic fallback the separate console stays. */
export const adminInWorkspace = (featureSet?: string | null, navigation?: string | null) =>
  featureSetOf(featureSet) === "mvp" && navigationOf(navigation) === "new";
