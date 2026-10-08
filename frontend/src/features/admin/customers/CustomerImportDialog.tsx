import { useState } from "react";
import { DialogBehaviour } from "../../shared/DialogBehaviour";
import { describeError, requestJson } from "../../../app/apiClient";

/** Import customers from a CSV file: a dry run shows what would be created, then the import runs. */
export function CustomerImportDialog({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [rows, setRows] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const parse = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      const lines = String(reader.result ?? "")
        .split(/\r?\n/)
        .filter(Boolean);
      if (lines.length < 2) return setError("CSV must include a header and at least one row.");
      const headers = lines[0].split(",").map((value) => value.trim());
      const parsed = lines
        .slice(1)
        .map((line) => {
          const values = line.split(",");
          return headers.reduce((row, header, index) => ({ ...row, [header]: values[index]?.trim() ?? "" }), {} as any);
        })
        .map((row) => ({
          company_name: row.company_name || row.name || row.legal_name,
          tenant_code: row.tenant_code || row.tenant_key,
          plan_code: row.plan_code || "ENTERPRISE_TEST",
          licensed_users_limit: Number(row.licensed_users_limit || 25),
          customer_admin_limit: Number(row.customer_admin_limit || 2),
          connector_limit: Number(row.connector_limit || 5),
          status: row.status || "active",
          notes: row.notes || undefined,
        }));
      if (parsed.some((row) => !row.company_name || !row.tenant_code))
        return setError("Each row requires company_name and tenant_code.");
      setError("");
      setRows(parsed);
    };
    reader.readAsText(file);
  };
  const submit = async (dryRun: boolean) => {
    setBusy(true);
    setError("");
    try {
      const result = await requestJson<any>("/api/v1/platform-admin/customers/import", {
        method: "POST",
        body: JSON.stringify({ rows, dry_run: dryRun }),
      });
      const rejected = (result.results ?? []).filter((row: any) => row.status === "REJECTED");
      if (rejected.length) setError(rejected.map((row: any) => `${row.tenant_code}: ${row.error}`).join("; "));
      else if (dryRun) setMessage(`${result.results?.length ?? 0} rows validated. Ready to import.`);
      else {
        setMessage(`${result.imported} customer${result.imported === 1 ? "" : "s"} imported.`);
        onImported();
      }
    } catch (reason) {
      setError(describeError(reason, "Customer import failed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="customer-import-dialog" role="dialog" aria-modal="true" aria-labelledby="customer-import-title">
      <DialogBehaviour onClose={onClose} />
      <div className="customer-import-panel">
        <div className="platform-admin-card-title">
          <div>
            <span className="eyebrow">Customer directory</span>
            <h3 id="customer-import-title">Import customers</h3>
            <p>Upload a CSV with company_name, tenant_code, plan_code, and optional license/seat columns.</p>
          </div>
          <button className="platform-admin-secondary" onClick={onClose}>
            Close
          </button>
        </div>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) parse(file);
          }}
        />
        {error && <div className="platform-admin-error">{error}</div>}
        {message && (
          <p className="platform-admin-status" role="status">
            {message}
          </p>
        )}
        {rows.length > 0 && (
          <>
            <p className="customer-import-summary">
              {rows.length} row{rows.length === 1 ? "" : "s"} ready for validation/import.
            </p>
            <div className="customer-import-preview">
              {rows.slice(0, 5).map((row, index) => (
                <div key={index}>
                  <strong>{row.company_name}</strong>
                  <span>
                    {row.tenant_code} · {row.plan_code}
                  </span>
                </div>
              ))}
            </div>
            <div className="customer-directory-actions">
              <button className="platform-admin-secondary" disabled={busy} onClick={() => submit(true)}>
                Validate import
              </button>
              <button className="platform-admin-primary" disabled={busy} onClick={() => submit(false)}>
                Import validated rows
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
