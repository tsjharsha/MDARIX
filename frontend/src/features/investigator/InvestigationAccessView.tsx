import { useEffect, useState } from "react";
import { ClipboardList } from "lucide-react";
import { TemporalMode, Product360 } from "../../app/types";
import { api } from "../../app/api";
import { InvestigationWorkspacePanel } from "./InvestigationWorkspacePanel";

export function InvestigationAccessView({
  view,
  selectedInvestigationId,
  onSelect,
  temporalMode,
  asOf,
  onOpenDecision,
}: {
  view: Product360;
  selectedInvestigationId: string;
  onSelect: (id: string) => void;
  temporalMode: TemporalMode;
  asOf: string;
  onOpenDecision: () => void;
}) {
  const [investigations, setInvestigations] = useState<Array<Record<string, string | null>>>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const selected = investigations.find((investigation) => investigation.id === selectedInvestigationId);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api<Array<Record<string, string | null>>>(`/api/v1/products/${view.product.id}/investigations`)
      .then((items) => {
        if (!active) return;
        setInvestigations(items);
        onSelect(
          items.some((investigation) => investigation.id === selectedInvestigationId)
            ? selectedInvestigationId
            : (items[0]?.id ?? ""),
        );
        setLoadError("");
      })
      .catch((err) => {
        if (active) setLoadError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [view.product.id]);

  return (
    <div className="content">
      <section className="product-header">
        <div>
          <p className="eyebrow">Investigation access</p>
          <h2>{view.product.name}</h2>
          <p>
            Version {view.selected_version?.version_identifier ?? "not recorded"}. Select an available investigation to
            open the existing Day 10–14 workspace.
          </p>
        </div>
        <div className="version-pill">
          <ClipboardList size={16} /> {loading ? "Loading" : `${investigations.length} available`}
        </div>
      </section>
      {loadError && <div className="error">Investigations could not be loaded: {loadError}</div>}
      {!loading && !loadError && investigations.length === 0 ? (
        <section className="panel empty-state">
          <h2>No investigations available</h2>
          <p>
            The selected product has no investigation records in the current Product 360 result. No workspace has been
            created or inferred.
          </p>
        </section>
      ) : (
        <>
          <section className="panel">
            <div className="section-title">
              <ClipboardList size={18} /> Available investigations
            </div>
            <div className="investigation-list">
              {investigations.map((investigation) => (
                <button
                  key={investigation.id}
                  className={`investigation-option ${investigation.id === selectedInvestigationId ? "selected" : ""}`}
                  onClick={() => onSelect(investigation.id ?? "")}
                >
                  <strong>{investigation.investigation_identifier ?? investigation.id}</strong>
                  <span>{investigation.investigation_question ?? "No question recorded."}</span>
                  <small>
                    ID: {investigation.id} | Status: {investigation.status ?? "not recorded"}
                  </small>
                </button>
              ))}
            </div>
          </section>
          {selectedInvestigationId && (
            <InvestigationWorkspacePanel
              key={selectedInvestigationId}
              investigationId={selectedInvestigationId}
              temporalMode={temporalMode}
              asOf={asOf}
              onOpenDecision={onOpenDecision}
            />
          )}
          {!selected && (
            <div className="error inline">The selected investigation is not available in this Product 360 result.</div>
          )}
        </>
      )}
    </div>
  );
}
