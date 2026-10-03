import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { EvidenceSummary } from "../../app/types";
import { api } from "../../app/api";

export function EvidenceAccessView({ productEvidenceCount }: { productEvidenceCount: number }) {
  const [evidence, setEvidence] = useState<EvidenceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    api<EvidenceSummary[]>("/api/v1/evidence?limit=50")
      .then((items) => {
        if (active) {
          setEvidence(items);
          setError("");
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Evidence access</p>
          <h2>Tenant evidence records</h2>
          <p>
            Product 360 currently shows {productEvidenceCount} evidence record{productEvidenceCount === 1 ? "" : "s"}{" "}
            linked to the selected product scope. This list covers your organization's evidence and does not imply a
            product link.
          </p>
        </div>
        <div className="version-pill">
          <FileText size={16} /> {loading ? "Loading" : `${evidence.length} available`}
        </div>
      </section>
      {error && <div className="error">Evidence could not be loaded: {error}</div>}
      {!loading && !error && evidence.length === 0 && (
        <section className="panel empty-state">
          <h2>No evidence records available</h2>
          <p>
            No evidence records were found for your organization. This is an empty state, not a conclusion about the
            selected product.
          </p>
        </section>
      )}
      {!loading && evidence.length > 0 && (
        <section className="panel">
          <div className="section-title">
            <FileText size={18} /> Available evidence
          </div>
          <div className="evidence-list">
            {evidence.map((item) => (
              <article key={item.id}>
                <strong>{item.evidence_identifier}</strong>
                <span>{item.title}</span>
                <small>
                  {item.evidence_type} | {item.reliability_status ?? "reliability not recorded"} |{" "}
                  {item.source_system ?? "source not recorded"}
                </small>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
