import { useEffect, useState } from "react";
import { requestJson } from "../../app/apiClient";

type DocumentRow = {
  id: string;
  document_identifier: string;
  document_type: string;
  title: string;
  status: string;
  current_version: number;
  lock_version: number;
};
type DocumentDetail = {
  document: DocumentRow;
  versions: Array<{ id: string; version: number; status: string; content: any; citations: any; created_at: string }>;
};

const templates = ["ESTAR_510K", "GSPR", "CER", "IFU"];

export function RegulatoryCopilot() {
  const [template, setTemplate] = useState("GSPR");
  const [identifier, setIdentifier] = useState("");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("Paste licensed source excerpt or evidence reference here…");
  const [claim, setClaim] = useState("");
  const [rows, setRows] = useState<DocumentRow[]>([]);
  const [selected, setSelected] = useState<DocumentDetail | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      setRows(await requestJson<DocumentRow[]>("/api/v1/regulatory/documents"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Regulatory documents unavailable.");
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const open = async (id: string) => {
    try {
      setSelected(await requestJson<DocumentDetail>(`/api/v1/regulatory/documents/${id}`));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Document unavailable.");
    }
  };
  const generate = async () => {
    if (!identifier.trim() || !claim.trim()) {
      setMessage("Document identifier and at least one claim are required.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await requestJson("/api/v1/regulatory/draft", {
        method: "POST",
        body: JSON.stringify({
          document_type: template,
          document_identifier: identifier,
          title,
          claims: [{ claim_id: "claim-1", text: claim }],
          citations: [],
          authoring_sections: {},
          change_reason: "Regulatory co-pilot draft",
        }),
      });
      setMessage("Draft created. Every uncited statement is marked UNKNOWN and requires human validation.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Draft could not be created.");
    } finally {
      setBusy(false);
    }
  };
  const transition = async (status: string) => {
    if (!selected) return;
    try {
      await requestJson(`/api/v1/regulatory/documents/${selected.document.id}/status`, {
        method: "POST",
        body: JSON.stringify({
          status,
          expected_lock_version: selected.document.lock_version,
          reason: `Human validation: ${status}`,
        }),
      });
      setMessage(`Document moved to ${status}.`);
      await open(selected.document.id);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Status change failed.");
    }
  };
  return (
    <div className="content governance-view regulatory-copilot">
      <section className="governance-hero">
        <div>
          <span className="eyebrow">Regulatory intelligence · advisory workspace</span>
          <h1>Regulatory co-pilot</h1>
          <p>
            Prepare reviewable evidence drafts for eSTAR, GSPR, CER, and IFU workflows. MDARIX does not provide
            regulatory advice or submit dossiers.
          </p>
        </div>
        <span className="platform-admin-badge warning">Human validation required</span>
      </section>
      <section className="panel regulatory-toolbar">
        <label>
          Template
          <select value={template} onChange={(event) => setTemplate(event.target.value)}>
            {templates.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          Document identifier
          <input
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            placeholder="CER-PRODUCT-001"
          />
        </label>
        <label>
          Title
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Controlled preparation title"
          />
        </label>
        <button className="primary-action" disabled={busy} onClick={() => void generate()}>
          {busy ? "Generating…" : "Generate draft"}
        </button>
      </section>
      <section className="regulatory-split">
        <article className="panel">
          <div className="section-title">Source documents and provenance</div>
          <p className="muted">
            Use official-source links or customer-provided licensed excerpts. Source material remains authoritative and
            is never silently rewritten.
          </p>
          <textarea
            aria-label="Source document excerpt"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            rows={14}
          />
          <div className="advisory-box">
            <strong>Citation rule</strong>
            <span>
              Each supported statement must carry a verified source, clause, and direct official link. Uncited
              statements remain UNKNOWN.
            </span>
          </div>
        </article>
        <article className="panel">
          <div className="section-title">AI drafting workspace</div>
          <label>
            Draft claim
            <textarea
              aria-label="Draft claim"
              value={claim}
              onChange={(event) => setClaim(event.target.value)}
              rows={5}
              placeholder="Enter a bounded evidence statement…"
            />
          </label>
          <div className="regulatory-review-card">
            <strong>Inline review controls</strong>
            <span>Review citation · Mark unsupported · Request evidence · Accept for human review</span>
            <small>Confidence is server-derived; it is not a probability of regulatory acceptance.</small>
          </div>
          {message && (
            <p role="status" className="state-panel">
              {message}
            </p>
          )}
        </article>
      </section>
      <section className="panel">
        <div className="section-title">Versioned drafts and approval history</div>
        {selected ? (
          <div className="regulatory-detail">
            <button className="secondary-link" onClick={() => setSelected(null)}>
              ← Back to drafts
            </button>
            <h2>{selected.document.title || selected.document.document_type}</h2>
            <p>
              {selected.document.document_identifier} · version {selected.document.current_version} ·{" "}
              {selected.document.status}
            </p>
            <div className="toolbar">
              <button onClick={() => void transition("IN_REVIEW")}>Submit for human review</button>
              <button onClick={() => void transition("APPROVED")}>Approve / sign</button>
              <button onClick={() => void transition("ARCHIVED")}>Archive</button>
            </div>
            {selected.versions.map((version) => (
              <article className="regulatory-version" key={version.id}>
                <strong>
                  Version {version.version} · {version.status}
                </strong>
                <span>{version.created_at}</span>
                <pre>{JSON.stringify(version.content, null, 2)}</pre>
                <details>
                  <summary>Verified citations and provenance</summary>
                  <pre>{JSON.stringify(version.citations, null, 2)}</pre>
                </details>
              </article>
            ))}
          </div>
        ) : (
          <div className="regulatory-document-list">
            {rows.map((row) => (
              <button key={row.id} onClick={() => void open(row.id)}>
                <strong>{row.title || row.document_type}</strong>
                <span>
                  {row.document_identifier} · v{row.current_version} · {row.status}
                </span>
              </button>
            ))}
            {!rows.length && <p className="muted">No regulatory drafts yet.</p>}
          </div>
        )}
      </section>
    </div>
  );
}
