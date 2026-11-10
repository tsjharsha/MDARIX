import { useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { Tabs } from "../../customer-admin/shared";
import { displayId } from "../../../app/displayId";
import { EvidenceAccessView } from "../../investigator/EvidenceAccessView";
import { useWorkspace } from "../workspaceContext";
import { parseRequestTab } from "../evidenceWorkflow";
import { currentTab } from "../../../app/linkTable";
import { Embedded, NeedsProduct, ProvenanceTable, RecordTable } from "./common";
import { Limitations } from "./Products";
import { CaseEvidencePanel } from "./CaseEvidence";
import { EvidenceRequestsPanel } from "./EvidenceRequests";

const TABS = [
  "Investigation evidence",
  "Requests",
  "Evidence library",
  "Product evidence",
  "Provenance",
  "Limitations",
] as const;
type Tab = (typeof TABS)[number];

/** A tab that needs a selected investigation says so while none is chosen. */
function NeedsCase({ detail, children }: { detail: string; children: (id: string, label: string) => React.ReactNode }) {
  const { work } = useWorkspace();
  if (!work.investigationId)
    return (
      <Panel title="No investigation selected">
        <Empty title="Choose an investigation" detail={detail} />
      </Panel>
    );
  const selected = work.investigations.find((item) => String(item.id) === work.investigationId);
  return <>{children(work.investigationId, displayId(selected, "investigation_identifier", "this investigation"))}</>;
}

export function EvidenceSection({ tab }: { tab?: string }) {
  // A tab may name a request to open ("Requests?request=…"); a former tab name opens the tab that replaced it.
  const [target] = useState(() => parseRequestTab(currentTab("Evidence", tab)));
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(target.tab) ? (target.tab as Tab) : "Investigation evidence",
  );
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Evidence sections">
        {active === "Investigation evidence" && (
          <NeedsCase detail="This evidence belongs to one investigation. Pick one in the context bar above.">
            {(id, label) => <CaseEvidencePanel key={id} investigationId={id} caseLabel={label} />}
          </NeedsCase>
        )}
        {active === "Requests" && (
          <NeedsCase detail="Pick an investigation in the context bar above to see its evidence requests.">
            {(id, label) => (
              <EvidenceRequestsPanel
                key={id}
                investigationId={id}
                caseLabel={label}
                initialRequest={target.tab === "Requests" ? target.request : null}
              />
            )}
          </NeedsCase>
        )}
        {active === "Evidence library" && (
          <NeedsProduct>
            {(view) => (
              <Embedded>
                <EvidenceAccessView productEvidenceCount={view.evidence.length} />
              </Embedded>
            )}
          </NeedsProduct>
        )}
        {active === "Product evidence" && (
          <NeedsProduct>
            {(view) => (
              <Panel eyebrow={view.product.name ?? "Product"} title="Evidence linked to the selected version">
                <RecordTable
                  caption="Product evidence"
                  idLabel="Evidence ID"
                  rows={view.evidence}
                  columns={["evidence_identifier", "evidence_type", "reliability_status", "ingestion_timestamp"]}
                  labels={{
                    evidence_type: "Type",
                    reliability_status: "Reliability",
                    ingestion_timestamp: "Received",
                  }}
                  codes={["evidence_type"]}
                  empty={{
                    title: "No linked evidence",
                    detail: "Documents, test reports and records linked to this product version appear here.",
                  }}
                />
              </Panel>
            )}
          </NeedsProduct>
        )}
        {active === "Provenance" && (
          <NeedsProduct>
            {(view) => (
              <Panel eyebrow="Traceability" title="Where each record came from">
                <ProvenanceTable rows={view.provenance} />
              </Panel>
            )}
          </NeedsProduct>
        )}
        {active === "Limitations" && <NeedsProduct>{(view) => <Limitations items={view.limitations} />}</NeedsProduct>}
      </Tabs>
    </>
  );
}
