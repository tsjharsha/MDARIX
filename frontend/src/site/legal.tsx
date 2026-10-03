import { useEffect, useState } from "react";
import { ArrowRight, Mail, MapPin } from "lucide-react";
import { Markdown } from "./markdown";

/*
 * Company details and legal documents come from the server (backend/app/site_info.py), so they are set once in the
 * server configuration and the lawyer's approved files can change without a new release (legal/README.md).
 */

export type SiteInfo = {
  company_name: string | null;
  company_address: string | null;
  support_email: string | null;
  privacy_email: string | null;
  legal_text_approved: boolean;
  trial: { days: number; users: number; rows: number; data_deleted_after_days: number };
};

let siteInfoRequest: Promise<SiteInfo | null> | null = null;

function loadSiteInfo(): Promise<SiteInfo | null> {
  siteInfoRequest ??= fetch("/api/v1/public/site-info", { headers: { Accept: "application/json" } })
    .then((response) => (response.ok ? (response.json() as Promise<SiteInfo>) : null))
    .catch(() => null)
    .then((info) => {
      if (!info) siteInfoRequest = null; // try again on the next page rather than caching a failure
      return info;
    });
  return siteInfoRequest;
}

export function useSiteInfo(): SiteInfo | null {
  const [info, setInfo] = useState<SiteInfo | null>(null);
  useEffect(() => {
    let active = true;
    loadSiteInfo().then((value) => active && setInfo(value));
    return () => {
      active = false;
    };
  }, []);
  return info;
}

export const LEGAL_PAGES = {
  "/privacy": { document: "privacy", title: "Privacy policy" },
  "/terms": { document: "terms", title: "Terms of service" },
  "/trial-agreement": { document: "trial-agreement", title: "Free trial agreement" },
} as const;
export type LegalPath = keyof typeof LEGAL_PAGES;

function EmailLink({ address }: { address: string }) {
  return <a href={`mailto:${address}`}>{address}</a>;
}

export function LegalDocumentPage({ path }: { path: LegalPath }) {
  const { document, title } = LEGAL_PAGES[path];
  const info = useSiteInfo();
  const [state, setState] = useState<{ status: "LOADING" | "READY" | "PENDING"; markdown?: string }>({
    status: "LOADING",
  });
  useEffect(() => {
    let active = true;
    setState({ status: "LOADING" });
    fetch(`/api/v1/public/legal/${document}`, { headers: { Accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { available?: boolean; markdown?: string | null } | null) => {
        if (!active) return;
        if (body?.available && body.markdown) setState({ status: "READY", markdown: body.markdown });
        else setState({ status: "PENDING" });
      })
      .catch(() => active && setState({ status: "PENDING" }));
    return () => {
      active = false;
    };
  }, [document]);
  const contact = info?.privacy_email ?? info?.support_email;
  return (
    <article className="ms-section ms-legal" aria-labelledby="legal-title">
      <span className="ms-eyebrow">Legal</span>
      <h1 id="legal-title">{title}</h1>
      {state.status === "LOADING" && <p className="ms-legal-note">Loading…</p>}
      {state.status === "PENDING" && (
        <p className="ms-legal-note" role="status">
          This document is being finalized and will be published here before any customer data is processed.
          {contact ? (
            <>
              {" "}
              Questions in the meantime: <EmailLink address={contact} />.
            </>
          ) : null}
        </p>
      )}
      {state.status === "READY" && state.markdown && (
        <div className="ms-legal-body">
          <Markdown source={state.markdown} />
        </div>
      )}
      <LegalLinks current={path} />
    </article>
  );
}

function LegalLinks({ current }: { current: string }) {
  const links: [string, string][] = [
    ["/privacy", "Privacy policy"],
    ["/terms", "Terms of service"],
    ["/trial-agreement", "Free trial agreement"],
    ["/security", "Security"],
    ["/contact", "Contact"],
  ];
  return (
    <nav className="ms-legal-links" aria-label="Legal and company">
      {links
        .filter(([href]) => href !== current)
        .map(([href, label]) => (
          <a key={href} href={href}>
            {label}
          </a>
        ))}
    </nav>
  );
}

// Each statement here is true of the product today (legal/README.md lists what is not offered).
const SECURITY_SECTIONS: { title: string; points: string[] }[] = [
  {
    title: "Your data stays in your organization",
    points: [
      "Every organization's records are separated in the database by row-level security, so one customer's queries cannot read another's data.",
      "Each person sees only what their role allows, and administrators manage access for their own organization.",
    ],
  },
  {
    title: "Signing in",
    points: [
      "Passwords are at least 12 characters, checked against known breached passwords, and stored only as salted scrypt hashes.",
      "Authenticator-app two-factor sign-in (MFA). Single sign-on (OIDC/SAML) is planned and not offered yet.",
      "Repeated failed sign-ins are slowed down and then locked; sessions end after 30 minutes without activity.",
      "Changing or resetting a password signs out every other session.",
    ],
  },
  {
    title: "Data in transit and at rest",
    points: [
      "All traffic uses TLS, including the connection to the database.",
      "Authenticator secrets and connector credentials are encrypted before they are stored.",
      "Every uploaded file is scanned for malware before it is accepted, and files over the size limit are refused.",
      "Encrypted backups are taken daily and copied off-site, and restoring them is tested.",
    ],
  },
  {
    title: "Accountability",
    points: [
      "An append-only audit trail records who did what and when, and electronic signatures record the signer, meaning and time.",
      "AI suggestions are advisory: they show the evidence they used, flag what could not be verified, and a person makes every decision.",
      "In production, AI processing uses only providers under a contract that forbids training on your data, or models we host ourselves.",
    ],
  },
];

export function SecurityPage() {
  const info = useSiteInfo();
  return (
    <article className="ms-section ms-legal" aria-labelledby="security-title">
      <span className="ms-eyebrow">Trust</span>
      <h1 id="security-title">Security at MDARIX</h1>
      <p className="ms-legal-lead">
        How MDARIX protects the quality, complaint and supplier records you investigate. MDARIX does not hold ISO 27001
        or SOC 2 certification yet and is not a validated (GxP) system; we are glad to answer security questionnaires
        for a pilot.
      </p>
      <div className="ms-legal-body">
        {SECURITY_SECTIONS.map((section) => (
          <section key={section.title}>
            <h2>{section.title}</h2>
            <ul>
              {section.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          </section>
        ))}
        <section>
          <h2>Reporting a security issue</h2>
          <p>
            {info?.support_email ? (
              <>
                Please email <EmailLink address={info.support_email} /> with the details.
              </>
            ) : (
              "Please use the contact page to reach us with the details."
            )}
          </p>
        </section>
      </div>
      <LegalLinks current="/security" />
    </article>
  );
}

export function ContactPage() {
  const info = useSiteInfo();
  return (
    <article className="ms-section ms-legal" aria-labelledby="contact-page-title">
      <span className="ms-eyebrow">Company</span>
      <h1 id="contact-page-title">Contact MDARIX</h1>
      <p className="ms-legal-lead">Questions about a trial, becoming a design partner, your account or your data.</p>
      <div className="ms-contact-grid">
        {info?.support_email && (
          <div className="ms-card">
            <Mail size={20} aria-hidden="true" />
            <strong>Support and sales</strong>
            <EmailLink address={info.support_email} />
          </div>
        )}
        {info?.privacy_email && (
          <div className="ms-card">
            <Mail size={20} aria-hidden="true" />
            <strong>Privacy and data requests</strong>
            <EmailLink address={info.privacy_email} />
          </div>
        )}
        {(info?.company_name || info?.company_address) && (
          <div className="ms-card">
            <MapPin size={20} aria-hidden="true" />
            <strong>{info.company_name ?? "Postal address"}</strong>
            {info.company_address && <span>{info.company_address}</span>}
          </div>
        )}
      </div>
      <div className="ms-cta-row">
        <a className="ms-btn ms-btn-primary" href="/request-demo">
          Request a demo <ArrowRight size={16} aria-hidden="true" />
        </a>
        <a className="ms-btn ms-btn-outline" href="/signup">
          Start free trial
        </a>
      </div>
      <LegalLinks current="/contact" />
    </article>
  );
}

export function NotFoundPage() {
  return (
    <section className="ms-section ms-legal ms-not-found" aria-labelledby="not-found-title">
      <span className="ms-eyebrow">404</span>
      <h1 id="not-found-title">Page not found</h1>
      <p className="ms-legal-lead">The page you asked for does not exist or has moved.</p>
      <div className="ms-cta-row">
        <a className="ms-btn ms-btn-primary" href="/">
          Go to the home page
        </a>
        <a className="ms-btn ms-btn-outline" href="/signin">
          Sign in
        </a>
        <a className="ms-btn ms-btn-outline" href="/contact">
          Contact us
        </a>
      </div>
    </section>
  );
}
