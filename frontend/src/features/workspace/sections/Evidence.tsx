import { useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { Tabs } from "../../customer-admin/shared";
import { displayId } from "../../../app/displayId";
import { EvidenceAccessView } from "../../investigator/EvidenceAccessView";
import { useWorkspace } from "../workspaceContext";
import { parseRequestTab } from "../evidenceWorkflow";
import { Embedded, NeedsProduct, RecordTable } from "./common";
import { Limitations } from "./Products";
import { CaseEvidencePanel } from "./CaseEvidence";
import { EvidenceRequestsPanel } from "./EvidenceRequests";

const TABS = [
  "Case evidence",
  "Requests",
  "Evidence library",
  "Product evidence",
  "Provenance",
  "Limitations",
] as const;
type Tab = (typeof TABS)[number];

/** A tab that needs a selected case says so while none is chosen. */
function NeedsCase({ detail, children }: { detail: string; children: (id: string, label: string) => React.ReactNode }) {
  const { work } = useWorkspace();
  if (!work.investigationId)
    return (
      <Panel title="No investigation selected">
        <Empty title="Choose an investigation" detail={detail} />
      </Panel>
    );
  const selected = work.investigations.find((item) => String(item.id) === work.investigationId);
  return <>{children(work.investigationId, displayId(selected, "investigation_identifier", "this case"))}</>;
}

export function EvidenceSection({ tab }: { tab?: string }) {
  // A tab may name a request to open ("Requests?request=…").
  const [target] = useState(() => parseRequestTab(tab));
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(target.tab) ? (target.tab as Tab) : "Case evidence",
  );
  return (
    <>
      <p className="ca-lede">
        Every record keeps its source. Supporting, contradicting and missing evidence stay visible side by side.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Evidence sections">
        {active === "Case evidence" && (
          <NeedsCase detail="Case evidence belongs to one investigation. Pick one in the context bar above.">
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
                  empty={{ title: "No linked evidence", detail: "Evidence linked to this version appears here." }}
                />
              </Panel>
            )}
          </NeedsProduct>
        )}
        {active === "Provenance" && (
          <NeedsProduct>
            {(view) => (
              <Panel eyebrow="Traceability" title="Where each record came from">
                <RecordTable
                  caption="Provenance"
                  rows={view.provenance}
                  columns={["canonical_entity_type", "source_value", "resolution_rule", "resolution_status"]}
                  empty={{ title: "No provenance records", detail: "Source-to-MDARIX resolution appears here." }}
                />
              </Panel>
            )}
          </NeedsProduct>
        )}
        {active === "Limitations" && <NeedsProduct>{(view) => <Limitations items={view.limitations} />}</NeedsProduct>}
      </Tabs>
    </>
  );
}
