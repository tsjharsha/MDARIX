import { useState } from "react";
import { Panel } from "../../admin/console/charts";
import { Tabs } from "../../customer-admin/shared";
import { EvidenceAccessView } from "../../investigator/EvidenceAccessView";
import { Embedded, NeedsProduct, RecordTable } from "./common";
import { Limitations } from "./Products";

const TABS = ["Evidence library", "Product evidence", "Provenance", "Limitations"] as const;
type Tab = (typeof TABS)[number];

export function EvidenceSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Evidence library",
  );
  return (
    <>
      <p className="ca-lede">
        Every record keeps its source. Supporting, contradicting and missing evidence stay visible side by side.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Evidence sections">
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
