import { useState } from "react";
import { X } from "lucide-react";
import { AiControlCenter } from "./AiControlCenter";
import { DataConfiguration } from "./DataConfiguration";
import { IdentityAccess } from "./IdentityAccess";
import { Integrations } from "./Integrations";
import { Operations } from "./Operations";
import { PlansLicensing } from "./PlansLicensing";
import { SecurityArea } from "./SecurityArea";
import { AREA_SECTIONS } from "./sections";
import { ColumnScopeProvider } from "../../tables/ColumnChooser";
import "../../customer-admin/customer-admin.css";
import "../customers/customers.css";
import "./areas.css";

export const isAreaDomain = (domain: string) => domain in AREA_SECTIONS;

/** One of the platform administrator's areas (Plans & Licensing … Operations), showing the chosen section. */
export function AdminArea({ domain, section }: { domain: string; section: string }) {
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const notify = (text: string, tone: "good" | "critical" = "good") => setMessage({ text, tone });
  const body =
    domain === "Plans & Licensing" ? (
      <PlansLicensing section={section} onMessage={notify} />
    ) : domain === "Data & Configuration" ? (
      <DataConfiguration section={section} onMessage={notify} />
    ) : domain === "Identity & Access" ? (
      <IdentityAccess section={section} />
    ) : domain === "Integrations" ? (
      <Integrations section={section} />
    ) : domain === "AI Control Center" ? (
      <AiControlCenter section={section} />
    ) : domain === "Security" ? (
      <SecurityArea section={section} onMessage={notify} />
    ) : (
      <Operations section={section} />
    );
  return (
    // Every list in the area lets the administrator choose the fields it shows.
    <ColumnScopeProvider scope={`admin:${domain}`}>
      <div className="cc-area ar-area">
        {message && (
          <div className={`ac-message tone-${message.tone}`} role="status">
            {message.text}
            <button type="button" className="ac-link" onClick={() => setMessage(null)} aria-label="Dismiss message">
              <X size={14} />
            </button>
          </div>
        )}
        {body}
      </div>
    </ColumnScopeProvider>
  );
}
