import { FileText, ShieldCheck } from "lucide-react";
import { Product360 } from "../../app/types";

export function AssuranceView({ view }: { view: Product360 }) {
  return (
    <div className="content governance-view">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Trust &amp; governance</span>
          <h2>AI Assurance</h2>
          <p>
            Inspect how MDARIX keeps AI outputs grounded, bounded, tenant-scoped, and distinct from authorized human
            decisions.
          </p>
        </div>
        <div className="governance-status">
          <ShieldCheck size={22} />
          <strong>Human authority preserved</strong>
          <span>Assurance informs review; it does not approve a decision.</span>
        </div>
      </section>
      <div className="governance-grid">
        <section className="panel">
          <h3>Assurance checks</h3>
          <ul className="governance-list">
            <li>
              <strong>Evidence grounding</strong>
              <span>Source references and provenance remain visible.</span>
            </li>
            <li>
              <strong>Temporal context</strong>
              <span>Results are evaluated against the selected date and event mode.</span>
            </li>
            <li>
              <strong>ProductVersion context</strong>
              <span>Product and version scope are carried into the workflow.</span>
            </li>
            <li>
              <strong>Causality restraint</strong>
              <span>Unsupported root-cause conclusions are not generated.</span>
            </li>
          </ul>
        </section>
        <section className="panel">
          <h3>Current scope</h3>
          <p>
            <strong>{view.product.name}</strong>
          </p>
          <p>Version {view.selected_version?.version_identifier ?? "not selected"}</p>
          <p>{view.limitations.length} visible limitations require attention.</p>
          <div className="advisory-box">
            <strong>Review required</strong>
            <p>Authorized humans remain responsible for regulated conclusions and final decisions.</p>
          </div>
        </section>
      </div>
    </div>
  );
}

export function AuditTrailView({ view }: { view: Product360 }) {
  return (
    <div className="content governance-view">
      <section className="governance-hero audit-hero">
        <div>
          <span className="eyebrow">Traceability</span>
          <h2>Audit Trail</h2>
          <p>Review the recorded context behind product, investigation, evidence, and decision activity.</p>
        </div>
        <div className="governance-status">
          <FileText size={22} />
          <strong>Controlled foundation</strong>
          <span>Tenant-scoped activity remains attributable and reviewable.</span>
        </div>
      </section>
      <section className="panel audit-table">
        <h3>Recent recorded context</h3>
        <div className="audit-row">
          <strong>Product scope</strong>
          <span>
            {view.product.product_identifier} · {view.product.name}
          </span>
          <small>Current workspace</small>
        </div>
        <div className="audit-row">
          <strong>Version context</strong>
          <span>{view.selected_version?.version_identifier ?? "Not selected"}</span>
          <small>Temporal context preserved</small>
        </div>
        <div className="audit-row">
          <strong>Evidence access</strong>
          <span>{view.evidence.length} product-linked records</span>
          <small>Tenant-scoped access</small>
        </div>
        <div className="audit-row">
          <strong>Limitations</strong>
          <span>{view.limitations.length} visible limitations</span>
          <small>Requires review before conclusion</small>
        </div>
      </section>
    </div>
  );
}
