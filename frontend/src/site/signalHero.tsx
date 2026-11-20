import { useEffect, useRef } from "react";

/*
 * The home page's hero (Clinical Signal): what MDARIX does, in one moving picture. Complaint signals flow into
 * MDARIX, which ties each one to its product, lot, supplier and evidence; each market's legal clock starts; a person
 * signs. Pure SVG, so it pre-renders; the animations are SVG's own (SMIL), paused for people who ask for reduced motion,
 * so they see the finished picture. Illustrative: no customer data and no real deadlines.
 */

const CX = 330;
const CY = 280;

const INPUTS = [
  { label: "Complaint", y: 150 },
  { label: "Service log", y: 280 },
  { label: "Field report", y: 410 },
];

const LINKS = [
  { label: "Product", angle: -90 },
  { label: "Lot", angle: 0 },
  { label: "Evidence", angle: 90 },
  { label: "Supplier", angle: 180 },
];

const MARKETS = ["US", "EU", "UK", "IN", "CA"];
const CYCLE = 7;

const inPath = (y: number) => `M 150 ${y} C 215 ${y}, 225 ${CY}, ${CX - 74} ${CY}`;
const outY = (i: number) => 120 + i * 80;
const outPath = (i: number) => `M ${CX + 74} ${CY} C 450 ${CY}, 455 ${outY(i)}, 510 ${outY(i)}`;
const at = (angle: number, r: number) => {
  const rad = (angle * Math.PI) / 180;
  return [CX + r * Math.cos(rad), CY + r * Math.sin(rad)] as const;
};

export function SignalHero() {
  const svg = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const apply = () => {
      const node = svg.current;
      if (!node) return;
      if (reduce?.matches) {
        node.pauseAnimations?.();
        node.setCurrentTime?.(CYCLE - 0.4); // the finished picture: every clock running, the decision signed
      } else node.unpauseAnimations?.();
    };
    apply();
    reduce?.addEventListener?.("change", apply);
    return () => reduce?.removeEventListener?.("change", apply);
  }, []);

  return (
    <figure className="ms-signal-hero">
      <svg
        ref={svg}
        viewBox="0 0 640 560"
        role="img"
        aria-label="Complaint signals flow into MDARIX, which links each one to its product, lot, supplier and evidence, starts every market's legal clock, and leaves the decision to a person who signs."
      >
        <defs>
          <linearGradient id="sh-core" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" className="sh-stop-glow" />
            <stop offset="100%" className="sh-stop-mint" />
          </linearGradient>
          <radialGradient id="sh-halo">
            <stop offset="0%" className="sh-stop-halo" />
            <stop offset="100%" className="sh-stop-none" />
          </radialGradient>
          <filter id="sh-blur" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
        </defs>

        <circle cx={CX} cy={CY} r="250" fill="url(#sh-halo)" />
        {[96, 150, 210].map((r) => (
          <circle key={r} cx={CX} cy={CY} r={r} className="sh-ring" />
        ))}
        <g>
          <animateTransform
            attributeName="transform"
            type="rotate"
            from={`0 ${CX} ${CY}`}
            to={`360 ${CX} ${CY}`}
            dur="40s"
            repeatCount="indefinite"
          />
          <circle cx={CX} cy={CY} r="210" className="sh-ring-dash" />
          <circle cx={CX + 210} cy={CY} r="4" className="sh-spark" />
        </g>

        {/* signals in */}
        {INPUTS.map((input, i) => (
          <g key={input.label}>
            <path d={inPath(input.y)} className="sh-wire sh-wire-in" />
            <rect x="14" y={input.y - 19} width="136" height="38" rx="19" className="sh-chip" />
            <circle cx="36" cy={input.y} r="5" className="sh-dot-in">
              <animate attributeName="r" values="4;7;4" dur="2.2s" begin={`${i * 0.5}s`} repeatCount="indefinite" />
            </circle>
            <text x="50" y={input.y + 5} className="sh-label">
              {input.label}
            </text>
            <circle r="4.5" className="sh-pulse-in">
              <animateMotion dur="2.6s" begin={`${i * 0.8}s`} repeatCount="indefinite" path={inPath(input.y)} />
              <animate
                attributeName="opacity"
                values="0;1;1;0"
                dur="2.6s"
                begin={`${i * 0.8}s`}
                repeatCount="indefinite"
              />
            </circle>
          </g>
        ))}

        {/* what MDARIX links each complaint to */}
        {LINKS.map((link, i) => {
          const [x, y] = at(link.angle, 96);
          // Product and Evidence sit outside their node; Lot and Supplier above it, clear of the wires.
          const [lx, ly] = link.angle % 180 === 0 ? [x, y - 18] : at(link.angle, 126);
          return (
            <g key={link.label}>
              <line x1={CX} y1={CY} x2={x} y2={y} className="sh-spoke" />
              <circle cx={x} cy={y} r="7" className="sh-node">
                <animate attributeName="r" values="6;9;6" dur="2.8s" begin={`${i * 0.7}s`} repeatCount="indefinite" />
              </circle>
              <text x={lx} y={ly + 4} textAnchor="middle" className="sh-label sh-label-sm">
                {link.label}
              </text>
            </g>
          );
        })}

        {/* market clocks out */}
        {MARKETS.map((market, i) => {
          const begin = `${1 + i * 0.45}s`;
          const y = outY(i);
          return (
            <g key={market}>
              <path d={outPath(i)} className="sh-wire" />
              <circle r="3.5" className="sh-pulse-out">
                <animateMotion
                  dur={`${CYCLE}s`}
                  begin={begin}
                  repeatCount="indefinite"
                  keyPoints="0;1;1"
                  keyTimes="0;0.2;1"
                  calcMode="linear"
                  path={outPath(i)}
                />
                <animate
                  attributeName="opacity"
                  values="0;1;0;0"
                  keyTimes="0;0.15;0.22;1"
                  dur={`${CYCLE}s`}
                  begin={begin}
                  repeatCount="indefinite"
                />
              </circle>
              <circle cx="540" cy={y} r="24" className="sh-clock-track" />
              <circle
                cx="540"
                cy={y}
                r="24"
                className="sh-clock"
                transform={`rotate(-90 540 ${y})`}
                strokeDasharray="151"
                strokeDashoffset="151"
              >
                <animate
                  attributeName="stroke-dashoffset"
                  values="151;151;38;38;151"
                  keyTimes="0;0.2;0.62;0.95;1"
                  dur={`${CYCLE}s`}
                  begin={begin}
                  repeatCount="indefinite"
                />
              </circle>
              <text x="540" y={y + 5} textAnchor="middle" className="sh-label sh-market">
                {market}
              </text>
            </g>
          );
        })}
        <text x="540" y="532" textAnchor="middle" className="sh-caption">
          LEGAL CLOCKS
        </text>

        {/* the core */}
        <circle cx={CX} cy={CY} r="66" className="sh-core-glow" filter="url(#sh-blur)">
          <animate attributeName="opacity" values="0.35;0.7;0.35" dur="3s" repeatCount="indefinite" />
        </circle>
        <rect x={CX - 60} y={CY - 60} width="120" height="120" rx="32" fill="url(#sh-core)" />
        <rect x={CX - 47} y={CY - 47} width="94" height="94" rx="25" className="sh-core-inner" />
        <path
          d={`M ${CX - 36} ${CY + 4} h 16 l 8 -20 l 12 36 l 9 -26 l 7 10 h 20`}
          className="sh-ecg"
          strokeDasharray="150"
          strokeDashoffset="150"
        >
          <animate
            attributeName="stroke-dashoffset"
            values="150;0;0;-150"
            keyTimes="0;0.45;0.7;1"
            dur="2.4s"
            repeatCount="indefinite"
          />
        </path>

        {/* the person's signature */}
        <g className="sh-seal">
          <rect x={CX - 92} y="470" width="184" height="40" rx="20" className="sh-seal-pill">
            <animate
              attributeName="opacity"
              values="0.35;0.35;1;1;0.35"
              keyTimes="0;0.6;0.7;0.95;1"
              dur={`${CYCLE}s`}
              begin="1s"
              repeatCount="indefinite"
            />
          </rect>
          <path d={`M ${CX - 70} 490 l 7 7 l 13 -14`} className="sh-check" />
          <text x={CX - 44} y="495" className="sh-label sh-seal-text">
            Signed by a person
          </text>
        </g>
        <line x1={CX} y1={CY + 66} x2={CX} y2="470" className="sh-wire sh-wire-down" />
      </svg>
      <figcaption>Illustrative · synthetic flow</figcaption>
    </figure>
  );
}
