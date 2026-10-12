/**
 * The sign-up page's one moving figure: a year of complaints arrives, MDARIX groups the repeat ones into a pattern
 * (one version, two lots), and a reviewer signs the decision. Illustrative synthetic data, drawn in SVG and animated
 * in CSS (styles.css, "su-motion"); with reduced motion it shows its last frame, still.
 */

const COLS = 14;
const ROWS = 6;
const X0 = 34;
const Y0 = 64;
const STEP_X = 26;
const STEP_Y = 22;

// The complaints that form the pattern: columns 8 to 11, rows 1 to 4, most of them.
const PATTERN = new Set([
  "8-1",
  "9-1",
  "10-1",
  "8-2",
  "9-2",
  "10-2",
  "11-2",
  "9-3",
  "10-3",
  "11-3",
  "8-4",
  "10-4",
  "11-4",
]);

const DOTS = Array.from({ length: COLS * ROWS }, (_, index) => {
  const col = index % COLS;
  const row = Math.floor(index / COLS);
  return { key: `${col}-${row}`, x: X0 + col * STEP_X, y: Y0 + row * STEP_Y, delay: index * 0.022 };
});

const BOX = { x: X0 + 8 * STEP_X - 13, y: Y0 + STEP_Y - 13, w: 3 * STEP_X + 26, h: 3 * STEP_Y + 26 };

export function SignupMotion() {
  return (
    <figure className="su-motion">
      <svg
        viewBox="0 0 440 300"
        role="img"
        aria-label="Illustration: a year of complaints arrives, MDARIX groups the repeat ones into a pattern on one version and two lots, and a reviewer signs the decision"
      >
        <text x="20" y="28" className="su-title">
          Complaints, last 12 months
        </text>
        <text x="420" y="28" textAnchor="end" className="su-note">
          Illustrative · synthetic data
        </text>
        <g aria-hidden="true">
          {DOTS.map((dot) => (
            <circle
              key={dot.key}
              cx={dot.x}
              cy={dot.y}
              r="6"
              className={PATTERN.has(dot.key) ? "su-dot su-dot-hit" : "su-dot"}
              style={{ animationDelay: `${dot.delay}s` }}
            />
          ))}
          <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx="10" className="su-box" pathLength={1} />
          <g className="su-label">
            <rect x={BOX.x - 70} y={BOX.y + BOX.h + 10} width="240" height="30" rx="15" />
            <text x={BOX.x + 50} y={BOX.y + BOX.h + 30} textAnchor="middle">
              Pattern · Version 2.1 · lots 3 and 7
            </text>
          </g>
        </g>
        <g className="su-stages" aria-hidden="true">
          <g className="su-stage su-stage-1">
            <rect x="20" y="246" width="118" height="34" rx="17" />
            <text x="79" y="268" textAnchor="middle">
              Imported
            </text>
          </g>
          <path d="M142 263 H160" className="su-link" />
          <g className="su-stage su-stage-2">
            <rect x="164" y="246" width="128" height="34" rx="17" />
            <text x="228" y="268" textAnchor="middle">
              Pattern found
            </text>
          </g>
          <path d="M296 263 H314" className="su-link" />
          <g className="su-stage su-stage-3">
            <rect x="318" y="246" width="102" height="34" rx="17" />
            <text x="369" y="268" textAnchor="middle">
              Signed
            </text>
          </g>
        </g>
      </svg>
    </figure>
  );
}
