import { useEffect, useState } from "react";
import { UserPlus, X } from "lucide-react";
import { CreateCustomer } from "../CreateCustomer";
import { TrialRequestsWorkspace } from "../TrialRequestsWorkspace";
import { CustomerAdmins } from "./CustomerAdmins";
import { CustomerDirectory } from "./CustomerDirectory";
import { CustomerPage } from "./CustomerPage";
import type { Section } from "./model";
import { TenantDirectory, TenantPage } from "./TenantPages";
import "../../customer-admin/customer-admin.css";
import "./customers.css";

type Open = { kind: "customer"; id: string } | { kind: "tenant"; id: string; from?: string } | null;

/**
 * The platform administrator's Customers & Tenants area: four sections instead of fourteen overlapping tabs.
 * A customer or tenant opens as one page; switching section always returns to that section's list.
 */
export function CustomersAndTenants({
  section,
  onSection,
}: {
  section: Section;
  onSection: (section: Section) => void;
}) {
  const [open, setOpen] = useState<Open>(null);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  // A record never stays open behind another section.
  useEffect(() => setOpen(null), [section]);
  const notify = (text: string, tone: "good" | "critical" = "good") => setMessage({ text, tone });

  return (
    <div className="cc-area">
      {message && (
        <div className={`ac-message tone-${message.tone}`} role="status">
          {message.text}
          <button type="button" className="ac-link" onClick={() => setMessage(null)} aria-label="Dismiss message">
            <X size={14} />
          </button>
        </div>
      )}
      {open?.kind === "customer" ? (
        <CustomerPage
          customerId={open.id}
          onBack={() => setOpen(null)}
          onOpenTenant={(id) => setOpen({ kind: "tenant", id, from: open.id })}
          onMessage={notify}
        />
      ) : open?.kind === "tenant" ? (
        <TenantPage
          tenantId={open.id}
          onBack={() => setOpen(open.from ? { kind: "customer", id: open.from } : null)}
          onMessage={notify}
        />
      ) : section === "Customers" ? (
        <CustomerDirectory
          onOpen={(row) =>
            row.customer_id
              ? setOpen({ kind: "customer", id: row.customer_id })
              : setOpen({ kind: "tenant", id: row.id })
          }
        />
      ) : section === "Customer administrators" ? (
        <CustomerAdmins onMessage={notify} />
      ) : section === "Tenants" ? (
        <TenantDirectory onOpen={(id) => setOpen({ kind: "tenant", id })} />
      ) : (
        <Onboarding onCreated={() => onSection("Customers")} />
      )}
    </div>
  );
}

function Onboarding({ onCreated }: { onCreated: () => void }) {
  const [creating, setCreating] = useState(false);
  return (
    <div className="cc-page">
      <div className="cc-title">
        <div>
          <p className="ac-eyebrow">Onboarding</p>
          <h2>New customers and trial requests</h2>
          <p className="ac-muted">
            A new customer gets its tenant, plan and first Customer Administrator, who is invited by email.
          </p>
        </div>
        {!creating && (
          <button type="button" className="ac-primary" onClick={() => setCreating(true)}>
            <UserPlus size={16} aria-hidden="true" /> New customer
          </button>
        )}
      </div>
      {creating ? (
        <section className="cc-wizard" aria-label="New customer">
          <button type="button" className="ac-link" onClick={() => setCreating(false)}>
            <X size={14} aria-hidden="true" /> Close
          </button>
          <CreateCustomer onCreated={onCreated} />
        </section>
      ) : (
        <TrialRequestsWorkspace />
      )}
    </div>
  );
}
