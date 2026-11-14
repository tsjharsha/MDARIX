import { useState } from "react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { AiControlCenter } from "./AiControlCenter";
import { DataConfiguration } from "./DataConfiguration";
import { IdentityAccess } from "./IdentityAccess";
import { Integrations } from "./Integrations";
import { Operations } from "./Operations";
import { PlansLicensing } from "./PlansLicensing";
import { SecurityArea } from "./SecurityArea";
import {
  AREA_SECTIONS,
  DATA_AND_INTEGRATIONS,
  DATA_INTEGRATION_GUIDE,
  DATA_INTEGRATION_SECTIONS,
  DATA_SECTIONS,
  dataIntegrationStep,
} from "./sections";
import { ColumnScopeProvider } from "../../tables/ColumnChooser";
import "../../customer-admin/customer-admin.css";
import "../customers/customers.css";
import "./areas.css";

export const isAreaDomain = (domain: string) => domain in AREA_SECTIONS;

/** One of the platform administrator's areas (Plans & Licensing … Operations), showing the chosen section. */
export function AdminArea({
  domain,
  section,
  onSection,
}: {
  domain: string;
  section: string;
  /** Opens another section of the same area (the step guide's Previous and Next). */
  onSection?: (section: string) => void;
}) {
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const notify = (text: string, tone: "good" | "critical" = "good") => setMessage({ text, tone });
  const body =
    domain === "Plans & Licensing" ? (
      <PlansLicensing section={section} onMessage={notify} />
    ) : domain === DATA_AND_INTEGRATIONS ? (
      (DATA_SECTIONS as readonly string[]).includes(section) ? (
        <DataConfiguration section={section} onMessage={notify} />
      ) : (
        <Integrations section={section} />
      )
    ) : domain === "Identity & Access" ? (
      <IdentityAccess section={section} />
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
        {domain === DATA_AND_INTEGRATIONS && <StepGuide section={section} onSection={onSection} />}
        {body}
      </div>
    </ColumnScopeProvider>
  );
}

/** Where this step sits in setting up a customer's data, what it is for, and the steps either side. */
function StepGuide({ section, onSection }: { section: string; onSection?: (section: string) => void }) {
  const step = dataIntegrationStep(section);
  if (!step) return null;
  const previous = DATA_INTEGRATION_SECTIONS[step.number - 2];
  const next = DATA_INTEGRATION_SECTIONS[step.number];
  return (
    <div className="ar-step-guide">
      <p>
        <span className="ar-step-count">
          Step {step.number} of {step.total} · {step.stage}
        </span>{" "}
        {DATA_INTEGRATION_GUIDE[section]}
      </p>
      {onSection && (
        <span className="ar-step-nav">
          {previous && (
            <button type="button" className="ac-link" onClick={() => onSection(previous)}>
              <ArrowLeft size={14} aria-hidden="true" /> {previous}
            </button>
          )}
          {next && (
            <button type="button" className="ac-link" onClick={() => onSection(next)}>
              {next} <ArrowRight size={14} aria-hidden="true" />
            </button>
          )}
        </span>
      )}
    </div>
  );
}
