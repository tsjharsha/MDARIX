import type { CSSProperties, ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  Boxes,
  Cable,
  Check,
  CircleDashed,
  Clock3,
  Database,
  FileSpreadsheet,
  KeyRound,
  Lock,
  Microscope,
  PenLine,
  PlugZap,
  ScrollText,
  SearchCheck,
  ShieldCheck,
  Shuffle,
  Sparkles,
  UserCheck,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import { menus, pages, postMarketResources, trialIncludes, type CapabilityIcon } from "./legacyContent";
import { DEMO_REQUESTS_OFFERED } from "./offer";
import {
  AVAILABILITY,
  afterTheTrial,
  capabilityStatus,
  img,
  lifecycleStages,
  platformGroups,
  productStructureTitles,
  solutionGroups,
  type Availability,
  type PlatformGroup,
  type PlatformPath,
} from "./content";
import { FlowChain, InvestigationAnimation, Photo, Reveal } from "./motion";
import { DesignPhases } from "./designPhases";
import { QUESTIONS, QUESTIONS_PATH, QUESTION_PATHS } from "./questions";
import {
  CustomerVoices,
  LifecycleHero,
  LotChart,
  ReportingWindows,
  SourceFlow,
  StandardsSection,
  WeeklyChart,
} from "./visuals";
import { BESIDE_YOUR_QMS } from "../features/help/besideYourQms";
import { QualityLoop } from "../features/workspace/sections/QualityLoop";
import { LOOP_ORDER, type LoopStation } from "../features/workspace/qualityLoop";

// The quality loop on the home page: illustrative, synthetic values (said on the picture), in the order a complaint
// travels; the product draws the same loop from each organization's own records (Readiness).
const ILLUSTRATIVE_LOOP: Record<string, { value: number; tone: LoopStation["tone"]; state: string }> = {
  COMPLAINTS_TO_RECHECK: { value: 5, tone: "critical", state: "Critical" },
  COMPLAINTS_PAST_TARGET: { value: 0, tone: "good", state: "Clear" },
  REPORTING_CLOCKS: { value: 2, tone: "warning", state: "Needs attention" },
  HARM_CLOSED_WITHOUT_CASE: { value: 1, tone: "critical", state: "Critical" },
  TRIAGE_OVERDUE: { value: 0, tone: "good", state: "Clear" },
  TRENDS_WITHOUT_ACTION: { value: 1, tone: "warning", state: "Needs attention" },
  CAPA_EFFECTIVENESS: { value: 1, tone: "critical", state: "Critical" },
  RISK_FILE_INPUT: { value: 3, tone: "critical", state: "Critical" },
};

export const SITE_LOOP: LoopStation[] = LOOP_ORDER.map((step, index) => ({
  key: step.code,
  number: index + 1,
  label: step.label,
  caption: step.caption,
  value: ILLUSTRATIVE_LOOP[step.code].value,
  tone: ILLUSTRATIVE_LOOP[step.code].tone,
  stateLabel: ILLUSTRATIVE_LOOP[step.code].state,
  done: ILLUSTRATIVE_LOOP[step.code].tone === "good",
}));

export const SITE_PAGES = [
  "/",
  "/platform",
  "/platform/product-360",
  "/platform/investigations",
  "/platform/decisions",
  "/platform/trust",
  "/roadmap",
  "/solutions",
  "/product-lifecycle",
  "/trust",
  "/trust/regulations",
  "/resources",
  "/company",
  "/videos",
  QUESTIONS_PATH,
  ...QUESTION_PATHS,
] as const satisfies readonly string[];
export type SitePage = (typeof SITE_PAGES)[number];

const QUESTION_FLOW = [
  "Complaint signal",
  "Product version",
  "Change",
  "Component",
  "Supplier",
  "Affected lots",
  "Evidence",
  "Hypotheses",
  "Contradictions",
  "Unknowns",
  "Assurance",
  "Human decision",
];

function PageHero({
  eyebrow,
  title,
  copy,
  image,
  visual,
  center = false,
  children,
}: {
  eyebrow: string;
  title: string;
  copy: string;
  image?: { src: string; alt: string; contain?: boolean };
  visual?: ReactNode;
  /** A text-only hero, centred. */
  center?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className={center ? "ms-page-hero ms-page-hero-center" : "ms-page-hero"}>
      <div className="ms-page-hero-copy">
        <span className="ms-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{copy}</p>
        {children}
      </div>
      {visual}
      {image && (
        <Photo
          src={image.src}
          alt={image.alt}
          className={image.contain ? "ms-page-hero-photo ms-photo-contain" : "ms-page-hero-photo"}
        />
      )}
    </section>
  );
}

function SectionHead({ eyebrow, title, copy, id }: { eyebrow: string; title: string; copy?: string; id?: string }) {
  return (
    <Reveal className="ms-section-head">
      <span className="ms-eyebrow">{eyebrow}</span>
      <h2 id={id}>{title}</h2>
      {copy && <p>{copy}</p>}
    </Reveal>
  );
}

function CtaBand({ trial = false }: { trial?: boolean }) {
  return (
    <section className="ms-cta-band">
      <Reveal>
        <span className="ms-eyebrow">Design partners</span>
        <h2>Bring one real investigation. See the whole story in one place.</h2>
        <p>Start with exports from your quality, product and supplier systems. {BESIDE_YOUR_QMS}</p>
        {trial && (
          <div className="ms-cta-trial">
            <strong>In your free trial</strong>
            <ul>
              {trialIncludes.map((item) => (
                <li key={item}>
                  <Check size={15} aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="ms-cta-row">
          {DEMO_REQUESTS_OFFERED && (
            <a className="ms-btn ms-btn-light" href="/request-demo">
              Request a demo <ArrowRight size={16} aria-hidden="true" />
            </a>
          )}
          <a className={`ms-btn ${DEMO_REQUESTS_OFFERED ? "ms-btn-ghost-light" : "ms-btn-light"}`} href="/signup">
            Start free trial
            {!DEMO_REQUESTS_OFFERED && <ArrowRight size={16} aria-hidden="true" />}
          </a>
        </div>
      </Reveal>
    </section>
  );
}

const ROADMAP_ICONS: Record<CapabilityIcon, LucideIcon> = {
  product: Boxes,
  "second-look": SearchCheck,
  clock: Clock3,
  signal: Activity,
  investigation: Microscope,
  signature: PenLine,
  capa: ShieldCheck,
  import: FileSpreadsheet,
  roles: UsersRound,
  connection: Cable,
  mapping: Shuffle,
  ai: Sparkles,
  sso: KeyRound,
  connector: PlugZap,
  database: Database,
};
// One tone per stage, in the order of capabilityStatus: available today, in a pilot, planned.
const ROADMAP_TONES = ["live", "next", "planned"] as const;
// Each stage lists only what it adds, so the track says that and the running total ("+3 more · 12 in total"): a
// later stage never reads as all there is.
const ROADMAP_COUNTS = capabilityStatus.map((status, index) => {
  const added = status.items.length;
  const total = capabilityStatus.slice(0, index + 1).reduce((sum, stage) => sum + stage.items.length, 0);
  if (index === 0) return `${added} ${added === 1 ? "capability" : "capabilities"}`;
  return `+${added} more · ${total} in total`;
});

// What you get, as a roadmap (the /roadmap page): a track from "Available today" to "Planned" that draws itself when it
// scrolls into view, the free trial's capabilities in full, then what comes in a pilot and what is planned.
// The motion runs once (the live stop keeps a soft pulse) and none of it runs for people who ask for reduced motion.
function ScopeClarity() {
  const [today, ...later] = capabilityStatus;
  const column = (status: (typeof capabilityStatus)[number], index: number) => {
    const tone = ROADMAP_TONES[index];
    return (
      <article
        key={status.label}
        className={`ms-roadmap-card is-${tone}`}
        aria-labelledby={`roadmap-${tone}`}
        style={{ "--stage": index } as CSSProperties}
      >
        <header>
          <span className="ms-roadmap-badge">{status.badge}</span>
          <h3 id={`roadmap-${tone}`}>{status.label}</h3>
          <p>{status.text}</p>
          {index === 0 && <span className="ms-roadmap-ribbon">Included in your free trial</span>}
        </header>
        <ul className="ms-roadmap-list">
          {status.items.map((item, n) => {
            const Icon = ROADMAP_ICONS[item.icon];
            return (
              <li key={item.title} style={{ "--n": n } as CSSProperties}>
                <span className="ms-roadmap-icon">
                  <Icon size={18} aria-hidden="true" />
                </span>
                <span>
                  <strong>{item.title}</strong>
                  <span>{item.detail}</span>
                </span>
              </li>
            );
          })}
        </ul>
        <p className="ms-roadmap-promise">{status.promise}</p>
      </article>
    );
  };
  return (
    <section className="ms-section ms-scope" aria-label="Roadmap">
      <Reveal className="ms-roadmap">
        <div className="ms-roadmap-head">
          <span className="ms-roadmap-rail" aria-hidden="true">
            <span className="ms-roadmap-rail-done" />
            <span className="ms-roadmap-rail-next" />
            <span className="ms-roadmap-spark" />
          </span>
          <ol className="ms-roadmap-track" aria-label="From what is available today to what is planned">
            {capabilityStatus.map((status, index) => (
              <li
                key={status.label}
                className={`ms-roadmap-stop is-${ROADMAP_TONES[index]}`}
                style={{ "--stage": index } as CSSProperties}
              >
                <span className="ms-roadmap-dot" aria-hidden="true" />
                <span className="ms-roadmap-badge">{status.badge}</span>
                <strong>{status.label}</strong>
                <span className="ms-roadmap-count">{ROADMAP_COUNTS[index]}</span>
              </li>
            ))}
          </ol>
        </div>
        {column(today, 0)}
        <div className="ms-roadmap-later">{later.map((status, index) => column(status, index + 1))}</div>
      </Reveal>
      <Reveal className="ms-card ms-card-flat ms-scope-trial">
        <strong>In your free trial</strong>
        <p>Everything marked Available today, on sample data first and then on your own exports.</p>
        <ul className="ms-check-list">
          {trialIncludes.map((item) => (
            <li key={item}>
              <Check size={16} aria-hidden="true" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
        <a className="ms-btn ms-btn-primary" href="/signup">
          Start free trial <ArrowRight size={16} aria-hidden="true" />
        </a>
      </Reveal>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ Home */

// The worked example on the home page: the free trial's sample story (OrbitCare 300 Rev B, site/visuals.tsx), from
// the rising signal to the signed decision, each step linking to the Platform section that does it.
const EXAMPLE_STEPS = [
  {
    title: "A signal rises",
    text: "Pressure-alarm complaints rise from about 2 to 12 a month after Rev B is released. A change is a lead, not a cause.",
    href: "/platform/product-360#product-version",
  },
  {
    title: "Scope to the lot and the supplier",
    text: "Lots 003 and 004, built with the new supplier's pressure sensors, hold 30 of the 42 complaints.",
    href: "/platform/investigations#evidence",
  },
  {
    title: "Weigh the explanations together",
    text: "Quality, regulatory, product, supplier quality and manufacturing review the same evidence, competing hypotheses and open questions.",
    href: "/platform/investigations#hypotheses",
  },
  {
    title: "Decide and sign",
    text: "An authorized person decides and signs, and the audit trail keeps every step. AI is off in the free trial: every step works by hand.",
    href: "/platform/decisions#decision-center",
  },
];

export function HomePage() {
  const home = pages["/"];
  return (
    <>
      <section className="ms-hero">
        <div className="ms-hero-backdrop" aria-hidden="true" />
        <div className="ms-hero-inner">
          <div className="ms-hero-copy">
            <span className="ms-eyebrow ms-eyebrow-light">{home.eyebrow}</span>
            <h1>{home.title}</h1>
            <p>{home.copy}</p>
            <div className="ms-cta-row">
              <a className="ms-btn ms-btn-light" href="/signup">
                Start free trial <ArrowRight size={16} aria-hidden="true" />
              </a>
              {DEMO_REQUESTS_OFFERED && (
                <a className="ms-btn ms-btn-ghost-light" href="/request-demo">
                  Request a demo
                </a>
              )}
              <a className="ms-btn ms-btn-ghost-light" href="/videos">
                Watch the videos
              </a>
              <a className="ms-btn ms-btn-ghost-light" href="/platform">
                Explore the platform
              </a>
            </div>
            <ul className="ms-hero-points">
              <li>
                <Check size={15} aria-hidden="true" /> Works beside your QMS or complaint software
              </li>
              <li>
                <Check size={15} aria-hidden="true" /> Every finding links to its records
              </li>
              <li>
                <Check size={15} aria-hidden="true" /> Authorized humans decide and sign
              </li>
            </ul>
          </div>
          <InvestigationAnimation />
        </div>
      </section>

      <section className="ms-section ms-loop" id="quality-loop">
        <SectionHead
          eyebrow="Inspection readiness"
          title="See your quality loop the way an inspector will."
          copy="Eight checks shaped by what FDA inspections cite and by the EU, UK and Canadian vigilance rules, read from your own records every day. Each one opens the records behind it, and the weakest link is named."
        />
        <Reveal>
          <QualityLoop
            stations={SITE_LOOP}
            eyebrow="Illustrative · synthetic data"
            title="2 of 8 inspection checks clear"
            detail="Hidden complaints, a harm complaint closed without an investigation, a CAPA without an effectiveness check, and field data that never reached the risk file: what an inspector would find first. Your free trial starts with sample data that tells this story."
            doneLabel="clear"
          >
            <a className="ms-btn ms-btn-light" href="/signup">
              Start free trial <ArrowRight size={16} aria-hidden="true" />
            </a>
            {DEMO_REQUESTS_OFFERED && (
              <a className="ms-btn ms-btn-ghost-light" href="/request-demo">
                Book a one-to-one demo
              </a>
            )}
          </QualityLoop>
        </Reveal>
      </section>

      <section className="ms-section ms-band ms-example" aria-labelledby="example-title">
        <SectionHead
          eyebrow="One investigation, start to finish"
          id="example-title"
          title="Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?"
          copy="From a rising signal to the lot, the component and the supplier, reviewed by every function in one place and decided by a person."
        />
        <div className="ms-viz-grid-2">
          <Reveal className="ms-card ms-viz-card">
            <span className="ms-eyebrow">Signal</span>
            <h3>Pressure-alarm complaints per week</h3>
            <WeeklyChart />
          </Reveal>
          <Reveal className="ms-card ms-viz-card" delay={120}>
            <span className="ms-eyebrow">Where it concentrates</span>
            <h3>Complaints per lot</h3>
            <LotChart />
            <p className="ms-viz-read">
              <span className="ms-viz-key ms-viz-key-hot" aria-hidden="true" /> Built with the new supplier's sensors. 2
              of the 42 complaints name no lot.
            </p>
          </Reveal>
        </div>
        <div className="ms-example-team">
          <Reveal className="ms-example-visual">
            <Photo
              src={img("medtech-investigation-team")}
              alt="Cross-functional MedTech team reviewing an investigation together"
            />
          </Reveal>
          <Reveal delay={120}>
            <ol className="ms-example-steps">
              {EXAMPLE_STEPS.map((step, index) => (
                <li key={step.title}>
                  <span className="ms-step-index" aria-hidden="true">
                    0{index + 1}
                  </span>
                  <div>
                    <a href={step.href}>
                      <strong>{step.title}</strong>
                    </a>
                    <p>{step.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Reveal>
        </div>
        <p className="ms-viz-caption">Illustrative example with synthetic data. No customer data is shown.</p>
      </section>

      <SourceFlow />

      <section className="ms-section ms-band ms-trust-short" aria-labelledby="trust-strip-title">
        <SectionHead eyebrow="Trust by design" title="Built for regulated teams." id="trust-strip-title" />
        <div className="ms-grid-4">
          {[
            [Lock, "Isolated data per customer", "The database itself enforces each organization's boundary."],
            [ShieldCheck, "AI off in the trial", "Every step works by hand. AI stays advisory and cites its evidence."],
            [BadgeCheck, "Signed decisions", "Approval authority by role, re-authentication and no self-approval."],
            [ScrollText, "Complete audit trail", "Who did what, when and why, ready to export."],
          ].map(([Icon, title, text], index) => {
            const I = Icon as typeof Lock;
            return (
              <Reveal key={String(title)} delay={index * 80} className="ms-card ms-card-flat">
                <span className="ms-icon">
                  <I size={20} aria-hidden="true" />
                </span>
                <strong>{String(title)}</strong>
                <p>{String(text)}</p>
              </Reveal>
            );
          })}
        </div>
        <Reveal className="ms-trust-links">
          <a className="ms-link" href="/trust/regulations">
            Covers reporting for the US, EU/NI, GB and India (MvPI worksheet){" "}
            <ArrowRight size={14} aria-hidden="true" />
          </a>
          <a className="ms-link" href="/trust">
            How MDARIX earns trust <ArrowRight size={14} aria-hidden="true" />
          </a>
        </Reveal>
      </section>

      <CustomerVoices />
      <CtaBand trial />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Platform */

const AVAILABILITY_TONE: Record<Availability, { tone: "live" | "next" | "planned"; icon: LucideIcon }> = {
  "Available today": { tone: "live", icon: BadgeCheck },
  "In a pilot": { tone: "next", icon: UsersRound },
  Planned: { tone: "planned", icon: CircleDashed },
};

/** A capability's availability, in the roadmap's three labels. */
export function AvailabilityTag({ status }: { status: Availability }) {
  const { tone, icon: Icon } = AVAILABILITY_TONE[status];
  return (
    <span className={`ms-avail is-${tone}`}>
      <Icon size={14} aria-hidden="true" />
      {status}
    </span>
  );
}

/** What the three labels mean, in the roadmap's words, with the way to the roadmap. */
function AvailabilityLegend() {
  return (
    <section className="ms-section ms-band" aria-labelledby="availability-title">
      <SectionHead
        eyebrow="Availability"
        id="availability-title"
        title="Every capability says where it stands."
        copy="The labels are the roadmap's: nothing is marked Available today until it works in a free trial workspace."
      />
      <div className="ms-grid-3">
        {capabilityStatus.map((status, index) => (
          <Reveal key={status.label} delay={index * 80} className="ms-card ms-card-flat">
            <AvailabilityTag status={AVAILABILITY[index]} />
            <p>{status.text}</p>
          </Reveal>
        ))}
      </div>
      <Reveal className="ms-center">
        <a className="ms-link" href="/roadmap">
          See the roadmap <ArrowRight size={14} aria-hidden="true" />
        </a>
      </Reveal>
    </section>
  );
}

function PlatformBoundary() {
  return (
    <section className="ms-section">
      <Reveal className="ms-boundary">
        <strong>MDARIX is a context and investigation layer.</strong>
        <span>
          It complements QMS, PLM, ERP/MES, and supplier systems; it does not replace their authoritative records.
        </span>
      </Reveal>
    </section>
  );
}

function CapabilitySection({ capability }: { capability: PlatformGroup["capabilities"][number] }) {
  const title = productStructureTitles[capability.slug] ?? capability.title;
  return (
    <article id={capability.slug} className="ms-capability" aria-labelledby={`${capability.slug}-title`}>
      <Reveal className="ms-capability-head">
        <div className="ms-capability-copy">
          <div className="ms-capability-label">
            <span className="ms-eyebrow">{capability.label}</span>
            <AvailabilityTag status={capability.availability.status} />
          </div>
          <h2 id={`${capability.slug}-title`}>{title}</h2>
          <p>{capability.summary}</p>
          <p className="ms-capability-note">{capability.availability.note}</p>
        </div>
        <ul className="ms-check-list">
          {capability.cards.map((card) => (
            <li key={card.title}>
              <Check size={16} aria-hidden="true" />
              <span>
                <strong>{card.title}.</strong> {card.text}
              </span>
            </li>
          ))}
        </ul>
      </Reveal>
      {capability.image && (
        <Reveal className="ms-capability-visual">
          <Photo src={capability.image.src} alt={capability.image.alt} />
        </Reveal>
      )}
      <FlowChain steps={capability.steps} label={`${capability.label} workflow`} />
    </article>
  );
}

/** The other Platform pages, at the foot of each one. */
function PlatformPager({ current }: { current?: PlatformPath }) {
  return (
    <nav className="ms-platform-pager" aria-label="Platform pages">
      {platformGroups
        .filter((group) => group.path !== current)
        .map((group) => (
          <a key={group.path} className="ms-card" href={group.path}>
            <span className="ms-eyebrow">Platform</span>
            <strong>{group.name}</strong>
            <span>{group.blurb}</span>
          </a>
        ))}
    </nav>
  );
}

export function PlatformPage() {
  const platform = pages["/platform"];
  return (
    <>
      <PageHero
        eyebrow="Platform"
        title={platform.title}
        copy={platform.copy}
        image={{ src: img("medtech-product-reality-graph-hero"), alt: "Connected product reality graph" }}
      />
      <section className="ms-section" aria-labelledby="platform-pages">
        <SectionHead
          eyebrow="Four pages"
          id="platform-pages"
          title="Every capability, and where it stands today."
          copy="Each page holds its capabilities as sections, and each capability carries its label: Available today, In a pilot or Planned."
        />
        <div className="ms-platform-pages">
          {platformGroups.map((group, index) => (
            <Reveal key={group.path} delay={(index % 2) * 80} className="ms-card ms-platform-card">
              <span className="ms-eyebrow">{group.blurb}</span>
              <h3>
                <a href={group.path}>{group.name}</a>
              </h3>
              <p>{group.copy}</p>
              <ul>
                {group.capabilities.map((capability) => (
                  <li key={capability.slug}>
                    <a href={`${group.path}#${capability.slug}`}>{capability.label}</a>
                    <AvailabilityTag status={capability.availability.status} />
                  </li>
                ))}
              </ul>
              <a className="ms-link" href={group.path}>
                Open {group.name} <ArrowRight size={14} aria-hidden="true" />
              </a>
            </Reveal>
          ))}
        </div>
      </section>
      <AvailabilityLegend />
      <PlatformBoundary />
      <CtaBand />
    </>
  );
}

/** One Platform page: its capabilities as sections, each with its availability. */
export function PlatformGroupPage({ path }: { path: PlatformPath }) {
  const group = platformGroups.find((item) => item.path === path) ?? platformGroups[0];
  const counts = AVAILABILITY.map((status) => ({
    status,
    count: group.capabilities.filter((capability) => capability.availability.status === status).length,
  })).filter((item) => item.count > 0);
  return (
    <>
      <PageHero eyebrow={`Platform · ${group.name}`} title={group.headline} copy={group.copy} center>
        <ul className="ms-avail-summary" aria-label="Where this page's capabilities stand">
          {counts.map((item) => (
            <li key={item.status}>
              <AvailabilityTag status={item.status} />
              <span>
                {item.count} {item.count === 1 ? "capability" : "capabilities"}
              </span>
            </li>
          ))}
        </ul>
      </PageHero>
      <nav className="ms-subnav" aria-label={`${group.name} sections`}>
        {group.capabilities.map((capability) => (
          <a key={capability.slug} href={`#${capability.slug}`}>
            {capability.label}
          </a>
        ))}
      </nav>
      <section className="ms-section ms-platform-group" aria-label={group.name}>
        {group.capabilities.map((capability) => (
          <CapabilitySection key={capability.slug} capability={capability} />
        ))}
      </section>
      {path === "/platform/trust" && (
        <section className="ms-section ms-band">
          <div className="ms-grid-2">
            <Reveal className="ms-card ms-card-flat">
              <strong>Regulations</strong>
              <p>
                Reporting for the US, EU/NI, GB and India (MvPI worksheet), and the standards whose evidence MDARIX
                organizes.
              </p>
              <a className="ms-link" href="/trust/regulations">
                See the regulations <ArrowRight size={14} aria-hidden="true" />
              </a>
            </Reveal>
            <Reveal className="ms-card ms-card-flat" delay={80}>
              <strong>Security and access</strong>
              <p>Organization isolation, sessions and MFA, and what MDARIX does and does not claim today.</p>
              <a className="ms-link" href="/trust#security">
                How MDARIX earns trust <ArrowRight size={14} aria-hidden="true" />
              </a>
            </Reveal>
          </div>
        </section>
      )}
      <AvailabilityLegend />
      <section className="ms-section">
        <PlatformPager current={path} />
      </section>
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Roadmap */

export function RoadmapPage() {
  return (
    <>
      <PageHero
        eyebrow="Roadmap"
        title="Know what is available today, and what comes next."
        copy="Everything marked Available today works in every workspace, the free trial included. What comes in a pilot and what is still planned is labelled as such, so you always know which is which."
        center
      />
      <ScopeClarity />
      <section className="ms-section ms-band" aria-labelledby="roadmap-pages">
        <SectionHead
          eyebrow="Page by page"
          id="roadmap-pages"
          title="Each capability, with its label."
          copy="The Platform pages show every capability with the same three labels."
        />
        <PlatformPager />
      </section>
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Regulations */

export function RegulationsPage() {
  return (
    <>
      <PageHero
        eyebrow="Trust · Regulations"
        title="Built around the evidence regulators ask for."
        copy="Post-market quality work is defined by a few standards and regulations. MDARIX organizes the evidence they call for. It does not certify compliance: your quality system and its validation stay yours."
        center
      />
      <ReportingWindows />
      <StandardsSection
        id="standards"
        title="The standards behind post-market quality work."
        copy="What each one asks for, and how MDARIX helps you show it."
      />
      <section className="ms-section ms-band">
        <div className="ms-grid-2">
          <Reveal className="ms-card ms-card-flat">
            <strong>What MDARIX claims</strong>
            <p>
              MDARIX is not yet a validated (GxP) system and does not hold ISO 27001 or SOC 2 certification. It never
              submits anything to a regulator.
            </p>
            <a className="ms-link" href="/security">
              Security at MDARIX <ArrowRight size={14} aria-hidden="true" />
            </a>
          </Reveal>
          <Reveal className="ms-card ms-card-flat" delay={80}>
            <strong>Human decisions, recorded</strong>
            <p>
              Reportability decisions are recorded by a named person with their reason. Investigation decisions are
              signed electronically, with re-authentication.
            </p>
            <a className="ms-link" href="/platform/trust">
              Trust on the Platform <ArrowRight size={14} aria-hidden="true" />
            </a>
          </Reveal>
        </div>
      </section>
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Solutions */

export function SolutionsPage() {
  const solutions = pages["/solutions"];
  const featured = menus.Solutions.find((group) => group.title === "Investigate with MDARIX")?.items[0];
  return (
    <>
      <PageHero
        eyebrow={solutions.eyebrow}
        title={solutions.title}
        copy={solutions.copy}
        image={{
          src: img("medtech-solution-complaints"),
          alt: "Complaint signals connected to product versions and evidence",
        }}
      />
      <nav className="ms-subnav" aria-label="Solution sections">
        {solutionGroups.map((group) => (
          <a key={group.id} href={`#${group.id}`}>
            {group.title}
          </a>
        ))}
      </nav>
      {featured && (
        <section className="ms-section">
          <Reveal className="ms-featured">
            <span className="ms-eyebrow">Investigate with MDARIX</span>
            <h2>{featured.label}</h2>
            <p>{featured.description}</p>
            <FlowChain steps={QUESTION_FLOW} label="Investigation flow" />
          </Reveal>
        </section>
      )}
      {solutionGroups.map((group) => (
        <section key={group.id} className="ms-section" aria-labelledby={group.id}>
          <SectionHead eyebrow="Solutions" title={group.title} id={group.id} />
          <div className="ms-solution-grid">
            {group.items.map((item, index) => (
              <Reveal key={item.key} delay={(index % 3) * 80} className="ms-solution">
                <article id={item.key}>
                  {item.image && <Photo src={item.image.src} alt={item.image.alt} />}
                  <span className="ms-eyebrow">{item.label}</span>
                  <h3>{item.title}</h3>
                  <p>{item.copy}</p>
                  {item.short && <p className="ms-muted">{item.short.copy}</p>}
                </article>
              </Reveal>
            ))}
          </div>
        </section>
      ))}
      <section className="ms-section ms-band">
        <SectionHead eyebrow="End-to-end solution story" title="Every solution follows the same governed path." />
        <div className="ms-grid-4">
          {[
            ["Frame the question", "Define the signal, scope, time window, and accountable review team."],
            [
              "Connect the context",
              "Bring product, version, change, supplier, lot, complaint, and evidence context together.",
            ],
            [
              "Inspect the uncertainty",
              "Separate what is observed from what is inferred, contradicted, missing, or still unknown.",
            ],
            [
              "Move to governed action",
              "Preserve provenance and limitations while authorized humans review and decide.",
            ],
          ].map(([title, text], index) => (
            <Reveal key={title} delay={index * 80} className="ms-card">
              <span className="ms-step-index">0{index + 1}</span>
              <strong>{title}</strong>
              <p>{text}</p>
            </Reveal>
          ))}
        </div>
      </section>
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Lifecycle */

export function LifecyclePage() {
  const lifecycle = pages["/product-lifecycle"];
  const roadmap = pages["/roadmap"];
  return (
    <>
      <PageHero eyebrow={lifecycle.eyebrow} title={lifecycle.title} copy={lifecycle.copy} visual={<LifecycleHero />} />
      <section className="ms-section">
        <div className="ms-legend-row">
          <span className="ms-badge ms-badge-current">
            <BadgeCheck size={14} aria-hidden="true" /> Current capability
          </span>
          <span className="ms-badge ms-badge-future">
            <CircleDashed size={14} aria-hidden="true" /> Future — informational only
          </span>
        </div>
        <div className="ms-lifecycle">
          {lifecycleStages.map((stage, stageIndex) => (
            <Reveal key={stage.id} delay={stageIndex * 90} className="ms-stage">
              <h2 id={stage.id}>{stage.title}</h2>
              <ul>
                {stage.items.map((item) => (
                  <li key={item.slug} className={item.future ? "is-future" : ""}>
                    {item.href ? <a href={item.href}>{item.label}</a> : <span>{item.label}</span>}
                    <small>{item.future ? "Future" : "Current"}</small>
                  </li>
                ))}
              </ul>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="ms-section ms-band" aria-labelledby="design-phases">
        <SectionHead
          id="design-phases"
          eyebrow="Design and development"
          title="Medical device design and development phases."
          copy="Each phase leaves design-control records: user needs, design inputs and outputs, verification, validation and the risk file. When a field problem appears, investigators trace back through those records, which is where MDARIX starts."
        />
        <DesignPhases />
      </section>
      <section className="ms-section">
        <SectionHead eyebrow="Current capabilities" title="Lifecycle intelligence available today." />
        <div className="ms-solution-grid">
          {lifecycleStages
            .flatMap((stage) => stage.items)
            .filter((item) => !item.future && item.copy)
            .map((item, index) => (
              <Reveal key={item.slug} delay={(index % 3) * 80} className="ms-solution">
                <article id={item.slug}>
                  <span className="ms-eyebrow">{item.label}</span>
                  <h3>{item.title}</h3>
                  <p>{item.copy}</p>
                </article>
              </Reveal>
            ))}
        </div>
      </section>
      <section className="ms-section ms-band" id="roadmap">
        <SectionHead eyebrow={roadmap.eyebrow} title={roadmap.title} copy={roadmap.copy} />
        <div className="ms-grid-2">
          <Reveal className="ms-card">
            <span className="ms-badge ms-badge-current">Available</span>
            <h3>Current capabilities</h3>
            <p>
              Products, versions and lots, temporal context, the second look at closed complaints, reporting clocks,
              signals and trend checks, investigations with evidence, hypotheses and open questions, signed decisions,
              CAPA effectiveness checks, risk-file input, the inspector summary, and the audit trail.
            </p>
            <a className="ms-link" href="/roadmap">
              See the roadmap <ArrowRight size={14} aria-hidden="true" />
            </a>
          </Reveal>
          <Reveal className="ms-card" delay={100}>
            <span className="ms-badge ms-badge-future">Future</span>
            <h3>Broader lifecycle intelligence</h3>
            <p>
              Strategy, requirements, design controls, regulatory, clinical, manufacturing operations, field actions and
              recalls, continuous monitoring, and retirement remain roadmap areas. AI assistance is switched on in a
              pilot once it is validated.
            </p>
          </Reveal>
        </div>
        <SectionHead
          eyebrow="Future"
          title="Where the lifecycle vision goes next."
          copy="Planned as part of the broader MDARIX Medical Device Product Lifecycle Intelligence platform. This section is informational and does not represent available functionality."
        />
        <div className="ms-solution-grid">
          {lifecycleStages
            .flatMap((stage) => stage.items)
            .filter((item) => item.future && item.copy)
            .map((item, index) => (
              <Reveal key={item.slug} delay={(index % 3) * 60} className="ms-solution ms-solution-future">
                <article id={item.slug}>
                  <span className="ms-badge ms-badge-future">Future</span>
                  <span className="ms-eyebrow">{item.label}</span>
                  <h3>{item.title}</h3>
                  <p>{item.copy}</p>
                </article>
              </Reveal>
            ))}
        </div>
      </section>
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Trust */

export function TrustPage() {
  const why = pages["/why-mdarix"];
  const ai = pages["/ai-trust"];
  const security = pages["/security"];
  const integrations = pages["/integrations"];
  const principles = menus.Trust.slice(0, 2).flatMap((group) => group.items);
  const questions = menus.Trust.find((group) => group.title === "Questions MDARIX Helps Explore")?.items ?? [];
  return (
    <>
      <PageHero
        eyebrow={why.eyebrow}
        title={why.title}
        copy={why.copy}
        image={{
          src: img("medtech-hero-human-review"),
          alt: "Reviewers examining evidence before approving a decision",
        }}
      />
      <nav className="ms-subnav" aria-label="Trust sections">
        <a href="#principles">Principles</a>
        <a href="#ai">AI trust</a>
        <a href="/trust/regulations">Regulations</a>
        <a href="#security">Security &amp; access</a>
        <a href="#integrations">Integrations</a>
      </nav>

      <section className="ms-section" aria-labelledby="principles">
        <SectionHead
          eyebrow="A different intelligence layer"
          title="The principles behind every screen."
          id="principles"
        />
        <div className="ms-grid-4">
          {principles.map((item, index) => (
            <Reveal key={item.label} delay={(index % 4) * 70} className="ms-card">
              <strong id={item.href.split("#").pop()}>{item.label}</strong>
              <p>{item.description ?? principleCopy[item.label] ?? ""}</p>
            </Reveal>
          ))}
        </div>
        <Reveal className="ms-question-chips">
          <span className="ms-eyebrow">Questions MDARIX helps explore</span>
          <div className="ms-chip-row">
            {questions.map((item) => (
              <a key={item.label} className="ms-chip" href={item.href}>
                {item.label}
              </a>
            ))}
          </div>
        </Reveal>
      </section>

      <section className="ms-section ms-band ms-split" aria-labelledby="ai">
        <Reveal className="ms-split-copy">
          <span className="ms-eyebrow">{ai.eyebrow}</span>
          <h2 id="ai">{ai.title}</h2>
          <p>{ai.copy}</p>
          <ul className="ms-check-list">
            <li>
              <Check size={16} aria-hidden="true" />
              <span>Answers cite the authorized evidence they were built from.</span>
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              <span>When evidence is thin, MDARIX holds back instead of guessing.</span>
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              <span>No unsupported root-cause claims; interpretation stays separate from observation.</span>
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              <span>Authorized humans review, decide and sign.</span>
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              <span>
                AI is switched on per organization by its administrator. It is off in the free trial while it is
                validated, and every step works by hand.
              </span>
            </li>
          </ul>
        </Reveal>
        <Reveal delay={120}>
          <Photo src={img("medtech-hero-ai-assurance")} alt="AI assurance workspace with validation checkpoints" />
        </Reveal>
      </section>

      <section className="ms-section" aria-labelledby="regulations-link">
        <Reveal className="ms-card ms-card-flat ms-regulations-link">
          <span className="ms-eyebrow">Regulations</span>
          <strong id="regulations-link">Built around the evidence regulators ask for.</strong>
          <p>
            Reporting windows for the US, EU/NI, GB and India (MvPI worksheet), and the standards whose evidence MDARIX
            organizes. MDARIX does not certify compliance: your quality system and its validation stay yours.
          </p>
          <a className="ms-link" href="/trust/regulations">
            See the regulations <ArrowRight size={14} aria-hidden="true" />
          </a>
        </Reveal>
      </section>

      <section className="ms-section" aria-labelledby="security">
        <SectionHead eyebrow={security.eyebrow} title={security.title} copy={security.copy} id="security" />
        <div className="ms-grid-3">
          {[
            [
              Lock,
              "Organization isolation",
              "Each organization's data is scoped to it on every request and enforced by the database (row-level security).",
            ],
            [
              UserCheck,
              "Identity and sessions",
              "Authenticator-app MFA (single sign-on is planned), sign-out after 30 minutes without activity, a 12-hour limit on any session, and immediate sign-out when access is suspended.",
            ],
            [
              ShieldCheck,
              "Least privilege",
              "Role-based access, approval authority by role, segregation of duties, and protected platform roles.",
            ],
          ].map(([Icon, title, text], index) => {
            const I = Icon as typeof Lock;
            return (
              <Reveal key={String(title)} delay={index * 80} className="ms-card">
                <span className="ms-icon">
                  <I size={20} aria-hidden="true" />
                </span>
                <strong>{String(title)}</strong>
                <p>{String(text)}</p>
              </Reveal>
            );
          })}
        </div>
        <div className="ms-subsection">
          <SectionHead
            eyebrow="What we claim"
            title="What MDARIX can accurately say today."
            copy="These statements describe controls in the product today. They are not certification claims."
          />
        </div>
        <div className="ms-grid-2">
          {[
            [
              "Implemented controls",
              "Authorization scoped to each organization, role and field policies, audit records, provenance, human approval controls, and advisory AI safeguards are built into the product.",
            ],
            [
              "Pilot boundary",
              `MDARIX is not yet a validated (GxP) system. Design-partner pilots use exported records without patient-identifiable information. ${BESIDE_YOUR_QMS}`,
            ],
            [
              "Certification status",
              "MDARIX does not claim ISO 27001 certification, HIPAA compliance, GDPR compliance, or 21 CFR Part 11 compliance on this site.",
            ],
            [
              "Evidence availability",
              "Validation protocols, test reports, and approved non-confidential sample dossiers may be shared during a controlled review. No confidential customer material is published.",
            ],
          ].map(([title, text], index) => (
            <Reveal key={title} delay={(index % 2) * 80} className="ms-card ms-card-flat">
              <strong>{title}</strong>
              <p>{text}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="ms-section ms-band ms-split" aria-labelledby="integrations">
        <Reveal className="ms-split-copy">
          <span className="ms-eyebrow">{integrations.eyebrow}</span>
          <h2 id="integrations">{integrations.title}</h2>
          <p>{integrations.copy}</p>
          <ul className="ms-check-list">
            <li>
              <Check size={16} aria-hidden="true" />
              <span>Start with file exports from your existing systems; live connections are built in a pilot.</span>
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              <span>Versioned, governed mappings from your fields to the MDARIX model, released with approval.</span>
            </li>
            <li>
              <Check size={16} aria-hidden="true" />
              <span>Source-system API keys are encrypted at rest and never shown again.</span>
            </li>
          </ul>
        </Reveal>
        <Reveal delay={120}>
          <figure className="ms-diagram">
            <img
              src="/medtech-source-network.svg"
              alt="QMS, PLM, ERP/MES and supplier systems connected to a governed MDARIX workspace"
            />
            <figcaption>Connected source systems, governed mappings, and traceable investigation context.</figcaption>
          </figure>
        </Reveal>
      </section>
      <CtaBand />
    </>
  );
}

const principleCopy: Record<string, string> = {
  "Challenge the Explanation":
    "Test the leading explanation against contradicting evidence and alternatives before it becomes a conclusion.",
  "AI You Can Inspect": "AI-assisted answers show the evidence they used and flag anything unverified.",
  "Humans Decide": "AI supports investigation. Authorized humans make controlled decisions.",
};

/* ------------------------------------------------------------------------------------------------ Resources */

export function ResourcesPage() {
  const resources = pages["/resources"];
  return (
    <>
      <PageHero
        eyebrow={resources.eyebrow}
        title={resources.title}
        copy={resources.copy}
        image={{
          src: img("medtech-resource-pms-signals"),
          alt: "Post-market surveillance signals reviewed by a quality team",
        }}
      />
      <section className="ms-section">
        <SectionHead
          eyebrow="Explore by topic"
          title="Follow an investigation from signal to decision."
          copy="See how MDARIX moves from a product signal to a traceable, reviewable decision while keeping evidence, uncertainty, and human authority visible."
        />
        <div className="ms-grid-3">
          {[
            [
              "Investigation scenarios",
              "Complaint increases, product changes, supplier issues, affected lots, and missing evidence.",
              "/solutions#challenges",
              "See the scenarios",
            ],
            [
              "Trust & governance",
              "AI assurance, provenance, role boundaries, audit trails, and controlled human review.",
              "/trust#ai",
              "Review trust controls",
            ],
            [
              "Lifecycle perspectives",
              "Discover, develop, prove, release, monitor, improve, and evolve with connected context.",
              "/product-lifecycle",
              "Explore lifecycle",
            ],
          ].map(([title, text, href, action], index) => (
            <Reveal key={title} delay={index * 80} className="ms-card">
              <strong>{title}</strong>
              <p>{text}</p>
              <a className="ms-link" href={href}>
                {action} <ArrowRight size={14} aria-hidden="true" />
              </a>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="ms-section ms-band" aria-labelledby="resources-questions">
        <SectionHead
          eyebrow="Questions and answers"
          id="resources-questions"
          title="Direct answers to the questions quality teams ask."
          copy="Trending complaints, reportability, the risk file and CAPA effectiveness: a short answer first, then the explanation and what MDARIX does about it."
        />
        <div className="ms-grid-3">
          {QUESTIONS.map((question, index) => (
            <Reveal key={question.path} delay={(index % 3) * 80} className="ms-card ms-card-flat">
              <strong>
                <a href={question.path}>{question.question}</a>
              </strong>
              <p>{question.summary}</p>
            </Reveal>
          ))}
        </div>
        <Reveal className="ms-center">
          <a className="ms-link" href={QUESTIONS_PATH}>
            All questions and answers <ArrowRight size={14} aria-hidden="true" />
          </a>
        </Reveal>
      </section>
      <section className="ms-section">
        <SectionHead
          eyebrow="Free trial videos"
          title="Watch the free trial, step by step."
          copy="Fourteen short videos follow a quality manager through the 30-day trial, from signing up to every chapter of the story, with English captions."
        />
        <a className="ms-link" href="/videos">
          Watch the videos <ArrowRight size={14} aria-hidden="true" />
        </a>
      </section>
      <section className="ms-section ms-band">
        <SectionHead
          eyebrow="MedTech intelligence desk"
          title="AI, safety signals, and post-market surveillance."
          copy="Explore how medical-device teams monitor real-world performance, investigate emerging signals, and keep AI-enabled devices under human oversight across the product lifecycle."
        />
        <div className="ms-resource-pictures">
          {[
            [
              "medtech-resource-pms-signals",
              "Medical-device post-market surveillance signals reviewed by a quality team",
              "Post-market signals",
            ],
            [
              "medtech-resource-ai-lifecycle",
              "AI-enabled medical device lifecycle monitoring and performance review",
              "AI lifecycle monitoring",
            ],
            [
              "medtech-resource-regulatory-intelligence",
              "Regulatory intelligence and source provenance for AI medical devices",
              "Regulatory intelligence",
            ],
          ].map(([name, alt, caption]) => (
            <Reveal key={name}>
              <Photo src={img(name)} alt={alt} />
              <div>
                <h3>{caption}</h3>
                <p>{alt}.</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="ms-section" aria-labelledby="latest-pms-resources">
        <SectionHead
          eyebrow="Latest reading · AI and post-market surveillance"
          title="Current regulatory and industry publications for MedTech teams."
          id="latest-pms-resources"
          copy="Curated links to official regulator and public-health sources. MDARIX does not replace regulatory advice; use the original source for the current text, scope, and applicability."
        />
        <div className="ms-grid-2">
          {postMarketResources.map((resource, index) => (
            <Reveal key={resource.href} delay={(index % 2) * 70} className="ms-card ms-resource">
              <div className="ms-resource-meta">
                <span>{resource.type}</span>
                {resource.date ? <time dateTime={resource.date}>{resource.date}</time> : <span>Reference page</span>}
              </div>
              <h3>{resource.title}</h3>
              <p>{resource.text}</p>
              <a className="ms-link" href={resource.href} target="_blank" rel="noreferrer">
                Open official source <ArrowRight size={14} aria-hidden="true" />
              </a>
            </Reveal>
          ))}
        </div>
      </section>
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Company */

export function CompanyPage() {
  const company = pages["/company"];
  const contact = pages["/request-demo"];
  return (
    <>
      <PageHero
        eyebrow={company.eyebrow}
        title={company.title}
        copy={company.copy}
        image={{
          src: img("medtech-role-quality-leaders"),
          alt: "Quality leaders reviewing signals, evidence and decisions",
        }}
      />
      <section className="ms-section" aria-labelledby="positioning-title">
        <SectionHead
          eyebrow="Positioning"
          title="An investigation intelligence layer for medical-device teams."
          id="positioning-title"
          copy="MDARIX is designed for quality, regulatory, product, supplier-quality, and manufacturing teams investigating a product signal across systems of record."
        />
        <div className="ms-grid-4">
          {[
            [
              "Where MDARIX fits",
              "MDARIX connects product context, complaints, changes, suppliers, lots, evidence, uncertainty, and human decisions. Your QMS keeps the complaint record, CAPA and change control.",
            ],
            [
              "What makes MDARIX different",
              "MDARIX focuses on evidence-bounded investigation: relationships are visible, competing explanations remain separate, missing evidence is explicit, and AI remains advisory.",
            ],
            [
              "What MDARIX is not",
              `It does not replace your QMS, PLM or ERP. ${BESIDE_YOUR_QMS} MDARIX is not a regulatory submission system: it never submits anything to a regulator.`,
            ],
            [
              "Design-partner outcome",
              "During a pilot, MDARIX records when each investigation is opened and closed, every data import with its result, every reportability decision with its reason, and every investigation decision with its review and signature, so the pilot can be reviewed from the audit trail.",
            ],
          ].map(([title, text], index) => (
            <Reveal key={title} delay={index * 80} className="ms-card">
              <strong>{title}</strong>
              <p>{text}</p>
            </Reveal>
          ))}
        </div>
      </section>
      <section className="ms-section ms-band ms-split" id="contact" aria-labelledby="contact-title">
        <Reveal className="ms-split-copy">
          <span className="ms-eyebrow">{contact.eyebrow}</span>
          <h2 id="contact-title">{contact.title}</h2>
          <p>{contact.copy}</p>
          <ol className="ms-trial-steps">
            {[
              [
                "Request your free trial",
                "Tell us your name, company and work email. With a company or personal email your trial is approved automatically and ready within minutes, up to a daily limit; requests from disposable email addresses are reviewed by the MDARIX team, usually within one business day.",
              ],
              [
                "Explore a ready-made investigation",
                "Activate your account from the invitation email. Your private workspace opens with sample data: products, lots, complaints and an investigation to follow.",
              ],
              [
                "Try it on your own data",
                "Download the CSV templates for products, lots, complaints and the components, suppliers, changes and risks around them. Every file is checked for problems and personal data before import, and insights appear straight away.",
              ],
            ].map(([title, text], index) => (
              <li key={title}>
                <span aria-hidden="true">{index + 1}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{text}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="ms-trial-steps-note">
            30 days · up to 3 users · 5,000 uploaded rows. Want live connections to your QMS, PLM or ERP? Ask about
            becoming a design partner.
          </p>
          <div className="ms-cta-row">
            <a className="ms-btn ms-btn-primary" href="/signup">
              Start free trial <ArrowRight size={16} aria-hidden="true" />
            </a>
            <a className="ms-btn ms-btn-outline" href="/signin">
              Sign in
            </a>
          </div>
        </Reveal>
        <Reveal delay={120}>
          <Photo
            src={img("medtech-role-investigators")}
            alt="Medical-device investigators connecting complaints, versions, suppliers and lots"
          />
        </Reveal>
      </section>
      <section className="ms-section" id="after-the-trial" aria-labelledby="after-the-trial-title">
        <SectionHead
          eyebrow={afterTheTrial.eyebrow}
          title={afterTheTrial.title}
          id="after-the-trial-title"
          copy={afterTheTrial.copy}
        />
        <div className="ms-grid-4">
          {afterTheTrial.points.map(([title, text], index) => (
            <Reveal key={title} delay={index * 80} className="ms-card">
              <strong>{title}</strong>
              <p>{text}</p>
            </Reveal>
          ))}
        </div>
      </section>
    </>
  );
}
