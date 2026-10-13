import { createContext, useContext } from "react";
import type { InvestigationSummary, Product, Product360, TemporalMode } from "../../app/types";
import { featureSetOf, type FeatureSet } from "../../app/featureSet";

export const WORKSPACE_SECTIONS = [
  // Shown only in free-trial workspaces (see UserWorkspace).
  "Getting started",
  // What an inspector would find today (the home of the lightweight MVP).
  "Readiness",
  "Dashboard",
  "My Work",
  "Products",
  // The second look at possible hidden complaints and the complaint backlog board.
  "Complaints",
  "Signals",
  "Investigations",
  "Evidence",
  "Decisions",
  // What goes to an inspector or a management review: CAPA effectiveness checks.
  "Records",
  "Intelligence",
  "Trust & Audit",
  // Shown to roles that may change records (see SECTION_PERMISSIONS).
  "Import data",
  "My Account",
  "Share feedback",
] as const;

/** Sections that exist only in a free-trial workspace. */
export const TRIAL_ONLY_SECTIONS: readonly string[] = ["Getting started"];

export type WorkspaceSection = (typeof WORKSPACE_SECTIONS)[number];

/** Server menu keys (session context `allowed_menu`) that grant each section. My Account is always available. */
export const SECTION_MENU_KEYS: Record<WorkspaceSection, string[]> = {
  "Getting started": ["home"],
  Readiness: ["home"],
  Dashboard: ["home"],
  "My Work": ["home", "investigations"],
  Products: ["products"],
  Complaints: ["products"],
  Signals: ["products"],
  Investigations: ["investigations"],
  Evidence: ["evidence"],
  Decisions: ["decision-center"],
  Records: ["home"],
  Intelligence: ["home"],
  "Trust & Audit": ["assurance", "audit"],
  "Import data": ["products"],
  "My Account": [],
  "Share feedback": [],
};

export type SessionContext = {
  user_id?: string;
  // The signed-in person's User ID and their organization's Tenant and Customer IDs (the IDs people see).
  business_id?: string | null;
  tenant_business_id?: string | null;
  customer_business_id?: string | null;
  email?: string;
  display_name?: string;
  active_role?: string | null;
  /** Every role the person holds: the account role and any additional workflow roles, with their labels. */
  roles?: Array<{ code: string; label?: string | null; source?: "account" | "additional" | string }>;
  tenant_id?: string;
  environment?: string;
  personas?: Array<{ code: string; label: string }>;
  permissions?: unknown;
  allowed_menu?: string[];
  allowed_actions?: unknown;
  business_permissions?: string[];
  memberships?: Array<{ tenant_id: string; tenant_key: string; tenant_name: string; is_default: boolean }>;
  current_tenant?: { tenant_id?: string; tenant_name?: string; tenant_key?: string };
  plan?: { code?: string; name?: string; version?: string } | null;
  license?: { state?: string; effective?: boolean };
  /** full or mvp (backend/app/feature_set.py): under mvp the parked tabs and screens are hidden (featureSet.ts). */
  feature_set?: string;
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
  /** Choose a case; with its product (from a task or a link), the context switches to that product as well. */
  setInvestigationId: (id: string, productId?: string | null) => void;
  /** Reload the selected product's investigations (after one is opened); `select` makes that one current. */
  refreshInvestigations: (select?: string) => void;
  /** Reload the organization's products (after an import added some). */
  refreshProducts: () => void;
  /** A request, from a complaint or a signal, to open an investigation for it; Investigations takes it once. */
  openInvestigationRequest: OpenInvestigationRequest | null;
  /** Switch the context to the complaint's product (and version) and leave the request for Investigations. */
  requestOpenInvestigation: (request: OpenInvestigationRequest) => void;
  clearOpenInvestigationRequest: () => void;
  /** The case named by the address (?case=INV000147) and whether it was found; null without one. */
  caseLink?: CaseLinkState | null;
  view: Product360 | null;
  state: "loading" | "ready" | "empty" | "error";
  error: string;
};

export type CaseLinkState = { id: string; state: "resolving" | "applied" | "not-found" | "failed" };

/** The complaint an investigation is to be opened for, with its product (and version identifier, when recorded). */
export type OpenInvestigationRequest = {
  productId: string;
  version: string | null;
  complaint: {
    id: string;
    business_id: string | null;
    complaint_identifier: string | null;
    description: string | null;
  };
};

export type WorkspaceApi = {
  session: SessionContext | null;
  work: WorkContext;
  open: (section: WorkspaceSection, tab?: string) => void;
  notify: (text: string, tone?: "good" | "critical") => void;
  /** The case page reports the step it shows, for the screen's address (workspaceAddress.ts). */
  reportStep?: (tab: string) => void;
};

export const WorkspaceContext = createContext<WorkspaceApi | null>(null);

export function useWorkspace(): WorkspaceApi {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside the user workspace");
  return value;
}

/** The server's feature set (session context `feature_set`); `full` outside the workspace or from older servers. */
export function useFeatureSet(): FeatureSet {
  const value = useContext(WorkspaceContext);
  return featureSetOf(value?.session?.feature_set);
}

export type BusinessPermission =
  | "records.write"
  | "ai.run"
  | "data.export"
  | "regulatory.approve"
  | "signal.triage"
  | "investigation.create"
  | "investigation.assign"
  | "investigation.work"
  | "evidence.review"
  | "evidence.request"
  | "risk.review"
  | "regulatory.review"
  | "quality.review"
  | "decision.sign";

/** Whether the signed-in role may perform a business action, from the server's own rule (session context).
 * Only hides controls the server would refuse; when permissions are unknown (outside the workspace, older
 * sessions) controls stay visible and the server still decides. */
export function useCan(permission: BusinessPermission): boolean {
  const value = useContext(WorkspaceContext);
  const granted = value?.session?.business_permissions;
  return !Array.isArray(granted) || granted.includes(permission);
}

const text = (value: unknown): string | null =>
  value === null || value === undefined || value === "" ? null : String(value);

/**
 * The open-investigation request for a complaint row (GET /api/v1/complaints) or a signal (GET /api/v1/signals/{id}):
 * null when the record has no id or no product, since a case is always opened for a product.
 */
export function investigationRequestFor(
  record: Record<string, unknown> | null | undefined,
): OpenInvestigationRequest | null {
  const id = text(record?.id);
  const productId = text(record?.product_id);
  if (!record || !id || !productId) return null;
  return {
    productId,
    version: text(record.version ?? record.version_identifier),
    complaint: {
      id,
      business_id: text(record.business_id),
      complaint_identifier: text(record.complaint_identifier ?? record.signal_id),
      description: text(record.description),
    },
  };
}

/**
 * Open an investigation for a complaint: switch the shared context to its product and version, go to Investigations
 * and open the form there with the complaint ticked. Null where that is not possible: outside the workspace, for a
 * role that may not change records, or when the Investigations section is not in the person's menu.
 */
export function useOpenInvestigation(): ((request: OpenInvestigationRequest) => void) | null {
  const value = useContext(WorkspaceContext);
  const canWrite = useCan("records.write");
  const session = value?.session;
  if (!value?.work?.requestOpenInvestigation || !canWrite) return null;
  if (!sectionAllowed("Investigations", session?.allowed_menu, session?.business_permissions)) return null;
  return (request) => {
    value.work.requestOpenInvestigation(request);
    value.open("Investigations", "All investigations");
  };
}

/** Sections that also need a business permission (the server enforces it on every call as well). */
export const SECTION_PERMISSIONS: Partial<Record<WorkspaceSection, BusinessPermission>> = {
  "Import data": "records.write",
};

export function sectionAllowed(
  section: WorkspaceSection,
  allowedMenu: string[] | undefined,
  businessPermissions?: string[],
) {
  const keys = SECTION_MENU_KEYS[section];
  const permission = SECTION_PERMISSIONS[section];
  // A section that changes data is shown only when the server listed the permission (fail closed).
  if (permission && !(Array.isArray(businessPermissions) && businessPermissions.includes(permission))) return false;
  // Fail closed: without a server-issued menu only My Account is shown. The server still authorizes every call.
  return !keys.length || (!!allowedMenu && keys.some((key) => allowedMenu.includes(key)));
}
