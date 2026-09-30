import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "../../app/api";

export function PlatformAdministrationAudit() {
  const [rows, setRows] = useState<any[]>([]);
  const [retention, setRetention] = useState<any>(null);
  const [message, setMessage] = useState("");
  useEffect(() => {
    Promise.all([api<any[]>("/api/v1/admin/audit-history"), api<any>("/api/v1/admin/retention-status")])
      .then(([events, status]) => {
        setRows(events);
        setRetention(status);
      })
      .catch((error) => setMessage(error.message));
  }, []);
  return (
    <div className="content governance-view">
      <section className="panel">
        <div className="section-title">
          <ShieldCheck size={18} /> Recent platform administration activity
        </div>
        <p>Server-recorded changes with actor, request metadata, reason, and before/after values.</p>
        <div className="audit-actions">
          <a className="secondary-link" href="/api/v1/admin/audit-history/export?output_format=CSV">
            Export CSV
          </a>
          <a className="secondary-link" href="/api/v1/admin/audit-history/export?output_format=JSON">
            Export JSON
          </a>
          <a className="primary-action" href="/api/v1/stage3/compliance-report?output_format=PDF">
            Download evidence package
          </a>
        </div>
        {retention && (
          <div className={`retention-banner ${retention.status === "HEALTHY" ? "healthy" : "attention"}`}>
            <strong>{retention.policy}</strong>
            <span>
              {retention.total_events} events · {retention.expired} expired · {retention.expiring_within_30_days}{" "}
              expiring within 30 days
            </span>
          </div>
        )}
        {message && <p className="field-error">{message}</p>}
        {rows.map((row) => (
          <div className="audit-row" key={String(row.id)}>
            <strong>{row.action}</strong>
            <span>
              {row.entity_type ?? "Configuration"} · {row.actor_ref ?? "System"}
            </span>
            <small>
              {row.created_at ? String(row.created_at).slice(0, 19).replace("T", " ") : "Server recorded"}
              {row.source_ip ? ` · ${row.source_ip}` : ""}
            </small>
          </div>
        ))}
        {!rows.length && !message && <p>No platform administration activity recorded.</p>}
      </section>
    </div>
  );
}
