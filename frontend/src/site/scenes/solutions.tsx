import type { CSSProperties, ReactNode } from "react";
import { Card, Illustrative, Scene, at, fs } from "./kit";
import type { SceneComponent } from "./index";

// Scenes for the Solutions page pictures, by picture name (see kit.tsx for the rules every scene follows).
// Most are small cards (about 340 px wide, three to a row), so each shows one idea with a few large labels, an
// entrance of under two seconds and at most one gentle loop. The three families share one system: a header badge in
// the top-left corner (an amber "?" for a challenge, a teal role badge for a role, a blue magnifier for an
// investigation) and the picture below it; an investigation also frames the record in focus with corner brackets.
// Text sizes are set with style: scenes.css gives every scene text 13px, which a fontSize attribute cannot override.

/* ------------------------------------------------------------------------------------------------ Story data */

// The free trial's sample story (site/visuals.tsx): OrbitCare 300 Rev B moved its pressure sensor to PS-2 from
// Kestrel Sensors (change CHG-014), released in week 13; pressure-alarm complaints rise afterwards, mostly from lots
// 003 and 004, the lots built with the new sensor.
const WEEKLY = [3, 2, 4, 3, 2, 3, 4, 2, 3, 3, 2, 3, 4, 6, 7, 6, 9, 8, 11, 10, 9, 12, 10, 11, 9, 10];
const RELEASE = 12; // index of week 13
const LOTS = [
  { lot: "001", count: 2, sensor: false },
  { lot: "002", count: 3, sensor: false },
  { lot: "003", count: 17, sensor: true },
  { lot: "004", count: 13, sensor: true },
  { lot: "005", count: 4, sensor: false },
  { lot: "006", count: 3, sensor: false },
];

/* ------------------------------------------------------------------------------------------------ Shared parts */

type Tone = "teal" | "amber" | "red" | "green" | "blue" | "muted" | "ink" | "ink-2";
const ink = (tone: Tone) => `var(--sc-${tone})`;
const tint = (tone: Tone, percent: number) => `color-mix(in srgb, var(--sc-${tone}) ${percent}%, transparent)`;

/** A line of text at a set size; with a motion class it takes the stagger index and offset. */
function Txt({
  x,
  y,
  size = 18,
  weight = 700,
  tone,
  anchor,
  className,
  index = 0,
  offset,
  spacing,
  children,
}: {
  x: number;
  y: number;
  size?: number;
  weight?: number;
  tone?: Tone;
  anchor?: "start" | "middle" | "end";
  className?: string;
  index?: number;
  offset?: string;
  spacing?: string;
  children: ReactNode;
}) {
  const style: CSSProperties = { ...(className ? at(index, offset) : {}), fontSize: fs(size), letterSpacing: spacing };
  return (
    <text
      x={x}
      y={y}
      textAnchor={anchor}
      fontWeight={weight}
      fill={tone ? ink(tone) : undefined}
      className={className}
      style={style}
    >
      {children}
    </text>
  );
}

/** A card-sized pill: larger than the kit's Chip, so it reads at a third of the page width. "muted" is dashed. */
function Pill({
  x,
  y,
  text,
  tone = "base",
  width,
  size = 16,
  index = 0,
  offset,
}: {
  x: number;
  y: number;
  text: string;
  tone?: "base" | "teal" | "amber" | "red" | "green" | "muted";
  width?: number;
  size?: number;
  index?: number;
  offset?: string;
}) {
  const w = width ?? Math.round(text.length * size * 0.6 + 32);
  const solid = tone !== "base" && tone !== "muted";
  const stroke = tone === "base" ? "var(--sc-line)" : tone === "muted" ? "var(--sc-muted)" : ink(tone);
  return (
    <g transform={`translate(${x} ${y})`}>
      <g className="sc-pop" style={at(index, offset)}>
        <rect x={-w / 2} y={-17} width={w} height={34} rx={17} fill="var(--sc-panel)" />
        <rect
          x={-w / 2}
          y={-17}
          width={w}
          height={34}
          rx={17}
          fill={solid ? tint(tone, 14) : "none"}
          stroke={stroke}
          strokeWidth={1.5}
          strokeDasharray={tone === "muted" ? "5 4" : undefined}
        />
        <text
          textAnchor="middle"
          y={size * 0.36}
          fontWeight={700}
          fill={tone === "base" ? "var(--sc-ink)" : stroke}
          style={{ fontSize: fs(size) }}
        >
          {text}
        </text>
      </g>
    </g>
  );
}

// Line glyphs on a 24-unit grid centred on 0,0, drawn in the stroke of the group that holds them.
const GLYPH = {
  shield: (
    <>
      <path d="M 0 -11 L 9 -7 V 0 C 9 6 5 10 0 12 C -5 10 -9 6 -9 0 V -7 Z" />
      <path d="M -4 0 L -1 3 L 5 -3" />
    </>
  ),
  trail: (
    <>
      <circle cx={-8} cy={8} r={2.5} />
      <circle cx={8} cy={-8} r={2.5} />
      <path d="M -6 6 L -2 0 L 2 3 L 6 -6" />
    </>
  ),
  document: (
    <>
      <path d="M -7 -10 H 3 L 8 -5 V 10 H -7 Z" />
      <path d="M -3 -1 H 4 M -3 4 H 4" />
    </>
  ),
  layers: (
    <>
      <path d="M 0 -9 L 10 -4 L 0 1 L -10 -4 Z" />
      <path d="M -10 2 L 0 7 L 10 2" />
    </>
  ),
  link: (
    <>
      <rect x={-11} y={-5} width={13} height={10} rx={5} />
      <rect x={-2} y={-5} width={13} height={10} rx={5} />
    </>
  ),
  factory: <path d="M -10 9 V -3 L -4 1 V -3 L 2 1 V -9 H 8 V 9 Z" />,
  briefcase: (
    <>
      <rect x={-10} y={-5} width={20} height={14} rx={2} />
      <path d="M -4 -5 V -9 H 4 V -5" />
    </>
  ),
  magnifier: (
    <>
      <circle cx={-2} cy={-2} r={7} />
      <path d="M 3 3 L 9 9" />
    </>
  ),
  sensor: (
    <>
      <rect x={-9} y={-9} width={18} height={18} rx={4} />
      <path d="M -5 1 H -2 L 0 -4 L 2 5 L 4 1 H 6" />
    </>
  ),
  boxes: (
    <>
      <rect x={-10} y={-1} width={9} height={9} rx={1.5} />
      <rect x={1} y={-1} width={9} height={9} rx={1.5} />
      <rect x={-4.5} y={-11} width={9} height={9} rx={1.5} />
    </>
  ),
  device: (
    <>
      <rect x={-10} y={-9} width={20} height={16} rx={3} />
      <path d="M -6 -1 H -3 L -1 -5 L 1 3 L 3 -1 H 6 M -4 11 H 4" />
    </>
  ),
  database: (
    <>
      <ellipse cx={0} cy={-7} rx={9} ry={3.5} />
      <path d="M -9 -7 V 7 C -9 11 9 11 9 7 V -7 M -9 0 C -9 4 9 4 9 0" />
    </>
  ),
  pen: <path d="M -8 8 L -6 2 L 5 -9 L 9 -5 L -2 6 Z M -8 8 L -2 6" />,
  hazard: (
    <>
      <path d="M 0 -10 L 11 9 H -11 Z" />
      <path d="M 0 -3 V 3 M 0 6 V 6.5" />
    </>
  ),
};

/** A glyph in the stroke of a tone, at a scale; position it with the transform of a wrapping group. */
function Glyph({ shape, tone, scale = 1 }: { shape: keyof typeof GLYPH; tone: Tone; scale?: number }) {
  return (
    <g
      transform={scale === 1 ? undefined : `scale(${scale})`}
      fill="none"
      stroke={ink(tone)}
      strokeWidth={2.2 / scale + 0.4}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {GLYPH[shape]}
    </g>
  );
}

/** The family header in the top-left corner: the badge and a short line of text beside it. */
function Head({
  family,
  text,
  glyph = "magnifier",
}: {
  family: "challenge" | "role" | "investigation";
  text: string;
  glyph?: keyof typeof GLYPH;
}) {
  const tone: Tone = family === "challenge" ? "amber" : family === "role" ? "teal" : "blue";
  return (
    <g className="sc-rise">
      <g transform="translate(44 50)">
        {family === "role" ? (
          <rect
            x={-18}
            y={-18}
            width={36}
            height={36}
            rx={10}
            fill={tint(tone, 16)}
            stroke={ink(tone)}
            strokeWidth={2}
          />
        ) : (
          <circle r={18} fill={tint(tone, 16)} stroke={ink(tone)} strokeWidth={2} />
        )}
        {family === "challenge" ? (
          <text textAnchor="middle" y={7.5} fontWeight={800} fill={ink(tone)} style={{ fontSize: fs(21) }}>
            ?
          </text>
        ) : (
          <Glyph shape={family === "role" ? glyph : "magnifier"} tone={tone} />
        )}
      </g>
      <Txt x={74} y={57} size={20} weight={800}>
        {text}
      </Txt>
    </g>
  );
}

/** Corner brackets that draw in around the record an investigation is about. */
function Focus({ x, y, w, h, offset = "0.5s" }: { x: number; y: number; w: number; h: number; offset?: string }) {
  const [x0, y0, x1, y1, l] = [x - 10, y - 10, x + w + 10, y + h + 10, 18];
  const corners = [
    `M ${x0} ${y0 + l} V ${y0} H ${x0 + l}`,
    `M ${x1 - l} ${y0} H ${x1} V ${y0 + l}`,
    `M ${x1} ${y1 - l} V ${y1} H ${x1 - l}`,
    `M ${x0 + l} ${y1} H ${x0} V ${y1 - l}`,
  ];
  return (
    <>
      {corners.map((d) => (
        <path
          key={d}
          d={d}
          pathLength={1}
          className="sc-draw"
          fill="none"
          stroke="var(--sc-blue)"
          strokeWidth={3}
          strokeLinecap="round"
          style={at(0, offset)}
        />
      ))}
    </>
  );
}

/** The kit's Card with its contents in a group of their own: scenes.css styles every rect directly inside a card as
 * the card's background, so a bar drawn straight into a Card would lose its fill. */
function Panel({ children, ...card }: Parameters<typeof Card>[0]) {
  return (
    <Card {...card}>
      <g>{children}</g>
    </Card>
  );
}

/** A check (linked evidence) or an exclamation (a gap) in a small tinted circle. */
function Mark({ x, y, kind, r = 11 }: { x: number; y: number; kind: "ok" | "gap" | "bad"; r?: number }) {
  const tone: Tone = kind === "ok" ? "green" : kind === "gap" ? "amber" : "red";
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle r={r} fill={tint(tone, 16)} stroke={ink(tone)} strokeWidth={1.8} />
      <path
        d={kind === "ok" ? "M -4.5 0 L -1.5 3.5 L 5 -3.5" : "M 0 -5 V 1.5 M 0 5 V 5.2"}
        fill="none"
        stroke={ink(tone)}
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  );
}

/** A line through weekly values inside a box (x, y is the top-left corner). */
function spark(values: number[], x: number, y: number, w: number, h: number, max: number, from = 0, to?: number) {
  const end = to ?? values.length - 1;
  const step = w / (values.length - 1);
  return values
    .slice(from, end + 1)
    .map(
      (value, index) =>
        `${index ? "L" : "M"} ${(x + (from + index) * step).toFixed(1)} ${(y + h - (value / max) * h).toFixed(1)}`,
    )
    .join(" ");
}

/* ------------------------------------------------------------------------------------------------ By challenge */

/** Complaints rising after Rev B, broken down by version (under the weekly bars) and by lot (lots 003 and 004, the
 * new-sensor lots, carry the rise). Solutions hero, and "Understand what is driving an increase in complaints". */
function SolutionComplaints({ label }: { label: string }) {
  const step = 12.6;
  const barW = 8;
  const base = 236;
  const unit = 12.5;
  const marker = 24 + RELEASE * step - (step - barW) / 2;
  const maxLot = 17;
  return (
    <Scene label={label} tone="dark">
      <Head family="challenge" text="Why are pressure alarms rising?" />
      <Panel x={24} y={82} w={372} h={282} index={1}>
        <Txt x={20} y={32} size={15} weight={800} tone="ink-2">
          Pressure-alarm complaints
        </Txt>
        <path d={`M 18 ${base} H 354`} className="sc-line" />
        {WEEKLY.map((value, index) => (
          <rect
            key={index}
            x={24 + index * step}
            y={base - value * unit}
            width={barW}
            height={value * unit}
            rx={2}
            fill={index >= RELEASE ? "var(--sc-amber)" : "var(--sc-teal)"}
            opacity={index >= RELEASE ? 1 : 0.55}
            className="sc-grow-y"
            style={at(0, `${(0.45 + index * 0.035).toFixed(2)}s`)}
          />
        ))}
        <path
          d={`M ${marker} 66 V ${base}`}
          className="sc-link sc-link-amber sc-draw"
          pathLength={1}
          style={at(0, "1.3s")}
          opacity={0.8}
        />
        <Pill x={marker} y={60} text="Rev B · CHG-014" tone="amber" size={15} offset="1.5s" />
        <Txt x={97} y={264} size={16} anchor="middle" tone="muted" className="sc-fade" offset="0.6s">
          Rev A
        </Txt>
        <Txt x={261} y={264} size={15} anchor="middle" tone="amber" className="sc-fade" offset="1.2s">
          Rev B
        </Txt>
      </Panel>
      <Panel x={412} y={82} w={204} h={282} index={2}>
        <Txt x={18} y={32} size={15} weight={800} tone="ink-2">
          By lot
        </Txt>
        {LOTS.map((lot, index) => {
          const y = 70 + index * 34;
          const w = (lot.count / maxLot) * 80;
          return (
            <g key={lot.lot}>
              <Txt x={18} y={y + 5} size={15} weight={600} tone={lot.sensor ? "ink" : "ink-2"}>
                {`Lot ${lot.lot}`}
              </Txt>
              <rect
                x={86}
                y={y - 6}
                width={w}
                height={12}
                rx={6}
                fill={lot.sensor ? "var(--sc-amber)" : "var(--sc-muted)"}
                opacity={lot.sensor ? 1 : 0.6}
                className="sc-grow-x"
                style={at(index, "1.1s")}
              />
              <Txt
                x={104 + w}
                y={y + 5}
                size={14}
                tone={lot.sensor ? "amber" : "muted"}
                className="sc-fade"
                index={index}
                offset="1.5s"
              >
                {lot.count}
              </Txt>
            </g>
          );
        })}
        <circle cx={166} cy={138} r={8} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
        <Txt x={18} y={266} size={14} tone="amber" className="sc-fade" offset="2s">
          ● New sensor PS-2
        </Txt>
      </Panel>
      <Illustrative />
    </Scene>
  );
}

/** Changes on one track, field complaints below: the trend turns after CHG-014, and the two are joined by a dashed
 * "possible link", a relationship to assess rather than a proven cause. "See how product changes relate to field
 * experience." */
function SolutionChanges({ label }: { label: string }) {
  const x0 = 40;
  const w = 560;
  const release = x0 + (RELEASE * w) / (WEEKLY.length - 1);
  const [top, h, max] = [236, 100, 13];
  const after = spark(WEEKLY, x0, top, w, h, max, RELEASE);
  return (
    <Scene label={label}>
      <Head family="challenge" text="Did a change reach the field?" />
      <Txt x={40} y={116} size={16} tone="muted" className="sc-fade" index={1}>
        Changes
      </Txt>
      <path d="M 40 152 H 600" className="sc-line sc-draw" pathLength={1} strokeWidth={3} style={at(2)} />
      {[128, 500].map((x, index) => (
        <circle
          key={x}
          cx={x}
          cy={152}
          r={7}
          fill="var(--sc-panel)"
          stroke="var(--sc-muted)"
          strokeWidth={2}
          className="sc-pop"
          style={at(index + 4)}
        />
      ))}
      <Txt x={40} y={218} size={16} tone="muted" className="sc-fade" index={3}>
        Field complaints
      </Txt>
      <path d={`M ${x0} ${top + h} H ${x0 + w}`} className="sc-line" />
      <g className="sc-fade" style={at(0, "1.6s")}>
        <path d={`${after} L ${x0 + w} ${top + h} L ${release} ${top + h} Z`} fill={tint("amber", 16)} />
      </g>
      <path
        d={spark(WEEKLY, x0, top, w, h, max, 0, RELEASE)}
        className="sc-link sc-draw"
        pathLength={1}
        strokeWidth={3}
        style={at(0, "0.9s")}
      />
      <path d={after} className="sc-link sc-link-amber sc-draw" pathLength={1} strokeWidth={3} style={at(0, "1.5s")} />
      <g className="sc-fade" style={at(0, "1.9s")}>
        <path
          d={`M ${release} 170 V ${top + h}`}
          className="sc-link sc-link-amber sc-link-dashed sc-flow"
          strokeWidth={2.5}
        />
      </g>
      <Pill x={release} y={152} text="CHG-014" tone="amber" size={17} index={6} />
      <Pill x={release + 92} y={212} text="Possible link" tone="muted" size={15} offset="2.1s" />
      <Illustrative />
    </Scene>
  );
}

/** The device, its versions and their lots: impact mapped to Rev B's lots 003 and 004 (a scope outline draws round
 * them), with 005 and 006 still to check. "Map potential impact across products and lots." */
function SolutionAffected({ label }: { label: string }) {
  const tile = (x: number, y: number, lot: string, kind: "base" | "scope" | "check", index: number) => (
    <g key={lot} transform={`translate(${x} ${y})`}>
      <g className="sc-pop" style={at(index, "0.8s")}>
        <rect x={-27} y={-21} width={54} height={42} rx={9} fill="var(--sc-panel)" />
        <rect
          x={-27}
          y={-21}
          width={54}
          height={42}
          rx={9}
          fill={kind === "scope" ? tint("amber", 16) : "none"}
          stroke={kind === "scope" ? "var(--sc-amber)" : kind === "check" ? "var(--sc-muted)" : "var(--sc-line)"}
          strokeWidth={1.8}
          strokeDasharray={kind === "check" ? "5 4" : undefined}
        />
        <text
          textAnchor="middle"
          y={6}
          fontWeight={800}
          fill={kind === "scope" ? "var(--sc-amber)" : kind === "check" ? "var(--sc-muted)" : "var(--sc-ink-2)"}
          style={{ fontSize: fs(17) }}
        >
          {lot}
        </text>
      </g>
    </g>
  );
  const scope =
    "M 368 259 H 484 Q 494 259 494 269 V 311 Q 494 321 484 321 H 368 Q 358 321 358 311 V 269 Q 358 259 368 259 Z";
  return (
    <Scene label={label}>
      <Head family="challenge" text="Which lots could be affected?" />
      <path d="M 197 215 C 222 215 206 140 226 140" className="sc-line sc-draw" pathLength={1} style={at(2)} />
      <path d="M 197 215 C 222 215 206 290 226 290" className="sc-link sc-draw" pathLength={1} style={at(3)} />
      <path d="M 318 140 H 457" className="sc-line sc-draw" pathLength={1} style={at(4)} />
      <path d="M 318 290 H 591" className="sc-link sc-draw" pathLength={1} style={at(5)} opacity={0.6} />
      <Pill x={112} y={215} text="OrbitCare 300" size={17} width={170} index={1} />
      <Pill x={272} y={140} text="Rev A" size={17} width={92} index={2} />
      <Pill x={272} y={290} text="Rev B" tone="teal" size={17} width={92} index={3} />
      {tile(395, 140, "001", "base", 0)}
      {tile(457, 140, "002", "base", 1)}
      {tile(395, 290, "003", "scope", 2)}
      {tile(457, 290, "004", "scope", 3)}
      {tile(531, 290, "005", "check", 4)}
      {tile(591, 290, "006", "check", 5)}
      <path
        d={scope}
        pathLength={1}
        className="sc-draw"
        fill="none"
        stroke="var(--sc-amber)"
        strokeWidth={2.5}
        style={at(0, "1.7s")}
      />
      <Txt x={426} y={350} size={16} weight={800} anchor="middle" tone="amber" className="sc-fade" offset="1.9s">
        Potential scope
      </Txt>
      <Txt x={561} y={350} size={16} anchor="middle" tone="muted" className="sc-fade" offset="2s">
        To check
      </Txt>
      <Illustrative />
    </Scene>
  );
}

/** A supplier issue followed hop by hop: Kestrel Sensors → sensor PS-2 → lots 003 and 004 → OrbitCare 300, with a
 * trace flowing along the chain. "Follow supplier relationships through to product impact." */
function SolutionSupplier({ label }: { label: string }) {
  const nodes: { x: number; text: string; glyph: keyof typeof GLYPH; tone: Tone }[] = [
    { x: 100, text: "Kestrel Sensors", glyph: "factory", tone: "amber" },
    { x: 247, text: "PS-2 sensor", glyph: "sensor", tone: "amber" },
    { x: 394, text: "Lots 003 · 004", glyph: "boxes", tone: "amber" },
    { x: 541, text: "OrbitCare 300", glyph: "device", tone: "teal" },
  ];
  const cy = 196;
  const r = 44;
  return (
    <Scene label={label}>
      <Head family="challenge" text="Where does a supplier issue reach?" />
      {nodes.slice(1).map((node, index) => (
        <path
          key={node.text}
          d={`M ${nodes[index].x + r} ${cy} H ${node.x - r}`}
          className="sc-line sc-draw"
          pathLength={1}
          strokeWidth={4}
          style={at(index * 2 + 2, "0.2s")}
        />
      ))}
      <g className="sc-fade" style={at(0, "1.8s")}>
        <path
          d={`M ${nodes[0].x + r} ${cy} H ${nodes[3].x - r}`}
          className="sc-link sc-link-amber sc-link-dashed sc-flow"
          strokeWidth={3}
        />
      </g>
      {nodes.map((node, index) => (
        <g key={node.text} transform={`translate(${node.x} ${cy})`}>
          {index === 3 && <circle r={r} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={2} />}
          <g className="sc-pop" style={at(index * 2 + 1, "0.1s")}>
            <circle r={r} fill="var(--sc-panel)" />
            <circle r={r} fill={tint(node.tone, 14)} stroke={ink(node.tone)} strokeWidth={2.5} />
            <Glyph shape={node.glyph} tone={node.tone} scale={1.6} />
            <Txt x={0} y={86} size={18} weight={800} anchor="middle">
              {node.text}
            </Txt>
          </g>
        </g>
      ))}
      <Illustrative />
    </Scene>
  );
}

/** Scattered records (a test report, field reports, supplier certificates) drawn into one decision context, where
 * the evidence still missing shows as a gap. "Bring scattered evidence into the decision context." */
function SolutionEvidence({ label }: { label: string }) {
  const docs = [
    { x: 40, y: 96, turn: -5, text: "Test report" },
    { x: 70, y: 182, turn: 4, text: "Field reports" },
    { x: 34, y: 268, turn: -3, text: "Supplier certs" },
  ];
  const panel = { x: 340, y: 92 };
  return (
    <Scene label={label}>
      <Head family="challenge" text="Where is the evidence?" />
      {docs.map((doc, index) => {
        const sx = doc.x + 184;
        const sy = doc.y + 28;
        const ty = panel.y + 78 + index * 48;
        return (
          <path
            key={doc.text}
            d={`M ${sx} ${sy} C ${sx + 50} ${sy} ${panel.x - 50} ${ty} ${panel.x} ${ty}`}
            className="sc-link sc-draw"
            pathLength={1}
            strokeWidth={2.5}
            style={at(index, "0.9s")}
          />
        );
      })}
      {docs.map((doc, index) => (
        <g key={doc.text} transform={`translate(${doc.x} ${doc.y}) rotate(${doc.turn})`}>
          <g className="sc-rise" style={at(index + 1)}>
            <rect width={184} height={56} rx={10} fill="var(--sc-panel)" stroke="var(--sc-line)" />
            <g transform="translate(26 28)">
              <Glyph shape="document" tone="teal" />
            </g>
            <Txt x={48} y={34} size={16}>
              {doc.text}
            </Txt>
          </g>
        </g>
      ))}
      <Panel x={panel.x} y={panel.y} w={272} h={262} index={2}>
        <Txt x={20} y={36} size={17} weight={800}>
          Decision context
        </Txt>
        {[0, 1, 2].map((row) => (
          <g key={row} className="sc-fade" style={at(row, "1.4s")}>
            <Mark x={30} y={78 + row * 48} kind="ok" />
            <rect x={52} y={72 + row * 48} width={150 - row * 24} height={12} rx={6} fill="var(--sc-line)" />
          </g>
        ))}
        <g className="sc-fade" style={at(0, "1.9s")}>
          <rect
            x={14}
            y={200}
            width={244}
            height={44}
            rx={10}
            fill={tint("amber", 8)}
            stroke="var(--sc-amber)"
            strokeDasharray="5 4"
          />
          <Mark x={34} y={222} kind="gap" />
          <Txt x={56} y={228} size={16} tone="amber">
            Missing record
          </Txt>
        </g>
        <circle cx={34} cy={222} r={11} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
      </Panel>
      <Illustrative />
    </Scene>
  );
}

/** Two suspected causes weighed against linked evidence: dots for each record that supports (green) or conflicts
 * with (red) each one, with no verdict drawn. "Test suspected causes against connected evidence." */
function SolutionChallenge({ label }: { label: string }) {
  const causes = [
    { x: 32, name: "Sensor change", supports: 5, conflicts: 0 },
    { x: 332, name: "Use error", supports: 1, conflicts: 3 },
  ];
  return (
    <Scene label={label}>
      <Head family="challenge" text="Which cause holds up?" />
      {causes.map((cause, card) => (
        <Panel key={cause.name} x={cause.x} y={100} w={276} h={214} index={card + 1}>
          <Txt x={22} y={48} size={20} weight={800}>
            {cause.name}
          </Txt>
          <path d="M 22 72 H 254" className="sc-line" strokeWidth={1.5} />
          <Txt x={22} y={120} size={16} tone="muted">
            For
          </Txt>
          <Txt x={22} y={176} size={16} tone="muted">
            Against
          </Txt>
          {Array.from({ length: cause.supports }, (_, index) => (
            <circle
              key={`s${index}`}
              cx={112 + index * 28}
              cy={114}
              r={10}
              fill="var(--sc-green)"
              className="sc-pop"
              style={at(index + card * 3, "0.7s")}
            />
          ))}
          {Array.from({ length: cause.conflicts }, (_, index) => (
            <circle
              key={`c${index}`}
              cx={112 + index * 28}
              cy={170}
              r={9}
              fill={tint("red", 14)}
              stroke="var(--sc-red)"
              strokeWidth={2.5}
              className="sc-pop"
              style={at(index + card * 3, "1.1s")}
            />
          ))}
          {cause.conflicts === 0 && (
            <Txt x={102} y={176} size={16} tone="muted" className="sc-fade" offset="1.2s">
              None yet
            </Txt>
          )}
        </Panel>
      ))}
      <Illustrative />
    </Scene>
  );
}

/** An evidence checklist where the gaps stand out: two records linked, supplier test data missing and the risk file
 * review outdated. "Make evidence gaps visible before decisions are finalized." */
function SolutionUnknowns({ label }: { label: string }) {
  const rows: { text: string; kind: "ok" | "gap" | "bad"; status?: string }[] = [
    { text: "Complaint records", kind: "ok" },
    { text: "Lot build records", kind: "ok" },
    { text: "Supplier test data", kind: "gap", status: "Missing" },
    { text: "Risk file review", kind: "bad", status: "Outdated" },
  ];
  return (
    <Scene label={label}>
      <Head family="challenge" text="What is still unknown?" />
      <Panel x={64} y={90} w={512} h={266} index={1}>
        {rows.map((row, index) => {
          const cy = 46 + index * 58;
          const tone: Tone = row.kind === "gap" ? "amber" : "red";
          return (
            <g key={row.text} className="sc-rise" style={at(index, "0.4s")}>
              {row.status && (
                <rect
                  x={12}
                  y={cy - 24}
                  width={488}
                  height={48}
                  rx={10}
                  fill={tint(tone, 8)}
                  stroke={ink(tone)}
                  strokeDasharray="5 4"
                />
              )}
              <Mark x={38} y={cy} kind={row.kind} r={13} />
              <Txt x={64} y={cy + 6} size={18} tone={row.status ? "ink" : "ink-2"}>
                {row.text}
              </Txt>
            </g>
          );
        })}
        {rows.map(
          (row, index) =>
            row.status && (
              <Pill
                key={row.text}
                x={430}
                y={46 + index * 58}
                text={row.status}
                tone={row.kind === "gap" ? "amber" : "red"}
                size={15}
                width={110}
                index={index}
                offset="1.2s"
              />
            ),
        )}
        <circle cx={38} cy={162} r={13} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
      </Panel>
      <Illustrative />
    </Scene>
  );
}

/* ------------------------------------------------------------------------------------------------ By role */

/** A quality leader's view: four tiles for the signal, evidence strength, risk context and the decision awaiting a
 * human sign-off. Company hero, and "Give quality leaders the full investigation picture". */
function RoleQualityLeaders({ label }: { label: string }) {
  const tiles = [
    { x: 24, y: 84, caption: "SIGNAL", title: "Pressure alarms" },
    { x: 324, y: 84, caption: "EVIDENCE", title: "7 linked · 2 gaps" },
    { x: 24, y: 228, caption: "RISK", title: "1 hazard · 2 controls" },
    { x: 324, y: 228, caption: "DECISION", title: "Human sign-off" },
  ];
  const sparkBox = [18, 66, 256, 52] as const;
  const releaseX = sparkBox[0] + (RELEASE * sparkBox[2]) / (WEEKLY.length - 1);
  return (
    <Scene label={label} tone="dark">
      <Head family="role" glyph="shield" text="Quality leader" />
      {tiles.map((tile, index) => (
        <Panel key={tile.caption} x={tile.x} y={tile.y} w={292} h={132} index={index + 1}>
          <Txt x={18} y={28} size={14} weight={800} tone="muted" spacing="0.08em">
            {tile.caption}
          </Txt>
          <Txt x={18} y={54} size={18} weight={800}>
            {tile.title}
          </Txt>
        </Panel>
      ))}
      {/* Signal: the weekly trend, turning after Rev B */}
      <g transform="translate(24 84)">
        <path
          d={`M ${releaseX} 66 V 118`}
          stroke="var(--sc-amber)"
          strokeWidth={1.5}
          strokeDasharray="3 4"
          opacity={0.7}
        />
        <path
          d={spark(WEEKLY, ...sparkBox, 12)}
          className="sc-link sc-link-amber sc-draw"
          pathLength={1}
          strokeWidth={2.5}
          style={at(0, "0.9s")}
        />
      </g>
      {/* Evidence: seven linked records and two gaps */}
      <g transform="translate(324 84)">
        {Array.from({ length: 9 }, (_, index) => (
          <rect
            key={index}
            x={18 + index * 29}
            y={74}
            width={24}
            height={36}
            rx={6}
            fill={index < 7 ? tint("green", 30) : "none"}
            stroke={index < 7 ? "var(--sc-green)" : "var(--sc-amber)"}
            strokeWidth={1.8}
            strokeDasharray={index < 7 ? undefined : "4 3"}
            className="sc-pop"
            style={at(index, "1s")}
          />
        ))}
      </g>
      {/* Risk: a hazard and the two controls linked to it */}
      <g transform="translate(24 228)">
        <g className="sc-fade" style={at(0, "1.2s")}>
          <path d="M 46 98 H 70" className="sc-line" />
          <g transform="translate(32 98)">
            <Glyph shape="hazard" tone="amber" scale={1.2} />
          </g>
        </g>
        <Pill x={122} y={98} text="Inspection" tone="teal" size={15} width={104} offset="1.4s" />
        <Pill x={234} y={98} text="Self-test" tone="teal" size={15} width={96} offset="1.55s" />
      </g>
      {/* Decision: the signature line, pending */}
      <g transform="translate(324 228)">
        <g className="sc-fade" style={at(0, "1.4s")}>
          <g transform="translate(28 100)">
            <Glyph shape="pen" tone="ink-2" />
          </g>
          <path d="M 48 108 H 168" stroke="var(--sc-muted)" strokeWidth={1.5} strokeDasharray="4 4" />
        </g>
        <circle cx={178} cy={108} r={7} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
        <Pill x={232} y={100} text="Pending" tone="amber" size={15} width={96} offset="1.7s" />
      </g>
      <Illustrative />
    </Scene>
  );
}

/** An investigator's path from signal to evidence, step by step: a pressure-alarm complaint → Rev B → lot 003 → the
 * test report that supports the finding. "Move from signal to evidence with confidence." */
function RoleInvestigators({ label }: { label: string }) {
  const steps: { x: number; y: number; text: string; tone: "amber" | "base" | "green" }[] = [
    { x: 122, y: 316, text: "Pressure alarm", tone: "amber" },
    { x: 252, y: 252, text: "Rev B", tone: "base" },
    { x: 382, y: 188, text: "Lot 003", tone: "base" },
    { x: 512, y: 124, text: "Test report", tone: "green" },
  ];
  const width = (text: string) => Math.round(text.length * 17 * 0.6 + 32);
  const legs = steps.slice(1).map((step, index) => {
    const prev = steps[index];
    return `M ${prev.x + width(prev.text) / 2} ${prev.y} H ${step.x} V ${step.y + 17}`;
  });
  return (
    <Scene label={label}>
      <Head family="role" glyph="trail" text="Investigator" />
      {legs.map((d, index) => (
        <path
          key={d}
          d={d}
          className="sc-link sc-draw"
          pathLength={1}
          strokeWidth={2.5}
          style={at(index * 2, "0.5s")}
        />
      ))}
      <g className="sc-fade" style={at(0, "1.9s")}>
        <path
          d={legs.join(" ")}
          className="sc-link sc-link-dashed sc-flow"
          strokeWidth={1.5}
          style={{ stroke: "var(--sc-panel)" }}
        />
      </g>
      {steps.map((step, index) => (
        <Pill
          key={step.text}
          x={step.x}
          y={step.y}
          text={step.text}
          tone={step.tone}
          size={17}
          index={index * 2}
          offset="0.3s"
        />
      ))}
      <Txt x={122} y={356} size={16} anchor="middle" tone="muted" className="sc-fade" offset="0.6s">
        Signal
      </Txt>
      <Txt x={512} y={92} size={15} anchor="middle" tone="green" className="sc-fade" offset="1.6s">
        Evidence
      </Txt>
      <Illustrative />
    </Scene>
  );
}

/** Regulatory review context: a reportability decision with its reasons kept, and the reporting windows that apply
 * (FDA, EU, UK and Canada, as illustrative day counts). "Prepare traceable review context." */
function RoleRegulatory({ label }: { label: string }) {
  const windows = [
    { region: "FDA", days: 30 },
    { region: "EU", days: 15 },
    { region: "UK", days: 15 },
    { region: "Canada", days: 30 },
  ];
  return (
    <Scene label={label}>
      <Head family="role" glyph="document" text="Regulatory affairs" />
      <Panel x={24} y={88} w={286} h={264} index={1}>
        <Txt x={20} y={36} size={18} weight={800}>
          Reportability
        </Txt>
        {["Malfunction", "Could recur"].map((reason, index) => (
          <g key={reason} className="sc-rise" style={at(index, "0.6s")}>
            <Mark x={30} y={80 + index * 42} kind="ok" />
            <Txt x={50} y={86 + index * 42} size={16}>
              {reason}
            </Txt>
          </g>
        ))}
        <path d="M 20 158 H 266" className="sc-line" strokeWidth={1.5} />
        <Txt x={20} y={192} size={14} weight={800} tone="muted" className="sc-fade" offset="1s">
          Decision
        </Txt>
        <Pill x={88} y={224} text="Reportable" tone="amber" size={16} width={136} offset="1.2s" />
        <Txt x={166} y={230} size={15} tone="ink-2" className="sc-fade" offset="1.4s">
          by reviewer
        </Txt>
      </Panel>
      <Panel x={326} y={88} w={290} h={264} index={2}>
        <Txt x={20} y={36} size={18} weight={800}>
          Reporting windows
        </Txt>
        {windows.map((row, index) => {
          const y = 82 + index * 46;
          const w = (row.days / 30) * 110;
          return (
            <g key={row.region}>
              <Txt x={20} y={y + 6} size={16} weight={800}>
                {row.region}
              </Txt>
              <rect x={100} y={y - 7} width={110} height={14} rx={7} fill="var(--sc-line)" opacity={0.5} />
              <rect
                x={100}
                y={y - 7}
                width={w}
                height={14}
                rx={7}
                fill="var(--sc-teal)"
                className="sc-grow-x"
                style={at(index, "0.9s")}
              />
              <Txt x={222} y={y + 6} size={15} tone="ink-2" className="sc-fade" index={index} offset="1.2s">
                {`${row.days} d`}
              </Txt>
            </g>
          );
        })}
      </Panel>
      <Illustrative />
    </Scene>
  );
}

/** Product and R&D: Rev A and Rev B with the change between them (CHG-014, the new sensor PS-2), each connected to
 * its field outcome. "Connect product changes to outcomes." */
function RoleProduct({ label }: { label: string }) {
  return (
    <Scene label={label}>
      <Head family="role" glyph="layers" text="Product & R&D" />
      <path d="M 132 196 V 248" className="sc-link sc-draw" pathLength={1} strokeWidth={2.5} style={at(0, "0.6s")} />
      <path d="M 232 142 H 280" className="sc-line sc-draw" pathLength={1} style={at(0, "1.1s")} />
      <path d="M 232 298 H 280" className="sc-link sc-draw" pathLength={1} style={at(0, "1.2s")} />
      <Panel x={32} y={92} w={200} h={104} index={1}>
        <Txt x={22} y={50} size={26} weight={800} tone="ink-2">
          Rev A
        </Txt>
        <Txt x={22} y={80} size={16} tone="muted">
          Released 2025
        </Txt>
      </Panel>
      <Panel x={32} y={248} w={200} h={104} index={3}>
        <rect width={200} height={104} rx={12} fill="none" stroke="var(--sc-teal)" strokeWidth={2} />
        <Txt x={22} y={50} size={26} weight={800}>
          Rev B
        </Txt>
        <Txt x={22} y={80} size={15} tone="amber">
          Sensor PS-2
        </Txt>
      </Panel>
      <Pill x={132} y={222} text="CHG-014" tone="amber" size={15} width={104} index={2} />
      <Panel x={280} y={92} w={332} h={260} index={2}>
        <Txt x={20} y={36} size={17} weight={800}>
          Field complaints
        </Txt>
        <path d="M 40 226 H 300" className="sc-line" />
        <rect
          x={74}
          y={206}
          width={56}
          height={20}
          rx={5}
          fill="var(--sc-muted)"
          opacity={0.6}
          className="sc-grow-y"
          style={at(0, "1.1s")}
        />
        <rect
          x={204}
          y={78}
          width={56}
          height={148}
          rx={5}
          fill="var(--sc-amber)"
          className="sc-grow-y"
          style={at(0, "1.3s")}
        />
        <Txt x={102} y={196} size={22} weight={800} anchor="middle" tone="ink-2" className="sc-fade" offset="1.5s">
          5
        </Txt>
        <Txt x={232} y={68} size={22} weight={800} anchor="middle" tone="amber" className="sc-fade" offset="1.8s">
          37
        </Txt>
        <Txt x={102} y={250} size={16} anchor="middle" tone="muted">
          Rev A
        </Txt>
        <Txt x={232} y={250} size={15} anchor="middle" tone="ink-2">
          Rev B
        </Txt>
      </Panel>
      <Illustrative />
    </Scene>
  );
}

/** Supplier quality: the supplier → component → lots relationship, and the incoming inspection per lot that fell
 * from 32 to 13 units with Rev B. "Follow supplier and component relationships." */
function RoleSupplierQuality({ label }: { label: string }) {
  const rows = [
    { rev: "Rev A", units: 32, tone: "teal" as Tone },
    { rev: "Rev B", units: 13, tone: "amber" as Tone },
  ];
  return (
    <Scene label={label}>
      <Head family="role" glyph="link" text="Supplier quality" />
      <path d="M 200 126 H 248" className="sc-link sc-draw" pathLength={1} strokeWidth={2.5} style={at(2)} />
      <path d="M 364 126 H 412" className="sc-link sc-draw" pathLength={1} strokeWidth={2.5} style={at(4)} />
      <Pill x={118} y={126} text="Kestrel Sensors" size={16} index={1} />
      <Pill x={306} y={126} text="PS-2 sensor" size={16} index={3} />
      <Pill x={490} y={126} text="Lots 003 · 004" tone="amber" size={16} index={5} />
      <Panel x={40} y={182} w={560} h={172} index={3}>
        <Txt x={22} y={38} size={16} weight={800} tone="ink-2">
          Incoming inspection per lot
        </Txt>
        {rows.map((row, index) => {
          const y = 84 + index * 52;
          const w = (row.units / 32) * 330;
          return (
            <g key={row.rev}>
              <Txt x={22} y={y + 6} size={16} tone={index ? "ink" : "ink-2"}>
                {row.rev}
              </Txt>
              <rect
                x={100}
                y={y - 10}
                width={w}
                height={20}
                rx={6}
                fill={ink(row.tone)}
                className="sc-grow-x"
                style={at(index * 3, "1s")}
              />
              <Txt
                x={124 + w}
                y={y + 7}
                size={20}
                weight={800}
                tone={row.tone}
                className="sc-fade"
                index={index * 3}
                offset="1.4s"
              >
                {`${row.units}`}
              </Txt>
            </g>
          );
        })}
        <circle cx={230} cy={136} r={10} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
      </Panel>
      <Illustrative />
    </Scene>
  );
}

/** Manufacturing quality: lots 001–006 along the line, CHG-014 between 002 and 003, and the complaints above each lot
 * rising for the lots built with the new sensor. "Understand affected lots and changes." */
function RoleManufacturing({ label }: { label: string }) {
  const xs = [80, 170, 280, 370, 460, 550];
  return (
    <Scene label={label}>
      <Head family="role" glyph="factory" text="Manufacturing quality" />
      <rect x={30} y={292} width={580} height={10} rx={5} fill="var(--sc-line)" />
      <path d="M 36 297 H 604" className="sc-link sc-link-dashed sc-flow" strokeWidth={2} opacity={0.6} />
      <g className="sc-fade" style={at(0, "1.2s")}>
        <path d="M 225 118 V 304" className="sc-link sc-link-amber sc-link-dashed" strokeWidth={2.5} />
      </g>
      {LOTS.map((lot, index) => (
        <g key={lot.lot}>
          <rect
            x={xs[index] - 11}
            y={226 - lot.count * 6}
            width={22}
            height={lot.count * 6}
            rx={4}
            fill={lot.sensor ? "var(--sc-amber)" : "var(--sc-muted)"}
            opacity={lot.sensor ? 1 : 0.55}
            className="sc-grow-y"
            style={at(index, "0.9s")}
          />
          <g transform={`translate(${xs[index]} 262)`}>
            <g className="sc-rise" style={at(index, "0.2s")}>
              <rect x={-36} y={-26} width={72} height={52} rx={9} fill="var(--sc-panel)" />
              <rect
                x={-36}
                y={-26}
                width={72}
                height={52}
                rx={9}
                fill={lot.sensor ? tint("amber", 16) : "none"}
                stroke={lot.sensor ? "var(--sc-amber)" : "var(--sc-line)"}
                strokeWidth={1.8}
              />
              <text
                textAnchor="middle"
                y={6}
                fontWeight={800}
                fill={lot.sensor ? "var(--sc-amber)" : "var(--sc-ink-2)"}
                style={{ fontSize: fs(18) }}
              >
                {lot.lot}
              </text>
            </g>
          </g>
        </g>
      ))}
      <Pill x={225} y={100} text="CHG-014" tone="amber" size={16} width={110} offset="1.3s" />
      <Txt x={610} y={150} size={15} anchor="end" tone="muted" className="sc-fade" offset="1.6s">
        Complaints
      </Txt>
      <Txt x={125} y={334} size={16} anchor="middle" tone="muted" className="sc-fade" offset="0.6s">
        Rev A
      </Txt>
      <Txt x={415} y={334} size={15} anchor="middle" tone="teal" className="sc-fade" offset="0.8s">
        Rev B
      </Txt>
      <Illustrative />
    </Scene>
  );
}

/** The executive summary: what is known, challenged and unresolved, and the sign-off that still needs a human.
 * "Review decision-ready assurance." */
function RoleExecutives({ label }: { label: string }) {
  const columns: { value: string; text: string; tone: Tone; share: number }[] = [
    { value: "7", text: "Known", tone: "green", share: 1 },
    { value: "2", text: "Challenged", tone: "amber", share: 0.4 },
    { value: "1", text: "Unresolved", tone: "red", share: 0.2 },
  ];
  return (
    <Scene label={label}>
      <Head family="role" glyph="briefcase" text="Executive" />
      <Panel x={40} y={88} w={560} h={172} index={1}>
        {[187, 373].map((x) => (
          <path key={x} d={`M ${x} 30 V 142`} className="sc-line" strokeWidth={1.5} />
        ))}
        {columns.map((column, index) => {
          const cx = 93 + index * 187;
          return (
            <g key={column.text}>
              <g className="sc-rise" style={at(index, "0.5s")}>
                <Txt x={cx} y={84} size={44} weight={800} anchor="middle" tone={column.tone}>
                  {column.value}
                </Txt>
                <Txt x={cx} y={120} size={17} anchor="middle" tone="ink-2">
                  {column.text}
                </Txt>
              </g>
              <rect x={cx - 60} y={138} width={120} height={6} rx={3} fill="var(--sc-line)" opacity={0.6} />
              <rect
                x={cx - 60}
                y={138}
                width={120 * column.share}
                height={6}
                rx={3}
                fill={ink(column.tone)}
                className="sc-grow-x"
                style={at(index, "0.9s")}
              />
            </g>
          );
        })}
      </Panel>
      <Panel x={40} y={276} w={560} h={76} index={3}>
        <g transform="translate(34 38)">
          <Glyph shape="pen" tone="ink-2" />
        </g>
        <Txt x={60} y={45} size={18} weight={800}>
          Sign-off required
        </Txt>
        <path d="M 250 50 H 396" stroke="var(--sc-muted)" strokeWidth={1.5} strokeDasharray="4 4" />
        <circle cx={406} cy={50} r={7} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
        <Pill x={480} y={38} text="Pending" tone="amber" size={15} width={104} offset="1.4s" />
      </Panel>
      <Illustrative />
    </Scene>
  );
}

/* ------------------------------------------------------------------------------------------------ By investigation */

/** The complaint signal in focus (42 pressure-alarm complaints and their trend), linked to the version and lots it
 * relates to, with the cause left an open question. "Understand the signal before deciding what changed." */
function InvestigationComplaint({ label }: { label: string }) {
  const links: { y: number; text: string; tone: "teal" | "amber" | "muted"; w: number }[] = [
    { y: 130, text: "Rev B", tone: "teal", w: 92 },
    { y: 210, text: "Lots 003 · 004", tone: "amber", w: 166 },
    { y: 290, text: "Cause: open", tone: "muted", w: 140 },
  ];
  return (
    <Scene label={label}>
      <Head family="investigation" text="Complaint investigation" />
      {links.map((link, index) =>
        link.tone === "muted" ? (
          <g key={link.text} className="sc-fade" style={at(0, "1.5s")}>
            <path
              d={`M 352 210 C 398 210 390 ${link.y} ${500 - link.w / 2} ${link.y}`}
              className="sc-line"
              strokeDasharray="4 5"
            />
          </g>
        ) : (
          <path
            key={link.text}
            d={`M 352 210 C 398 210 390 ${link.y} ${500 - link.w / 2} ${link.y}`}
            className={`sc-link sc-draw ${link.tone === "amber" ? "sc-link-amber" : ""}`}
            pathLength={1}
            strokeWidth={2.5}
            style={at(index, "1s")}
          />
        ),
      )}
      <Panel x={60} y={104} w={280} h={212} index={1}>
        <Txt x={20} y={40} size={20} weight={800}>
          Pressure alarm
        </Txt>
        <Txt x={20} y={94} size={40} weight={800} tone="amber">
          42
        </Txt>
        <Txt x={78} y={93} size={16} tone="muted">
          complaints
        </Txt>
        <path
          d={spark(WEEKLY, 20, 116, 240, 70, 12)}
          className="sc-link sc-link-amber sc-draw"
          pathLength={1}
          strokeWidth={2.5}
          style={at(0, "0.7s")}
        />
      </Panel>
      <Focus x={60} y={104} w={280} h={212} />
      {links.map((link, index) => (
        <Pill
          key={link.text}
          x={500}
          y={link.y}
          text={link.text}
          tone={link.tone}
          size={16}
          width={link.w}
          index={index}
          offset="1.3s"
        />
      ))}
      <Illustrative />
    </Scene>
  );
}

/** Two released versions side by side, Rev B in focus: its release, its share of the complaints, and its place in
 * the investigation. "See which product version belongs in the investigation." */
function InvestigationVersion({ label }: { label: string }) {
  const versions = [
    { x: 50, name: "Rev A", date: "Released 2025", complaints: 5, focus: false },
    { x: 354, name: "Rev B", date: "Released 2026", complaints: 37, focus: true },
  ];
  return (
    <Scene label={label}>
      <Head family="investigation" text="Version investigation" />
      {versions.map((version, index) => (
        <Panel key={version.name} x={version.x} y={100} w={236} h={196} index={index + 1}>
          <g>
            <Txt x={22} y={52} size={30} weight={800}>
              {version.name}
            </Txt>
            <Txt x={22} y={80} size={16} tone="muted">
              {version.date}
            </Txt>
            <path d="M 22 104 H 214" className="sc-line" strokeWidth={1.5} />
            <Txt x={22} y={150} size={30} weight={800} tone={version.focus ? "amber" : "ink-2"}>
              {`${version.complaints}`}
            </Txt>
            <Txt x={version.focus ? 66 : 46} y={149} size={16} tone="muted">
              complaints
            </Txt>
            <rect x={22} y={166} width={192} height={10} rx={5} fill="var(--sc-line)" opacity={0.6} />
            <rect
              x={22}
              y={166}
              width={(version.complaints / 37) * 192}
              height={10}
              rx={5}
              fill={version.focus ? "var(--sc-amber)" : "var(--sc-muted)"}
              className="sc-grow-x"
              style={at(index, "1s")}
            />
          </g>
        </Panel>
      ))}
      <Focus x={354} y={100} w={236} h={196} offset="0.8s" />
      <Pill x={472} y={340} text="In the investigation" tone="teal" size={16} offset="1.5s" />
      <Illustrative />
    </Scene>
  );
}

/** The change record in focus (CHG-014: a new sensor supplier, inspection cut from 32 to 13 units), traced to the
 * outcomes it may affect by dashed links, relationships rather than proof. "Trace product changes to the outcomes
 * they may affect." */
function InvestigationChange({ label }: { label: string }) {
  const outcomes: { x: number; text: string; tone: "amber" | "base" }[] = [
    { x: 128, text: "Pressure alarms", tone: "amber" },
    { x: 320, text: "Lots 003 · 004", tone: "base" },
    { x: 512, text: "Risk file", tone: "base" },
  ];
  return (
    <Scene label={label}>
      <Head family="investigation" text="Change investigation" />
      <g className="sc-fade" style={at(0, "1.1s")}>
        {outcomes.map((outcome) => (
          <path
            key={outcome.text}
            d={`M 320 236 C 320 272 ${outcome.x} 262 ${outcome.x} 299`}
            className="sc-link sc-link-dashed sc-flow"
            strokeWidth={2.5}
          />
        ))}
      </g>
      <Panel x={190} y={102} w={260} h={124} index={1}>
        <Txt x={20} y={42} size={24} weight={800} tone="amber">
          CHG-014
        </Txt>
        <Txt x={20} y={72} size={16} tone="ink-2">
          New sensor supplier
        </Txt>
        <Txt x={20} y={104} size={16} weight={800}>
          Inspection 32 → 13
        </Txt>
      </Panel>
      <Focus x={190} y={102} w={260} h={124} />
      {outcomes.map((outcome, index) => (
        <Pill
          key={outcome.text}
          x={outcome.x}
          y={316}
          text={outcome.text}
          tone={outcome.tone}
          size={16}
          index={index}
          offset="1.3s"
        />
      ))}
      <Txt x={320} y={364} size={16} anchor="middle" tone="muted" className="sc-fade" offset="1.8s">
        Relationships, not proof
      </Txt>
      <Illustrative />
    </Scene>
  );
}

/** The supplier in focus, Kestrel Sensors, with its context fanned out: the component it supplies, the change that
 * brought it in, the lots built with it and the complaints from them. "Follow supplier context through to product
 * impact." */
function InvestigationSupplier({ label }: { label: string }) {
  const context: { y: number; text: string; tone: "amber" | "base" }[] = [
    { y: 112, text: "PS-2 sensor", tone: "base" },
    { y: 180, text: "CHG-014", tone: "base" },
    { y: 248, text: "Lots 003 · 004", tone: "amber" },
    { y: 316, text: "30 complaints", tone: "amber" },
  ];
  const width = (text: string) => Math.round(text.length * 16 * 0.6 + 32);
  return (
    <Scene label={label}>
      <Head family="investigation" text="Supplier investigation" />
      {context.map((item, index) => (
        <path
          key={item.text}
          d={`M 282 205 C 340 205 350 ${item.y} ${492 - width(item.text) / 2} ${item.y}`}
          className="sc-link sc-draw"
          pathLength={1}
          strokeWidth={2.5}
          style={at(index, "0.9s")}
        />
      ))}
      <Panel x={40} y={130} w={230} h={150} index={1}>
        <g transform="translate(36 40)">
          <Glyph shape="factory" tone="amber" scale={1.3} />
        </g>
        <Txt x={20} y={94} size={19} weight={800}>
          Kestrel Sensors
        </Txt>
        <Txt x={20} y={122} size={16} tone="muted">
          Sensor supplier
        </Txt>
      </Panel>
      <Focus x={40} y={130} w={230} h={150} />
      {context.map((item, index) => (
        <Pill
          key={item.text}
          x={492}
          y={item.y}
          text={item.text}
          tone={item.tone}
          size={16}
          index={index}
          offset="1.2s"
        />
      ))}
      <Illustrative />
    </Scene>
  );
}

/** One component in focus, sensor PS-2, and its thread through the device lifecycle: specification, supplier,
 * build and field, where the signal shows. "Trace a component across the device lifecycle." */
function InvestigationComponent({ label }: { label: string }) {
  const stages = ["Spec", "Supplier", "Build", "Field"];
  const xs = [110, 250, 390, 530];
  return (
    <Scene label={label}>
      <Head family="investigation" text="Component investigation" />
      <path d="M 70 290 H 570" className="sc-line sc-draw" pathLength={1} strokeWidth={3} style={at(1)} />
      <path
        d="M 320 194 C 320 240 110 236 110 278"
        className="sc-link sc-draw"
        pathLength={1}
        strokeWidth={3}
        style={at(0, "0.7s")}
      />
      <path d="M 110 290 H 530" className="sc-link sc-draw" pathLength={1} strokeWidth={4} style={at(0, "1.3s")} />
      <Panel x={200} y={94} w={240} h={100} index={1}>
        <g transform="translate(46 50)">
          <circle r={27} fill={tint("teal", 14)} stroke="var(--sc-teal)" strokeWidth={2} />
          <Glyph shape="sensor" tone="teal" scale={1.3} />
        </g>
        <Txt x={88} y={48} size={20} weight={800}>
          PS-2 sensor
        </Txt>
        <Txt x={88} y={74} size={16} tone="muted">
          Pressure sensor
        </Txt>
      </Panel>
      <Focus x={200} y={94} w={240} h={100} />
      {xs.map((x, index) => (
        <g key={x}>
          <circle
            cx={x}
            cy={290}
            r={12}
            fill={index === 3 ? tint("amber", 30) : "var(--sc-panel)"}
            stroke={index === 3 ? "var(--sc-amber)" : "var(--sc-teal)"}
            strokeWidth={3}
            className="sc-pop"
            style={at(index * 2, "1.2s")}
          />
          <Txt
            x={x}
            y={330}
            size={16}
            anchor="middle"
            tone={index === 3 ? "amber" : "ink-2"}
            className="sc-fade"
            index={index * 2}
            offset="1.3s"
          >
            {stages[index]}
          </Txt>
        </g>
      ))}
      <circle cx={530} cy={290} r={12} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
      <Illustrative />
    </Scene>
  );
}

/** Lot 003 in focus with its context at the corners (build record, product, complaints) and the distribution record
 * still missing, a gap left visible. "Map lot context before assessing scope." */
function InvestigationLot({ label }: { label: string }) {
  const corners: { x: number; y: number; text: string; tone: "base" | "amber" | "muted"; from: [number, number] }[] = [
    { x: 132, y: 120, text: "Build record", tone: "base", from: [228, 156] },
    { x: 508, y: 120, text: "17 complaints", tone: "amber", from: [412, 156] },
    { x: 132, y: 312, text: "OrbitCare 300", tone: "base", from: [228, 272] },
    { x: 508, y: 312, text: "Distribution", tone: "muted", from: [412, 272] },
  ];
  return (
    <Scene label={label}>
      <Head family="investigation" text="Lot investigation" />
      {corners.map((corner, index) => {
        const ty = corner.y + (corner.y < 200 ? 17 : -17);
        const tx = corner.x + (corner.x < 320 ? 30 : -30);
        const d = `M ${corner.from[0]} ${corner.from[1]} L ${tx} ${ty}`;
        return corner.tone === "muted" ? (
          <g key={corner.text} className="sc-fade" style={at(0, "1.4s")}>
            <path d={d} className="sc-line" strokeDasharray="4 5" strokeWidth={2.5} />
          </g>
        ) : (
          <path
            key={corner.text}
            d={d}
            className="sc-link sc-draw"
            pathLength={1}
            strokeWidth={2.5}
            style={at(index, "0.9s")}
          />
        );
      })}
      <Panel x={240} y={168} w={160} h={92} index={1}>
        <Txt x={20} y={44} size={24} weight={800}>
          Lot 003
        </Txt>
        <Txt x={20} y={72} size={16} tone="muted">
          Rev B · PS-2
        </Txt>
      </Panel>
      <Focus x={240} y={168} w={160} h={92} />
      {corners.map((corner, index) => (
        <Pill
          key={corner.text}
          x={corner.x}
          y={corner.y}
          text={corner.text}
          tone={corner.tone}
          size={16}
          index={index}
          offset="1.2s"
        />
      ))}
      <g className="sc-fade" style={at(0, "1.9s")}>
        <Mark x={600} y={312} kind="gap" r={10} />
      </g>
      <circle cx={600} cy={312} r={10} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={2} />
      <Illustrative />
    </Scene>
  );
}

/** The hazard in focus (a missed pressure alarm) with its risk controls on one side and the evidence about it on the
 * other, all linked. "Keep risk review connected to evidence and controls." */
function InvestigationRisk({ label }: { label: string }) {
  const sides = [
    { x: 112, caption: "Controls", tone: "teal" as const, items: ["Inspection", "Self-test"], edge: 220 },
    { x: 528, caption: "Evidence", tone: "amber" as const, items: ["42 complaints", "Lot 003 tests"], edge: 420 },
  ];
  return (
    <Scene label={label}>
      <Head family="investigation" text="Risk investigation" />
      {sides.map((side, s) =>
        side.items.map((item, index) => {
          const y = 182 + index * 74;
          const px = side.x + (s ? -78 : 66);
          return (
            <path
              key={item}
              d={`M ${px} ${y} C ${(px + side.edge) / 2} ${y} ${(px + side.edge) / 2} 215 ${side.edge} 215`}
              className={`sc-link sc-draw ${s ? "sc-link-amber" : ""}`}
              pathLength={1}
              strokeWidth={2.5}
              style={at(index + s * 2, "1s")}
            />
          );
        }),
      )}
      <Panel x={230} y={160} w={180} h={110} index={1}>
        <g transform="translate(90 36)">
          <Glyph shape="hazard" tone="amber" scale={1.3} />
        </g>
        <Txt x={90} y={80} size={19} weight={800} anchor="middle">
          Missed alarm
        </Txt>
        <Txt x={90} y={100} size={14} anchor="middle" tone="muted">
          Hazard
        </Txt>
      </Panel>
      <Focus x={230} y={160} w={180} h={110} />
      {sides.map((side, s) => (
        <g key={side.caption}>
          <Txt x={side.x} y={140} size={15} weight={800} anchor="middle" tone="muted" className="sc-fade" offset="0.6s">
            {side.caption}
          </Txt>
          {side.items.map((item, index) => (
            <Pill
              key={item}
              x={side.x}
              y={182 + index * 74}
              text={item}
              tone={s ? (index ? "base" : "amber") : "teal"}
              size={16}
              width={s ? 156 : 132}
              index={index + s * 2}
              offset="0.7s"
            />
          ))}
        </g>
      ))}
      <Illustrative />
    </Scene>
  );
}

/** Four systems of record (QMS, PLM, ERP/MES, supplier portal) linked into one investigation, each keeping its own
 * records: the links are references, shown flowing in. "Bring the investigation together across systems of record." */
function InvestigationCrossSystem({ label }: { label: string }) {
  const systems: { text: string; tone: Tone }[] = [
    { text: "QMS", tone: "teal" },
    { text: "PLM", tone: "blue" },
    { text: "ERP / MES", tone: "amber" },
    { text: "Supplier portal", tone: "green" },
  ];
  const card = { x: 372, y: 116 };
  return (
    <Scene label={label}>
      <Head family="investigation" text="Cross-system investigation" />
      <g className="sc-fade" style={at(0, "1s")}>
        {systems.map((system, index) => {
          const sy = 88 + index * 68 + 26;
          const ty = card.y + 96 + index * 26;
          return (
            <path
              key={system.text}
              d={`M 242 ${sy} C 306 ${sy} 300 ${ty} ${card.x} ${ty}`}
              className="sc-link sc-link-dashed sc-flow"
              strokeWidth={2.5}
            />
          );
        })}
      </g>
      {systems.map((system, index) => (
        <Panel key={system.text} x={32} y={88 + index * 68} w={210} h={52} index={index + 1}>
          <g transform="translate(26 26)">
            <Glyph shape="database" tone="ink-2" />
          </g>
          <Txt x={50} y={32} size={17} weight={800}>
            {system.text}
          </Txt>
          <circle cx={192} cy={26} r={5} fill={ink(system.tone)} />
        </Panel>
      ))}
      <Panel x={card.x} y={card.y} w={226} h={200} index={2}>
        <Txt x={20} y={40} size={20} weight={800}>
          INV-001
        </Txt>
        <Txt x={20} y={64} size={16} tone="muted">
          Pressure alarms
        </Txt>
        {systems.map((system, index) => (
          <g key={system.text} className="sc-fade" style={at(index, "1.3s")}>
            <circle cx={26} cy={96 + index * 26} r={5} fill={ink(system.tone)} />
            <rect x={40} y={92 + index * 26} width={150 - (index % 2) * 30} height={8} rx={4} fill="var(--sc-line)" />
          </g>
        ))}
      </Panel>
      <Focus x={card.x} y={card.y} w={226} h={200} />
      <Txt x={485} y={354} size={16} anchor="middle" tone="muted" className="sc-fade" offset="1.8s">
        Sources keep their records
      </Txt>
      <Illustrative />
    </Scene>
  );
}

export const solutionScenes: Record<string, SceneComponent> = {
  "medtech-solution-complaints": SolutionComplaints,
  "medtech-solution-changes": SolutionChanges,
  "medtech-solution-affected": SolutionAffected,
  "medtech-solution-supplier": SolutionSupplier,
  "medtech-solution-evidence": SolutionEvidence,
  "medtech-solution-challenge": SolutionChallenge,
  "medtech-solution-unknowns": SolutionUnknowns,
  "medtech-role-quality-leaders": RoleQualityLeaders,
  "medtech-role-investigators": RoleInvestigators,
  "medtech-role-regulatory": RoleRegulatory,
  "medtech-role-product": RoleProduct,
  "medtech-role-supplier-quality": RoleSupplierQuality,
  "medtech-role-manufacturing": RoleManufacturing,
  "medtech-role-executives": RoleExecutives,
  "medtech-investigation-complaint": InvestigationComplaint,
  "medtech-investigation-version": InvestigationVersion,
  "medtech-investigation-change": InvestigationChange,
  "medtech-investigation-supplier": InvestigationSupplier,
  "medtech-investigation-component": InvestigationComponent,
  "medtech-investigation-lot": InvestigationLot,
  "medtech-investigation-risk": InvestigationRisk,
  "medtech-investigation-cross-system": InvestigationCrossSystem,
};
