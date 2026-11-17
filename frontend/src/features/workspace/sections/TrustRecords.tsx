import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { Table, listOf, useResource } from "../../customer-admin/shared";
import { requestJson } from "../../../app/apiClient";
import { formatDateTime } from "../../../app/dates";
import { roleLabel } from "../../../app/roles";
import { SummaryDownload } from "./Readiness";
import { useCan } from "../workspaceContext";

/*
 * The trust page for an inspector (hero review 2, F-E1, F-E2, F-E5, F-E6): the organization's audit trail with its
 * chain check, the latest signatures checked now, and the evidence pack. Each panel reads a route the server offers
 * only to the people allowed to read it; anyone else (or an older server) sees nothing here, never an error.
 */

/** A signer's training on one controlled document (from the signature routes). */
export type TrainingDoc = { code?: string; title?: string; version?: string | number; current?: boolean };

/** The authenticator check on a signature in words: checked, not checked, or not recorded. */
export const mfaWords = (value: unknown) =>
  value === true ? "Authenticator code checked" : value === false ? "No authenticator code" : "Not recorded";

/** A signer's training in a few words: "Trained · 2 current documents", or what is out of date. */
export function trainingWords(value: unknown): string {
  const documents = listOf(value) as TrainingDoc[];
  if (!documents.length) return "No training recorded";
  const old = documents.filter((item) => item.current === false);
  if (old.length)
    return `Training out of date: ${old.map((item) => item.code ?? item.title ?? "a document").join(", ")}`;
  return `Trained · ${documents.length} current ${documents.length === 1 ? "document" : "documents"}`;
}

/** The two columns F-E6 adds wherever signatures are listed. */
export const signerProofColumns = [
  { key: "mfa", label: "Authenticator", render: (row: any) => mfaWords(row.mfa_verified) },
  { key: "training", label: "Signer training", render: (row: any) => trainingWords(row.training) },
];

type SignedItem = {
  signature_id: string;
  business_id?: string | null;
  /** What was signed: Decision, TriageRecord, ReportSnapshot... and the same in words ("Triage"). */
  object_type?: string | null;
  record_label?: string | null;
  decision_business_id?: string | null;
  decision?: string | null;
  signer_name?: string | null;
  signer_role?: string | null;
  meaning?: string | null;
  signed_at?: string | null;
  mfa_verified?: boolean | null;
  training?: TrainingDoc[];
  /** Checked now for decisions; null for the other kinds, which their own screens verify. */
  fingerprint_ok?: boolean | null;
};

/** A signature's integrity in words: only a decision is checked on this list (null: verified on its own screen). */
export function integrityBadge(value: boolean | null | undefined): {
  tone: "good" | "critical" | "neutral";
  label: string;
} {
  if (value === true) return { tone: "good", label: "Unchanged" };
  if (value === false) return { tone: "critical", label: "Changed since signing" };
  return { tone: "neutral", label: "Checked on its own record" };
}

/** The organization's latest signatures, each checked now against what was signed (F-E2). */
export function LatestSignatures() {
  const signed = useResource<{ items: SignedItem[] }>("/api/v1/governance/signed-records");
  const items = signed.data?.items ?? [];
  if (signed.state !== "ready" || !items.length) return null;
  const changed = items.filter((item) => item.fingerprint_ok === false).length;
  return (
    <Panel eyebrow="Checked now" title="Latest signed records">
      <p className="uw-seal" role="status">
        <ShieldCheck size={24} aria-hidden="true" />
        <span>
          <strong>
            {items.length} {items.length === 1 ? "signature" : "signatures"}
          </strong>{" "}
          · {changed ? `${changed} changed since signing` : "unchanged since signing"} · checked{" "}
          {formatDateTime(new Date().toISOString())}
        </span>
      </p>
      <Table
        caption="Latest signed records"
        rows={items}
        rowKey={(row) => row.signature_id}
        pageSize={10}
        pageNoun="signature"
        empty={{ title: "No signed record yet", detail: "Signed records appear here." }}
        columns={[
          {
            key: "what",
            label: "Record",
            render: (row) => (
              <span className="cc-trial-org">
                <strong>{row.decision_business_id ?? row.business_id ?? row.record_label ?? "Decision"}</strong>
                <small>{[row.record_label, titleCase(String(row.decision ?? ""))].filter(Boolean).join(" � ")}</small>
              </span>
            ),
          },
          {
            key: "signer",
            label: "Signed by",
            render: (row) => (
              <span className="cc-trial-org">
                <strong>{row.signer_name ?? "—"}</strong>
                <small>{roleLabel(row.signer_role) || ""}</small>
              </span>
            ),
          },
          { key: "meaning", label: "Meaning", render: (row) => row.meaning ?? "—" },
          { key: "when", label: "Signed", render: (row) => formatDateTime(row.signed_at) },
          ...signerProofColumns,
          {
            key: "valid",
            label: "Integrity",
            render: (row) => <ToneBadge {...integrityBadge(row.fingerprint_ok)} />,
          },
        ]}
      />
    </Panel>
  );
}

type AuditRow = {
  id: string;
  created_at?: string | null;
  action?: string | null;
  action_label?: string | null;
  actor_name?: string | null;
  reason?: string | null;
  details?: { reason?: string } | null;
};

/** The organization's own audit trail for the trial owner, with the chain check (F-E1). */
export function OrganizationAuditTrail() {
  const audit = useResource<AuditRow[]>("/api/v1/admin/audit-history");
  const [chain, setChain] = useState<{ valid: boolean; checked: number } | "checking" | "failed" | null>(null);
  const rows = listOf(audit.data) as AuditRow[];
  if (audit.state !== "ready" || !rows.length) return null;
  const check = async () => {
    setChain("checking");
    try {
      setChain(await requestJson("/api/v1/admin/audit-chain", { timeoutMs: 60000 }));
    } catch {
      setChain("failed");
    }
  };
  return (
    <Panel eyebrow="Audit trail" title="Everything done in your organization">
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={() => void check()} disabled={chain === "checking"}>
          <ShieldCheck size={15} aria-hidden="true" />{" "}
          {chain === "checking" ? "Checking…" : "Check the audit trail is intact"}
        </button>
        <span role="status" className="ac-muted">
          {chain && typeof chain === "object"
            ? chain.valid
              ? `All ${chain.checked} events checked: nothing has been changed.`
              : "The trail does not verify. Contact MDARIX support."
            : chain === "failed"
              ? "The check could not run right now."
              : "Each event is chained to the one before it, so any change is detected."}
        </span>
      </div>
      <Table
        caption="Audit events"
        rows={rows}
        rowKey={(row) => row.id}
        pageSize={15}
        pageNoun="event"
        empty={{ title: "No events yet", detail: "Every action in your organization appears here." }}
        columns={[
          { key: "when", label: "When", render: (row) => formatDateTime(row.created_at) },
          { key: "who", label: "Who", render: (row) => row.actor_name ?? "System" },
          {
            key: "what",
            label: "What",
            render: (row) => <strong>{row.action_label ?? titleCase(String(row.action ?? ""))}</strong>,
          },
          { key: "why", label: "Reason", render: (row) => row.reason ?? row.details?.reason ?? "—" },
        ]}
      />
    </Panel>
  );
}

/** The evidence pack at the top of Records: what it holds, and its downloads (F-E5). */
export function EvidencePackCard() {
  if (!useCan("data.export")) return null;
  return (
    <Panel eyebrow="For an inspector" title="Evidence pack">
      <p className="ac-muted">
        The readiness summary as a PDF, and the inspection pack: every check and the records behind it as CSV, each file
        with its SHA-256 fingerprint, made when you download it.
      </p>
      <SummaryDownload />
    </Panel>
  );
}
