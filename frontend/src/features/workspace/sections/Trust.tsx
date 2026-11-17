import { useEffect, useRef, useState } from "react";
import { BadgeCheck, Ban, CheckCircle2 } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { Table, Tabs, listOf, useResource } from "../../customer-admin/shared";
import { displayId } from "../../../app/displayId";
import { useFeatureSet, useWorkspace } from "../workspaceContext";
import { tabsFor } from "../../../app/featureSet";
import { CASE_TRUST_TABS, TRUST_TABS, initialTrustTab, parseTrustTab, type TrustTab } from "../caseAudit";
import { NeedsProduct, ProvenanceTable } from "./common";
import { Limitations } from "./Products";
import { AuditTab } from "./AuditTab";
import { TrustEvaluation } from "./TrustEvaluation";
import { CaseAiRuns, CaseIntegrity, CaseReplay, CaseTimeline } from "./CaseAudit";
import { DecisionRecordDrawer } from "./DecisionRecord";

type Tab = TrustTab;

export function TrustSection({ tab, segmented = false }: { tab?: string; segmented?: boolean }) {
  const { work, open } = useWorkspace();
  const [requested] = useState(() => parseTrustTab(tab));
  // A case opened from a decision, which the context bar may not hold (another product).
  const [opened, setOpened] = useState<{ id: string; label: string | null } | null>(() =>
    requested.caseId ? { id: requested.caseId, label: requested.caseLabel } : null,
  );
  // Choosing another case in the context bar shows that case.
  const previous = useRef(work.investigationId);
  useEffect(() => {
    if (previous.current === work.investigationId) return;
    previous.current = work.investigationId;
    if (work.investigationId) setOpened((current) => (current && current.id !== work.investigationId ? null : current));
  }, [work.investigationId]);
  const caseId = opened?.id ?? work.investigationId;
  const selected = work.investigations.find((item) => String(item.id) === caseId);
  const caseLabel =
    (selected ? displayId(selected, "investigation_identifier", "") : "") || opened?.label || "Selected investigation";
  // Under the MVP feature set AI assurance is parked (featureSet.ts); a link to it opens the default tab instead.
  const featureSet = useFeatureSet();
  const mvp = featureSet === "mvp";
  const tabs = tabsFor("Trust & Audit", TRUST_TABS, featureSet);
  const requestedTab = requested.tab && tabs.includes(requested.tab) ? requested.tab : null;
  // Without a tab asked for, a chosen case opens on its timeline; otherwise AI assurance as before (Audit trail
  // where AI assurance is parked).
  const [chosen, setChosen] = useState<Tab | null>(null);
  const active =
    chosen ?? initialTrustTab(requestedTab, !!caseId, tabs.includes("AI assurance") ? "AI assurance" : "Audit trail");
  const [recordId, setRecordId] = useState<string | null>(null);
  const caseTab = CASE_TRUST_TABS.includes(active);
  return (
    <>
      <Tabs tabs={tabs} active={active} onChange={setChosen} label="Trust and audit sections" segmented={segmented}>
        {caseTab && opened && opened.id !== work.investigationId && (
          <p className="ac-note" role="status">
            {mvp
              ? "Opened from a decision: not the investigation you have open."
              : "Opened from a decision. The context bar above still shows another investigation."}
          </p>
        )}
        {caseTab && !caseId && (
          <Panel title="No investigation selected">
            {/* Under the MVP this is Records › Audit trail, which has no context bar: the case is chosen on its page. */}
            <Empty
              title="Choose an investigation"
              detail={
                mvp
                  ? "The investigation timeline, replay, AI runs and integrity checks belong to an investigation. Open one in Investigations, then its Record step's timeline."
                  : "The investigation timeline, replay, AI runs and integrity checks belong to an investigation. Pick one in the context bar above."
              }
              action={
                mvp ? (
                  <button type="button" className="ac-secondary" onClick={() => open("Investigations")}>
                    Open Investigations
                  </button>
                ) : undefined
              }
            />
          </Panel>
        )}
        {active === "Investigation timeline" && caseId && (
          <CaseTimeline key={caseId} investigationId={caseId} caseLabel={caseLabel} onOpenDecision={setRecordId} />
        )}
        {active === "Replay" && caseId && (
          <CaseReplay key={caseId} investigationId={caseId} caseLabel={caseLabel} onOpenDecision={setRecordId} />
        )}
        {active === "AI runs" && caseId && <CaseAiRuns key={caseId} investigationId={caseId} caseLabel={caseLabel} />}
        {active === "Integrity" && caseId && (
          <CaseIntegrity key={caseId} investigationId={caseId} caseLabel={caseLabel} onOpenDecision={setRecordId} />
        )}
        {active === "AI assurance" && <Assurance />}
        {active === "Audit trail" && <AuditTab />}
        {active === "Data limitations" && (
          <NeedsProduct>
            {(view) => (
              <>
                <Limitations items={view.limitations} />
                <Panel eyebrow="Traceability" title="How source values were matched">
                  <ProvenanceTable rows={view.provenance} />
                </Panel>
              </>
            )}
          </NeedsProduct>
        )}
      </Tabs>
      {recordId && (
        <DecisionRecordDrawer
          key={recordId}
          decisionId={recordId}
          onClose={() => setRecordId(null)}
          showCaseStory={false}
        />
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
      <Panel eyebrow="Declared by the AI service" title="Guardrails on every AI answer" source={summary}>
        <ul className="ac-posture-list">
          {guardrails.map(([name, value]) => (
            <li key={name}>
              <BadgeCheck size={16} aria-hidden="true" /> {titleCase(name)}: {titleCase(value)}
            </li>
          ))}
        </ul>
        <p className="ac-muted">
          These are the rules the AI service declares it enforces. They describe behavior; they are not a test result.
        </p>
      </Panel>
      <Panel eyebrow="AI agents" title="What each assistant may and may not do" source={agents}>
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
