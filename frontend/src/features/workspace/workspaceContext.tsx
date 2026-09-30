import { createContext, useContext } from "react";
import type { InvestigationSummary, Product, Product360, TemporalMode } from "../../app/types";

export const WORKSPACE_SECTIONS = [
  "Overview",
  "My Work",
  "Products",
  "Signals",
  "Investigations",
  "Evidence",
  "Decisions",
  "Intelligence",
  "Trust & Audit",
  "My Account",
] as const;

export type WorkspaceSection = (typeof WORKSPACE_SECTIONS)[number];

/** Server menu keys (session context `allowed_menu`) that grant each section. My Account is always available. */
export const SECTION_MENU_KEYS: Record<WorkspaceSection, string[]> = {
  Overview: ["home"],
  "My Work": ["home", "investigations"],
  Products: ["products"],
  Signals: ["products"],
  Investigations: ["investigations"],
  Evidence: ["evidence"],
  Decisions: ["decision-center"],
  Intelligence: ["home"],
  "Trust & Audit": ["assurance", "audit"],
  "My Account": [],
};

export type SessionContext = {
  user_id?: string;
  email?: string;
  display_name?: string;
  active_role?: string | null;
  tenant_id?: string;
  environment?: string;
  personas?: Array<{ code: string; label: string }>;
  permissions?: unknown;
  allowed_menu?: string[];
  allowed_actions?: unknown;
  memberships?: Array<{ tenant_id: string; tenant_key: string; tenant_name: string; is_default: boolean }>;
  current_tenant?: { tenant_id?: string; tenant_name?: string; tenant_key?: string };
  plan?: { code?: string; name?: string; version?: string } | null;
  license?: { state?: string; effective?: boolean };
};

export type WorkContext = {
  products: Product[];
  productId: string;
  setProductId: (id: string) => void;
  version: string;
  setVersion: (version: string) => void;
  asOf: string;
  setAsOf: (date: string) => void;
  mode: TemporalMode;
  setMode: (mode: TemporalMode) => void;
  investigations: InvestigationSummary[];
  investigationId: string;
  setInvestigationId: (id: string) => void;
  view: Product360 | null;
  state: "loading" | "ready" | "empty" | "error";
  error: string;
};

export type WorkspaceApi = {
  session: SessionContext | null;
  work: WorkContext;
  open: (section: WorkspaceSection, tab?: string) => void;
  notify: (text: string, tone?: "good" | "critical") => void;
};

export const WorkspaceContext = createContext<WorkspaceApi | null>(null);

export function useWorkspace(): WorkspaceApi {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside the user workspace");
  return value;
}

export function sectionAllowed(section: WorkspaceSection, allowedMenu: string[] | undefined) {
  const keys = SECTION_MENU_KEYS[section];
  // Fail closed: without a server-issued menu only My Account is shown. The server still authorizes every call.
  return !keys.length || (!!allowedMenu && keys.some((key) => allowedMenu.includes(key)));
}
