import type { ReactNode } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Check,
  CircleDashed,
  Lock,
  Network,
  ScrollText,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from "lucide-react";
import { menus, pages, postMarketResources } from "./legacyContent";
import { DEMO_REQUESTS_OFFERED } from "./offer";
import {
  capabilityStatus,
  img,
  lifecycleStages,
  platformGroups,
  productStructureTitles,
  solutionGroups,
  type Capability,
} from "./content";
import { FlowChain, InvestigationAnimation, Photo, Reveal } from "./motion";
import { CustomerVoices, LifecycleHero, SignalStory, SourceFlow, StandardsSection } from "./visuals";
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
  "/solutions",
  "/product-lifecycle",
  "/trust",
  "/resources",
  "/company",
] as const;
export type SitePage = (typeof SITE_PAGES)[number];

const QUESTION_FLOW = [
  "Complaint signal",
  "ProductVersion",
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
  children,
}: {
  eyebrow: string;
  title: string;
  copy: string;
  image?: { src: string; alt: string; contain?: boolean };
  visual?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="ms-page-hero">
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

function CtaBand() {
  return (
    <section className="ms-cta-band">
      <Reveal>
        <span className="ms-eyebrow">Design partners</span>
        <h2>Bring one real investigation. See the whole story in one place.</h2>
        <p>
          Start with exports from your quality, product and supplier systems. Your systems of record stay where they
          are.
        </p>
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

function ScopeClarity() {
  return (
    <section className="ms-section ms-scope" aria-labelledby="scope-title">
      <SectionHead
        eyebrow="What you get"
        title="Know what is available today."
        id="scope-title"
        copy="What works in every workspace now, what we build with design partners, and what is still planned."
      />
      <div className="ms-grid-3">
        {capabilityStatus.map((status, index) => (
          <Reveal key={status.label} delay={index * 80} className="ms-card ms-card-flat">
            <strong>{status.label}</strong>
            <p>{status.text}</p>
            <ul className="ms-check-list">
              {status.items.map((item) => (
                <li key={item}>
                  <Check size={16} aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ Home */

export function HomePage() {
  const home = pages["/"];
  const steps = [
    {
      title: "Reconstruct product reality",
      text: "Relate products, versions, components, suppliers, lots, changes, complaints, risks, and evidence.",
      image: img("medtech-product-360-device"),
      alt: "Medical device shown with its product structure and versions",
      href: "/platform#product-intelligence",
    },
    {
      title: "Investigate with evidence",
      text: "Separate observations, interpretations, hypotheses, contradictions, unknowns, and decisions.",
      image: img("medtech-evidence-intelligence-hero"),
      alt: "Evidence records connected with provenance",
      href: "/platform#investigation-intelligence",
    },
    {
      title: "Challenge before concluding",
      text: "Compare competing explanations and keep missing evidence visible before anyone decides.",
      image: img("medtech-hero-challenger"),
      alt: "Competing explanations compared against evidence",
      href: "/platform#challenger",
    },
    {
      title: "Decide, sign and trace",
      text: "AI supports investigation. Authorized humans make controlled decisions, with a full audit trail.",
      image: img("medtech-decision-center-hero"),
      alt: "Reviewer preparing a decision with the evidence package",
      href: "/platform#decision-intelligence",
    },
  ];
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
              <a className="ms-btn ms-btn-ghost-light" href="/platform">
                Explore the platform
              </a>
            </div>
            <ul className="ms-hero-points">
              <li>
                <Check size={15} aria-hidden="true" /> Works above QMS, PLM, ERP and supplier systems
              </li>
              <li>
                <Check size={15} aria-hidden="true" /> AI answers show their evidence
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
          copy="From the complaint that comes in to the risk file it must reach: eight checks drawn from 2026 FDA warning letters, read from your own records every day. Each one opens the records behind it, and the weakest link is named."
        />
        <Reveal>
          <QualityLoop
            stations={SITE_LOOP}
            eyebrow="Illustrative · synthetic data"
            title="2 of 8 inspection checks clear"
            detail="Hidden complaints, a harm complaint closed without an investigation, a CAPA closed without an effectiveness check, and post-market data that never reached the risk file: what an inspector would find first. Your free trial starts with sample data that tells this story, then reads your own export."
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

      <section className="ms-section ms-question">
        <SectionHead
          eyebrow="A product investigation question"
          title="Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?"
          copy="MDARIX helps teams follow the question across product reality, evidence, uncertainty, assurance, and controlled human decision-making."
        />
        <Reveal>
          <FlowChain steps={QUESTION_FLOW} label="Investigation flow from complaint signal to human decision" />
        </Reveal>
      </section>

      <section className="ms-section">
        <SectionHead
          eyebrow="How MDARIX works"
          title="From field signal to a decision you can defend."
          copy="One connected path, from the first signal to an authorized decision, with every step traceable."
        />
        <div className="ms-steps">
          {steps.map((step, index) => (
            <Reveal key={step.title} delay={index * 90} className="ms-step">
              <a href={step.href}>
                <Photo src={step.image} alt={step.alt} />
                <span className="ms-step-index">0{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
                <span className="ms-link">
                  Learn more <ArrowRight size={14} aria-hidden="true" />
                </span>
              </a>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="ms-section ms-band">
        <SectionHead
          eyebrow="A different intelligence layer"
          title="Keep your systems of record. Connect the investigation."
        />
        <div className="ms-grid-4">
          {[
            [
              Network,
              "Product reality",
              "Relate products, versions, components, suppliers, lots, changes, complaints, risks, and evidence.",
            ],
            [
              ScrollText,
              "Evidence before inference",
              "Separate observations, interpretations, hypotheses, contradictions, unknowns, and decisions.",
            ],
            [
              Sparkles,
              "AI you can inspect",
              "Show grounding, temporal context, ProductVersion validation, provenance, and limitations.",
            ],
            [UserCheck, "Humans decide", "AI supports investigation. Authorized humans make controlled decisions."],
          ].map(([Icon, title, text], index) => {
            const I = Icon as typeof Network;
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
      </section>

      <SourceFlow />
      <SignalStory />

      <section className="ms-section ms-split">
        <Reveal className="ms-split-copy">
          <span className="ms-eyebrow">Built for MedTech investigation teams</span>
          <h2>Bring quality, regulatory, product, supplier, and manufacturing context into one review.</h2>
          <p>
            MDARIX helps cross-functional teams inspect the same product reality while preserving source ownership,
            evidence provenance, uncertainty, and accountable human decisions.
          </p>
          <div className="ms-chip-row">
            {menus.Solutions[1].items.map((role) => (
              <a key={role.label} href={role.href.replace("/solutions#", "/solutions#")} className="ms-chip">
                {role.label}
              </a>
            ))}
          </div>
        </Reveal>
        <Reveal delay={120}>
          <Photo
            src={img("medtech-investigation-team")}
            alt="Cross-functional MedTech team reviewing an investigation together"
            caption="Product reality → signals → evidence → governed decision"
          />
        </Reveal>
      </section>

      <section className="ms-section">
        <div className="ms-grid-3">
          {[
            [
              "Quality signal loop",
              "From field signal to controlled action.",
              "Follow complaints and service observations through product version, affected lots, evidence review, and an accountable human decision.",
              "/medtech-quality-loop.svg",
              "Workflow from field signal through triage, evidence review, action, and effectiveness check",
            ],
            [
              "Evidence chain",
              "Make every conclusion traceable.",
              "Keep source records, observations, competing hypotheses, unknowns, and approvals visible in the same investigation story.",
              "/medtech-evidence-chain.svg",
              "Evidence chain linking source records to observations, hypotheses, and decisions",
            ],
            [
              "Connected systems",
              "Work above the systems you already use.",
              "Connect QMS, PLM, ERP, supplier, and manufacturing context through governed mappings while each source remains authoritative.",
              "/medtech-source-network.svg",
              "Connected medical device systems feeding a governed MDARIX investigation workspace",
            ],
          ].map(([eyebrow, title, text, src, alt], index) => (
            <Reveal key={eyebrow} delay={index * 90} className="ms-card ms-card-diagram">
              <span className="ms-eyebrow">{eyebrow}</span>
              <h3>{title}</h3>
              <p>{text}</p>
              <img src={src} alt={alt} loading="lazy" />
            </Reveal>
          ))}
        </div>
      </section>

      <StandardsSection id="standards" />

      <section className="ms-section ms-trust-strip">
        <SectionHead
          eyebrow="Trust by design"
          title="Built for regulated teams from the first line of code."
          copy="Your data stays in your organization's space, AI stays advisory and cited, and every decision is signed and recorded."
        />
        <div className="ms-grid-4">
          {[
            [
              Lock,
              "Isolated data per customer",
              "Every record belongs to one organization; the database itself enforces the boundary on every query.",
            ],
            [
              ShieldCheck,
              "Grounded, bounded AI",
              "Answers cite authorized evidence and hold back when the evidence is thin.",
            ],
            [
              BadgeCheck,
              "Controlled signatures",
              "Approval authority by role, re-authentication and no self-approval.",
            ],
            [ScrollText, "Complete audit trail", "Who did what, when and why, ready to export for review."],
          ].map(([Icon, title, text], index) => {
            const I = Icon as typeof Lock;
            return (
              <Reveal key={String(title)} delay={index * 80} className="ms-card ms-card-dark">
                <I size={20} aria-hidden="true" />
                <strong>{String(title)}</strong>
                <p>{String(text)}</p>
              </Reveal>
            );
          })}
        </div>
        <Reveal className="ms-center">
          <a className="ms-link" href="/trust">
            How MDARIX earns trust <ArrowRight size={14} aria-hidden="true" />
          </a>
        </Reveal>
      </section>

      <CustomerVoices />
      <ScopeClarity />
      <CtaBand />
    </>
  );
}

/* ------------------------------------------------------------------------------------------------ Platform */

function CapabilitySection({ capability, index }: { capability: Capability; index: number }) {
  return (
    <article id={capability.slug} className={`ms-capability ${index % 2 ? "ms-capability-flip" : ""}`}>
      <Reveal className="ms-capability-copy">
        <span className="ms-eyebrow">{capability.label}</span>
        <h3>{productStructureTitles[capability.slug] ?? capability.title}</h3>
        <p>{capability.summary}</p>
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
        <FlowChain steps={capability.steps} label={`${capability.label} workflow`} />
      </Reveal>
      {capability.image && (
        <Reveal delay={120}>
          <Photo src={capability.image.src} alt={capability.image.alt} />
        </Reveal>
      )}
    </article>
  );
}

export function PlatformPage() {
  const platform = pages["/platform"];
  return (
    <>
      <PageHero
        eyebrow={platform.eyebrow}
        title={platform.title}
        copy={platform.copy}
        image={{ src: img("medtech-product-reality-graph-hero"), alt: "Connected product reality graph" }}
      />
      <nav className="ms-subnav" aria-label="Platform sections">
        {platformGroups.map((group) => (
          <a key={group.id} href={`#${group.id}`}>
            {group.title}
          </a>
        ))}
      </nav>
      {platformGroups.map((group) => (
        <section key={group.id} className="ms-section ms-platform-group" aria-labelledby={group.id}>
          <SectionHead
            eyebrow="Platform"
            title={group.title}
            id={group.id}
            copy={group.capabilities.map((capability) => capability.label).join(" · ")}
          />
          {group.capabilities.map((capability, index) => (
            <CapabilitySection key={capability.slug} capability={capability} index={index} />
          ))}
        </section>
      ))}
      <section className="ms-section ms-band">
        <Reveal className="ms-boundary">
          <strong>MDARIX Product 360 is a context and investigation layer.</strong>
          <span>
            It complements QMS, PLM, ERP/MES, and supplier systems; it does not replace their authoritative records.
          </span>
        </Reveal>
      </section>
      <ScopeClarity />
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
        <Reveal className="ms-lc-phases">
          <Photo
            src={img("medtech-product-lifecycle-hero")}
            alt="Medical device design and development phases 0 to 6: concept and ideation, user needs and feasibility, design inputs and prototyping, detailed design and design controls, verification and validation, manufacturing transfer and regulatory submission, post-market surveillance and feedback loops"
            className="ms-photo-contain"
          />
        </Reveal>
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
              Product 360, Product Reality Graph, temporal context, evidence intelligence, investigation, hypotheses,
              challenger, unknowns, failure chain, counterfactuals, decisions, assurance, and governance foundations.
            </p>
          </Reveal>
          <Reveal className="ms-card" delay={100}>
            <span className="ms-badge ms-badge-future">Future</span>
            <h3>Broader lifecycle intelligence</h3>
            <p>
              Strategy, requirements, design controls, regulatory, clinical, manufacturing operations, CAPA, recall,
              continuous monitoring, and retirement remain roadmap areas.
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
          </ul>
        </Reveal>
        <Reveal delay={120}>
          <Photo src={img("medtech-hero-ai-assurance")} alt="AI assurance workspace with validation checkpoints" />
        </Reveal>
      </section>

      <StandardsSection id="trust-standards" />

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
              "Authenticator-app MFA (single sign-on is planned), 60-minute sessions, idle sign-out, and immediate sign-out when access is suspended.",
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
              "MDARIX is not yet a validated (GxP) system. Design-partner pilots use exported records without patient-identifiable information, and your systems of record stay authoritative.",
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
              <span>
                Start with file exports from your existing systems; move to live connections when you are ready.
              </span>
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
      <section className="ms-section ms-band">
        <SectionHead
          eyebrow="MedTech intelligence desk"
          title="AI, safety signals, and post-market surveillance."
          copy="Explore how medical-device teams monitor real-world performance, investigate emerging signals, and keep AI-enabled devices under human oversight across the product lifecycle."
        />
        <div className="ms-grid-3">
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
          ].map(([name, alt, caption], index) => (
            <Reveal key={name} delay={index * 80}>
              <Photo src={img(name)} alt={alt} caption={caption} />
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
              "MDARIX connects product context, complaints, changes, suppliers, lots, evidence, uncertainty, and human decisions. QMS, PLM, ERP, and supplier systems remain authoritative.",
            ],
            [
              "What makes MDARIX different",
              "MDARIX focuses on evidence-bounded investigation: relationships are visible, competing explanations remain separate, missing evidence is explicit, and AI remains advisory.",
            ],
            [
              "What MDARIX is not",
              "It does not replace your QMS, PLM or ERP, and it is not a regulatory submission system: its regulatory drafts are a starting point that your team reviews, edits and approves. Those systems stay the record; MDARIX connects them for investigation.",
            ],
            [
              "Design-partner outcome",
              "During a pilot, MDARIX records when each investigation is opened and closed, every data import with its result, and every decision with its review and signature, so the pilot can be reviewed from the audit trail.",
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
                "Tell us your name, company and work email. We review every request, usually within one business day.",
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
    </>
  );
}
