import { useState } from "react";
import { BadgeCheck, Ban, CheckCircle2 } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { Table, Tabs, listOf, useResource } from "../../customer-admin/shared";
import { NeedsProduct, RecordTable } from "./common";
import { Limitations } from "./Products";
import { AuditTab } from "./AuditTab";
import { TrustEvaluation } from "./TrustEvaluation";

const TABS = ["AI assurance", "Audit trail", "Data limitations"] as const;
type Tab = (typeof TABS)[number];

export function TrustSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "AI assurance",
  );
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Trust and audit sections" />
      {active === "AI assurance" && <Assurance />}
      {active === "Audit trail" && <AuditTab />}
      {active === "Data limitations" && (
        <NeedsProduct>
          {(view) => (
            <>
              <Limitations items={view.limitations} />
              <Panel eyebrow="Traceability" title="Source resolution">
                <RecordTable
                  caption="Provenance"
                  rows={view.provenance}
                  columns={["canonical_entity_type", "source_value", "resolution_rule", "resolution_status"]}
                  empty={{ title: "No provenance records", detail: "Source-to-MDARIX resolution appears here." }}
                />
              </Panel>
            </>
          )}
        </NeedsProduct>
      )}
    </>
  );
}

function Assurance() {
  const summary = useResource<any>("/api/v1/ai/assurance/summary");
  const agents = useResource<any>("/api/v1/ai/agents/catalog");
  const guardrails = Object.entries((summary.data?.guardrails ?? {}) as Record<string, string>);
  return (
    <>
      <TrustEvaluation />
      <Panel
        eyebrow="Declared by the AI service"
        title="Guardrails on every AI answer"
        state={summary.state}
        error={summary.error}
      >
        <ul className="ac-posture-list">
          {guardrails.map(([name, value]) => (
            <li key={name}>
              <BadgeCheck size={16} aria-hidden="true" /> {titleCase(name)}: {titleCase(value)}
            </li>
          ))}
        </ul>
        <p className="ac-muted">
          These are the rules the AI service declares it enforces. They describe behaviour; they are not a test result.
        </p>
      </Panel>
      <Panel
        eyebrow="AI agents"
        title="What each assistant may and may not do"
        state={agents.state}
        error={agents.error}
      >
        <Table
          caption="AI agents"
          rows={listOf(agents.data?.agents)}
          rowKey={(row) => row.code}
          empty={{ title: "No AI agents listed", detail: "The AI service did not return its catalog." }}
          columns={[
            { key: "label", label: "Assistant", render: (row) => <strong>{row.label}</strong> },
            {
              key: "allowed",
              label: "May",
              render: (row) => (
                <span className="uw-inline-list">
                  <CheckCircle2 size={14} className="ac-tone-icon tone-good" aria-hidden="true" />
                  {listOf(row.allowed)
                    .map((item: string) => titleCase(item))
                    .join(", ")}
                </span>
              ),
            },
            {
              key: "forbidden",
              label: "Never",
              render: (row) => (
                <span className="uw-inline-list">
                  <Ban size={14} className="ac-tone-icon tone-critical" aria-hidden="true" />
                  {listOf(row.forbidden)
                    .map((item: string) => titleCase(item))
                    .join(", ")}
                </span>
              ),
            },
          ]}
        />
      </Panel>
    </>
  );
}
