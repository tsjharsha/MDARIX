import { useEffect, useState } from "react";
import { BASIS_DISCLAIMER, basisOf } from "../features/shared/standards";
import { MARKETS } from "./content";

/* The website's pictures: drawn in HTML and SVG from the free trial's sample story, so they show the real concepts
   (the product twin, the investigation, the legal clocks, the effectiveness check) without app screenshots that go
   stale. Every one says it is illustrative and synthetic. HTML where the picture holds words, so it reflows on a
   phone instead of shrinking its text. */

const Caption = () => <figcaption className="ms-fig-note">Illustrative · synthetic sample data</figcaption>;

/* ----------------------------------------------------------------- The product twin (home page hero) */

// The free trial's sample story (backend/app/trial/sample_data.py): OrbitCare 300 Rev B moved its pressure sensor to a
// new supplier (change CHG-014); pressure-alarm complaints rise afterwards.
const TWIN_NODES = [
  { key: "complaints", label: "Complaints", value: "Pressure alarms rising", hot: true },
  { key: "version", label: "Version at the event date", value: "Rev B", hot: true },
  { key: "markets", label: "Markets", value: "US · EU · GB · CA · IN", hot: false },
  { key: "component", label: "Component", value: "Pressure sensor", hot: true },
  { key: "lots", label: "Lots built with it", value: "003–008", hot: true },
  { key: "supplier", label: "Supplier", value: "Changed in CHG-014", hot: true },
] as const;

export function ProductTwin() {
  return (
    <figure className="ms-twin" aria-labelledby="twin-title">
      <svg className="ms-twin-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {[
          [17, 17],
          [83, 17],
          [17, 50],
          [83, 50],
          [17, 83],
          [83, 83],
        ].map(([x, y], index) => (
          <line
            key={index}
            x1={50}
            y1={50}
            x2={x}
            y2={y}
            className={TWIN_NODES[index].hot ? "is-hot" : undefined}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      <div className="ms-twin-core">
        <span id="twin-title">Product Lifecycle Twin</span>
        <strong>OrbitCare 300</strong>
        <small>Infusion pump · sample product</small>
      </div>
      <ul className="ms-twin-nodes">
        {TWIN_NODES.map((node) => (
          <li key={node.key} className={`ms-twin-node is-${node.key}${node.hot ? " is-hot" : ""}`}>
            <span>{node.label}</span>
            <strong>{node.value}</strong>
          </li>
        ))}
      </ul>
      <Caption />
    </figure>
  );
}

/* ------------------------------------------------------------------------------------------- 1. Signal */

// One synthetic case told the same way on every page: 42 complaints in 26 weeks, 6 in the 13 weeks before Rev B
// (about 2 a month) and 36 in the 13 weeks after (about 12 a month).
const WEEKLY = [1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 1, 2, 2, 3, 2, 3, 3, 3, 3, 4, 3, 3, 4];
const RELEASE_WEEK = 13;
/** The example's numbers, for its tests. */
export const EXAMPLE_NUMBERS = { weekly: WEEKLY, releaseWeek: RELEASE_WEEK } as const;

export function SignalChart() {
  const width = 480;
  const height = 220;
  const pad = { left: 12, right: 12, top: 40, bottom: 36 };
  const max = 4.5;
  const x = (index: number) => pad.left + (index / (WEEKLY.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + (1 - value / max) * (height - pad.top - pad.bottom);
  const line = WEEKLY.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(
    " ",
  );
  const area = `${line} L${x(WEEKLY.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;
  const release = x(RELEASE_WEEK - 1);
  return (
    <figure className="ms-fig">
      <svg className="ms-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="signal-chart-title">
        <title id="signal-chart-title">
          Pressure-alarm complaints per week: about 2 a month before Rev B is released in week 13, about 12 a month
          after
        </title>
        <rect
          className="ms-chart-after"
          x={release}
          y={pad.top - 8}
          width={width - pad.right - release}
          height={y(0) - pad.top + 8}
        />
        <line className="ms-chart-base" x1={pad.left} x2={width - pad.right} y1={y(0)} y2={y(0)} />
        <path className="ms-chart-area" d={area} />
        <path className="ms-chart-line" d={line} />
        <line className="ms-chart-marker" x1={release} x2={release} y1={pad.top - 8} y2={y(0)} />
        <text className="ms-chart-note" x={release + 8} y={pad.top - 14}>
          Rev B released
        </text>
        <text className="ms-chart-axis" x={pad.left} y={height - 10}>
          Week 1
        </text>
        <text className="ms-chart-axis" x={width - pad.right} y={height - 10} textAnchor="end">
          Week 26
        </text>
      </svg>
      <div className="ms-fig-stats">
        <span>
          <strong>~2</strong> a month before
        </span>
        <span className="is-hot">
          <strong>~12</strong> a month after
        </span>
      </div>
      <Caption />
    </figure>
  );
}

/* ---------------------------------------------------------------------------------- 2. Product reality */

const REVISIONS = [
  ["Pressure sensor supplier", "Original supplier", "New supplier (CHG-014)"],
  ["Incoming inspection sample", "32 units", "13 units"],
  ["Finished lots", "001–002", "003–008"],
] as const;

export function RevisionCompare() {
  return (
    <figure className="ms-fig">
      <table className="ms-compare">
        <caption>OrbitCare 300: what changed between Rev A and Rev B</caption>
        <thead>
          <tr>
            <th scope="col">
              <span className="ms-sr">Attribute</span>
            </th>
            <th scope="col">Rev A</th>
            <th scope="col">Rev B</th>
          </tr>
        </thead>
        <tbody>
          {REVISIONS.map(([what, before, after]) => (
            <tr key={what}>
              <th scope="row">{what}</th>
              <td>{before}</td>
              <td className="is-changed">{after}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ms-fig-read">A change is a lead, not a cause: the investigation tests it.</p>
      <Caption />
    </figure>
  );
}

/* -------------------------------------------------------------------------------------- 3. Investigation */

const RAIL = ["Signal", "Evidence", "Possible causes", "Brief", "Decision"] as const;
const CAUSES = [
  { cause: "New supplier's sensor drifts at low pressure", state: "Supported", tone: "good", support: 4, against: 1 },
  { cause: "Alarm threshold set too tight in firmware", state: "Weakened", tone: "warn", support: 1, against: 3 },
  { cause: "Set-up error at the bedside", state: "Open question", tone: "open", support: 1, against: 1 },
] as const;

export function InvestigationRail() {
  return (
    <figure className="ms-fig">
      <ol className="ms-rail" aria-label="Investigation steps">
        {RAIL.map((step, index) => (
          <li key={step} className={index === 2 ? "is-current" : index < 2 ? "is-done" : undefined}>
            {step}
          </li>
        ))}
      </ol>
      <ul className="ms-causes">
        {CAUSES.map((item) => (
          <li key={item.cause}>
            <span className="ms-cause-text">{item.cause}</span>
            <span className={`ms-pill is-${item.tone}`}>{item.state}</span>
            <span className="ms-weigh" aria-label={`${item.support} pieces of evidence for, ${item.against} against`}>
              <span className="is-for" style={{ flexGrow: item.support }} />
              <span className="is-against" style={{ flexGrow: item.against }} />
            </span>
          </li>
        ))}
      </ul>
      <p className="ms-fig-read">
        <span className="ms-key is-for" aria-hidden="true" /> Evidence for{" "}
        <span className="ms-key is-against" aria-hidden="true" /> Evidence against
      </p>
      <Caption />
    </figure>
  );
}

/* --------------------------------------------------------------------------- 4. Decision and reports */

const MARKET_STATES: Record<string, { state: string; tone: string }> = {
  "United States": { state: "Reportable · clock running", tone: "warn" },
  "EU and Northern Ireland": { state: "Not reportable · reason kept", tone: "good" },
  "Great Britain": { state: "Reportable · clock running", tone: "warn" },
  Canada: { state: "Not reportable · reason kept", tone: "good" },
  India: { state: "Not reportable · reason kept", tone: "good" },
};

export function MarketDecisions() {
  return (
    <figure className="ms-fig">
      <ul className="ms-markets">
        {MARKETS.map((market) => (
          <li key={market.region}>
            <span>
              <strong>{market.region}</strong>
              <small>
                {basisOf(market.basis)
                  .map((standard) => standard.short)
                  .join(" · ")}
              </small>
            </span>
            <span className={`ms-pill is-${MARKET_STATES[market.region].tone}`}>
              {MARKET_STATES[market.region].state}
            </span>
          </li>
        ))}
      </ul>
      <p className="ms-signed">Signed with password and authenticator code · nobody signs their own work</p>
      <Caption />
    </figure>
  );
}

/** The markets with their legal basis, for the Trust page. */
export function MarketBasis() {
  return (
    <>
      <div className="ms-grid ms-grid-5">
        {MARKETS.map((market) => (
          <div key={market.region} className="ms-card">
            <span className="ms-eyebrow">{market.region}</span>
            <strong>{market.name}</strong>
            <ul className="ms-basis">
              {basisOf(market.basis).map((standard) => (
                <li key={standard.id}>
                  <b>{standard.short}</b> {standard.title}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="ms-note">{BASIS_DISCLAIMER}</p>
    </>
  );
}

/* ---------------------------------------------------------------------------------------- 5. Did it work */

const OUTCOMES = [
  ["Effective", "good"],
  ["Not effective", "bad"],
  ["Inconclusive", "warn"],
] as const;

export function EffectivenessCheck() {
  return (
    <figure className="ms-fig">
      <dl className="ms-check">
        <div>
          <dt>Action</dt>
          <dd>CAPA-02: full incoming inspection of the pressure sensor restored</dd>
        </div>
        <div>
          <dt>Criteria, set before the action</dt>
          <dd>Pressure-alarm complaints on lots built after the fix fall back to the Rev A rate</dd>
        </div>
        <div>
          <dt>Measured from</dt>
          <dd>The first lot built after the fix, not the day the CAPA closed</dd>
        </div>
      </dl>
      <div className="ms-outcomes" role="group" aria-label="The signed result is one of">
        {OUTCOMES.map(([label, tone]) => (
          <span key={label} className={`ms-pill is-${tone}`}>
            {label}
          </span>
        ))}
      </div>
      <p className="ms-fig-read">Too early to tell is said plainly, not counted as a success.</p>
      <Caption />
    </figure>
  );
}

/* ----------------------------------------------------------------------------------- Customer voices */

type Voice = { quote: string; attribution: string; rating: number };

/** What trial customers said, shared with their permission (approved in platform administration). Shows nothing
 * until there is at least one approved voice: the website never shows invented quotes. */
export function CustomerVoices() {
  const [voices, setVoices] = useState<Voice[]>([]);
  useEffect(() => {
    fetch("/api/v1/public/testimonials", { headers: { Accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : { items: [] }))
      .then((data) => setVoices(Array.isArray(data?.items) ? data.items.slice(0, 3) : []))
      .catch(() => setVoices([]));
  }, []);
  if (!voices.length) return null;
  return (
    <section className="ms-section" aria-labelledby="voices-title">
      <div className="ms-head">
        <span className="ms-eyebrow">Customer voices</span>
        <h2 id="voices-title">What MedTech teams say after their trial.</h2>
        <p>In their own words, shared with their permission.</p>
      </div>
      <div className="ms-grid ms-grid-3">
        {voices.map((voice, index) => (
          <figure key={`${voice.attribution}-${index}`} className="ms-card ms-voice">
            <blockquote>{voice.quote}</blockquote>
            <span className="ms-voice-rating" aria-label={`Rated ${voice.rating} of 5`}>
              {"★".repeat(voice.rating)}
              <span aria-hidden="true">{"★".repeat(5 - voice.rating)}</span>
            </span>
            <figcaption>{voice.attribution}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
