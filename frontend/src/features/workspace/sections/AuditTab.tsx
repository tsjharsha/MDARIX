import { useState } from "react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { Table, formatDate, idColumn, listOf, useResource } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
import { StatusBadge } from "./common";
import { roleLabel } from "../../../app/roles";
import { SignatureBasis } from "../../shared/Basis";

/**
 * The record a user may see: decisions in the selected investigation and the signatures on them.
 * The organization-wide audit trail (IP addresses, before/after values) stays with administrators.
 */
export function AuditTab() {
  const { work } = useWorkspace();
  const decisions = useResource<any>(
    work.investigationId ? `/api/v1/investigations/${work.investigationId}/decisions` : null,
  );
  const [selected, setSelected] = useState<string | null>(null);
  if (!work.investigationId)
    return (
      <Panel title="No investigation selected">
        <Empty title="Choose an investigation" detail="The decision record belongs to an investigation." />
      </Panel>
    );
  const rows = listOf(decisions.data?.decisions ?? decisions.data);
  return (
    <>
      <Panel eyebrow="Decision record" title="Decisions in this investigation" source={decisions}>
        <p className="ac-muted">
          Every decision keeps who decided, when, and the exact version signed. Your organization's full audit trail is
          available to its administrators.
        </p>
        <Table
          caption="Decisions"
          rows={rows}
          rowKey={(row) => String(row.id)}
          empty={{ title: "No decisions yet", detail: "Decisions recorded for this investigation appear here." }}
          columns={[
            idColumn("Decision ID", "decision_identifier"),
            {
              key: "action",
              label: "Action",
              render: (row) => titleCase(String(row.selected_action ?? row.disposition ?? "—")),
            },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.decision_status} /> },
            { key: "updated", label: "Last change", render: (row) => formatDate(row.updated_at) },
            {
              key: "verify",
              label: "",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => setSelected(String(row.id))}>
                  Signatures
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {selected && <Signatures decisionId={selected} />}
    </>
  );
}

function Signatures({ decisionId }: { decisionId: string }) {
  const verification = useResource<any>(`/api/v1/governance/decisions/${decisionId}/signature-verification`);
  const status = String(verification.data?.verification_status ?? "");
  // INVALID: at least one signature no longer matches what was signed - a problem, shown as one.
  const label =
    status === "VALID"
      ? "All signatures valid"
      : status === "INVALID"
        ? "Invalid: a signature does not match"
        : status === "NOT_SIGNED"
          ? "Not signed"
          : titleCase(status || "Unknown");
  return (
    <Panel
      eyebrow="Signatures"
      title="Signature verification"
      source={verification}
      action={
        verification.data ? (
          <ToneBadge
            tone={status === "VALID" ? "good" : status === "NOT_SIGNED" ? "neutral" : "critical"}
            label={label}
          />
        ) : undefined
      }
    >
      <Table
        caption="Signatures"
        rows={listOf(verification.data?.signatures)}
        rowKey={(row) => String(row.signature_id)}
        empty={{ title: "Not signed yet", detail: "Signatures appear once an authorized person signs." }}
        columns={[
          idColumn("Signature ID"),
          { key: "decision", label: "Signed as", render: (row) => titleCase(String(row.decision ?? "—")) },
          { key: "role", label: "Signer role", render: (row) => roleLabel(row.signer_role) || "—" },
          { key: "meaning", label: "Meaning", render: (row) => row.meaning ?? "—" },
          {
            key: "valid",
            label: "Integrity",
            render: (row) => (
              <ToneBadge
                tone={row.valid ? "good" : "critical"}
                label={row.valid ? "Unchanged" : "Changed since signing"}
              />
            ),
          },
          { key: "when", label: "Signed", render: (row) => formatDate(row.signed_at) },
        ]}
      />
      {listOf(verification.data?.signatures).length > 0 && <SignatureBasis />}
    </Panel>
  );
}
