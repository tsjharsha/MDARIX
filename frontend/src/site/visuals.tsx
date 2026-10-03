import { Reveal } from "./motion";

/* Website visuals drawn from data (SVG): an example investigation in numbers, the customer systems MDARIX reads,
   and the MedTech standards whose evidence it organizes. Every number here is synthetic and labelled as such. */

/* ------------------------------------------------------------------------- An investigation in numbers */

// Weekly complaints for one product: Rev D (change ECN-4471) is released in week 13.
const WEEKLY = [3, 2, 4, 3, 2, 3, 4, 2, 3, 3, 2, 3, 4, 6, 7, 6, 9, 8, 11, 10, 9, 12, 10, 11, 9, 10];
const RELEASE_WEEK = 13;
// Complaints per lot; lots built with sensor lot KS-5521 are marked.
const LOTS = [
  { lot: "L24-0518", count: 2, sensor: false, rev: "Rev C" },
  { lot: "L24-0611", count: 3, sensor: false, rev: "Rev C" },
  { lot: "L24-0702", count: 4, sensor: false, rev: "Rev D" },
  { lot: "L24-0815", count: 17, sensor: true, rev: "Rev D" },
  { lot: "L24-0902", count: 13, sensor: true, rev: "Rev D" },
  { lot: "L24-0927", count: 3, sensor: false, rev: "Rev D" },
];
const LINKS = [
  { label: "Linked to a lot", value: 94 },
  { label: "Linked to a component", value: 88 },
  { label: "Linked to a supplier", value: 81 },
];

function WeeklyChart() {
  const width = 520;
  const height = 230;
  const pad = { left: 34, right: 16, top: 26, bottom: 30 };
  const max = 14;
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
        Weekly complaints rise from about 3 a week to about 10 a week after Rev D is released in week 13
      </title>
      {[0, 4, 8, 12].map((tick) => (
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
        Rev D released · ECN-4471
      </text>
      {WEEKLY.map((value, index) => (
        <circle key={index} className="ms-viz-point" cx={x(index)} cy={y(value)} r={7}>
          <title>{`Week ${index + 1}: ${value} complaints`}</title>
        </circle>
      ))}
      <circle className="ms-viz-end" cx={x(WEEKLY.length - 1)} cy={y(WEEKLY[WEEKLY.length - 1])} r={4} />
      {[1, 13, 26].map((week) => (
        <text key={week} className="ms-viz-axis" x={x(week - 1)} y={height - 8} textAnchor="middle">
          Week {week}
        </text>
      ))}
    </svg>
  );
}

function LotChart() {
  const width = 520;
  const rowHeight = 30;
  const pad = { left: 118, right: 42, top: 8 };
  const height = pad.top + LOTS.length * rowHeight + 8;
  const max = 20;
  const scale = (value: number) => (value / max) * (width - pad.left - pad.right);
  return (
    <svg className="ms-viz" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="viz-lots-title">
      <title id="viz-lots-title">
        Complaints per lot: the two lots built with sensor lot KS-5521 hold 30 of 42 complaints
      </title>
      {LOTS.map((item, index) => {
        const top = pad.top + index * rowHeight;
        return (
          <g key={item.lot} className="ms-viz-row" style={{ animationDelay: `${index * 90}ms` }}>
            <text className="ms-viz-label" x={pad.left - 10} y={top + 18} textAnchor="end">
              {item.lot} · {item.rev}
            </text>
            <rect className="ms-viz-track" x={pad.left} y={top + 6} width={scale(max)} height={16} rx={4} />
            <rect
              className={item.sensor ? "ms-viz-bar ms-viz-bar-hot" : "ms-viz-bar"}
              x={pad.left}
              y={top + 6}
              width={scale(item.count)}
              height={16}
              rx={4}
            >
              <title>{`${item.lot} (${item.rev}): ${item.count} complaints${item.sensor ? ", sensor lot KS-5521" : ""}`}</title>
            </rect>
            <text className="ms-viz-value" x={pad.left + scale(item.count) + 8} y={top + 18}>
              {item.count}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function CoverageRings() {
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="ms-viz-rings">
      {LINKS.map((item, index) => (
        <figure key={item.label} className="ms-viz-ring">
          <svg viewBox="0 0 90 90" role="img" aria-label={`${item.label}: ${item.value} percent of complaints`}>
            <circle className="ms-viz-ring-track" cx="45" cy="45" r={radius} />
            <circle
              className="ms-viz-ring-fill"
              cx="45"
              cy="45"
              r={radius}
              strokeDasharray={`${(item.value / 100) * circumference} ${circumference}`}
              style={{ animationDelay: `${200 + index * 160}ms` }}
              transform="rotate(-90 45 45)"
            />
            <text x="45" y="50" textAnchor="middle" className="ms-viz-ring-value">
              {item.value}%
            </text>
          </svg>
          <figcaption>{item.label}</figcaption>
        </figure>
      ))}
    </div>
  );
}

export function SignalStory() {
  return (
    <section className="ms-section ms-band" aria-labelledby="signal-story-title">
      <Reveal className="ms-section-head">
        <span className="ms-eyebrow">See an investigation take shape</span>
        <h2 id="signal-story-title">From a rising signal to the lot, the component and the supplier.</h2>
        <p>
          The same question an investigation team asks, answered from connected records: when did complaints change,
          which lots carry them, and how much of the evidence is already linked.
        </p>
      </Reveal>
      <div className="ms-viz-grid-2">
        <Reveal className="ms-card ms-viz-card">
          <span className="ms-eyebrow">Signal</span>
          <h3>Complaints per week, AquaFlow 200</h3>
          <WeeklyChart />
          <p className="ms-viz-read">Complaints roughly triple after Rev D. A change is a lead, not a cause.</p>
        </Reveal>
        <Reveal className="ms-card ms-viz-card" delay={120}>
          <span className="ms-eyebrow">Where it concentrates</span>
          <h3>Complaints per lot</h3>
          <LotChart />
          <p className="ms-viz-read">
            <span className="ms-viz-key ms-viz-key-hot" aria-hidden="true" /> Built with sensor lot KS-5521: 30 of 42
            complaints.
          </p>
        </Reveal>
      </div>
      <Reveal className="ms-card ms-viz-card ms-viz-wide" delay={200}>
        <div>
          <span className="ms-eyebrow">Evidence coverage</span>
          <h3>How much of the story is already connected</h3>
          <p className="ms-viz-read">
            MDARIX shows what is linked and what is still missing, so a decision never rests on a gap nobody saw.
          </p>
        </div>
        <CoverageRings />
      </Reveal>
      <p className="ms-viz-caption">Illustrative example with synthetic data. No customer data is shown.</p>
    </section>
  );
}

/* ------------------------------------------------------------------------------ Customer systems */

const SOURCES = [
  ["TrackWise Digital", "Complaints · CAPAs"],
  ["Veeva Vault QMS", "Quality events · documents"],
  ["Teamcenter / Windchill", "Items · BOM · changes"],
  ["SAP S/4HANA / Oracle", "Batches · plants · vendors"],
  ["MES", "Production · genealogy"],
  ["LIMS", "Test results"],
  ["Risk file", "Risks · FMEA · controls"],
  ["Coupa", "Suppliers · certificates"],
] as const;
const OUTCOMES = [
  ["Product 360", "Versions, lots, components, suppliers"],
  ["Investigations", "Question, evidence, hypotheses"],
  ["Ask MDARIX", "Answers cited to records"],
  ["Decisions", "Signed, traceable, audited"],
] as const;

export function SourceFlow() {
  const width = 1000;
  const rowGap = 50;
  const top = 30;
  const center = { x: 500, y: top + ((SOURCES.length - 1) * rowGap) / 2 };
  const height = top * 2 + (SOURCES.length - 1) * rowGap;
  const outGap = 78;
  const outTop = center.y - ((OUTCOMES.length - 1) * outGap) / 2;
  return (
    <section className="ms-section" aria-labelledby="source-flow-title">
      <Reveal className="ms-section-head">
        <span className="ms-eyebrow">Connected systems</span>
        <h2 id="source-flow-title">Your systems stay the record. MDARIX connects the story.</h2>
        <p>
          Each system keeps its data. MDARIX reads it with the customer's own API key and a standard mapping, checks
          every record, and links complaints to versions, lots, components, suppliers, risks and evidence.
        </p>
      </Reveal>
      <Reveal className="ms-sysflow">
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="source-flow-svg-title">
          <title id="source-flow-svg-title">
            Eight customer systems flow into MDARIX, which serves Product 360, investigations, Ask MDARIX and decisions
          </title>
          {SOURCES.map(([name, detail], index) => {
            const y = top + index * rowGap;
            const path = `M232,${y} C360,${y} 360,${center.y} 430,${center.y}`;
            return (
              <g key={name}>
                <path id={`flow-in-${index}`} className="ms-flow-path" d={path} />
                <circle className="ms-flow-dot" r="3.5">
                  <animateMotion
                    dur={`${2.6 + (index % 3) * 0.5}s`}
                    begin={`${index * 0.35}s`}
                    repeatCount="indefinite"
                  >
                    <mpath href={`#flow-in-${index}`} />
                  </animateMotion>
                </circle>
                <rect className="ms-flow-node" x="16" y={y - 19} width="216" height="38" rx="9" />
                <text className="ms-flow-name" x="30" y={y - 2}>
                  {name}
                </text>
                <text className="ms-flow-detail" x="30" y={y + 12}>
                  {detail}
                </text>
              </g>
            );
          })}
          {OUTCOMES.map(([name, detail], index) => {
            const y = outTop + index * outGap;
            const path = `M570,${center.y} C640,${center.y} 640,${y} 768,${y}`;
            return (
              <g key={name}>
                <path id={`flow-out-${index}`} className="ms-flow-path ms-flow-path-out" d={path} />
                <circle className="ms-flow-dot ms-flow-dot-out" r="3.5">
                  <animateMotion dur="2.4s" begin={`${0.6 + index * 0.4}s`} repeatCount="indefinite">
                    <mpath href={`#flow-out-${index}`} />
                  </animateMotion>
                </circle>
                <rect className="ms-flow-node ms-flow-node-out" x="768" y={y - 24} width="216" height="48" rx="10" />
                <text className="ms-flow-name" x="784" y={y - 3}>
                  {name}
                </text>
                <text className="ms-flow-detail" x="784" y={y + 13}>
                  {detail}
                </text>
              </g>
            );
          })}
          <circle className="ms-flow-pulse" cx="500" cy={center.y} r="78" />
          <circle className="ms-flow-core" cx="500" cy={center.y} r="70" />
          <text className="ms-flow-core-title" x="500" y={center.y - 8} textAnchor="middle">
            MDARIX
          </text>
          <text className="ms-flow-core-detail" x="500" y={center.y + 12} textAnchor="middle">
            checked import
          </text>
          <text className="ms-flow-core-detail" x="500" y={center.y + 28} textAnchor="middle">
            tenant-isolated
          </text>
        </svg>
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

export function StandardsSection({ id }: { id?: string }) {
  return (
    <section className="ms-section" id={id} aria-labelledby={`${id ?? "standards"}-title`}>
      <Reveal className="ms-section-head">
        <span className="ms-eyebrow">MedTech standards</span>
        <h2 id={`${id ?? "standards"}-title`}>Built around the evidence regulators ask for.</h2>
        <p>
          Post-market quality work is defined by a few standards and regulations. MDARIX organizes the evidence they
          call for. It does not certify compliance: your quality system and its validation stay yours.
        </p>
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
