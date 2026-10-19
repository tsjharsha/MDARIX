import { useEffect, useState } from "react";
import { ArrowRight, Mail, MapPin } from "lucide-react";
import { Markdown } from "./markdown";
import { DEMO_REQUESTS_OFFERED } from "./offer";

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
  trial: {
    days: number;
    users: number;
    rows: number;
    data_deleted_after_days: number;
    /** Personal and disposable mail domains: a person reviews these requests (backend/app/trial/auto_approval.py). */
    free_mail_domains?: string[];
  };
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

/** The site details as a page waits for them: still loading, answered, or not reachable. */
export type SiteInfoState = { status: "loading" } | { status: "ready"; info: SiteInfo } | { status: "failed" };

export function useSiteInfoState(): SiteInfoState {
  const [state, setState] = useState<SiteInfoState>({ status: "loading" });
  useEffect(() => {
    let active = true;
    loadSiteInfo().then((info) => active && setState(info ? { status: "ready", info } : { status: "failed" }));
    return () => {
      active = false;
    };
  }, []);
  return state;
}

/** The addresses the approved legal texts publish (legal/privacy.md, terms.md, trial-agreement.md), shown when the
 * server cannot be reached. */
export const PUBLISHED_CONTACT = { support: "support@mdarix.in", privacy: "privacy@mdarix.in" } as const;

/** What the contact page shows: nothing while loading; the server's addresses once it answers, with the "being
 * configured" notice only when it has neither; the published addresses when it cannot be reached. */
export function contactAddresses(state: SiteInfoState): {
  support: string | null;
  privacy: string | null;
  notice: boolean;
} {
  if (state.status === "loading") return { support: null, privacy: null, notice: false };
  if (state.status === "failed") return { ...PUBLISHED_CONTACT, notice: false };
  const support = state.info.support_email?.trim() || null;
  const privacy = state.info.privacy_email?.trim() || null;
  return { support, privacy, notice: !support && !privacy };
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

const LEGAL_SUMMARIES: Record<LegalPath, { intro: string; sections: { title: string; body: string }[] }> = {
  "/privacy": {
    intro:
      "This page explains how MDARIX handles website, trial, account, security, and customer-submitted investigation data.",
    sections: [
      {
        title: "What we collect",
        body: "We collect information needed to respond to trial requests, operate accounts, protect the service, maintain audit history, and provide customer-requested investigation workflows.",
      },
      {
        title: "Customer content",
        body: "Customer quality, complaint, product, supplier, and investigation content is processed to provide the service and remains subject to the customer agreement and configured access controls.",
      },
      {
        title: "AI and human review",
        body: "AI features are advisory. They may process authorized context when enabled, but AI output is not a verified fact, regulatory conclusion, or human decision.",
      },
      {
        title: "Retention and rights",
        body: "Retention, deletion, export, legal holds, and data requests follow the applicable customer agreement and approved retention schedule. Trial requests that do not lead to a trial lose the requester's name, email address, job title and phone number 90 days after we decline them or after the invitation expires unused. Contact MDARIX for privacy questions.",
      },
    ],
  },
  "/terms": {
    intro:
      "These terms describe the permitted use of the MDARIX product-investigation platform by organizations and their authorized users.",
    sections: [
      {
        title: "The service",
        body: "MDARIX connects product, complaint, supplier, evidence, investigation, and human-review workflows. Availability and included capabilities depend on the applicable order or trial arrangement.",
      },
      {
        title: "Your responsibilities",
        body: "Customers control their users, permissions, connected systems, and submitted content. Users must not access another organization’s data, bypass security controls, or upload malicious content.",
      },
      {
        title: "Human decisions",
        body: "MDARIX and its AI features support investigation work. Authorized customer personnel remain responsible for quality, regulatory, safety, and product decisions.",
      },
      {
        title: "Data and security",
        body: "Customer content is used to provide and secure the service. Access is tenant-scoped, activity is audited, and production commitments are governed by the signed customer agreement.",
      },
    ],
  },
  "/trial-agreement": {
    intro:
      "The free trial lets an invited organization evaluate MDARIX with synthetic or non-sensitive data before deciding whether to proceed.",
    sections: [
      {
        title: "Trial scope",
        body: "A trial is limited by the invitation, plan, seat, and data allowances shown at activation. Features may be limited, AI features are off during the product validation phase, and the environment is intended for evaluation.",
      },
      {
        title: "Use safe evaluation data",
        body: "Use synthetic data or data that does not identify patients during a trial. Do not upload patient-identifiable or regulated production records unless a separate written arrangement permits it.",
      },
      {
        title: "AI and decisions",
        body: "AI output is advisory and requires human review. The trial does not replace a customer’s quality system, regulatory process, validation, or approval controls.",
      },
      {
        title: "End of trial",
        body: "Trial access ends on the date shown in the invitation or workspace. Trial data is handled according to the applicable retention notice and agreement; contact MDARIX before expiry if you need an export or extension.",
      },
    ],
  },
};

function EmailLink({ address }: { address: string }) {
  return <a href={`mailto:${address}`}>{address}</a>;
}

export type LegalDocumentState = { status: "LOADING" | "READY" | "PENDING" | "ERROR"; markdown?: string };

/** What the legal text request answered: the text, "not provided yet" (the server says `available: false`), or
 * an error (no answer, or not a readable one). Only the server's own "not provided" shows the pending summary: a
 * failed request never suggests the published texts are unapproved. */
export function legalDocumentState(
  response: { ok: boolean } | null,
  body: { available?: boolean; markdown?: string | null } | null,
): LegalDocumentState {
  if (!response?.ok || body === null || typeof body !== "object") return { status: "ERROR" };
  if (body.available && body.markdown) return { status: "READY", markdown: body.markdown };
  if (body.available === false) return { status: "PENDING" };
  return { status: "ERROR" };
}

export function LegalDocumentPage({ path }: { path: LegalPath }) {
  const { document } = LEGAL_PAGES[path];
  const info = useSiteInfo();
  const [state, setState] = useState<LegalDocumentState>({ status: "LOADING" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setState({ status: "LOADING" });
    fetch(`/api/v1/public/legal/${document}`, { headers: { Accept: "application/json" } })
      .then(async (response) => {
        const body = response.ok ? await response.json().catch(() => null) : null;
        if (active) setState(legalDocumentState(response, body));
      })
      .catch(() => active && setState({ status: "ERROR" }));
    return () => {
      active = false;
    };
  }, [document, attempt]);
  return (
    <LegalDocumentView
      path={path}
      state={state}
      contact={info?.privacy_email ?? info?.support_email ?? null}
      onRetry={() => setAttempt((count) => count + 1)}
    />
  );
}

/** A legal page in one of its states (exported for its test). */
export function LegalDocumentView({
  path,
  state,
  contact,
  onRetry,
}: {
  path: LegalPath;
  state: LegalDocumentState;
  contact: string | null;
  onRetry: () => void;
}) {
  const { title } = LEGAL_PAGES[path];
  // When the request failed the server's addresses may be unknown too: the ones the published texts give.
  const writeTo = contact ?? PUBLISHED_CONTACT.privacy;
  return (
    <article className="ms-section ms-legal" aria-labelledby="legal-title">
      <span className="ms-eyebrow">Legal</span>
      <h1 id="legal-title">{title}</h1>
      {state.status === "LOADING" && <p className="ms-legal-note">Loading…</p>}
      {state.status === "ERROR" && (
        <div className="ms-legal-notice ms-legal-error" role="alert">
          <strong>The {title.toLowerCase()} could not be loaded</strong>
          <span>
            This is a problem reaching MDARIX, not a change to the document. Please try again, or write to{" "}
            <EmailLink address={writeTo} /> and we will send you the text.
          </span>
          <span className="ms-cta-row">
            <button type="button" className="ms-btn ms-btn-primary" onClick={onRetry}>
              Try again
            </button>
            <a className="ms-btn ms-btn-outline" href={`mailto:${writeTo}?subject=${encodeURIComponent(title)}`}>
              Email us for the text
            </a>
          </span>
        </div>
      )}
      {state.status === "PENDING" && (
        <>
          <div className="ms-legal-notice" role="status">
            <strong>Information page — formal legal text pending approval</strong>
            <span>
              This summary is provided for product orientation only and is not a substitute for the approved agreement.
            </span>
          </div>
          <p className="ms-legal-lead">{LEGAL_SUMMARIES[path].intro}</p>
          <div className="ms-legal-body ms-legal-summary">
            {LEGAL_SUMMARIES[path].sections.map((section) => (
              <section key={section.title}>
                <h2>{section.title}</h2>
                <p>{section.body}</p>
              </section>
            ))}
          </div>
          {contact && (
            <p className="ms-legal-note">
              Questions about the formal document: <EmailLink address={contact} />.
            </p>
          )}
        </>
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
    ["/accessibility", "Accessibility"],
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
      "Every file MDARIX stores, such as evidence attachments, is scanned for malware before it is stored, and files over the size limit are refused. Imported CSV and Excel files are read as data only and are not stored; workbooks with macros are refused.",
      "During the validation phase the database runs on MDARIX's own server in Mumbai. It is backed up every day: an encrypted copy goes to Delhi, and a daily snapshot of the server's disk is kept in Mumbai. Restoring follows a written, rehearsed procedure.",
    ],
  },
  {
    title: "Accountability",
    points: [
      "An append-only audit trail records who did what and when; each event is hash-chained to the one before it and verified daily, so any change to history is detected. Electronic signatures record the signer, meaning and time.",
      "AI suggestions are advisory: they show the evidence they used, flag what could not be verified, and a person makes every decision. AI is off until an organization's administrator switches it on, and it stays off in free trials during the product validation phase.",
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

// What was done and what is known to fall short, as tested; no conformance is claimed (CMP-16). Engineering keeps it
// current: a fixed gap leaves the list, and the date changes.
export const ACCESSIBILITY_UPDATED = "19 October 2026";
const ACCESSIBILITY_DONE = [
  "Every page can be used with a keyboard, shows where the focus is, and starts with a link that skips to the content.",
  "Form fields on the website have visible labels, and required fields are marked.",
  "Diagrams and animated scenes carry a text description, and animations stop when your device asks for reduced motion.",
  "Body text was checked for colour contrast on the main pages, and an automated accessibility check (axe) runs on the home page in our tests.",
  "The website was reviewed at phone, laptop and desktop widths. Each page declares its language and has one main heading and its own title.",
];
const ACCESSIBILITY_GAPS = [
  "The menus in the website header: after a menu is opened with the keyboard, the Tab key moves to the next menu instead of into the open menu. Its links are reached after the rest of the header; Escape closes it.",
  "On the light header, the focus outline has low contrast, and the skip link shows as a thin dark line at the top-left of each page.",
  "The legal pages skip a heading level (from the page title straight to the third level).",
  "The videos have English captions as part of the picture: they cannot be switched off or resized, and there is no separate transcript yet.",
  "A few small labels, such as the video durations, are close to the minimum contrast.",
  "The signed-in application has not been reviewed as fully as the website.",
];

export function AccessibilityPage() {
  const info = useSiteInfo();
  const address = info?.support_email ?? PUBLISHED_CONTACT.support;
  return (
    <article className="ms-section ms-legal" aria-labelledby="accessibility-title">
      <span className="ms-eyebrow">Legal</span>
      <h1 id="accessibility-title">Accessibility statement</h1>
      <p className="ms-legal-lead">
        We want everyone to be able to use the MDARIX website and the MDARIX application. We use the Web Content
        Accessibility Guidelines (WCAG) 2.2, level AA, as our guide. MDARIX has not been audited against them and we do
        not claim that it conforms.
      </p>
      <div className="ms-legal-body">
        <p>Last updated: {ACCESSIBILITY_UPDATED}</p>
        <section>
          <h2>What we have done</h2>
          <ul>
            {ACCESSIBILITY_DONE.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>
        <section>
          <h2>Known gaps</h2>
          <p>We know of these problems and are working on them:</p>
          <ul>
            {ACCESSIBILITY_GAPS.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>
        <section>
          <h2>Tell us about a problem</h2>
          <p>
            If something on the website or in the application is hard to use, or you need information in another format,
            email <EmailLink address={address} />. Say which page you were on and what happened, and we will reply.
          </p>
        </section>
      </div>
      <LegalLinks current="/accessibility" />
    </article>
  );
}

export function ContactPage() {
  return <ContactView state={useSiteInfoState()} />;
}

export function ContactView({ state }: { state: SiteInfoState }) {
  const info = state.status === "ready" ? state.info : null;
  const addresses = contactAddresses(state);
  return (
    <article className="ms-section ms-legal" aria-labelledby="contact-page-title">
      <span className="ms-eyebrow">Company</span>
      <h1 id="contact-page-title">Contact MDARIX</h1>
      <p className="ms-legal-lead">
        Questions about a trial, becoming a design partner, your account, integrations, or your data? Choose the route
        that best matches your request and our team will direct it to the right owner.
      </p>
      <div className="ms-contact-grid">
        {addresses.support && (
          <div className="ms-card">
            <Mail size={20} aria-hidden="true" />
            <strong>Support and sales</strong>
            <EmailLink address={addresses.support} />
          </div>
        )}
        {addresses.privacy && (
          <div className="ms-card">
            <Mail size={20} aria-hidden="true" />
            <strong>Privacy and data requests</strong>
            <EmailLink address={addresses.privacy} />
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
      {addresses.notice && (
        <div className="ms-legal-notice" role="status">
          <strong>Contact details are being configured</strong>
          <span>
            The MDARIX operator will publish the approved support and privacy addresses before customer onboarding.
          </span>
        </div>
      )}
      <div className="ms-contact-topics">
        <div>
          <strong>Product and design partnerships</strong>
          <span>
            Discuss post-market surveillance, investigation workflows, evidence review
            {DEMO_REQUESTS_OFFERED ? ", or a controlled demo." : ", or a design partnership."}
          </span>
        </div>
        <div>
          <strong>Support and account help</strong>
          <span>
            Include your organization, workspace, and a short description of the issue. Do not include patient data.
          </span>
        </div>
        <div>
          <strong>Privacy and data requests</strong>
          <span>
            Use the privacy contact for access, correction, deletion, export, or other personal-data questions.
          </span>
        </div>
      </div>
      <div className="ms-cta-row">
        {DEMO_REQUESTS_OFFERED && (
          <a className="ms-btn ms-btn-primary" href="/request-demo">
            Request a demo <ArrowRight size={16} aria-hidden="true" />
          </a>
        )}
        <a className={`ms-btn ${DEMO_REQUESTS_OFFERED ? "ms-btn-outline" : "ms-btn-primary"}`} href="/signup">
          Start free trial
          {!DEMO_REQUESTS_OFFERED && <ArrowRight size={16} aria-hidden="true" />}
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
