import { Scene, at } from "./kit";
import type { SceneComponent } from "./index";

// Compact scenes for small frames (the home page's four steps, about 270 px wide): one idea each, drawn large enough
// to read at that size (labels 28 px and up on the 640×400 canvas, so about 12 px on screen). The full scenes for
// the same pictures stay on the Platform page. See kit.tsx for the rules every scene follows.

const big = { fontSize: 30, fontWeight: 800 } as const;

/** 01 Reconstruct product reality: the device, and its version, sensor, supplier and lots linking in. */
function ProductRealityCompact({ label }: { label: string }) {
  const around = [
    { text: "Rev B", x: 130, y: 92 },
    { text: "PS-2", x: 510, y: 92 },
    { text: "Kestrel", x: 130, y: 310 },
    { text: "Lots 003–004", x: 490, y: 310 },
  ];
  return (
    <Scene label={label}>
      {around.map((node, index) => (
        <path
          key={node.text}
          className="sc-link sc-draw"
          pathLength={1}
          d={`M 320 200 L ${node.x} ${node.y}`}
          strokeWidth={4}
          style={at(index, "0.3s")}
        />
      ))}
      <g transform="translate(320 200)">
        <circle r={62} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={3} />
        <g className="sc-pop">
          <circle r={62} fill="var(--sc-panel)" stroke="var(--sc-teal)" strokeWidth={5} />
          <rect x={-24} y={-30} width={48} height={42} rx={8} fill="none" stroke="var(--sc-teal)" strokeWidth={4} />
          <path d="M -15 -10 h 7 l 5 -9 l 6 18 l 5 -9 h 9" fill="none" stroke="var(--sc-teal)" strokeWidth={3.5} />
          <text textAnchor="middle" y={42} style={{ fontSize: 22, fontWeight: 800 }} fill="var(--sc-teal)">
            OrbitCare
          </text>
        </g>
      </g>
      {around.map((node, index) => (
        <g key={node.text} transform={`translate(${node.x} ${node.y})`}>
          <g className="sc-pop" style={at(index + 3, "0.3s")}>
            <rect
              x={-(node.text.length * 9.5 + 26)}
              y={-26}
              width={node.text.length * 19 + 52}
              height={52}
              rx={26}
              fill="var(--sc-panel)"
              stroke={index >= 2 ? "var(--sc-amber)" : "var(--sc-teal)"}
              strokeWidth={3}
            />
            <text textAnchor="middle" dy={10} style={big}>
              {node.text}
            </text>
          </g>
        </g>
      ))}
    </Scene>
  );
}

/** 02 Investigate with evidence: records from separate systems land in one investigation. */
function EvidenceCompact({ label }: { label: string }) {
  const sources = ["QMS", "PLM", "ERP"];
  return (
    <Scene label={label}>
      {sources.map((source, index) => (
        <g key={source} transform={`translate(70 ${70 + index * 100})`}>
          <g className="sc-rise" style={at(index)}>
            <rect width={150} height={70} rx={14} fill="var(--sc-panel)" stroke="var(--sc-line)" strokeWidth={3} />
            <text x={75} y={46} textAnchor="middle" style={big}>
              {source}
            </text>
          </g>
        </g>
      ))}
      {sources.map((source, index) => (
        <path
          key={source}
          className="sc-link sc-draw"
          pathLength={1}
          d={`M 222 ${105 + index * 100} C 300 ${105 + index * 100}, 300 200, 360 200`}
          strokeWidth={4}
          style={at(index, "0.5s")}
        />
      ))}
      <g transform="translate(360 112)">
        <g className="sc-pop" style={at(0, "1.1s")}>
          <rect width={230} height={176} rx={18} fill="var(--sc-panel)" stroke="var(--sc-teal)" strokeWidth={4} />
          <text x={115} y={62} textAnchor="middle" style={{ fontSize: 56, fontWeight: 800 }} fill="var(--sc-teal)">
            14
          </text>
          <text x={115} y={104} textAnchor="middle" style={{ fontSize: 26, fontWeight: 700 }}>
            records
          </text>
          <text x={115} y={140} textAnchor="middle" style={{ fontSize: 26, fontWeight: 700 }}>
            linked
          </text>
        </g>
      </g>
    </Scene>
  );
}

/** 03 Challenge before concluding: two explanations, what supports and what contradicts each, no verdict yet. */
function ChallengeCompact({ label }: { label: string }) {
  const rows = [
    { text: "Sensor change", supports: 0.78, contradicts: 0.12 },
    { text: "Use error", supports: 0.22, contradicts: 0.55 },
  ];
  return (
    <Scene label={label}>
      <line x1={320} y1={70} x2={320} y2={330} stroke="var(--sc-line)" strokeWidth={4} />
      {rows.map((row, index) => (
        <g key={row.text} transform={`translate(0 ${120 + index * 130})`}>
          <g className="sc-fade" style={at(index)}>
            <text x={320} y={-24} textAnchor="middle" style={big}>
              {row.text}
            </text>
          </g>
          <rect
            className="sc-grow-x"
            x={326}
            y={0}
            width={260 * row.supports}
            height={34}
            rx={8}
            fill="var(--sc-teal)"
            style={at(index, "0.4s")}
          />
          <g transform={`translate(${314 - 260 * row.contradicts} 0)`}>
            <rect
              width={260 * row.contradicts}
              height={34}
              rx={8}
              fill="var(--sc-red)"
              opacity={0.85}
              className="sc-fade"
              style={at(index, "0.6s")}
            />
          </g>
        </g>
      ))}
      <g className="sc-fade" style={at(0, "1.4s")}>
        <text x={60} y={372} style={{ fontSize: 24, fontWeight: 700 }} fill="var(--sc-red)">
          contradicts
        </text>
        <text x={580} y={372} textAnchor="end" style={{ fontSize: 24, fontWeight: 700 }} fill="var(--sc-teal)">
          supports
        </text>
      </g>
    </Scene>
  );
}

/** 04 Decide, sign and trace: the decision is signed by a person, and lands in the audit trail. */
function DecisionCompact({ label }: { label: string }) {
  const trail = ["Reviewed", "Re-authenticated", "Signed"];
  return (
    <Scene label={label}>
      <g transform="translate(200 175)">
        <circle r={112} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={3} />
        <g className="sc-pop" style={at(0, "0.2s")}>
          <circle r={112} fill="var(--sc-panel)" stroke="var(--sc-teal)" strokeWidth={6} />
          <circle r={94} fill="none" stroke="var(--sc-teal)" strokeWidth={2.5} strokeDasharray="5 6" />
          <path
            d="M -26 -40 l 16 16 l 30 -32"
            fill="none"
            stroke="var(--sc-teal)"
            strokeWidth={8}
            strokeLinecap="round"
          />
          <text textAnchor="middle" y={22} style={{ fontSize: 40, fontWeight: 900 }} fill="var(--sc-teal)">
            SIGNED
          </text>
          <text textAnchor="middle" y={58} style={{ fontSize: 26, fontWeight: 700 }} fill="var(--sc-ink-2)">
            QA lead
          </text>
        </g>
      </g>
      <path className="sc-line sc-draw" pathLength={1} d="M 400 80 V 290" strokeWidth={4} style={at(0, "0.8s")} />
      {trail.map((step, index) => (
        <g key={step} transform={`translate(400 ${90 + index * 96})`}>
          <g className="sc-rise" style={at(index, "1s")}>
            <circle
              r={12}
              fill={index === 2 ? "var(--sc-teal)" : "var(--sc-panel)"}
              stroke="var(--sc-teal)"
              strokeWidth={4}
            />
            <text x={26} y={9} style={{ fontSize: 26, fontWeight: 700 }}>
              {step}
            </text>
          </g>
        </g>
      ))}
    </Scene>
  );
}

// By the name of the picture each replaces in a small frame (motion.tsx Photo with compact).
export const compactScenes: Record<string, SceneComponent> = {
  "medtech-product-360-device": ProductRealityCompact,
  "medtech-evidence-intelligence-hero": EvidenceCompact,
  "medtech-hero-challenger": ChallengeCompact,
  "medtech-decision-center-hero": DecisionCompact,
};
