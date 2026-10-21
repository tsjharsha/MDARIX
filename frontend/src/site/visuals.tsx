import { useEffect, useId, useState } from "react";
import { Reveal } from "./motion";
import { Enlargeable } from "./enlarge";
import { BASIS_DISCLAIMER, basisOf } from "../features/shared/standards";

/* Website visuals drawn from data (SVG): an example investigation in numbers, the customer systems MDARIX reads,
   the reporting windows and the MedTech standards whose evidence it organizes. Every number here is synthetic and
   labelled as such. SVG text scales with its viewBox: sizes here are chosen so every label renders at 14.5 px or more
   at the width the page gives the picture on a 1,440 px screen (site.css sets them). */

/* ------------------------------------------------------------------------- An investigation in numbers */

// The free trial's sample story (backend/app/trial/sample_data.py): OrbitCare 300 Rev B moved its pressure sensor to a
// new supplier (change CHG-014), released in week 13; pressure-alarm complaints rise afterwards. One synthetic case,
// INV-031, told the same way on every page: 42 complaints in 26 weeks, 6 in the 13 weeks before Rev B (2 a month) and
// 36 in the 13 weeks after (12 a month, six times as many); 40 name a lot, 2 do not; lots 003 and 004 hold 30.
// The Platform scenes (site/scenes) use the same numbers.
const WEEKLY = [1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 1, 2, 2, 3, 2, 3, 3, 3, 3, 4, 3, 3, 4];
const RELEASE_WEEK = 13;
// Complaints per lot; lots built with the new supplier's first sensors are marked.
const LOTS = [
  { lot: "Lot 001", count: 2, sensor: false, rev: "Rev A" },
  { lot: "Lot 002", count: 3, sensor: false, rev: "Rev A" },
  { lot: "Lot 003", count: 17, sensor: true, rev: "Rev B" },
  { lot: "Lot 004", count: 13, sensor: true, rev: "Rev B" },
  { lot: "Lot 005", count: 3, sensor: false, rev: "Rev B" },
  { lot: "Lot 006", count: 2, sensor: false, rev: "Rev B" },
];
/** The example's numbers, for its tests; 2 complaints name no lot (the hero's evidence list says so too). */
export const EXAMPLE_NUMBERS = { weekly: WEEKLY, releaseWeek: RELEASE_WEEK, lots: LOTS, withoutLot: 2 } as const;
export function WeeklyChart() {
  const width = 520;
  const height = 240;
  const pad = { left: 34, right: 16, top: 30, bottom: 34 };
  const max = 5;
  const x = (index: number) => pad.left + (index / (WEEKLY.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + (1 - value / max) * (height - pad.top - pad.bottom);
  const line = WEEKLY.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(
    " ",
  );
  const area = `${line} L${x(WEEKLY.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;
  const releaseX = x(RELEASE_WEEK - 1);
  return (
    <svg className="ms-viz" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="viz-weekly-title">
      <title id="viz-weekly-title">
        Weekly complaints: 6 in the 13 weeks before Rev B is released in week 13, 36 in the 13 weeks after (from about 2
        a month to about 12)
      </title>
      {[0, 2, 4].map((tick) => (
        <g key={tick}>
          <line className="ms-viz-grid" x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
          <text className="ms-viz-axis" x={pad.left - 8} y={y(tick) + 4} textAnchor="end">
            {tick}
          </text>
        </g>
      ))}
      <path className="ms-viz-area" d={area} />
      <path className="ms-viz-line" d={line} pathLength={1} />
      <line className="ms-viz-marker" x1={releaseX} x2={releaseX} y1={pad.top - 8} y2={y(0)} />
      <text className="ms-viz-note" x={releaseX + 6} y={pad.top - 10}>
        Rev B released · CHG-014
      </text>
      {WEEKLY.map((value, index) => (
        <circle key={index} className="ms-viz-point" cx={x(index)} cy={y(value)} r={7}>
          <title>{`Week ${index + 1}: ${value} complaints`}</title>
        </circle>
      ))}
      <circle className="ms-viz-end" cx={x(WEEKLY.length - 1)} cy={y(WEEKLY[WEEKLY.length - 1])} r={4} />
      {[1, 13, 26].map((week, index) => (
        <text
          key={week}
          className="ms-viz-axis"
          x={x(week - 1)}
          y={height - 8}
          textAnchor={index === 0 ? "start" : index === 2 ? "end" : "middle"}
        >
          Week {week}
        </text>
      ))}
    </svg>
  );
}

export function LotChart() {
  const width = 520;
  const rowHeight = 34;
  const pad = { left: 146, right: 42, top: 8 };
  const height = pad.top + LOTS.length * rowHeight + 8;
  const max = 20;
  const scale = (value: number) => (value / max) * (width - pad.left - pad.right);
  return (
    <svg className="ms-viz" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="viz-lots-title">
      <title id="viz-lots-title">
        Complaints per lot: the two lots built with the new supplier's sensors hold 30 of 42 complaints; 2 complaints
        name no lot
      </title>
      {LOTS.map((item, index) => {
        const top = pad.top + index * rowHeight;
        return (
          <g key={item.lot} className="ms-viz-row" style={{ animationDelay: `${index * 90}ms` }}>
            <text className="ms-viz-label" x={pad.left - 10} y={top + 22} textAnchor="end">
              {item.lot} · {item.rev}
            </text>
            <rect className="ms-viz-track" x={pad.left} y={top + 8} width={scale(max)} height={18} rx={4} />
            <rect
              className={item.sensor ? "ms-viz-bar ms-viz-bar-hot" : "ms-viz-bar"}
              x={pad.left}
              y={top + 8}
              width={scale(item.count)}
              height={18}
              rx={4}
            >
              <title>{`${item.lot} (${item.rev}): ${item.count} complaints${item.sensor ? ", new supplier's sensors" : ""}`}</title>
            </rect>
            <text className="ms-viz-value" x={pad.left + scale(item.count) + 8} y={top + 22}>
              {item.count}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ------------------------------------------------------------------------------ Customer systems */

// Typical source systems, by kind: named vendor connectors are not offered yet (they are planned, as the roadmap says).
const SOURCES = [
  ["QMS", "Complaints · CAPAs"],
  ["Document control", "Quality events · documents"],
  ["PLM", "Items · BOM · changes"],
  ["ERP", "Batches · plants · vendors"],
  ["MES", "Production · genealogy"],
  ["LIMS", "Test results"],
  ["Risk file", "Risks · FMEA · controls"],
  ["Supplier portal", "Suppliers · certificates"],
] as const;
const OUTCOMES = [
  ["Product records", "Versions, lots, components, suppliers"],
  ["Investigations", "Question, evidence, hypotheses"],
  ["Ask MDARIX", "Answers with their evidence"],
  ["Decisions", "Signed, traceable, audited"],
] as const;

/** The systems-to-MDARIX picture. Drawn twice when enlarged, so its ids are its own (`uid`). */
function SourceFlowDiagram({ uid }: { uid: string }) {
  const width = 1000;
  const rowGap = 50;
  const top = 30;
  const center = { x: 500, y: top + ((SOURCES.length - 1) * rowGap) / 2 };
  const height = top * 2 + (SOURCES.length - 1) * rowGap;
  const outGap = 78;
  const outTop = center.y - ((OUTCOMES.length - 1) * outGap) / 2;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={`${uid}-title`}>
      <title id={`${uid}-title`}>
        Eight customer systems flow into MDARIX, which serves product records, investigations, Ask MDARIX and decisions
      </title>
      {SOURCES.map(([name, detail], index) => {
        const y = top + index * rowGap;
        const path = `M232,${y} C360,${y} 360,${center.y} 430,${center.y}`;
        return (
          <g key={name}>
            <path id={`${uid}-in-${index}`} className="ms-flow-path" d={path} />
            <circle className="ms-flow-dot" r="3.5">
              <animateMotion dur={`${2.6 + (index % 3) * 0.5}s`} begin={`${index * 0.35}s`} repeatCount="indefinite">
                <mpath href={`#${uid}-in-${index}`} />
              </animateMotion>
            </circle>
            <rect className="ms-flow-node" x="16" y={y - 21} width="216" height="42" rx="9" />
            <text className="ms-flow-name" x="28" y={y - 3}>
              {name}
            </text>
            <text className="ms-flow-detail" x="28" y={y + 14}>
              {detail}
            </text>
          </g>
        );
      })}
      {OUTCOMES.map(([name, detail], index) => {
        const y = outTop + index * outGap;
        const path = `M570,${center.y} C640,${center.y} 640,${y} 744,${y}`;
        return (
          <g key={name}>
            <path id={`${uid}-out-${index}`} className="ms-flow-path ms-flow-path-out" d={path} />
            <circle className="ms-flow-dot ms-flow-dot-out" r="3.5">
              <animateMotion dur="2.4s" begin={`${0.6 + index * 0.4}s`} repeatCount="indefinite">
                <mpath href={`#${uid}-out-${index}`} />
              </animateMotion>
            </circle>
            <rect className="ms-flow-node ms-flow-node-out" x="744" y={y - 26} width="244" height="52" rx="10" />
            <text className="ms-flow-name" x="758" y={y - 4}>
              {name}
            </text>
            <text className="ms-flow-detail" x="758" y={y + 15}>
              {detail}
            </text>
          </g>
        );
      })}
      <circle className="ms-flow-pulse" cx="500" cy={center.y} r="78" />
      <circle className="ms-flow-core" cx="500" cy={center.y} r="70" />
      <text className="ms-flow-core-title" x="500" y={center.y - 10} textAnchor="middle">
        MDARIX
      </text>
      <text className="ms-flow-core-detail" x="500" y={center.y + 12} textAnchor="middle">
        checked import
      </text>
      <text className="ms-flow-core-detail" x="500" y={center.y + 30} textAnchor="middle">
        your data only
      </text>
    </svg>
  );
}

export function SourceFlow() {
  const uid = `flow-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const label = "Your systems stay the record: eight customer systems flowing into MDARIX";
  return (
    <section className="ms-section" aria-labelledby="source-flow-title">
      <Reveal className="ms-section-head">
        <span className="ms-eyebrow">Typical source systems</span>
        <h2 id="source-flow-title">Your systems stay the record. MDARIX connects the story.</h2>
        <p>
          Each system keeps its data. Today MDARIX imports CSV exports from them; live connections are built in a pilot.
          Every record is checked and linked to versions, lots, components, suppliers, risks and evidence.
        </p>
      </Reveal>
      <Reveal className="ms-sysflow">
        <Enlargeable
          label={label}
          enlarged={() => (
            <div className="ms-enlarged-flow">
              <SourceFlowDiagram uid={`${uid}-big`} />
            </div>
          )}
        >
          <SourceFlowDiagram uid={uid} />
        </Enlargeable>
        <ul className="ms-flow-list">
          {SOURCES.map(([name, detail]) => (
            <li key={name}>
              <strong>{name}</strong> {detail}
            </li>
          ))}
        </ul>
      </Reveal>
    </section>
  );
}

/* ---------------------------------------------------------------------------------- Reporting windows */

// The four reporting templates of Complaints › Reporting windows, each with its basis from the standards catalog
// (features/shared/standards.json, mirrored from backend/app/standards.py).
const REPORTING = [
  { region: "United States", name: "FDA medical device reporting", basis: ["CFR803_50", "CFR803_53"] },
  { region: "European Union", name: "EU MDR vigilance", basis: ["MDR_87"] },
  { region: "Great Britain", name: "UK medical devices vigilance", basis: ["UK_MDR"] },
  { region: "Canada", name: "Mandatory problem reporting", basis: ["CA_MDR"] },
];

export function ReportingWindows() {
  return (
    <section className="ms-section" aria-labelledby="reporting-title">
      <Reveal className="ms-section-head">
        <span className="ms-eyebrow">Reporting windows</span>
        <h2 id="reporting-title">FDA, EU MDR, UK and Canada reporting.</h2>
        <p>
          Each window is counted from the day you became aware, and each reportability decision keeps its reason. People
          decide what is reportable; MDARIX never submits anything to a regulator.
        </p>
      </Reveal>
      <div className="ms-grid-4">
        {REPORTING.map((item, index) => (
          <Reveal key={item.region} delay={index * 70} className="ms-card ms-reporting">
            <span className="ms-standard-region">{item.region}</span>
            <strong>{item.name}</strong>
            <ul>
              {basisOf(item.basis).map((standard) => (
                <li key={standard.id}>
                  <b>{standard.short}</b> {standard.title}
                </li>
              ))}
            </ul>
          </Reveal>
        ))}
      </div>
      <p className="ms-viz-caption">{BASIS_DISCLAIMER}</p>
    </section>
  );
}

/* ------------------------------------------------------------------------------- MedTech standards */

const STANDARDS = [
  {
    code: "ISO 13485",
    mark: "13485",
    region: "International",
    name: "Medical devices: quality management systems",
    asks: "Complaint handling (8.2.2), corrective and preventive action (8.5.2, 8.5.3) and controlled records.",
    helps:
      "Every complaint is linked to its product version, lot, component and supplier, with the investigation and CAPA beside it.",
  },
  {
    code: "QMSR",
    mark: "820",
    region: "United States",
    name: "FDA 21 CFR 820, in force since 2 February 2026",
    asks: "ISO 13485 by reference: complaint files, failure investigations and CAPA records the FDA can inspect.",
    helps:
      "One investigation record holds the question, the evidence, the competing explanations and the signed decision.",
  },
  {
    code: "ISO 14971",
    mark: "14971",
    region: "International",
    name: "Application of risk management to medical devices",
    asks: "Production and post-production information must flow back into the risk file.",
    helps:
      "Complaints and failure modes are linked to the risks and controls they touch, so field signals reach the risk file.",
  },
  {
    code: "IEC 62304",
    mark: "62304",
    region: "International",
    name: "Medical device software life cycle",
    asks: "A problem resolution process for software, with traceability to versions and changes.",
    helps:
      "Firmware versions are part of each product version, and engineering changes are linked to the complaints that follow.",
  },
  {
    code: "Part 11",
    mark: "11",
    region: "United States",
    name: "FDA 21 CFR 11: electronic records and signatures",
    asks: "Trustworthy electronic records, signatures with meaning and an audit trail that cannot be altered.",
    helps:
      "Signatures need re-authentication and record their meaning and a content fingerprint; the audit trail is append-only.",
  },
  {
    code: "Part 803",
    mark: "803",
    region: "United States",
    name: "FDA 21 CFR 803: medical device reporting",
    asks: "Timely reports of deaths, serious injuries and malfunctions, from the date of awareness.",
    helps:
      "Awareness date, serious injury, death and malfunction flags travel from the complaint system for reportability review.",
  },
  {
    code: "EU MDR",
    mark: "MDR",
    region: "European Union",
    name: "Regulation (EU) 2017/745, Articles 83–92",
    asks: "Post-market surveillance, vigilance and trend reporting of statistically significant increases (Article 88).",
    helps: "Trends by version and lot show when and where complaints change, with the records behind every point.",
  },
  {
    code: "IMDRF",
    mark: "AET",
    region: "International",
    name: "Adverse event terminology",
    asks: "Consistent problem codes so events can be grouped and compared.",
    helps: "Problem codes are carried from the source system and grouped across products and sites.",
  },
];

/** A seal drawn for the page (not any body's logo), carrying the standard's short number. */
function Emblem({ mark }: { mark: string }) {
  return (
    <svg className="ms-emblem" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="29" className="ms-emblem-ring" />
      <circle cx="32" cy="32" r="23" className="ms-emblem-core" />
      <path d="M20 41 L44 41" className="ms-emblem-rule" />
      <text x="32" y="35" textAnchor="middle" className="ms-emblem-text">
        {mark}
      </text>
    </svg>
  );
}

export function StandardsSection({
  id,
  title = "Built around the evidence regulators ask for.",
  copy = "Post-market quality work is defined by a few standards and regulations. MDARIX organizes the evidence they call for. It does not certify compliance: your quality system and its validation stay yours.",
}: {
  id?: string;
  title?: string;
  copy?: string;
}) {
  return (
    <section className="ms-section" id={id} aria-labelledby={`${id ?? "standards"}-title`}>
      <Reveal className="ms-section-head">
        <span className="ms-eyebrow">MedTech standards</span>
        <h2 id={`${id ?? "standards"}-title`}>{title}</h2>
        <p>{copy}</p>
      </Reveal>
      <div className="ms-standards">
        {STANDARDS.map((standard, index) => (
          <Reveal key={standard.code} delay={(index % 4) * 70} className="ms-card ms-standard">
            <div className="ms-standard-head">
              <Emblem mark={standard.mark} />
              <div>
                <strong>{standard.code}</strong>
                <span className="ms-standard-region">{standard.region}</span>
              </div>
            </div>
            <p className="ms-standard-name">{standard.name}</p>
            <dl>
              <dt>What it asks</dt>
              <dd>{standard.asks}</dd>
              <dt>How MDARIX helps</dt>
              <dd>{standard.helps}</dd>
            </dl>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------- Lifecycle hero (animated) */

// The device lifecycle as a closed loop: post-market findings feed the next design. MDARIX works in post-market today.
const LIFECYCLE_LOOP = [
  { label: ["Concept"], today: false },
  { label: ["Design", "controls"], today: false },
  { label: ["Verification &", "validation"], today: false },
  { label: ["Regulatory", "submission"], today: false },
  { label: ["Manufacturing"], today: false },
  { label: ["Distribution"], today: false },
  { label: ["Post-market", "surveillance"], today: true },
];
const LOOP_STANDARDS = ["ISO 13485", "ISO 14971", "IEC 62304", "FDA QMSR", "EU MDR"];

export function LifecycleHero() {
  const cx = 300;
  const cy = 230;
  const radius = 150;
  const nodes = LIFECYCLE_LOOP.map((stage, index) => {
    const angle = -Math.PI / 2 + (index / LIFECYCLE_LOOP.length) * 2 * Math.PI;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    return {
      ...stage,
      x: cx + radius * cos,
      y: cy + radius * sin,
      lx: cx + (radius + 30) * cos,
      ly: cy + (radius + 30) * sin + (sin > 0.3 ? 14 : sin < -0.3 ? -14 - (stage.label.length - 1) * 15 : 0),
      anchor: (cos > 0.3 ? "start" : cos < -0.3 ? "end" : "middle") as "start" | "end" | "middle",
    };
  });
  return (
    <figure className="ms-lc-hero">
      <svg viewBox="0 0 600 470" role="img" aria-labelledby="lc-hero-title">
        <title id="lc-hero-title">
          The medical device lifecycle as a loop, from concept, design controls, verification and validation, regulatory
          submission, manufacturing and distribution to post-market surveillance, whose findings feed the next design.
          MDARIX works in post-market surveillance today.
        </title>
        <defs>
          <radialGradient id="lc-glow">
            <stop offset="0" stopColor="#73d6cb" stopOpacity="0.45" />
            <stop offset="1" stopColor="#73d6cb" stopOpacity="0" />
          </radialGradient>
        </defs>
        <circle className="ms-lc-halo" cx={cx} cy={cy} r={110} fill="url(#lc-glow)" />
        <circle className="ms-lc-track" cx={cx} cy={cy} r={radius} />
        <circle className="ms-lc-dash" cx={cx} cy={cy} r={radius} />
        {nodes.map((node, index) => (
          <line
            key={`spoke-${index}`}
            className={node.today ? "ms-lc-spoke ms-lc-spoke-today" : "ms-lc-spoke"}
            x1={node.x}
            y1={node.y}
            x2={cx}
            y2={cy}
          />
        ))}
        <g className="ms-lc-orbit">
          <circle className="ms-lc-comet-tail" cx={cx} cy={cy - radius} r={12} />
          <circle className="ms-lc-comet" cx={cx} cy={cy - radius} r={5} />
        </g>
        {/* Infusion pump at the centre: one product reality. */}
        <g className="ms-lc-device">
          <circle cx={cx} cy={cy} r={66} className="ms-lc-core" />
          <g transform="translate(0 -10)">
            <rect x={cx - 30} y={cy - 38} width={60} height={64} rx={9} className="ms-lc-pump" />
            <rect x={cx - 21} y={cy - 29} width={42} height={20} rx={3} className="ms-lc-screen" />
            <polyline
              className="ms-lc-beat"
              points={`${cx - 18},${cy - 19} ${cx - 8},${cy - 19} ${cx - 4},${cy - 26} ${cx + 1},${cy - 12} ${cx + 5},${cy - 19} ${cx + 18},${cy - 19}`}
            />
            {[-14, 0, 14].map((dx) => (
              <circle key={dx} cx={cx + dx} cy={cy + 5} r={4} className="ms-lc-key" />
            ))}
            <rect x={cx - 16} y={cy + 15} width={32} height={4} rx={2} className="ms-lc-key" />
            <path d={`M${cx + 30},${cy - 10} q18,6 14,32`} className="ms-lc-line" />
          </g>
          <text textAnchor="middle" className="ms-lc-core-label">
            <tspan x={cx} y={cy + 33}>
              One product
            </tspan>
            <tspan x={cx} y={cy + 45}>
              reality
            </tspan>
          </text>
        </g>
        {nodes.map((node, index) => (
          <g key={node.label.join(" ")} className={node.today ? "ms-lc-node ms-lc-node-today" : "ms-lc-node"}>
            <circle
              className="ms-lc-ping"
              cx={node.x}
              cy={node.y}
              r={node.today ? 15 : 11}
              style={{ animationDelay: `${index * 2}s` }}
            />
            <circle className="ms-lc-dot" cx={node.x} cy={node.y} r={node.today ? 11 : 8} />
            <text className="ms-lc-num" x={node.x} y={node.y + 4} textAnchor="middle">
              {index + 1}
            </text>
            <text className="ms-lc-label" x={node.lx} y={node.ly} textAnchor={node.anchor}>
              {node.label.map((line, row) => (
                <tspan key={line} x={node.lx} dy={row ? 15 : 0}>
                  {line}
                </tspan>
              ))}
            </text>
          </g>
        ))}
      </svg>
      <figcaption>
        <span className="ms-lc-key-today">MDARIX today: post-market investigation</span>
        <span className="ms-lc-key-next">Roadmap: the rest of the loop</span>
        <span className="ms-lc-standards" aria-label="Standards that govern the lifecycle">
          {LOOP_STANDARDS.map((code) => (
            <span key={code}>{code}</span>
          ))}
        </span>
      </figcaption>
    </figure>
  );
}

/* ------------------------------------------------------------------------- Customer voices */

type Voice = { quote: string; attribution: string; rating: number };

/** Quotes trial customers agreed to share, credited as they chose. Shows nothing until one has been published. */
export function CustomerVoices() {
  const [voices, setVoices] = useState<Voice[]>([]);
  useEffect(() => {
    fetch("/api/v1/public/testimonials", { headers: { Accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : { items: [] }))
      .then((data) => setVoices(Array.isArray(data?.items) ? data.items.slice(0, 6) : []))
      .catch(() => setVoices([]));
  }, []);
  if (!voices.length) return null;
  return (
    <section className="ms-section" aria-labelledby="voices-title">
      <Reveal className="ms-section-head">
        <span className="ms-eyebrow">Customer voices</span>
        <h2 id="voices-title">What MedTech teams say after their trial.</h2>
        <p>In their own words, shared with their permission.</p>
      </Reveal>
      <div className="ms-voices">
        {voices.map((voice, index) => (
          <Reveal key={`${voice.attribution}-${index}`} delay={(index % 3) * 80} className="ms-card ms-voice">
            <span className="ms-voice-mark" aria-hidden="true">
              &ldquo;
            </span>
            <blockquote>{voice.quote}</blockquote>
            <span className="ms-voice-rating" aria-label={`Rated ${voice.rating} of 5`}>
              {"★".repeat(voice.rating)}
              <span aria-hidden="true">{"★".repeat(5 - voice.rating)}</span>
            </span>
            <cite>{voice.attribution}</cite>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
