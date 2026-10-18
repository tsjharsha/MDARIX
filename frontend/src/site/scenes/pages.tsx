import { Card, Chip, ChipRow, Illustrative, Scene, at, fs } from "./kit";
import type { SceneComponent } from "./index";

// Scenes for the home, trust, resources and company pictures, by picture name (see kit.tsx for the rules every scene follows).

/** One device, taken apart: the OrbitCare 300 drawn at the centre, with leader lines out to its versions, components,
 * supplier and lots, as an exploded product drawing (lots 003–004, built with the new sensor, marked). Home step 01,
 * "Reconstruct product reality". */
function DeviceAssembly({ label }: { label: string }) {
  const lots = ["001", "002", "003", "004", "005", "006"];
  // Leader lines from a point on the device to the edge of each card.
  const leaders = [
    "M 262 136 Q 240 88 220 88",
    "M 378 150 Q 400 88 420 88",
    "M 262 240 Q 240 308 220 308",
    "M 378 240 Q 400 308 420 308",
  ];
  return (
    <Scene label={label}>
      {/* Leaders, drawn out from the device */}
      {leaders.map((d, index) => (
        <path key={d} className="sc-link sc-draw" pathLength={1} d={d} style={at(index, "0.5s")} />
      ))}
      {/* The device */}
      <g transform="translate(320 193)">
        <g className="sc-pop">
          <rect
            x={-58}
            y={-75}
            width={116}
            height={150}
            rx={16}
            fill="var(--sc-panel)"
            stroke="var(--sc-teal)"
            strokeWidth={2.5}
          />
          <rect
            x={-44}
            y={-59}
            width={88}
            height={60}
            rx={6}
            fill="color-mix(in srgb, var(--sc-teal) 12%, transparent)"
            stroke="var(--sc-teal)"
            strokeWidth={1.5}
          />
          <path
            d="M -36 -28 h 18 l 6 -14 l 8 26 l 6 -12 h 34"
            fill="none"
            stroke="var(--sc-teal)"
            strokeWidth={2}
            strokeLinejoin="round"
          />
          {[-26, -8, 10].map((x) => (
            <circle key={x} cx={x} cy={26} r={6} fill="none" stroke="var(--sc-ink-2)" strokeWidth={1.5} />
          ))}
          {/* The pressure sensor port */}
          <circle
            cx={32}
            cy={59}
            r={9}
            fill="color-mix(in srgb, var(--sc-amber) 22%, transparent)"
            stroke="var(--sc-amber)"
            strokeWidth={2}
          />
        </g>
        <circle cx={32} cy={59} r={9} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
      </g>
      {/* Leader ends on the device */}
      {[
        [262, 136],
        [378, 150],
        [262, 240],
        [378, 240],
      ].map(([x, y], index) => (
        <g key={`${x}-${y}`} className="sc-pop" style={at(index, "0.4s")}>
          <circle cx={x} cy={y} r={4} fill="var(--sc-teal)" />
        </g>
      ))}
      <g className="sc-fade" style={at(0, "0.5s")}>
        <text x={320} y={296} textAnchor="middle" style={{ fontSize: fs(14) }} fontWeight={800}>
          OrbitCare 300
        </text>
      </g>
      {/* Versions */}
      <Card x={24} y={36} w={196} h={104} title="Versions" index={6}>
        <path d="M 22 46 V 70" className="sc-line" strokeWidth={1.5} />
        <circle cx={22} cy={46} r={5} fill="var(--sc-line)" />
        <text x={36} y={50} style={{ fontSize: fs(13) }} fill="var(--sc-muted)">
          Rev A · 2025
        </text>
        <circle cx={22} cy={72} r={5} fill="var(--sc-teal)" />
        <text x={36} y={76} style={{ fontSize: fs(13) }} fontWeight={800} fill="var(--sc-teal)">
          Rev B · 2026
        </text>
        <text x={14} y={94} className="sc-note">
          Change CHG-014
        </text>
      </Card>
      {/* Components */}
      <Card x={420} y={36} w={196} h={104} title="Components" index={7}>
        {[
          ["Sensor PS-2", "var(--sc-amber)"],
          ["Main board", "var(--sc-ink-2)"],
          ["Housing", "var(--sc-ink-2)"],
        ].map(([text, tone], index) => (
          <g key={text}>
            <circle cx={20} cy={46 + index * 20} r={3.5} fill={tone} />
            <text x={30} y={50 + index * 20} style={{ fontSize: fs(12) }} fontWeight={index === 0 ? 800 : 500}>
              {text}
            </text>
          </g>
        ))}
      </Card>
      {/* Supplier */}
      <Card x={24} y={256} w={196} h={104} title="Supplier" index={8}>
        <text x={14} y={52} style={{ fontSize: fs(13) }} fontWeight={800}>
          Kestrel Sensors
        </text>
        <text x={14} y={70} className="sc-note">
          Supplies PS-2
        </text>
        <text x={14} y={88} className="sc-note">
          Since Rev B
        </text>
      </Card>
      {/* Lots */}
      <Card x={420} y={256} w={196} h={104} title="Lots" index={9}>
        {lots.map((lot, index) => {
          const fresh = lot === "003" || lot === "004";
          return (
            <g key={lot}>
              <g className="sc-pop" style={at(index, "1.6s")}>
                <rect
                  x={16 + index * 28}
                  y={34}
                  width={22}
                  height={22}
                  rx={5}
                  fill={fresh ? "color-mix(in srgb, var(--sc-amber) 22%, transparent)" : "var(--sc-panel)"}
                  stroke={fresh ? "var(--sc-amber)" : "var(--sc-line)"}
                  strokeWidth={1.5}
                />
              </g>
              <text x={27 + index * 28} y={72} style={{ fontSize: fs(11) }} textAnchor="middle" fill="var(--sc-ink-2)">
                {lot}
              </text>
            </g>
          );
        })}
        <text x={14} y={92} style={{ fontSize: fs(11) }} fontWeight={700} fill="var(--sc-amber)">
          003–004 · new sensor
        </text>
      </Card>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** A signal out of the noise (Resources hero, dark): weekly pressure-alarm complaints scatter in, the trend draws
 * through them after Rev B and crosses the review threshold, and a signal is raised for investigation. "AI, safety
 * signals, and post-market surveillance." */
function SignalFromNoise({ label }: { label: string }) {
  const weeks = 26;
  const px = (week: number) => 60 + week * 21.6;
  const py = (value: number) => 316 - value * 18;
  const threshold = 7;
  // The underlying rate: flat, then rising from week 12 (Rev B shipping).
  const trend = (week: number) => (week < 12 ? 2 : 2 + (week - 12) * 0.55);
  // Deterministic scatter around the trend: two to three complaint counts per week.
  const noise = (k: number) => {
    const s = Math.sin(k * 12.9898) * 43758.5453;
    return s - Math.floor(s);
  };
  const dots = Array.from({ length: weeks }, (_, week) =>
    Array.from({ length: 2 + (week % 2) }, (_, j) => {
      const value = Math.max(0.4, Math.min(10, trend(week) + (noise(week * 3 + j) - 0.5) * 3));
      return { x: px(week) + (j - 1) * 4, y: py(value), high: value > threshold };
    }),
  ).flat();
  const cross = 12 + (threshold - 2) / 0.55;
  const segment = (from: number, to: number) => {
    const points = [from, ...Array.from({ length: weeks }, (_, w) => w).filter((w) => w > from && w < to), to];
    return points.map((w, i) => `${i ? "L" : "M"} ${px(w).toFixed(1)} ${py(trend(w)).toFixed(1)}`).join(" ");
  };
  return (
    <Scene label={label} tone="dark">
      <text x={50} y={50} style={{ fontSize: fs(14) }} fontWeight={800}>
        Pressure-alarm complaints
      </text>
      <text x={50} y={68} className="sc-note">
        OrbitCare 300 · weekly
      </text>
      {/* Axis and the Rev B marker */}
      <path d="M 50 320 H 606" className="sc-line" />
      <text x={60} y={340} className="sc-note">
        Week 1
      </text>
      <text x={600} y={340} className="sc-note" textAnchor="end">
        Week 26
      </text>
      <path d={`M ${px(11.5)} 90 V 320`} className="sc-line" strokeDasharray="3 5" />
      <text x={px(11.5) + 6} y={100} className="sc-note">
        Rev B · CHG-014
      </text>
      {/* The noise */}
      {dots.map((dot, index) => (
        <g key={index} className="sc-fade" style={at(0, `${(index * 0.025).toFixed(3)}s`)}>
          <circle
            cx={dot.x}
            cy={dot.y}
            r={3}
            fill={dot.high ? "var(--sc-amber)" : "var(--sc-ink-2)"}
            opacity={dot.high ? 0.9 : 0.45}
          />
        </g>
      ))}
      {/* The review threshold */}
      <g className="sc-fade" style={at(0, "0.4s")}>
        <path
          d={`M 50 ${py(threshold)} H 606`}
          stroke="var(--sc-amber)"
          strokeWidth={1.5}
          strokeDasharray="6 5"
          opacity={0.8}
        />
        <text x={58} y={py(threshold) - 8} style={{ fontSize: fs(11) }} fontWeight={700} fill="var(--sc-amber)">
          Review threshold
        </text>
      </g>
      {/* The trend, teal up to the threshold and amber beyond it */}
      <path className="sc-link sc-draw" pathLength={1} d={segment(0, cross)} strokeWidth={3} style={at(0, "1.1s")} />
      <path
        className="sc-link sc-link-amber sc-draw"
        pathLength={1}
        d={segment(cross, weeks - 1)}
        strokeWidth={3}
        style={at(0, "1.9s")}
      />
      {/* The signal */}
      <g transform={`translate(${px(cross)} ${py(threshold)})`}>
        <circle r={10} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} style={at(1)} />
        <g className="sc-pop" style={at(0, "1.9s")}>
          <circle r={6} fill="var(--sc-amber)" />
        </g>
      </g>
      <g className="sc-fade" style={at(0, "2.1s")}>
        <path
          d={`M ${px(cross)} ${py(threshold) - 10} V 118`}
          stroke="var(--sc-amber)"
          strokeWidth={1.5}
          opacity={0.7}
        />
      </g>
      <Chip x={px(cross)} y={104} width={126} text="Signal raised" tone="amber" index={16} />
      <g className="sc-fade" style={at(0, "2.6s")}>
        <text x={50} y={370} style={{ fontSize: fs(12) }} fontWeight={700} fill="var(--sc-teal)">
          ● Reviewed by people → investigation opened
        </text>
      </g>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** AI across the device lifecycle, governed: validate, monitor and change control as one loop around an AI-enabled
 * device, with human oversight at the centre. A topic picture for "AI lifecycle monitoring", not a product claim. */
function AiLifecycleGoverned({ label }: { label: string }) {
  const stages = [
    { title: "Validate", note: "Pre-set acceptance criteria", x: 320, y: 72, w: 236 },
    { title: "Monitor", note: "Real-world performance", x: 502, y: 265, w: 210 },
    { title: "Change control", note: "Planned change · re-test", x: 138, y: 265, w: 210 },
  ];
  // Arcs between the stages' edges (Q curves), each with an arrowhead turned to the curve's end direction.
  const arcs = [
    { d: "M 442 84 Q 502 100 502 224", end: [502, 224], angle: 90 },
    { d: "M 440 304 Q 320 362 200 304", end: [200, 304], angle: 206 },
    { d: "M 138 226 Q 138 84 196 84", end: [196, 84], angle: 0 },
  ];
  return (
    <Scene label={label}>
      {/* A slow dashed ring of oversight round the device */}
      <g className="sc-orbit">
        <circle cx={320} cy={200} r={60} className="sc-line" strokeDasharray="3 7" />
      </g>
      {arcs.map((arc, index) => (
        <path
          key={arc.d}
          className="sc-link sc-draw"
          pathLength={1}
          d={arc.d}
          strokeWidth={2.5}
          style={at(index * 3, "0.6s")}
        />
      ))}
      {arcs.map((arc, index) => (
        <g key={arc.angle} transform={`translate(${arc.end[0]} ${arc.end[1]}) rotate(${arc.angle})`}>
          <g className="sc-fade" style={at(index * 3, "1.3s")}>
            <path
              d="M -8 -6 L 1 0 L -8 6"
              fill="none"
              stroke="var(--sc-teal)"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </g>
        </g>
      ))}
      {/* The device at the centre */}
      <g transform="translate(320 200)">
        <g className="sc-pop">
          <circle r={48} fill="var(--sc-panel)" stroke="var(--sc-teal)" strokeWidth={2.5} />
          <text y={-2} style={{ fontSize: fs(12) }} fontWeight={800} textAnchor="middle">
            AI-enabled
          </text>
          <text y={16} style={{ fontSize: fs(12) }} fontWeight={800} textAnchor="middle">
            device
          </text>
        </g>
      </g>
      {/* The oversight, named under the ring (between the two lower stages, where a chip would not fit) */}
      <g className="sc-fade" style={at(0, "2s")}>
        <text x={320} y={284} textAnchor="middle" style={{ fontSize: fs(13) }} fontWeight={800} fill="var(--sc-teal)">
          Human oversight
        </text>
      </g>
      {/* The three stages */}
      {stages.map((stage, index) => (
        <Card key={stage.title} x={stage.x - stage.w / 2} y={stage.y - 35} w={stage.w} h={70} index={index * 3 + 1}>
          <text x={14} y={28} style={{ fontSize: fs(14) }} fontWeight={800}>
            {stage.title}
          </text>
          <text x={14} y={50} className="sc-note">
            {stage.note}
          </text>
          {stage.title === "Monitor" && (
            <path
              d="M 130 26 L 140 20 L 150 24 L 160 16 L 170 22 L 180 14"
              fill="none"
              stroke="var(--sc-teal)"
              strokeWidth={2}
              strokeLinejoin="round"
            />
          )}
        </Card>
      ))}
      <g className="sc-fade" style={at(0, "2.4s")}>
        <text x={24} y={384} className="sc-note">
          Governed across the lifecycle
        </text>
      </g>
      <Illustrative x={616} y={384} />
    </Scene>
  );
}

/** Reporting clocks: four jurisdictions' reporting windows laid out from the awareness date, with today's line
 * crossing them and the days left on each (illustrative counts), each tied to its source text. "Regulatory
 * intelligence". */
function ReportingClocks({ label }: { label: string }) {
  const day = 11; // pixels per day on the track
  const x0 = 110;
  const today = 11;
  const clocks = [
    { name: "FDA", days: 30 },
    { name: "EU", days: 15 },
    { name: "UK", days: 15 },
    { name: "Canada", days: 30 },
  ];
  return (
    <Scene label={label}>
      <Card x={24} y={32} w={592} h={336} index={0}>
        <text x={18} y={28} style={{ fontSize: fs(15) }} fontWeight={800}>
          Reporting windows
        </text>
        <text x={18} y={48} className="sc-note">
          Counted from the awareness date
        </text>
        {/* The day axis */}
        <text x={x0} y={76} className="sc-note">
          Day 0 · aware
        </text>
        <text x={x0 + 15 * day} y={76} className="sc-note" textAnchor="middle">
          Day 15
        </text>
        <text x={x0 + 30 * day} y={76} className="sc-note" textAnchor="end">
          Day 30
        </text>
        <g transform={`translate(${x0} 88)`}>
          <g className="sc-pop" style={at(0, "0.3s")}>
            <path d="M 0 -6 L 6 0 L 0 6 L -6 0 Z" fill="var(--sc-amber)" />
          </g>
        </g>
        {clocks.map((clock, index) => {
          const y = 112 + index * 46;
          const left = clock.days - today;
          const urgent = left <= 5;
          const tone = urgent ? "var(--sc-amber)" : "var(--sc-teal)";
          return (
            <g key={clock.name}>
              <g className="sc-rise" style={at(index, "0.3s")}>
                <text x={18} y={y + 5} style={{ fontSize: fs(13) }} fontWeight={800}>
                  {clock.name}
                </text>
                <rect x={x0} y={y - 7} width={30 * day} height={14} rx={7} fill="var(--sc-line)" opacity={0.5} />
              </g>
              <rect
                x={x0}
                y={y - 7}
                width={clock.days * day}
                height={14}
                rx={7}
                fill={`color-mix(in srgb, ${tone} 40%, transparent)`}
                stroke={tone}
                className="sc-grow-x"
                style={at(index * 2, "0.7s")}
              />
              <g className="sc-fade" style={at(index, "1.6s")}>
                <text
                  x={576}
                  y={y + 4.5}
                  textAnchor="end"
                  style={{ fontSize: fs(12) }}
                  fontWeight={700}
                  fill={urgent ? "var(--sc-amber)" : "var(--sc-ink-2)"}
                >
                  {left} days left
                </text>
              </g>
              {urgent && (
                <g className="sc-fade" style={at(index, "1.6s")}>
                  <circle cx={x0 + 30 * day + 12} cy={y} r={4} fill="var(--sc-amber)" className="sc-pulse" />
                </g>
              )}
            </g>
          );
        })}
        {/* Today */}
        <path
          d={`M ${x0 + today * day} 94 V 264`}
          className="sc-link sc-draw"
          pathLength={1}
          strokeWidth={2}
          style={at(0, "1.4s")}
        />
        <g className="sc-fade" style={at(0, "1.8s")}>
          <text
            x={x0 + today * day}
            y={282}
            style={{ fontSize: fs(11) }}
            fontWeight={700}
            textAnchor="middle"
            fill="var(--sc-teal)"
          >
            Today · day {today}
          </text>
        </g>
        <path d="M 14 298 H 578" className="sc-line" strokeWidth={1} />
        <ChipRow
          x={14}
          y={320}
          chips={[
            { text: "Source linked: regulator text", tone: "teal", index: 16 },
            { text: "Check current text", tone: "muted", index: 18 },
          ]}
        />
      </Card>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

export const pageScenes: Record<string, SceneComponent> = {
  "medtech-product-360-device": DeviceAssembly,
  "medtech-resource-pms-signals": SignalFromNoise,
  "medtech-resource-ai-lifecycle": AiLifecycleGoverned,
  "medtech-resource-regulatory-intelligence": ReportingClocks,
};
