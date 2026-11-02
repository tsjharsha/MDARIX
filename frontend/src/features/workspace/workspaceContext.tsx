import { createContext, useContext, useEffect, useState } from "react";
import type { InvestigationSummary, Product, Product360, TemporalMode } from "../../app/types";
import { featureSetOf, type FeatureSet } from "../../app/featureSet";
import { tabParam, withTabParam } from "./workspaceAddress";
import { tabParts, type Navigation } from "../../app/linkTable";
import { requestJson } from "../../app/apiClient";
import type { ResolvedCase } from "./savedContext";

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
  // A read-only preview of the distributor and authorised-representative views: free trials only (sections/LookAhead.tsx).
  "Look ahead",
  // From trial to pilot: shown only in free-trial workspaces, to everyone in one (sections/TrialNextSteps.tsx).
  "Next steps",
  // The new navigation's own screens (0.10.68, tenants.navigation = new): the trends, the settings, the team and one
  // complaint's page. An organization on the classic navigation never shows them (linkTable.json classicHomes).
  "Trends",
  "Settings",
  "Team",
  "Complaint",
] as const;

/** Sections only the new navigation shows. */
export const NEW_ONLY_SECTIONS: readonly string[] = ["Trends", "Settings", "Team", "Complaint"];

/** Sections that exist only in a free-trial workspace. */
export const TRIAL_ONLY_SECTIONS: readonly string[] = ["Getting started", "Look ahead", "Next steps"];

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
  "Look ahead": [],
  "Next steps": [],
  Trends: ["products"],
  // Everyone reads the settings; each one says who may change it (sections/Settings.tsx).
  Settings: [],
  Team: [],
  Complaint: ["products"],
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
  /** classic or new (tenants.navigation, 0.10.67): the organization's menu (app/linkTable.ts). */
  navigation?: string;
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
  reportStep?: (tab: string, how?: "push" | "replace") => void;
  /** The tab the section shows now, with the record, panel and filters it carries (workspaceAddress.ts). */
  shownTab?: string;
  /**
   * A section says which tab it shows now (and what it carries), for the screen's address: a new history entry, so
   * Back returns to the previous tab or panel; `replace` (a filter changed) replaces the current entry instead.
   */
  reportTab?: (tab: string, how?: "push" | "replace") => void;
  /** A free-trial workspace (its trial-only sections are shown; the Help menu offers Next steps). */
  isTrial?: boolean;
  /** The organization's navigation in this workspace: new only under the MVP feature set (app/linkTable.ts). */
  navigation?: Navigation;
};

export const WorkspaceContext = createContext<WorkspaceApi | null>(null);

export function useWorkspace(): WorkspaceApi {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside the user workspace");
  return value;
}

/**
 * One parameter of the shown tab's address: the record whose panel is open ("report"), or a filter. Setting it
 * opens or closes the panel and gives the screen its address: opening a record pushes a history entry (Back closes
 * it again); `replace` is for a filter. Outside the workspace it is plain state, starting at `initial`.
 */
export function useTabParam(
  name: string,
  how: "push" | "replace" = "push",
  initial: string | null = null,
): [string | null, (value: string | null) => void] {
  const value = useContext(WorkspaceContext);
  const [local, setLocal] = useState<string | null>(initial);
  const report = value?.reportTab;
  if (!report) return [local, setLocal];
  const shown = value.shownTab;
  return [tabParam(shown, name), (next) => report(withTabParam(shown, name, next), how)];
}

/**
 * A filter's parameters in the shown tab's address (each set value; an empty one is left out), and a setter that
 * replaces the current history entry: changing a filter is not a step Back walks through. Outside the workspace
 * (or before a tab is shown) the setter does nothing and the component keeps its own state.
 */
export function useTabFilters(): (values: Record<string, string>) => void {
  const value = useContext(WorkspaceContext);
  return (values) => {
    const report = value?.reportTab;
    if (!report) return;
    let tab = value.shownTab ?? "";
    for (const [name, text] of Object.entries(values)) tab = withTabParam(tab, name, text.trim() || null);
    report(tab, "replace");
  };
}

/**
 * Make a case of any product the current one: its product is looked up by the case's business ID (the same lookup a
 * case link uses), then the context switches to both. False when the case cannot be found or opened.
 */
export async function chooseCase(work: Pick<WorkContext, "setInvestigationId">, caseRef: string): Promise<boolean> {
  try {
    const found = await requestJson<ResolvedCase>(
      `/api/v1/workspace/context/resolve?investigation=${encodeURIComponent(caseRef)}`,
    );
    work.setInvestigationId(String(found.investigation_id), String(found.product_id));
    return true;
  } catch {
    return false;
  }
}

/** The tab with another name, keeping what it carries (a link's ?signal= stays when the inbox is named). */
export const renamed = (tab: string | undefined, name: string) => {
  const query = tabParts(tab).query;
  return query ? `${name}?${query}` : name;
};

/**
 * A section's tab, as useState, with each change reported for the screen's address (a new history entry). The tab it
 * opens on is said once too, replacing the address (so /app/my-work reads /app/my-work?tab=Assigned+to+me, and a
 * former tab name the new one), unless the address already names it.
 */
export function useReportedTab<T extends string>(initial: T | (() => T)): [T, (next: T) => void] {
  const [active, setActive] = useState<T>(initial);
  const value = useContext(WorkspaceContext);
  const report = value?.reportTab;
  const shown = value?.shownTab;
  useEffect(() => {
    if (report && tabParts(shown).name !== active) report(renamed(shown, active), "replace");
  }, []);
  return [
    active,
    (next) => {
      setActive(next);
      report?.(next);
    },
  ];
}

/** The workspace's navigation: classic outside the workspace. */
export function useNavigation(): Navigation {
  return useContext(WorkspaceContext)?.navigation ?? "classic";
}

/** Whether the workspace is a free trial (false outside the workspace). */
export function useIsTrial(): boolean {
  return !!useContext(WorkspaceContext)?.isTrial;
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

/** Whether to offer an AI action: the role may run AI and the workspace is not a free trial, whose AI is off (the
 * server refuses it there either way: genai/governance.py, GENAI_OFF_FOR_FREE_TRIAL). */
export function useCanRunAi(): boolean {
  const value = useContext(WorkspaceContext);
  return useCan("ai.run") && !value?.isTrial;
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
