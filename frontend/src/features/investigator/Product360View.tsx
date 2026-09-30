import { useState } from "react";
import {
  AlertTriangle,
  Boxes,
  CalendarClock,
  ChevronRight,
  CircleDot,
  Factory,
  FileText,
  GitBranch,
  History,
  Layers,
  ShieldCheck,
} from "lucide-react";
import { ProductVersionStory } from "./ProductVersionStory";
import { fmt } from "../../app/format";
import { DenseTable, Metric, Panel } from "../../app/ui";
import { Product360 } from "../../app/types";

export function Product360View({ view }: { view: Product360 }) {
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">{view.product.product_identifier}</p>
          <h2>{view.product.name}</h2>
          <p>
            {view.product.product_family} · {view.product.lifecycle_status}
          </p>
        </div>
        <div className="version-pill">
          <Layers size={16} /> {view.selected_version?.version_identifier ?? "No version selected"}
        </div>
      </section>

      <section className="metric-strip">
        <Metric icon={<Boxes />} label="Components" value={view.overview.component_count} />
        <Metric icon={<Factory />} label="Lots" value={view.overview.lot_count} />
        <Metric icon={<AlertTriangle />} label="Complaints" value={view.overview.complaint_count} />
        <Metric icon={<FileText />} label="Evidence" value={view.overview.evidence_count} />
      </section>

      <ProductVersionStory
        productId={view.product.id ?? undefined}
        versionId={view.selected_version?.id ?? undefined}
      />

      <section className="two-col">
        <Panel title="Configuration" icon={<GitBranch />}>
          <DenseTable
            rows={view.configuration.components.slice(0, 8)}
            columns={["component_identifier", "name", "revision", "status"]}
          />
          <h3>Supplier Context</h3>
          <DenseTable
            rows={view.configuration.suppliers.slice(0, 8)}
            columns={["supplier_identifier", "name", "component_identifier"]}
          />
        </Panel>
        <Panel title="Data Quality / Limitations" icon={<ShieldCheck />}>
          <ul className="limitations">
            {view.limitations.map((item) => (
              <li key={item.code}>
                <strong>{item.code}</strong>
                <span>{item.description}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>

      <section className="two-col">
        <Panel title="Changes" icon={<History />}>
          <DenseTable
            rows={view.changes.slice(0, 8)}
            columns={["change_identifier", "change_type", "effective_timestamp"]}
          />
        </Panel>
        <Panel title="Manufacturing / Lots" icon={<Factory />}>
          <DenseTable
            rows={view.manufacturing.lots.slice(0, 10)}
            columns={["lot_identifier", "site_identifier", "traceability_state", "manufactured_timestamp"]}
          />
        </Panel>
      </section>

      <section className="two-col">
        <Panel title="Field / Complaints" icon={<AlertTriangle />}>
          <DenseTable
            rows={view.complaints.slice(0, 10)}
            columns={["complaint_identifier", "event_timestamp", "recorded_timestamp", "status"]}
          />
        </Panel>
        <Panel title="Evidence" icon={<FileText />}>
          <DenseTable
            rows={view.evidence.slice(0, 10)}
            columns={["evidence_identifier", "evidence_type", "reliability_status", "ingestion_timestamp"]}
          />
        </Panel>
      </section>

      <section className="two-col">
        <Panel title="Risk & Controls" icon={<ShieldCheck />}>
          <DenseTable rows={view.risks.slice(0, 6)} columns={["risk_identifier", "description", "status"]} />
          <DenseTable rows={view.controls.slice(0, 6)} columns={["control_identifier", "control_type", "status"]} />
        </Panel>
        <Panel title="Provenance" icon={<CircleDot />}>
          <DenseTable
            rows={view.provenance.slice(0, 8)}
            columns={["canonical_entity_type", "source_value", "resolution_rule", "resolution_status"]}
          />
        </Panel>
      </section>

      <section className="timeline-section">
        <div className="section-title">
          <CalendarClock size={18} /> Lifecycle Timeline
        </div>
        <div className="timeline">
          {view.timeline.slice(0, 40).map((event) => (
            <article
              key={event.event_id}
              className={expandedEventId === event.event_id ? "timeline-event expanded" : "timeline-event"}
            >
              <div className="event-date">{fmt(event.event_time ?? event.effective_time)}</div>
              <div className="event-body">
                <span className="category">{event.category}</span>
                <h3>{event.title}</h3>
                <p>
                  Event {fmt(event.event_time)} · Effective {fmt(event.effective_time)} · Recorded{" "}
                  {fmt(event.recorded_time)} · Known {fmt(event.knowledge_available_time)}
                </p>
                {event.late_arriving && <span className="late">Late-arriving evidence</span>}
                {expandedEventId === event.event_id && (
                  <div className="event-details">
                    <p>
                      <strong>Description:</strong> {event.description ?? "No additional description recorded."}
                    </p>
                    <p>
                      <strong>Related entity:</strong> {event.related_entity_type ?? "Not recorded"} /{" "}
                      {event.related_entity_id ?? "Not recorded"}
                    </p>
                    <p>
                      <strong>Source:</strong> {event.source ?? "Not recorded"}
                    </p>
                    <p>
                      <strong>Provenance:</strong>{" "}
                      {event.metadata?.provenance_available === false
                        ? "Not available"
                        : "Available when recorded by the source context."}
                    </p>
                  </div>
                )}
              </div>
              <button
                className="timeline-toggle"
                aria-label={`${expandedEventId === event.event_id ? "Collapse" : "Expand"} ${event.title}`}
                aria-expanded={expandedEventId === event.event_id}
                onClick={() => setExpandedEventId((current) => (current === event.event_id ? null : event.event_id))}
              >
                <ChevronRight size={16} />
              </button>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
