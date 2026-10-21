import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { CreateCustomer } from "../CreateCustomer";
import { TrialFeedbackWorkspace } from "../TrialFeedbackWorkspace";
import { CustomerDirectory } from "./CustomerDirectory";
import { CustomerPage } from "./CustomerPage";
import type { Section } from "./model";
import { TenantDirectory, TenantPage } from "./TenantPages";
import { TrialsOverview } from "./TrialsOverview";
import { SupportWorkspace } from "./SupportWorkspace";
import { ColumnScopeProvider } from "../../tables/ColumnChooser";
import "../../customer-admin/customer-admin.css";
import "./customers.css";

type Open =
  | { kind: "customer"; id: string }
  | { kind: "tenant"; id: string; from?: string }
  // The read-only support workspace of a trial (opened from Trials, under the access its owner approved).
  | { kind: "workspace"; id: string }
  | null;

/**
 * The platform administrator's Customers & Tenants area: the customer and tenant records, the free trials and how far
 * into the story each went, and trial feedback. A
 * customer or tenant opens as one page; switching section always returns to that section's list. People's requests
 * (demo and trial requests) and every kind of account are under Identity & Access.
 */
export function CustomersAndTenants({
  section,
  onSection,
  startCreating = false,
  onCreatingStarted,
}: {
  section: Section;
  onSection: (section: Section) => void;
  /** Open the new-customer wizard straight away (the dashboard's "New customer"). */
  startCreating?: boolean;
  onCreatingStarted?: () => void;
}) {
  const [open, setOpen] = useState<Open>(null);
  const [creating, setCreating] = useState(startCreating);
  useEffect(() => {
    if (!startCreating) return;
    setCreating(true);
    onCreatingStarted?.();
  }, [startCreating, onCreatingStarted]);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  // A record (or the new-customer wizard) never stays open behind another section.
  useEffect(() => {
    setOpen(null);
    if (section !== "Customers") setCreating(false);
  }, [section]);
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
            backLabel={open.from ? "Back to customer" : "All tenants"}
            onBack={() => setOpen(open.from ? { kind: "customer", id: open.from } : null)}
            onOpenCustomer={(id) => setOpen({ kind: "customer", id })}
            onMessage={notify}
          />
        ) : open?.kind === "workspace" ? (
          <SupportWorkspace tenantId={open.id} onBack={() => setOpen(null)} onMessage={notify} />
        ) : section === "Customers" && creating ? (
          <NewCustomer
            onClose={() => setCreating(false)}
            onCreated={(customerId) => {
              setCreating(false);
              // Open the new customer's page; without its id, return to the directory.
              if (customerId) setOpen({ kind: "customer", id: customerId });
              else onSection("Customers");
            }}
          />
        ) : section === "Customers" ? (
          <CustomerDirectory onOpen={(id) => setOpen({ kind: "customer", id })} onCreate={() => setCreating(true)} />
        ) : section === "Tenants" ? (
          <TenantDirectory onOpen={(id) => setOpen({ kind: "tenant", id })} />
        ) : section === "Trials" ? (
          <TrialsOverview
            onOpenTenant={(id) => setOpen({ kind: "tenant", id })}
            onOpenWorkspace={(id) => setOpen({ kind: "workspace", id })}
          />
        ) : (
          <div className="cc-page">
            <div className="cc-title">
              <div>
                <p className="ac-eyebrow">Feedback</p>
                <h2>Trial feedback and website quotes</h2>
              </div>
            </div>
            <TrialFeedbackWorkspace />
          </div>
        )}
      </div>
    </ColumnScopeProvider>
  );
}

/** A new customer with its first tenant, plan and Customer Administrator (invited by email). */
function NewCustomer({ onClose, onCreated }: { onClose: () => void; onCreated: (customerId?: string) => void }) {
  return (
    <div className="cc-page">
      <div className="cc-title">
        <div>
          <p className="ac-eyebrow">Customers</p>
          <h2>New customer</h2>
          <p className="ac-muted">
            A new customer gets its first tenant, with a plan and the tenant&apos;s first Customer Administrator, who is
            invited by email. Further tenants are added from the customer&apos;s page.
          </p>
        </div>
      </div>
      <section className="cc-wizard" aria-label="New customer">
        <button type="button" className="ac-link" onClick={onClose}>
          <X size={14} aria-hidden="true" /> Close
        </button>
        <CreateCustomer onCreated={onCreated} />
      </section>
    </div>
  );
}
