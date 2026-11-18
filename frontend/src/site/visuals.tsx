import { useEffect, useState } from "react";
import { BASIS_DISCLAIMER, basisOf } from "../features/shared/standards";
import { MARKETS } from "./content";
import { SAMPLE_LABEL } from "./motion";

/* The website's drawn pictures: the sample's signal chart (drawn on as it scrolls into view, beside the Cases screen)
   and the markets' legal basis. The app's own screens are in motion.tsx (Shot). */

const Caption = () => <figcaption className="ms-fig-note">{SAMPLE_LABEL}</figcaption>;

/* ------------------------------------------------------------------------------------------- 1. Signal */

// The sample's 19 OrbitCare pressure-alarm complaints by event week over the last 26 weeks (sample_data.py _PRODUCTS
// days + 2, and SAMPLE-RT-04): 4 in the 15 weeks before Rev B (released 75 days ago, week 16), 15 in the 11 after.
const WEEKLY = [0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 2, 1, 2, 1, 2, 1, 2, 1];
const RELEASE_WEEK = 16;
/** The example's numbers, for its tests. */
export const EXAMPLE_NUMBERS = { weekly: WEEKLY, releaseWeek: RELEASE_WEEK } as const;

export function SignalChart() {
  const width = 480;
  const height = 220;
  const pad = { left: 12, right: 12, top: 40, bottom: 36 };
  const max = 2.5;
  const x = (index: number) => pad.left + (index / (WEEKLY.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + (1 - value / max) * (height - pad.top - pad.bottom);
  const line = WEEKLY.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(
    " ",
  );
  const area = `${line} L${x(WEEKLY.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;
  const release = x(RELEASE_WEEK - 1);
  return (
    <figure className="ms-fig ms-fig-chart">
      <svg className="ms-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="signal-chart-title">
        <title id="signal-chart-title">
          Pressure-alarm complaints per week: 4 in the 15 weeks before Rev B is released in week 16, 15 in the 11 weeks
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
        <path className="ms-chart-line" d={line} pathLength={1} />
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
          <strong data-count="4">4</strong> in the 15 weeks before
        </span>
        <span className="is-hot">
          <strong data-count="15">15</strong> in the 11 weeks after
        </span>
        <span className="is-hot">
          <strong data-count="9.3×">9.3×</strong> the expected count in the trend check
        </span>
      </div>
      <Caption />
    </figure>
  );
}

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
