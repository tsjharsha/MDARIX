import type { ReactNode } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Check,
  Globe2,
  ListChecks,
  Lock,
  PenLine,
  ScrollText,
  ShieldCheck,
  Timer,
  UserCheck,
  type LucideIcon,
} from "lucide-react";
import { AVAILABILITY, WORK_AREAS, afterTheTrial, trialIncludes } from "./content";
import { QUESTIONS_PATH, QUESTION_PATHS } from "./questions";
import { CustomerVoices, MarketBasis, SignalChart } from "./visuals";
import { HeroStory, Shot } from "./motion";
import { BESIDE_YOUR_QMS } from "../features/help/besideYourQms";

// The website's own pages besides the questions, the videos and the legal pages. Four pages: what MDARIX does (home),
// how it works (/platform), why it can be trusted (/trust) and who it is for and how to start (/company).
export const SITE_PAGES = [
  "/",
  "/platform",
  "/trust",
  "/company",
  "/videos",
  QUESTIONS_PATH,
  ...QUESTION_PATHS,
] as const satisfies readonly string[];
export type SitePage = (typeof SITE_PAGES)[number];

/* ----------------------------------------------------------------------------------------------- Parts */

function Head({ eyebrow, title, copy, id }: { eyebrow: string; title: string; copy?: ReactNode; id: string }) {
  return (
    <div className="ms-head ms-reveal">
      <span className="ms-eyebrow">{eyebrow}</span>
      <h2 id={id}>{title}</h2>
      {copy && <p>{copy}</p>}
    </div>
  );
}

function PageHero({
  eyebrow,
  title,
  copy,
  children,
}: {
  eyebrow: string;
  title: string;
  copy: string;
  children?: ReactNode;
}) {
  return (
    <section className="ms-page-hero ms-dark">
      <span className="ms-eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{copy}</p>
      {children}
    </section>
  );
}

function Checks({ items }: { items: readonly string[] }) {
  return (
    <ul className="ms-checks">
      {items.map((item) => (
        <li key={item}>
          <Check size={16} aria-hidden="true" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function Cards({ items, columns = 3 }: { items: readonly (readonly [string, string])[]; columns?: 2 | 3 | 4 }) {
  return (
    <div className={`ms-grid ms-grid-${columns} ms-reveal`}>
      {items.map(([title, text]) => (
        <div key={title} className="ms-card">
          <strong>{title}</strong>
          <p>{text}</p>
        </div>
      ))}
    </div>
  );
}

function IconCards({ items }: { items: readonly (readonly [LucideIcon, string, string])[] }) {
  return (
    <div className={`ms-grid ms-grid-${items.length === 3 ? 3 : 4} ms-reveal`}>
      {items.map(([Icon, title, text]) => (
        <div key={title} className="ms-card">
          <span className="ms-icon">
            <Icon size={20} aria-hidden="true" />
          </span>
          <strong>{title}</strong>
          <p>{text}</p>
        </div>
      ))}
    </div>
  );
}

function CtaBand({ title = "See your own complaints the way an inspector will." }: { title?: string }) {
  return (
    <section className="ms-cta" aria-labelledby="cta-title">
      <div>
        <h2 id="cta-title">{title}</h2>
        <p>Start on sample data in minutes, then try it on your own exports. No demo call, no credit card.</p>
        <div className="ms-actions">
          <a className="ms-btn ms-btn-primary" href="/signup">
            Start free trial <ArrowRight size={16} aria-hidden="true" />
          </a>
          <a className="ms-btn ms-btn-quiet" href="/contact">
            Talk to us
          </a>
        </div>
      </div>
      <div className="ms-cta-trial">
        <strong>In your free trial</strong>
        <Checks items={trialIncludes} />
      </div>
    </section>
  );
}

const TRUST_POINTS = [
  [Lock, "Isolated data per customer", "The database itself enforces each organization's boundary."],
  [
    ShieldCheck,
    "AI that only proposes",
    "In the trial, AI works on the sample data only; a person reviews every proposal.",
  ],
  [BadgeCheck, "Signed decisions", "Approval authority by role, re-authentication and no self-approval."],
  [ScrollText, "Complete audit trail", "Who did what, when and why, ready to export."],
] as const;

/* ------------------------------------------------------------------------------------------------ Home */

// The story of one sample product (OrbitCare 300) in five steps, each with the work area that does it and the app's own
// screen for it, captured from a free trial's sample data (public/site/app, at 2x).
const STORY = [
  {
    id: "signal",
    eyebrow: "Signal",
    title: "Catch the signal on the version that caused it.",
    text: "Complaints are counted per product version against their own history, so a rise after a change shows up before anyone spots it in a spreadsheet. Closed “no fault found” complaints get a second look.",
    area: ["Cases", "/platform#cases"],
    shot: "signal",
    alt: "MDARIX Cases: the OrbitCare 300 pressure-alarm trend, rising after Rev B, from the trial's sample data",
  },
  {
    id: "product",
    eyebrow: "Product reality",
    title: "See the product behind the complaint.",
    text: "Every complaint sits on the version in the field on the event date, with its components, suppliers, lots and markets. What changed between versions is one click away, and so is every lot that shares a suspect part.",
    area: ["Products", "/platform#products"],
    shot: "product",
    alt: "MDARIX Products: OrbitCare 300 Rev B compared with Rev A; the pressure sensor supplier changed from Precision Sensors Ltd to NovaSense Components in SAMPLE-CHG-014",
  },
  {
    id: "investigation",
    eyebrow: "Evidence-grounded investigation",
    title: "Weigh every possible cause against the evidence.",
    text: "Quality, regulatory, product and supplier quality review the same evidence. Each possible cause shows what supports it, what contradicts it and what is still unknown. AI may propose; a person reviews.",
    area: ["Investigations", "/platform#investigations"],
    shot: "investigation",
    alt: "MDARIX Investigations: SAMPLE-INV-001, with what is known, unknown, contradicted and missing",
  },
  {
    id: "decision",
    eyebrow: "Decision and reports",
    title: "Sign the decision. Get the right report ready for every market.",
    text: "Reportability is assessed for the US, EU and Northern Ireland, Great Britain, Canada and India, each against its legal clock and with its reason kept. People submit every report; MDARIX never does.",
    area: ["Decisions & Reports", "/platform#decisions"],
    shot: "decision",
    alt: "MDARIX Decisions: the sample investigation's decision, signed by a person with password and authenticator code",
  },
  {
    id: "effectiveness",
    eyebrow: "Did it work?",
    title: "Prove the action worked, or say it is too early.",
    text: "The CAPA's effectiveness check is planned before the action, measured from the right date and signed: effective, not effective or inconclusive. Field data that touches the risk file is sent there.",
    area: ["Decisions & Reports", "/platform#decisions"],
    shot: "effectiveness",
    alt: "MDARIX effectiveness check for SAMPLE-CAPA-02: the synthetic follow-up after the fix, signed inconclusive",
  },
] as const;

const shotOf = (name: string) => `/site/app/${name}.webp`;

// What is true today, at a glance: the facts strip under the home hero.
const FACTS = [
  [Globe2, "5 markets", "United States, EU and Northern Ireland, Great Britain, Canada and India"],
  [ListChecks, "6-step investigation", "From the signal to the decision and the action"],
  [PenLine, "A person signs", "Every decision, with password and authenticator code"],
  [Timer, "Sample data in minutes", "A private trial workspace, no demo call"],
] as const;

export function HomePage() {
  return (
    <>
      <section className="ms-hero ms-dark" aria-labelledby="hero-title">
        <div className="ms-hero-copy">
          <span className="ms-eyebrow">Post-market surveillance for medical devices</span>
          <h1 id="hero-title">
            Get every complaint to a defensible decision, and the right report on time in every market.
          </h1>
          <p>
            MDARIX ties each complaint to the product version, lots and supplier behind it, weighs the evidence for and
            against, and keeps the signed decision with the evidence to prove why.
          </p>
          <div className="ms-actions">
            <a className="ms-btn ms-btn-primary" href="/signup">
              Start free trial <ArrowRight size={16} aria-hidden="true" />
            </a>
            <a className="ms-btn ms-btn-quiet" href="/platform">
              See how it works
            </a>
          </div>
          <ul className="ms-hero-points">
            <li>Works beside your QMS or complaint software</li>
            <li>US, EU, GB, Canada and India</li>
            <li>Authorized people decide and sign</li>
          </ul>
        </div>
        <div className="ms-hero-visual">
          <Shot
            src={shotOf("hero")}
            alt="MDARIX Today: the sample investigation of OrbitCare 300 pressure-alarm complaints, the overdue and due work, and the legal clock per market, from the free trial's sample data"
            address="mdarix.com/app"
            priority
          />
          <HeroStory />
        </div>
      </section>

      <section className="ms-facts" aria-label="MDARIX at a glance">
        <ul>
          {FACTS.map(([Icon, title, text]) => (
            <li key={title}>
              <span className="ms-icon">
                <Icon size={20} aria-hidden="true" />
              </span>
              <strong>{title}</strong>
              <span>{text}</span>
            </li>
          ))}
        </ul>
        <p>
          Reportability is assessed against each market&rsquo;s own rules: 21 CFR 803 in the US, EU MDR Art. 87 in the
          EU and Northern Ireland, UK MDR 2002 in Great Britain, SOR/98-282 in Canada and India MDR 2017 in India.
        </p>
      </section>

      <section className="ms-section ms-band" aria-labelledby="story-title">
        <Head
          eyebrow="One product, start to finish"
          id="story-title"
          title="Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?"
          copy="The free trial's sample story, in five steps. Each step is one place in MDARIX."
        />
        <ol className="ms-story">
          {STORY.map((step, index) => (
            <li key={step.id} id={step.id} className="ms-story-step ms-reveal">
              <div className="ms-story-copy">
                <span className="ms-step">
                  <span aria-hidden="true">0{index + 1}</span> {step.eyebrow}
                </span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
                <a className="ms-link" href={step.area[1]}>
                  In MDARIX: {step.area[0]} <ArrowRight size={14} aria-hidden="true" />
                </a>
              </div>
              <div className="ms-story-visual">
                <Shot src={shotOf(step.shot)} alt={step.alt} address="mdarix.com/app" />
                {step.id === "signal" && <SignalChart />}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="ms-section ms-band ms-dark" aria-labelledby="beside-title">
        <Head eyebrow="Beside your QMS" id="beside-title" title="Built for regulated teams." copy={BESIDE_YOUR_QMS} />
        <IconCards items={TRUST_POINTS} />
        <p className="ms-more">
          <a className="ms-link" href="/trust">
            How MDARIX earns trust <ArrowRight size={14} aria-hidden="true" />
          </a>
        </p>
      </section>

      <CustomerVoices />
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------- How it works */

// Each work area's own screen, from a free trial's sample data.
const AREA_SHOTS: Record<(typeof WORK_AREAS)[number]["id"], [string, string]> = {
  today: ["hero", "MDARIX Today: the person's own work first, from the trial's sample data"],
  cases: ["signal", "MDARIX Cases: the OrbitCare 300 pressure-alarm trend, rising after Rev B"],
  investigations: ["investigation", "MDARIX Investigations: SAMPLE-INV-001, what is known and what is not"],
  products: ["product", "MDARIX Products: OrbitCare 300 Rev B compared with Rev A"],
  decisions: ["decision", "MDARIX Decisions: the decision signed by a person with password and authenticator code"],
};

export function PlatformPage() {
  return (
    <>
      <PageHero
        eyebrow="How MDARIX works"
        title="Five places, one product story."
        copy="Everyone works in the same five places. Each person opens on their own part of the work, and every record links back to the product it came from."
      >
        <nav className="ms-areas" aria-label="Work areas">
          {WORK_AREAS.map((area, index) => (
            <a key={area.id} href={`#${area.id}`}>
              <span aria-hidden="true">0{index + 1}</span>
              <strong>{area.name}</strong>
              <small>{area.line}</small>
            </a>
          ))}
        </nav>
      </PageHero>

      {WORK_AREAS.map((area, index) => (
        <section
          key={area.id}
          className={`ms-section ms-split${index % 2 ? " ms-band" : ""}`}
          aria-labelledby={area.id}
        >
          <div>
            <Head eyebrow={`0${index + 1} · ${area.name}`} id={area.id} title={area.line} />
            <Checks items={area.points} />
          </div>
          <Shot
            className="ms-reveal"
            src={shotOf(AREA_SHOTS[area.id][0])}
            alt={AREA_SHOTS[area.id][1]}
            address="mdarix.com/app"
          />
        </section>
      ))}

      <section className="ms-section" aria-labelledby="beside-your-qms">
        <Head
          eyebrow="Your data"
          id="beside-your-qms"
          title="Start with exports. Connect your systems in a pilot."
          copy={BESIDE_YOUR_QMS}
        />
        <Cards
          items={[
            [
              "Your own exports",
              "CSV or Excel with your own column names, guided by templates for products, lots, complaints, components, suppliers, changes and risks.",
            ],
            [
              "Checked before import",
              "Every file is checked for problems and personal data. Personal details are refused or replaced before anything is stored.",
            ],
            [
              "Live connections in a pilot",
              "Your QMS, PLM, ERP and supplier systems feed MDARIX on a schedule, with your fields mapped by governed templates.",
            ],
          ]}
        />
      </section>

      <section className="ms-section ms-band" aria-labelledby="availability">
        <Head
          eyebrow="What you get"
          id="availability"
          title="What is in the free trial, what comes in a pilot, and what is planned."
        />
        <div className="ms-grid ms-grid-3">
          {AVAILABILITY.map((stage) => (
            <div key={stage.label} className="ms-card ms-stage">
              <strong>{stage.label}</strong>
              <p>{stage.note}</p>
              <Checks items={stage.items} />
            </div>
          ))}
        </div>
      </section>

      <CtaBand title="Follow the sample story yourself." />
    </>
  );
}

/* ----------------------------------------------------------------------------------------------- Trust */

export function TrustPage() {
  return (
    <>
      <PageHero
        eyebrow="Trust"
        title="People decide. Every step is recorded. AI only proposes."
        copy="Post-market decisions have to stand up in an inspection. MDARIX keeps the evidence, the reasoning and the signature together, and says plainly what it does not do."
      >
        <nav className="ms-subnav" aria-label="Trust sections">
          <a href="#principles">Principles</a>
          <a href="#ai">AI</a>
          <a href="#markets">Markets and regulations</a>
          <a href="#security">Security</a>
          <a href="#integrations">Your systems</a>
        </nav>
      </PageHero>

      <section className="ms-section" aria-labelledby="principles">
        <Head eyebrow="Principles" id="principles" title="Evidence before inference. Humans decide." />
        <Cards
          items={[
            [
              "Beside your QMS",
              `${BESIDE_YOUR_QMS} MDARIX is not a regulatory submission system: it never submits anything to a regulator.`,
            ],
            [
              "Evidence before inference",
              "Relationships are visible, competing explanations stay separate, and missing evidence is stated instead of guessed.",
            ],
            [
              "Humans decide",
              "Decisions are signed with password and authenticator code by people with the authority to sign. Whoever writes a brief never reviews or signs it.",
            ],
          ]}
        />
      </section>

      <section className="ms-section ms-band ms-dark" aria-labelledby="ai">
        <Head eyebrow="AI" id="ai" title="AI that proposes, cites and steps back." />
        <Checks
          items={[
            "Answers cite the authorized evidence they were built from.",
            "When evidence is thin, MDARIX holds back instead of guessing.",
            "No unsupported root-cause claims; interpretation stays separate from observation.",
            "AI is switched on per organization by its administrator. In the free trial it works on the sample data only, and every AI output is a proposal a person reviews.",
            "An AI proposal is never a signature.",
          ]}
        />
      </section>

      <section className="ms-section" aria-labelledby="markets">
        <Head
          eyebrow="Markets and regulations"
          id="markets"
          title="Built around the evidence regulators ask for."
          copy="Each reportability decision is counted from the day you became aware and keeps its reason. People decide what is reportable and submit every report."
        />
        <MarketBasis />
      </section>

      <section className="ms-section ms-band" aria-labelledby="security">
        <Head eyebrow="Security and access" id="security" title="Each organization's data is its own." />
        <IconCards
          items={[
            [
              Lock,
              "Organization isolation",
              "Each organization's data is scoped to it on every request and enforced by the database (row-level security).",
            ],
            [
              UserCheck,
              "Identity and sessions",
              "Authenticator-app MFA, sign-out after 30 minutes without activity, a 12-hour limit on any session, and immediate sign-out when access is suspended.",
            ],
            [
              ShieldCheck,
              "Least privilege",
              "Role-based access, approval authority by role, segregation of duties, and protected platform roles.",
            ],
          ]}
        />
        <div className="ms-sub">
          <h3>What MDARIX can accurately say today</h3>
          <Cards
            columns={2}
            items={[
              [
                "Implemented controls",
                "Authorization scoped to each organization, role and field policies, audit records, provenance, human approval controls, and advisory AI safeguards are built into the product.",
              ],
              [
                "Pilot boundary",
                "MDARIX is not yet a validated (GxP) system. Design-partner pilots use exported records without patient-identifiable information.",
              ],
              [
                "Certification status",
                "MDARIX does not claim ISO 27001 certification, HIPAA compliance, GDPR compliance, or 21 CFR Part 11 compliance on this site.",
              ],
              [
                "Evidence availability",
                "Validation protocols, test reports, and approved non-confidential sample dossiers may be shared during a controlled review. No confidential customer material is published.",
              ],
            ]}
          />
          <p className="ms-more">
            <a className="ms-link" href="/security">
              Security details and how to report an issue <ArrowRight size={14} aria-hidden="true" />
            </a>
          </p>
        </div>
      </section>

      <section className="ms-section" aria-labelledby="integrations">
        <Head eyebrow="Your systems" id="integrations" title="Start with exports. Connect in a pilot." />
        <Checks
          items={[
            "Start with file exports from your existing systems; live connections are built in a pilot.",
            "Versioned, governed mappings from your fields to the MDARIX model, released with approval.",
            "Source-system API keys are encrypted at rest and never shown again.",
          ]}
        />
      </section>
      <CtaBand />
    </>
  );
}

/* --------------------------------------------------------------------------------------------- Company */

const TRIAL_STEPS = [
  [
    "Request your free trial",
    "Tell us your name, company and work email. With a company or personal email your trial is approved automatically and ready within minutes, up to a daily limit; requests from disposable email addresses are reviewed by the MDARIX team, usually within one business day.",
  ],
  [
    "Follow the sample story",
    "Activate your account from the invitation email. Your private workspace opens with sample data: one product's story from the first complaint to the signed decision.",
  ],
  [
    "Try it on your own data",
    "Download the CSV templates for products, lots, complaints and the components, suppliers, changes and risks around them. Every file is checked for problems and personal data before import.",
  ],
] as const;

export function CompanyPage() {
  return (
    <>
      <PageHero
        eyebrow="About MDARIX"
        title="For medical device makers who have to prove every decision."
        copy="MDARIX is built for small and mid-size device makers and exporters, starting in India: the quality, regulatory, product and supplier-quality people who handle complaints and report to authorities in more than one market."
      />

      <section className="ms-section" aria-labelledby="fit">
        <Head eyebrow="Where MDARIX fits" id="fit" title="An intelligence layer beside your systems of record." />
        <Cards
          columns={2}
          items={[
            [
              "Where MDARIX fits",
              "MDARIX connects product context, complaints, changes, suppliers, lots, evidence, uncertainty and human decisions. Your QMS keeps the complaint record, CAPA and change control.",
            ],
            [
              "What MDARIX is not",
              `It does not replace your QMS, PLM or ERP. ${BESIDE_YOUR_QMS} MDARIX is not a regulatory submission system: it never submits anything to a regulator.`,
            ],
          ]}
        />
      </section>

      <section className="ms-section ms-band" id="start" aria-labelledby="start-title">
        <Head eyebrow="How to start" id="start-title" title="A free trial first. No demo call needed." />
        <ol className="ms-steps">
          {TRIAL_STEPS.map(([title, text], index) => (
            <li key={title}>
              <span aria-hidden="true">{index + 1}</span>
              <div>
                <strong>{title}</strong>
                <p>{text}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="ms-note">
          30 days · up to 50 people · 5,000 uploaded rows. Want live connections to your QMS, PLM or ERP? Ask about
          becoming a design partner.
        </p>
        <div className="ms-actions">
          <a className="ms-btn ms-btn-primary" href="/signup">
            Start free trial <ArrowRight size={16} aria-hidden="true" />
          </a>
          <a className="ms-btn ms-btn-quiet" href="/contact">
            Contact us
          </a>
        </div>
      </section>

      <section className="ms-section" id="after-the-trial" aria-labelledby="after-the-trial-title">
        <Head
          eyebrow={afterTheTrial.eyebrow}
          id="after-the-trial-title"
          title={afterTheTrial.title}
          copy={afterTheTrial.copy}
        />
        <Cards columns={2} items={afterTheTrial.points} />
      </section>

      <section className="ms-section ms-band" aria-labelledby="learn">
        <Head eyebrow="Learn more" id="learn" title="Short answers and step-by-step videos." />
        <Cards
          columns={2}
          items={[
            [
              "Questions and answers",
              "Trending complaints, reportability, the risk file and CAPA effectiveness: a short answer first, then what MDARIX does about it.",
            ],
            [
              "Free trial videos",
              "Fourteen short videos follow a quality manager through the 30-day trial, with English captions.",
            ],
          ]}
        />
        <p className="ms-more">
          <a className="ms-link" href={QUESTIONS_PATH}>
            Questions and answers <ArrowRight size={14} aria-hidden="true" />
          </a>
          <a className="ms-link" href="/videos">
            Free trial videos <ArrowRight size={14} aria-hidden="true" />
          </a>
        </p>
      </section>
    </>
  );
}
