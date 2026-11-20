import { Card, Chip, Illustrative, Scene, at, fs } from "./kit";
import type { SceneComponent } from "./index";

// Scenes for the Platform page pictures, by picture name (see kit.tsx for the rules every scene follows).

/** One product reality: the device at the centre, the records about it around it, linked as they connect, and a
 * complaint traced through the links to the lots it touches. Platform hero, and "Map how everything connects". */
function ProductRealityGraph({ label }: { label: string }) {
  const cx = 320;
  const cy = 196;
  const nodes = [
    { text: "Versions", a: -90 },
    { text: "Components", a: -45 },
    { text: "Suppliers", a: 0 },
    { text: "Lots", a: 45 },
    { text: "Complaints", a: 90 },
    { text: "Changes", a: 135 },
    { text: "Risk file", a: 180 },
    { text: "Evidence", a: 225 },
  ].map((node) => {
    const r = (node.a * Math.PI) / 180;
    return { ...node, x: cx + Math.cos(r) * 205, y: cy + Math.sin(r) * 132 };
  });
  const at_ = (text: string) => nodes.find((node) => node.text === text)!;
  const complaints = at_("Complaints");
  const lots = at_("Lots");
  const suppliers = at_("Suppliers");
  return (
    <Scene label={label} tone="dark">
      {/* Faint orbit rings that turn slowly */}
      <g className="sc-orbit">
        <ellipse cx={cx} cy={cy} rx={205} ry={132} className="sc-line" strokeDasharray="2 8" />
        <ellipse cx={cx} cy={cy} rx={120} ry={78} className="sc-line" strokeDasharray="2 10" />
      </g>
      {/* Links from the device to each record, drawn one after another */}
      {nodes.map((node, index) => (
        <path
          key={node.text}
          className="sc-link sc-draw"
          pathLength={1}
          d={`M ${cx} ${cy} L ${node.x} ${node.y}`}
          style={at(index, "0.3s")}
          opacity={0.55}
        />
      ))}
      {/* A complaint traced: complaints → device → suppliers → lots, in amber, flowing */}
      <g className="sc-fade" style={at(0, "2.2s")}>
        <path
          className="sc-link sc-link-amber sc-link-dashed sc-flow"
          d={`M ${complaints.x} ${complaints.y} Q ${cx - 20} ${cy + 40} ${cx} ${cy} T ${suppliers.x} ${suppliers.y} L ${lots.x} ${lots.y}`}
          strokeWidth={2.5}
        />
      </g>
      {/* The device */}
      <g transform={`translate(${cx} ${cy})`}>
        <circle r={46} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={2} />
        <g className="sc-pop">
          <circle r={46} fill="var(--sc-solid)" stroke="var(--sc-teal)" strokeWidth={3} />
          <rect x={-17} y={-24} width={34} height={30} rx={6} fill="none" stroke="var(--sc-teal)" strokeWidth={2.5} />
          <path d="M -11 -10 l 5 0 l 3 -6 l 4 12 l 3 -6 l 7 0" fill="none" stroke="var(--sc-teal)" strokeWidth={2} />
          <text textAnchor="middle" y={24} style={{ fontSize: fs(10) }} fontWeight={800} fill="var(--sc-teal)">
            REV B
          </text>
        </g>
        <g className="sc-fade" style={at(0, "0.4s")}>
          {/* A halo in the stage colour keeps the name readable where the traced line crosses it */}
          <text
            textAnchor="middle"
            y={68}
            style={{ fontSize: fs(12) }}
            fontWeight={800}
            stroke="var(--sc-solid)"
            strokeWidth={5}
            strokeLinejoin="round"
            paintOrder="stroke"
          >
            OrbitCare 300
          </text>
        </g>
      </g>
      {/* The records */}
      {nodes.map((node, index) => (
        <Chip
          key={node.text}
          x={node.x}
          y={node.y}
          text={node.text}
          tone={["Complaints", "Suppliers", "Lots"].includes(node.text) ? "amber" : "teal"}
          index={index + 3}
        />
      ))}
      <g className="sc-fade" style={at(0, "2.6s")}>
        <text x={20} y={384} style={{ fontSize: fs(12) }} fill="var(--sc-amber)" fontWeight={700}>
          ● Traced: complaints → supplier change → lots 003–004
        </text>
      </g>
      <Illustrative />
    </Scene>
  );
}

/** Product 360: one product record that holds its versions, components, suppliers and lots, with the post-market
 * picture beside it. "See the whole device in one place." */
function Product360({ label }: { label: string }) {
  const tree = [
    { depth: 0, text: "OrbitCare 300", tone: "ink" },
    { depth: 1, text: "Rev A · 2025", tone: "muted" },
    { depth: 1, text: "Rev B · 2026", tone: "teal" },
    { depth: 2, text: "Pressure sensor PS-2", tone: "ink" },
    { depth: 3, text: "Supplier · Kestrel Sensors", tone: "amber" },
    { depth: 2, text: "Lots 003 – 006", tone: "ink" },
  ];
  const stats = [
    { title: "Complaints", value: "42", bar: 0.84, tone: "var(--sc-amber)" },
    { title: "Changes", value: "3", bar: 0.3, tone: "var(--sc-teal)" },
    { title: "Open CAPA", value: "1", bar: 0.12, tone: "var(--sc-blue)" },
  ];
  return (
    <Scene label={label}>
      <Card x={24} y={22} w={592} h={356} index={0}>
        {/* Record header */}
        <rect x={0} y={0} width={592} height={46} rx={12} fill="color-mix(in srgb, var(--sc-teal) 9%, transparent)" />
        <text x={18} y={29} style={{ fontSize: fs(15) }} fontWeight={800}>
          Product 360 · OrbitCare 300
        </text>
        <Chip x={578} y={23} align="end" text="Rev B in focus" tone="teal" index={2} />
        {/* Tree */}
        {tree.map((row, index) => (
          <g key={row.text} className="sc-rise" style={at(index, "0.4s")}>
            {row.depth > 0 && (
              <path
                d={`M ${40 + (row.depth - 1) * 22} ${78 + index * 40 - 30} V ${78 + index * 40} H ${40 + row.depth * 22 - 8}`}
                className="sc-line"
                strokeWidth={1.5}
              />
            )}
            <circle
              cx={40 + row.depth * 22}
              cy={78 + index * 40}
              r={5}
              fill={
                row.tone === "teal"
                  ? "var(--sc-teal)"
                  : row.tone === "amber"
                    ? "var(--sc-amber)"
                    : row.tone === "muted"
                      ? "var(--sc-line)"
                      : "var(--sc-ink-2)"
              }
            />
            <text
              x={52 + row.depth * 22}
              y={82 + index * 40}
              style={{ fontSize: fs(13) }}
              fontWeight={row.depth === 0 ? 800 : 500}
              fill={row.tone === "muted" ? "var(--sc-muted)" : "var(--sc-ink)"}
            >
              {row.text}
            </text>
          </g>
        ))}
        {/* Post-market picture */}
        {stats.map((stat, index) => (
          <g key={stat.title} transform={`translate(340 ${66 + index * 92})`}>
            <g className="sc-rise" style={at(index, "0.9s")}>
              <rect width={232} height={78} rx={10} fill="var(--sc-panel)" stroke="var(--sc-line)" />
              <text x={14} y={24} className="sc-card-title">
                {stat.title}
              </text>
              <text x={14} y={56} style={{ fontSize: fs(26) }} fontWeight={800}>
                {stat.value}
              </text>
              <rect x={80} y={46} width={136} height={8} rx={4} fill="var(--sc-line)" opacity={0.6} />
              <rect
                x={80}
                y={46}
                width={136 * stat.bar}
                height={8}
                rx={4}
                fill={stat.tone}
                className="sc-grow-x"
                style={at(index, "1.3s")}
              />
            </g>
          </g>
        ))}
      </Card>
      <Illustrative x={606} y={392} />
    </Scene>
  );
}

export const platformScenes: Record<string, SceneComponent> = {
  "medtech-product-reality-graph-hero": ProductRealityGraph,
  "medtech-product-360-hero": Product360,
};
