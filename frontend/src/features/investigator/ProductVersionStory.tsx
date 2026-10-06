import { useEffect, useState } from "react";
import { describeError, requestJson } from "../../app/apiClient";

type Props = { productId?: string; versionId?: string };

export function ProductVersionStory({ productId, versionId }: Props) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!productId || !versionId) return;
    requestJson<any>(
      `/api/v1/products/${encodeURIComponent(productId)}/versions/${encodeURIComponent(versionId)}/story`,
    )
      .then(setData)
      .catch((reason) => setError(describeError(reason, "The version story could not be loaded.")));
  }, [productId, versionId]);
  if (!productId || !versionId) return null;
  if (error)
    return (
      <section className="panel">
        <h3>Product Version Story</h3>
        <p className="error" role="alert">
          {error}
        </p>
      </section>
    );
  if (!data)
    return (
      <section className="panel">
        <h3>Product Version Story</h3>
        <p>Loading version story…</p>
      </section>
    );
  if (data.status === "NOT_FOUND")
    return (
      <section className="panel empty-state">
        <h3>Product Version Story unavailable</h3>
        <p>This version is not available in the authenticated tenant.</p>
      </section>
    );
  const version = data.version ?? {};
  return (
    <section className="panel product-version-story">
      <div className="section-title">Product Version Story</div>
      <p className="story-lead">
        The story of the selected release, the field signals it received, the investigations opened, and the evidence
        available for review.
      </p>
      <div className="home-insight-grid">
        <article>
          <span className="eyebrow">Release</span>
          <strong>{version.version_identifier ?? "Not recorded"}</strong>
          <p>{version.lifecycle_status ?? "Lifecycle not recorded"}</p>
        </article>
        <article>
          <span className="eyebrow">Complaints</span>
          <strong>{data.counts?.complaints ?? 0}</strong>
          <p>Source-recorded signals</p>
        </article>
        <article>
          <span className="eyebrow">Investigations</span>
          <strong>{data.counts?.investigations ?? 0}</strong>
          <p>Related workspaces</p>
        </article>
        <article>
          <span className="eyebrow">Evidence</span>
          <strong>{data.counts?.evidence ?? 0}</strong>
          <p>Available for review</p>
        </article>
      </div>
      <div className="two-col">
        <div>
          <h3>Signals</h3>
          <div className="evidence-list">
            {(data.complaints ?? []).slice(0, 5).map((item: any) => (
              <article key={item.complaint_identifier}>
                <strong>{item.complaint_identifier}</strong>
                <span>{item.description ?? "Description not recorded"}</span>
                <small>{item.status ?? "Status not recorded"}</small>
              </article>
            ))}
          </div>
        </div>
        <div>
          <h3>Investigations &amp; evidence</h3>
          <div className="evidence-list">
            {(data.investigations ?? []).slice(0, 3).map((item: any) => (
              <article key={item.investigation_identifier}>
                <strong>{item.investigation_identifier}</strong>
                <span>{item.investigation_question ?? "Question not recorded"}</span>
                <small>{item.status ?? "Status not recorded"}</small>
              </article>
            ))}
            {(data.evidence ?? []).slice(0, 3).map((item: any) => (
              <article key={item.evidence_identifier}>
                <strong>{item.evidence_identifier}</strong>
                <span>{item.title ?? "Evidence title not recorded"}</span>
                <small>{item.reliability_status ?? "Reliability not recorded"}</small>
              </article>
            ))}
          </div>
        </div>
      </div>
      <ul className="limitations">
        {(data.limitations ?? []).map((item: string) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
