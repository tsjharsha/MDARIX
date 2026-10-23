// The frame of every sign-in and account page (WEB-06): in a module of its own, so the trial sign-up page, a website
// page loaded with the website, does not bring the sign-in, activation and MFA screens (AuthPage.tsx) with it.
import type { ReactNode } from "react";
import { CalendarCheck, FileSearch, LockKeyhole, ShieldCheck, UserCheck } from "lucide-react";
import { SignupMotion } from "./SignupMotion";
import { trialApproval, type TrialApproval } from "./trialProfile";
import { useSiteInfo } from "../../site/legal";

/** How soon the sign-up page's workspace is ready, as the server approves requests (site-info). Exported for its test. */
export const READY_LINES: Record<TrialApproval, string> = {
  "company-and-personal": "Ready within minutes with a company or personal email, isolated from every other customer.",
  "company-domains": "Ready within minutes with a company email, isolated from every other customer.",
  off: "Prepared once the MDARIX team approves your request, isolated from every other customer.",
};

function TrialReadyLine() {
  return <>{READY_LINES[trialApproval(useSiteInfo()?.trial)]}</>;
}

const ASIDE: Record<string, { eyebrow: string; title: string; points: [typeof ShieldCheck, string, ReactNode][] }> = {
  signin: {
    eyebrow: "Investigation intelligence",
    title: "Evidence before inference. Humans decide.",
    points: [
      [ShieldCheck, "Your organization's own workspace", "Every record you see belongs to your tenant only."],
      [
        FileSearch,
        "Evidence-linked investigations",
        "Complaints, versions, lots and suppliers connected in one place.",
      ],
      [UserCheck, "People make the decisions", "Every finding cites its records; authorized reviewers decide."],
    ],
  },
  signup: {
    eyebrow: "Free 30-day trial",
    title: "Watch MDARIX find the pattern in your complaints.",
    points: [
      [ShieldCheck, "Your own private workspace", <TrialReadyLine />],
      [FileSearch, "Sample data on day one", "Explore a full device investigation before sharing anything."],
      [UserCheck, "Then your own exports", "CSV templates, checked for personal data before import."],
    ],
  },
  "request-demo": {
    eyebrow: "Request a demo",
    title: "See MDARIX on an investigation like yours.",
    points: [
      [FileSearch, "A walkthrough on a real signal", "One complaint trend, traced to the supplier lot it shares."],
      [CalendarCheck, "At a time that suits you", "Our team contacts you to agree the date and who should join."],
      [UserCheck, "Governance you can defend", "Evidence citations, visible unknowns and human sign-off."],
    ],
  },
  security: {
    eyebrow: "Account security",
    title: "Your access is protected at every step.",
    points: [
      [LockKeyhole, "Single-use secure links", "Activation and reset links expire and work only once."],
      [ShieldCheck, "Strong passwords and MFA", "Passwords are yours alone and never shown to administrators."],
      [UserCheck, "Every sign-in is audited", "Access events are recorded for your administrators."],
    ],
  },
};

// Shared frame for every sign-in and account page: website brand, light med-tech backdrop, value panel and the form.
export function AuthFrame({ mode, children }: { mode: string; children: ReactNode }) {
  const aside = ASIDE[mode] ?? ASIDE.security;
  return (
    <div className={mode === "signup" ? "auth-page is-signup" : "auth-page"}>
      <a className="app-skip" href="#auth-main">
        Skip to content
      </a>
      <header className="auth-page-top">
        <a className="auth-brand" href="/" aria-label="MDARIX home">
          <span className="auth-logo" aria-hidden="true">
            M
          </span>
          MDARIX<small>Product intelligence</small>
        </a>
        <a className="auth-back" href="/">
          Back to website
        </a>
      </header>
      <main className="auth-page-body">
        <section className="auth-aside" aria-label="About MDARIX">
          <span className="auth-eyebrow">{aside.eyebrow}</span>
          <h2>{aside.title}</h2>
          {mode === "signup" && <SignupMotion />}
          <ul>
            {aside.points.map(([Icon, title, text]) => (
              <li key={title}>
                <span aria-hidden="true">
                  <Icon size={18} />
                </span>
                <div>
                  <strong>{title}</strong>
                  <p>{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
        <div id="auth-main" tabIndex={-1} className="auth-page-main">
          {children}
        </div>
      </main>
      <footer className="auth-page-foot">
        <span>MDARIX · System of Intelligence, not System of Record</span>
        <span>
          <LockKeyhole size={13} aria-hidden="true" /> Encrypted connection · Tenant-isolated data
        </span>
      </footer>
    </div>
  );
}
