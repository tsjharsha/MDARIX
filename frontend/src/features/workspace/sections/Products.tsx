import { useState } from "react";
import { AlertTriangle, Boxes, Factory, FileText, GitBranch, Layers } from "lucide-react";
import { Empty, Panel, StatTile } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { Tabs, formatDate } from "../../customer-admin/shared";
import { ProductVersionStory } from "../../investigator/ProductVersionStory";
import { useWorkspace } from "../workspaceContext";
import { Embedded, NeedsProduct, RecordTable, StatusBadge, recordFieldKeys } from "./common";
import { displayId, safeText } from "../../../app/displayId";

const TABS = [
  "Overview",
  "Configuration",
  "Manufacturing",
  "Changes",
  "Risks & controls",
  "Timeline",
  "Version story",
] as const;
type Tab = (typeof TABS)[number];

export function ProductsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Overview",
  );
  const { open } = useWorkspace();
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Product sections">
        <NeedsProduct>
          {(view) => (
            <>
              {active === "Overview" && (
                <>
                  <Panel
                    eyebrow={productEyebrow(view.product)}
                    title={view.product.name ?? "Product"}
                    action={<StatusBadge value={view.product.lifecycle_status} />}
                  >
                    <dl className="ca-facts">
                      <div>
                        <dt>Product ID</dt>
                        <dd>{displayId(view.product, "product_identifier")}</dd>
                      </div>
                      {safeText(view.product.business_id) && (
                        <div>
                          <dt>Source ID</dt>
                          <dd>{safeText(view.product.product_identifier) ?? "—"}</dd>
                        </div>
                      )}
                      <div>
                        <dt>Family</dt>
                        <dd>{view.product.product_family ?? "—"}</dd>
                      </div>
                      <div>
                        <dt>Selected version</dt>
                        <dd>{view.selected_version?.version_identifier ?? "No version selected"}</dd>
                      </div>
                      <div>
                        <dt>Versions</dt>
                        <dd>{String(view.overview.version_count ?? view.versions.length)}</dd>
                      </div>
                      <div>
                        <dt>Time view</dt>
                        <dd>
                          {titleCase(String(view.temporal_context.mode ?? "event"))} ·{" "}
                          {formatDate(view.temporal_context.as_of)}
                        </dd>
                      </div>
                    </dl>
                  </Panel>
                  <section className="ac-stats" aria-label="Product figures">
                    <StatTile
                      label="Components"
                      value={Number(view.overview.component_count ?? 0)}
                      detail="In this version"
                      icon={<Boxes size={18} />}
                      onOpen={() => setActive("Configuration")}
                    />
                    <StatTile
                      label="Suppliers"
                      value={Number(view.overview.supplier_count ?? 0)}
                      detail="Linked to components"
                      icon={<Layers size={18} />}
                      onOpen={() => setActive("Configuration")}
                    />
                    <StatTile
                      label="Lots"
                      value={Number(view.overview.lot_count ?? 0)}
                      detail="Manufactured"
                      icon={<Factory size={18} />}
                      onOpen={() => setActive("Manufacturing")}
                    />
                    <StatTile
                      label="Complaints"
                      value={Number(view.overview.complaint_count ?? 0)}
                      detail="Recorded signals"
                      icon={<AlertTriangle size={18} />}
                      onOpen={() => open("Signals")}
                    />
                    <StatTile
                      label="Evidence"
                      value={Number(view.overview.evidence_count ?? 0)}
                      detail="Linked records"
                      icon={<FileText size={18} />}
                      onOpen={() => open("Evidence")}
                    />
                    <StatTile
                      label="Changes"
                      value={view.changes.length}
                      detail="Design and process"
                      icon={<GitBranch size={18} />}
                      onOpen={() => setActive("Changes")}
                    />
                  </section>
                  <Limitations items={view.limitations} />
                </>
              )}
              {active === "Configuration" && (
                <div className="ac-grid two">
                  <Panel eyebrow="Configuration" title="Components">
                    <RecordTable
                      caption="Components"
                      idLabel="Component ID"
                      rows={view.configuration.components}
                      columns={["component_identifier", "name", "revision", "status"]}
                      empty={{
                        title: "No components recorded",
                        detail: "Components appear once product structure is connected.",
                      }}
                    />
                  </Panel>
                  <Panel eyebrow="Configuration" title="Suppliers">
                    <RecordTable
                      caption="Suppliers"
                      idLabel="Supplier ID"
                      rows={view.configuration.suppliers}
                      columns={["supplier_identifier", "name", "component_identifier"]}
                      empty={{
                        title: "No suppliers recorded",
                        detail: "Suppliers appear once supply data is connected.",
                      }}
                    />
                  </Panel>
                </div>
              )}
              {active === "Manufacturing" && (
                <div className="ac-grid two">
                  <Panel eyebrow="Manufacturing" title="Lots">
                    <RecordTable
                      caption="Lots"
                      idLabel="Lot ID"
                      rows={view.manufacturing.lots}
                      columns={["lot_identifier", "site_identifier", "traceability_state", "manufactured_timestamp"]}
                      empty={{ title: "No lots recorded", detail: "Lots appear once manufacturing data is connected." }}
                    />
                  </Panel>
                  <Panel eyebrow="Manufacturing" title="Sites">
                    <RecordTable
                      caption="Sites"
                      idLabel="Site ID"
                      rows={view.manufacturing.sites}
                      columns={recordFieldKeys(view.manufacturing.sites[0], ["site_identifier", "name"]).slice(0, 4)}
                      empty={{
                        title: "No sites recorded",
                        detail: "Sites appear once manufacturing data is connected.",
                      }}
                    />
                  </Panel>
                </div>
              )}
              {active === "Changes" && (
                <Panel eyebrow="Change control" title="Design and process changes">
                  <RecordTable
                    caption="Changes"
                    idLabel="Change ID"
                    rows={view.changes}
                    columns={["change_identifier", "change_type", "effective_timestamp"]}
                    empty={{ title: "No changes recorded", detail: "Approved changes to this product appear here." }}
                  />
                </Panel>
              )}
              {active === "Risks & controls" && (
                <>
                  <div className="ac-grid two">
                    <Panel eyebrow="Risk" title="Risks">
                      <RecordTable
                        caption="Risks"
                        idLabel="Risk ID"
                        rows={view.risks}
                        columns={["risk_identifier", "description", "status"]}
                        empty={{ title: "No risks recorded", detail: "The risk file appears here when connected." }}
                      />
                    </Panel>
                    <Panel eyebrow="Risk" title="Controls">
                      <RecordTable
                        caption="Controls"
                        idLabel="Control ID"
                        rows={view.controls}
                        columns={["control_identifier", "control_type", "status"]}
                        empty={{ title: "No controls recorded", detail: "Risk controls appear here when connected." }}
                      />
                    </Panel>
                  </div>
                  <Panel eyebrow="Risk" title="Failure modes">
                    <RecordTable
                      caption="Failure modes"
                      idLabel="Failure mode ID"
                      rows={view.failure_modes}
                      columns={recordFieldKeys(view.failure_modes[0], ["failure_mode_identifier", "description"]).slice(
                        0,
                        4,
                      )}
                      empty={{ title: "No failure modes recorded", detail: "FMEA entries appear here when connected." }}
                    />
                  </Panel>
                </>
              )}
              {active === "Timeline" && (
                <Panel eyebrow="History" title="Product timeline">
                  {view.timeline.length ? (
                    <ul className="ca-timeline">
                      {view.timeline.slice(0, 80).map((event) => (
                        <li key={event.event_id}>
                          <strong>{event.title}</strong>
                          <small>
                            {titleCase(event.category)} · {formatDate(event.event_time ?? event.recorded_time)}
                            {event.late_arriving ? " · arrived late" : ""}
                          </small>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <Empty
                      title="No timeline events"
                      detail="Changes, lots, complaints and decisions appear here in order."
                    />
                  )}
                </Panel>
              )}
              {active === "Version story" && (
                <Embedded>
                  <ProductVersionStory
                    productId={view.product.id ?? undefined}
                    versionId={view.selected_version?.id ?? undefined}
                  />
                </Embedded>
              )}
            </>
          )}
        </NeedsProduct>
      </Tabs>
    </>
  );
}

/** "Product · PROD000003": the product's MDARIX ID (its source number until the record carries one). */
const productEyebrow = (product: Record<string, string | null>) => {
  const id = displayId(product, "product_identifier", "");
  return id ? `Product · ${id}` : "Product";
};

export function Limitations({ items }: { items: Array<{ code: string; severity: string; description: string }> }) {
  return (
    <Panel eyebrow="Know the gaps" title="Data limitations">
      {items.length ? (
        <ul className="ac-attention">
          {items.map((item) => (
            <li key={item.code}>
              <StatusBadge value={item.severity} />
              <span>
                <strong>{titleCase(item.code)}</strong>
                <small>{item.description}</small>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <Empty title="No known limitations" detail="Gaps in the data are listed here so nobody over-reads it." />
      )}
    </Panel>
  );
}
