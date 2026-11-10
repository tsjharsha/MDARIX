// Pure rules for Records › Reports › Ready-to-use documents (T-G35): what the screen asks the server for, where each
// source record opens, and when a judgement or a signature may be sent. The server (/api/v1/documents,
// backend/app/qms_documents) fills the data sections from the records, checks every rule again and signs; MDARIX never
// writes a judgement section.
import { recordsTab } from "./effectiveness";

export type Clause = { id: string; short: string; title: string; state: string };
export type Template = {
  code: DocumentCode;
  title: string;
  template_version: string;
  clauses: Clause[];
  scope: "ORGANIZATION" | "CASE" | "CHANGE";
  purpose: string;
  judgements: { key: string; title: string; prompt: string }[];
  starter_mark: string;
};
export type DocumentCode =
  "MANAGEMENT_REVIEW" | "CAPA_LOG" | "INVESTIGATION_REPORT" | "RISK_REVIEW_EXTRACT" | "CHANGE_IMPACT";
export type DocumentTypes = {
  templates: Template[];
  cases: { id: string; ref: string; identifier: string; question: string }[];
  changes: { id: string; ref: string; type: string }[];
  periods: number[];
  default_period: number;
  practice_label: string | null;
  written_by_manufacturer: string;
  data_note: string;
};
export type Source = { type: string; id: string | null; ref: string; case?: string };
export type Row = { text: string; sources: Source[]; more?: number };
export type Section =
  | { key: string; title: string; kind: "data"; rows: Row[]; note?: string }
  | { key: string; title: string; kind: "judgement"; prompt: string };
export type Signature = {
  record_id: string;
  record_business_id: string | null;
  signer_name: string;
  signer_role: string;
  meaning: string;
  signed_at: string;
  content_fingerprint: string;
  pdf_sha256?: string;
};
export type VersionSummary = {
  id: string;
  business_id: string | null;
  code: DocumentCode;
  title: string;
  version: number;
  status: "DRAFT" | "SIGNED";
  template_version: string;
  period: { from: string; to: string; days: number } | null;
  cut_off: string;
  scope_ref: string | null;
  generated_by: string;
  signed_by: string | null;
  signed_at: string | null;
  superseded_by: number | null;
  filing: { qms_reference: string | null; minutes_spent: number | null } | null;
};
export type DocumentVersion = VersionSummary & {
  clauses: Clause[];
  sections: Section[];
  judgement: Record<string, { text: string; written_by_name: string; written_at: string }>;
  signature: Signature | null;
  writer_note: string | null;
  practice_label: string | null;
  starter_mark: string;
  data_note: string;
  editable: boolean;
};

export const DOCUMENTS_PATH = "/api/v1/documents";
export const TYPES_PATH = `${DOCUMENTS_PATH}/types`;
export const JUDGEMENT_MIN = 10;

export const versionsPath = (code: DocumentCode, scopeId?: string | null) =>
  `${DOCUMENTS_PATH}?${new URLSearchParams({ code, ...(scopeId ? { scope_id: scopeId } : {}) })}`;
export const versionPath = (id: string) => `${DOCUMENTS_PATH}/${encodeURIComponent(id)}`;
export const filePath = (id: string, kind: "pdf" | "docx") => `${versionPath(id)}/${kind}`;

/** What the generate button sends; null while the case or change record is still to be chosen. */
export function generateBody(template: Template, periodDays: number, scopeId: string) {
  if (template.scope === "ORGANIZATION") return { code: template.code, period_days: periodDays };
  if (!scopeId) return null;
  return template.scope === "CASE"
    ? { code: template.code, case_id: scopeId }
    : { code: template.code, change_id: scopeId };
}

/** "pending approval" beside each clause the consultant has not confirmed (TA-35.5). */
export const clauseText = (clause: Clause) =>
  `${clause.short} ${clause.title}${clause.state === "confirmed" ? "" : ` (${clause.state})`}`;

/** Why a judgement cannot be saved yet, or null. */
export function judgementProblem(text: string): string | null {
  return text.trim().length < JUDGEMENT_MIN ? `Write at least ${JUDGEMENT_MIN} characters` : null;
}

/** The judgement sections still unwritten (the signature waits for them). */
export function unwritten(version: DocumentVersion): string[] {
  return version.sections
    .filter((section) => section.kind === "judgement" && !version.judgement[section.key]?.text)
    .map((section) => section.title);
}

export function signProblem(version: DocumentVersion, password: string): string | null {
  const missing = unwritten(version);
  if (missing.length) return `Write ${missing.join(" and ")} first`;
  return password ? null : "Enter your password to sign";
}

export type SourceTarget =
  { kind: "section"; section: string; tab: string } | { kind: "case"; caseId: string; tab: string };

/** Where a source record opens in MDARIX (null: no screen shows it on its own). */
export function sourceTarget(source: Source): SourceTarget | null {
  const caseTabs: Record<string, string> = {
    Case: "Workspace",
    CaseReview: "Reviews",
    Decision: "Decision",
    Signature: "Decision",
    Evidence: "Investigation evidence",
    Hypothesis: "Intelligence",
    FollowUp: "Decision",
  };
  if (source.case && caseTabs[source.type]) return { kind: "case", caseId: source.case, tab: caseTabs[source.type] };
  if (source.case && source.type === "Complaint") return { kind: "case", caseId: source.case, tab: "Scope" };
  const sections: Record<string, [string, string]> = {
    Complaint: ["Complaints", "Dispositions"],
    Disposition: ["Complaints", "Dispositions"],
    MarketAssessment: ["Complaints", "Reportability"],
    SecondLook: ["Complaints", "Second look"],
    Signal: ["Signals", "Signal inbox"],
    Product: ["Records", "Risk file input"],
    Risk: ["Records", "Risk file input"],
    Lot: ["Records", "Risk file input"],
  };
  if (source.type === "Capa" && source.id) return { kind: "section", section: "Records", tab: recordsTab(source.id) };
  const found = sections[source.type];
  return found ? { kind: "section", section: found[0], tab: found[1] } : null;
}

/** "1 record", "72 records" (the row's sources and those it did not list). */
export function recordsText(row: Row): string {
  const count = row.sources.length + (row.more ?? 0);
  return `${count} record${count === 1 ? "" : "s"}`;
}

/** The address a Records › Reports link carries (`Reports?doc=…&scope=…`), read back. */
export function parseDocumentLink(tab: string | undefined): { code: DocumentCode | null; scope: string | null } {
  const query = new URLSearchParams((tab ?? "").split("?")[1] ?? "");
  const code = query.get("doc") as DocumentCode | null;
  return { code: code || null, scope: query.get("scope") || null };
}

export const documentLink = (code: DocumentCode, scope?: string | null) =>
  `Reports?${new URLSearchParams({ doc: code, ...(scope ? { scope } : {}) })}`;
