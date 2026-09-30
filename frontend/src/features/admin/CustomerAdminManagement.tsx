import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "../../app/api";

export function CustomerAdminManagement() {
  // The change was recorded in audit history.
  const [users, setUsers] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<any | null>(null);
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const load = () =>
    api<any[]>("/api/v1/admin/identity/users")
      .then(setUsers)
      .catch((error) => setMessage(error.message));
  useEffect(() => {
    load();
  }, []);
  const visible = users.filter(
    (user) =>
      String(user.role).toUpperCase() === "CUSTOMER_ADMIN" &&
      [user.email, user.display_name, user.company].some((value) =>
        String(value ?? "")
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
  );
  const updateEmail = async () => {
    if (!selected) return;
    const response = await fetch(`/api/v1/admin/control-plane/users/${selected.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: { email } }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message ?? "Email update failed");
    setMessage("Customer administrator email updated.");
    setSelected(null);
    load();
  };
  const retire = async () => {
    if (!selected || !confirm("Retire this customer administrator account?")) return;
    const response = await fetch(`/api/v1/admin/identity/users/${selected.id}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "OFFBOARDED" }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message ?? "Account retirement failed");
    setMessage("Customer administrator account retired; audit history was preserved.");
    setSelected(null);
    load();
  };
  const reactivate = async () => {
    if (!selected || !confirm("Reactivate this account and send a new activation email?")) return;
    const response = await fetch(`/api/v1/admin/identity/users/${selected.id}/reactivate`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail?.message ?? "Account reactivation failed");
    setMessage(
      result.email_delivery === "SENT"
        ? "Account reactivated and a new activation email was sent."
        : `Account reactivated. SMTP is not configured; development token: ${result.development_token ?? "not returned"}`,
    );
    setSelected(null);
    load();
  };
  return (
    <div className="content governance-view">
      <section className="panel">
        <div className="section-title">
          <ShieldCheck size={18} /> Manage Customer Administrators
        </div>
        <p>
          Search by customer name, administrator name, or email address. Email changes and account retirement are
          tenant-scoped and audited.
        </p>
        <input
          aria-label="Search customer administrators"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by customer name or email"
        />
        {message && (
          <p className="review-success" role="status">
            {message}
          </p>
        )}
        <div className="audit-row">
          <strong>Customer / Administrator</strong>
          <span>Email</span>
          <small>Status</small>
        </div>
        {visible.map((user) => (
          <div className="audit-row" key={user.id}>
            <strong>
              {user.company ?? "Customer"} — {user.display_name}
            </strong>
            <span>{user.email}</span>
            <small>
              {user.status}{" "}
              <button
                className="secondary-link"
                onClick={() => {
                  setSelected(user);
                  setEmail(user.email);
                }}
              >
                Manage
              </button>
            </small>
          </div>
        ))}
        {!visible.length && <p>No customer administrators match the search.</p>}
      </section>
      {selected && (
        <section className="panel admin-forms">
          <div className="section-title">Manage {selected.display_name}</div>
          <label>
            Account email
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <button className="primary-action" onClick={() => updateEmail().catch((error) => setMessage(error.message))}>
            Update email
          </button>
          {String(selected.status).toUpperCase() === "OFFBOARDED" ? (
            <button className="primary-action" onClick={() => reactivate().catch((error) => setMessage(error.message))}>
              Activate account and send email
            </button>
          ) : (
            <button className="secondary-link" onClick={() => retire().catch((error) => setMessage(error.message))}>
              Retire account
            </button>
          )}
        </section>
      )}
    </div>
  );
}
