import { useEffect, useState } from "react";
import { UserPlus, X } from "lucide-react";
import { CreateCustomer } from "../CreateCustomer";
import { DemoRequestsWorkspace } from "../DemoRequestsWorkspace";
import { TrialFeedbackWorkspace } from "../TrialFeedbackWorkspace";
import { TrialRequestsWorkspace } from "../TrialRequestsWorkspace";
import { CustomerAdmins } from "./CustomerAdmins";
import { CustomerDirectory } from "./CustomerDirectory";
import { CustomerPage } from "./CustomerPage";
import type { Section } from "./model";
import { TenantDirectory, TenantPage } from "./TenantPages";
import { ColumnScopeProvider } from "../../tables/ColumnChooser";
import "../../customer-admin/customer-admin.css";
import "./customers.css";

type Open = { kind: "customer"; id: string } | { kind: "tenant"; id: string; from?: string } | null;

/**
 * The platform administrator's Customers & Tenants area: five sections instead of fourteen overlapping tabs.
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
    // Every list here lets the administrator choose the fields it shows.
    <ColumnScopeProvider scope="admin:Customers & Tenants">
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
            onOpenCustomer={(id) => setOpen({ kind: "customer", id })}
            onMessage={notify}
          />
        ) : section === "Customers" ? (
          <CustomerDirectory onOpen={(id) => setOpen({ kind: "customer", id })} />
        ) : section === "Customer administrators" ? (
          <CustomerAdmins onMessage={notify} />
        ) : section === "Tenants" ? (
          <TenantDirectory onOpen={(id) => setOpen({ kind: "tenant", id })} />
        ) : section === "Feedback" ? (
          <div className="cc-page">
            <div className="cc-title">
              <div>
                <p className="ac-eyebrow">Feedback</p>
                <h2>Trial feedback and website quotes</h2>
                <p className="ac-muted">
                  What trial users think of MDARIX. Publish a quote only where the person agreed; it is credited as they
                  chose.
                </p>
              </div>
            </div>
            <TrialFeedbackWorkspace />
          </div>
        ) : (
          <Onboarding onCreated={() => onSection("Customers")} />
        )}
      </div>
    </ColumnScopeProvider>
  );
}

function Onboarding({ onCreated }: { onCreated: () => void }) {
  const [creating, setCreating] = useState(false);
  return (
    <div className="cc-page">
      <div className="cc-title">
        <div>
          <p className="ac-eyebrow">Onboarding</p>
          <h2>New customers, demo and trial requests</h2>
          <p className="ac-muted">
            A new customer gets its first tenant, with a plan and the tenant&apos;s first Customer Administrator, who is
            invited by email. Further tenants are added from the customer&apos;s page.
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
        <>
          <DemoRequestsWorkspace />
          <TrialRequestsWorkspace />
        </>
      )}
    </div>
  );
}
