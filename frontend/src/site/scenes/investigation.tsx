import type { CSSProperties } from "react";
import { Card, Chip, Illustrative, Scene, at, fs } from "./kit";
import type { SceneComponent } from "./index";

// Scenes for the investigation pictures, by picture name (see kit.tsx for the rules every scene follows).
// Font sizes are set with style (not the fontSize attribute): the stage's ".sc text" rule outranks the attribute.

/** A font size as an inline style. */
const px = (size: number, extra?: CSSProperties): CSSProperties => ({ fontSize: fs(size), ...extra });
/** The small upper-case label used for card and column titles. */
const CAPS: CSSProperties = { fontSize: fs(11), fontWeight: 800, letterSpacing: "0.08em" };
/** A light tint of a colour token, for chip and band fills. */
const tint = (color: string, amount = 14) => `color-mix(in srgb, ${color} ${amount}%, transparent)`;
/** A rounded rectangle as a path, so its outline can draw itself (sc-draw needs a path with pathLength). */
const roundRect = (x: number, y: number, w: number, h: number, r: number) =>
  `M ${x + r} ${y} H ${x + w - r} A ${r} ${r} 0 0 1 ${x + w} ${y + r} V ${y + h - r} A ${r} ${r} 0 0 1 ${x + w - r} ${y + h} H ${x + r} A ${r} ${r} 0 0 1 ${x} ${y + h - r} V ${y + r} A ${r} ${r} 0 0 1 ${x + r} ${y} Z`;

/** The tinted header band of a record card. Card styles its own direct <rect> children as the card, so every extra
 * rect inside a Card sits in a <g>. */
function HeaderBand() {
  return (
    <g>
      <rect x={0} y={0} width={592} height={46} rx={12} fill={tint("var(--sc-teal)", 9)} />
    </g>
  );
}

/** Product versioning: Rev A and Rev B of OrbitCare 300 compared row by row, the rows CHG-014 changed marked in
 * amber, and a frame drawn around the revision under investigation. Platform, "Know exactly which revision you are
 * investigating." */
function RevisionCompare({ label }: { label: string }) {
  const colA = 300;
  const colB = 500;
  const rows = [
    { label: "Status", a: "Superseded", b: "Released" },
    { label: "Effective", a: "2025-10-22", b: "2026-08-03" },
    { label: "Pressure sensor", a: "PS-1", b: "PS-2 · Kestrel", changed: true },
    { label: "Inspection sample", a: "32 per lot", b: "13 per lot", changed: true },
    { label: "Lots built", a: "001–002", b: "003–006" },
    { label: "Alarm complaints / mo", a: "0.8", b: "5.6", changed: true },
  ];
  const rowY = (index: number) => 128 + index * 36;
  return (
    <Scene label={label}>
      <Card x={24} y={24} w={592} h={338} index={0}>
        {/* Record header */}
        <HeaderBand />
        <text x={18} y={29} style={px(15)} fontWeight={800}>
          OrbitCare 300 · Revisions
        </text>
        <Chip x={498} y={23} text="Investigating Rev B" tone="teal" index={2} />
        {/* Column heads, and the change that separates them */}
        <Chip x={colA} y={84} text="Rev A" tone="muted" width={76} index={3} />
        <Chip x={colB} y={84} text="Rev B" tone="teal" width={76} index={4} />
        <g className="sc-fade" style={at(0, "0.8s")}>
          <path className="sc-link sc-link-amber sc-link-dashed sc-flow" d={`M ${colA + 46} 84 H ${colB - 50}`} />
        </g>
        <g className="sc-fade" style={at(0, "0.8s")}>
          <path d={`M ${colB - 56} 79 L ${colB - 48} 84 L ${colB - 56} 89`} className="sc-link sc-link-amber" />
          <text
            x={(colA + colB) / 2 - 2}
            y={72}
            textAnchor="middle"
            style={px(11)}
            fontWeight={800}
            fill="var(--sc-amber)"
          >
            CHG-014
          </text>
        </g>
        {/* Changed rows: an amber band behind the row */}
        <g>
          {rows.map((row, index) =>
            row.changed ? (
              <rect
                key={`band-${row.label}`}
                x={10}
                y={rowY(index) - 19}
                width={572}
                height={28}
                rx={8}
                fill={tint("var(--sc-amber)", 13)}
                className="sc-grow-x"
                style={at(index, "1.9s")}
              />
            ) : null,
          )}
        </g>
        {/* The rows */}
        {rows.map((row, index) => (
          <g key={row.label} className="sc-rise" style={at(index, "0.9s")}>
            {index > 0 && <path d={`M 18 ${rowY(index) - 23} H 574`} className="sc-line" strokeWidth={1} />}
            {row.changed && <circle cx={18} cy={rowY(index) - 5} r={3.5} fill="var(--sc-amber)" />}
            <text x={28} y={rowY(index)} style={px(13)} fill="var(--sc-ink-2)">
              {row.label}
            </text>
            <text x={colA} y={rowY(index)} textAnchor="middle" style={px(13)} fill="var(--sc-muted)">
              {row.a}
            </text>
            <text x={colB} y={rowY(index)} textAnchor="middle" style={px(13)} fontWeight={700}>
              {row.b}
            </text>
          </g>
        ))}
        {/* The revision in focus */}
        <path
          d={roundRect(colB - 70, 62, 140, 262, 10)}
          fill="none"
          stroke="var(--sc-teal)"
          strokeWidth={2}
          className="sc-draw"
          pathLength={1}
          style={at(0, "1.5s")}
        />
      </Card>
      <Illustrative x={606} y={390} />
    </Scene>
  );
}

/** Timeline intelligence: the Rev B change and the first pressure alarm on three lanes of time (when it took effect,
 * when it was recorded, when it could be known), with the lag between them, and a "known as of" cursor that leaves
 * later knowledge out. Platform, "Separate what happened from what was known, and when." */
function TimelineViews({ label }: { label: string }) {
  const x = (week: number) => 130 + (week - 10) * 36;
  const lanes = [
    { y: 110, name: "Effective", note: "happened" },
    { y: 180, name: "Recorded", note: "entered" },
    { y: 250, name: "Known", note: "could know" },
  ];
  const cursor = x(19);
  // Each event at its three times (weeks); the first pressure alarm is linked to Rev B only in week 20.
  const events = [
    { color: "var(--sc-teal)", weeks: [13, 14, 14] },
    { color: "var(--sc-amber)", weeks: [15, 17, 20] },
  ];
  return (
    <Scene label={label}>
      <Card x={24} y={24} w={592} h={338} index={0}>
        <HeaderBand />
        <text x={18} y={29} style={px(15)} fontWeight={800}>
          Timeline · OrbitCare 300 Rev B
        </text>
        {/* Lanes and the week axis */}
        {lanes.map((lane, index) => (
          <g key={lane.name}>
            <g className="sc-fade" style={at(index, "0.3s")}>
              <text x={16} y={lane.y - 2} style={px(13)} fontWeight={800}>
                {lane.name}
              </text>
              <text x={16} y={lane.y + 15} style={px(11)} fill="var(--sc-muted)">
                {lane.note}
              </text>
            </g>
            <path d={`M 120 ${lane.y} H 572`} className="sc-line sc-draw" pathLength={1} style={at(index, "0.3s")} />
          </g>
        ))}
        <g className="sc-fade" style={at(0, "0.6s")}>
          <path d="M 120 292 H 572" className="sc-line" strokeWidth={1.5} />
          {[10, 12, 14, 16, 18, 20, 22].map((week) => (
            <g key={week}>
              <path d={`M ${x(week)} 288 V 296`} className="sc-line" strokeWidth={1.5} />
              <text x={x(week)} y={312} textAnchor="middle" style={px(11)} fill="var(--sc-muted)">
                wk {week}
              </text>
            </g>
          ))}
        </g>
        {/* Known as of week 19: what lies to the right was not yet known */}
        <g className="sc-fade" style={at(0, "2.3s")}>
          <rect x={cursor} y={78} width={572 - cursor} height={204} fill={tint("var(--sc-blue)", 7)} />
          <path d={`M ${cursor} 80 V 292`} stroke="var(--sc-blue)" strokeWidth={2} strokeDasharray="5 5" />
          <rect x={cursor - 70} y={53} width={140} height={26} rx={13} fill="var(--sc-panel)" stroke="var(--sc-blue)" />
          <text x={cursor} y={70} textAnchor="middle" style={px(12)} fontWeight={700} fill="var(--sc-blue)">
            Known as of wk 19
          </text>
        </g>
        <circle cx={cursor} cy={292} r={5} fill="var(--sc-blue)" className="sc-pulse" />
        {/* Lag between the three times of each event */}
        {events.map((event, index) => (
          <g key={event.color}>
            {[0, 1].map((step) => (
              <path
                key={step}
                d={`M ${x(event.weeks[step])} ${lanes[step].y} L ${x(event.weeks[step + 1])} ${lanes[step + 1].y}`}
                stroke={event.color}
                strokeWidth={2}
                strokeLinecap="round"
                fill="none"
                className="sc-draw"
                pathLength={1}
                style={at(index, `${1.1 + step * 0.6}s`)}
              />
            ))}
          </g>
        ))}
        <g className="sc-fade" style={at(0, "1.5s")}>
          <text x={248} y={150} textAnchor="end" style={px(11)} fontWeight={700} fill="var(--sc-teal)">
            +1 wk
          </text>
          <text x={356} y={148} style={px(11)} fontWeight={700} fill="var(--sc-amber)">
            +2 wk
          </text>
        </g>
        <g className="sc-fade" style={at(0, "2.1s")}>
          <text x={428} y={230} textAnchor="end" style={px(11)} fontWeight={700} fill="var(--sc-amber)">
            +3 wk
          </text>
          <text x={x(20) + 12} y={238} style={px(11)} fontWeight={700} fill="var(--sc-muted)">
            not yet
          </text>
        </g>
        {/* Event markers, lane by lane */}
        {events.map((event, index) =>
          event.weeks.map((week, step) => {
            const later = x(week) > cursor;
            return (
              <g key={`${event.color}-${step}`} transform={`translate(${x(week)} ${lanes[step].y})`}>
                <circle
                  r={7}
                  fill={later ? "var(--sc-panel)" : event.color}
                  stroke={event.color}
                  strokeWidth={2}
                  strokeDasharray={later ? "3 3" : undefined}
                  className="sc-pop"
                  style={at(index, `${0.8 + step * 0.6}s`)}
                />
              </g>
            );
          }),
        )}
        <g className="sc-fade" style={at(0, "0.9s")}>
          <text x={x(13) - 10} y={96} textAnchor="end" style={px(12)} fontWeight={700} fill="var(--sc-teal)">
            Rev B · CHG-014
          </text>
          <text x={x(15) + 10} y={96} style={px(12)} fontWeight={700} fill="var(--sc-amber)">
            Pressure alarm
          </text>
        </g>
      </Card>
      <Illustrative x={606} y={390} />
    </Scene>
  );
}

/** Ask MDARIX: a scoped question, an answer whose every sentence cites a source record, and the line it will not
 * claim. Marked advisory and with design partners, because AI is off in the free trial. Platform, "Ask a precise
 * question and get a cited, bounded answer." */
function AskCited({ label }: { label: string }) {
  const answer = [
    { text: "Complaints rose from 0.8 to 5.6 a month", end: 260, source: "Complaint trend" },
    { text: "Most are from lots 003 and 004", end: 208, source: "Lot build records" },
    { text: "Both lots carry PS-2 from Kestrel", end: 214, source: "CHG-014 record" },
  ];
  const lineY = (index: number) => 182 + index * 32;
  return (
    <Scene label={label}>
      <Card x={24} y={24} w={592} h={338} index={0}>
        <HeaderBand />
        <text x={18} y={29} style={px(15)} fontWeight={800}>
          Ask MDARIX
        </text>
        <Chip x={474} y={23} text="Advisory · design partners" tone="amber" index={1} />
        {/* The question and its scope */}
        <g className="sc-rise" style={at(0, "0.3s")}>
          <rect
            x={236}
            y={62}
            width={338}
            height={38}
            rx={12}
            fill={tint("var(--sc-teal)", 10)}
            stroke="var(--sc-teal)"
          />
          <text x={252} y={86} style={px(13)} fontWeight={600}>
            Why did pressure alarms rise after Rev B?
          </text>
        </g>
        <g className="sc-fade" style={at(0, "0.6s")}>
          <text x={574} y={120} textAnchor="end" style={px(11)} fill="var(--sc-muted)">
            Scope · OrbitCare 300 Rev B · lots 001–006
          </text>
        </g>
        {/* The answer, one cited sentence at a time */}
        <g className="sc-fade" style={at(0, "0.9s")}>
          <text x={18} y={152} style={CAPS} fill="var(--sc-ink-2)">
            ANSWER
          </text>
          <text x={404} y={152} style={CAPS} fill="var(--sc-ink-2)">
            SOURCES
          </text>
        </g>
        {answer.map((line, index) => (
          <g key={line.text}>
            <g className="sc-rise" style={at(index * 3, "1s")}>
              <text x={18} y={lineY(index)} style={px(13)}>
                {line.text}
              </text>
              <rect
                x={line.end}
                y={lineY(index) - 14}
                width={22}
                height={18}
                rx={5}
                fill={tint("var(--sc-teal)")}
                stroke="var(--sc-teal)"
              />
              <text
                x={line.end + 11}
                y={lineY(index) - 1}
                textAnchor="middle"
                style={px(11)}
                fontWeight={800}
                fill="var(--sc-teal)"
              >
                {index + 1}
              </text>
            </g>
            <path
              d={`M ${line.end + 22} ${lineY(index) - 5} C ${line.end + 70} ${lineY(index) - 5}, 360 ${lineY(index) - 5}, 404 ${lineY(index) - 5}`}
              className="sc-link sc-draw"
              pathLength={1}
              strokeWidth={1.5}
              opacity={0.6}
              style={at(index, "1.7s")}
            />
            <g className="sc-rise" style={at(index, "1.4s")}>
              <rect
                x={404}
                y={lineY(index) - 19}
                width={170}
                height={28}
                rx={8}
                fill="var(--sc-panel)"
                stroke="var(--sc-line)"
              />
              <rect x={410} y={lineY(index) - 14} width={22} height={18} rx={5} fill="var(--sc-teal)" />
              <text x={421} y={lineY(index) - 1} textAnchor="middle" style={px(11)} fontWeight={800} fill="#ffffff">
                {index + 1}
              </text>
              <text x={442} y={lineY(index) - 1} style={px(12)} fontWeight={600}>
                {line.source}
              </text>
            </g>
          </g>
        ))}
        {/* What the answer does not establish */}
        <g className="sc-rise" style={at(0, "2.3s")}>
          <rect
            x={18}
            y={270}
            width={556}
            height={34}
            rx={8}
            fill={tint("var(--sc-amber)", 10)}
            stroke="var(--sc-amber)"
            strokeDasharray="4 4"
          />
          <text x={56} y={291} style={px(12)} fontWeight={600}>
            <tspan fill="var(--sc-amber)" fontWeight={800}>
              Not established ·
            </tspan>{" "}
            whether PS-2 causes the alarms
          </text>
        </g>
        <circle cx={37} cy={287} r={9} fill="var(--sc-amber)" className="sc-pulse" />
        <text x={37} y={291} textAnchor="middle" style={px(12)} fontWeight={800} fill="#10202f">
          !
        </text>
        <g className="sc-fade" style={at(0, "2.5s")}>
          <text x={18} y={326} style={px(11)} fill="var(--sc-muted)">
            Cites only records you can access · a reviewer decides
          </text>
        </g>
      </Card>
      <Illustrative x={606} y={390} />
    </Scene>
  );
}

/** Investigation workspace: the five roles of a cross-functional review (as initials, not faces) joined to one
 * investigation, each adding the records it owns. Platform, "Run the investigation in one governed workspace", and
 * Home, "Bring quality, regulatory, product, supplier, and manufacturing context into one review." */
function TeamWorkspace({ label }: { label: string }) {
  const roles = [
    { id: "QA", name: "Quality", record: "Complaint trend", color: "var(--sc-teal)", x: 100, y: 150 },
    { id: "RA", name: "Regulatory", record: "Reportability check", color: "var(--sc-blue)", x: 100, y: 290 },
    { id: "PD", name: "Product", record: "Rev B design change", color: "var(--sc-green)", x: 320, y: 58 },
    { id: "SQ", name: "Supplier quality", record: "Kestrel PS-2 data", color: "var(--sc-amber)", x: 540, y: 150 },
    { id: "MF", name: "Manufacturing", record: "Lots 003–004 builds", color: "var(--sc-ink-2)", x: 540, y: 290 },
  ];
  // Where each role's link meets the workspace card (x 190–450, y 112–348).
  const join = (role: (typeof roles)[number]) =>
    role.x === 320
      ? `M 320 ${role.y + 22} V 112`
      : role.x < 320
        ? `M ${role.x + 22} ${role.y} C 160 ${role.y}, 160 ${role.y < 200 ? 170 : 280}, 190 ${role.y < 200 ? 170 : 280}`
        : `M ${role.x - 22} ${role.y} C 480 ${role.y}, 480 ${role.y < 200 ? 170 : 280}, 450 ${role.y < 200 ? 170 : 280}`;
  return (
    <Scene label={label}>
      {/* Links from each role into the workspace, flowing once they appear */}
      {roles.map((role, index) => (
        <g key={`link-${role.id}`} className="sc-fade" style={at(index, "0.9s")}>
          <path d={join(role)} className="sc-link sc-link-dashed sc-flow" stroke={role.color} />
        </g>
      ))}
      {/* The one investigation */}
      <Card x={190} y={112} w={260} h={236} index={0}>
        <text x={14} y={24} style={CAPS} fill="var(--sc-ink-2)">
          INV-031 · PRESSURE ALARMS
        </text>
        <text x={14} y={42} style={px(11)} fill="var(--sc-muted)">
          OrbitCare 300 · Rev B
        </text>
        {roles.map((role, index) => (
          <g key={`row-${role.id}`} className="sc-rise" style={at(index, "1.1s")}>
            <circle cx={26} cy={70 + index * 30} r={11} fill={tint(role.color, 16)} />
            <text
              x={26}
              y={74 + index * 30}
              textAnchor="middle"
              style={px(11, { letterSpacing: "-0.02em" })}
              fontWeight={800}
              fill={role.color}
            >
              {role.id}
            </text>
            <text x={46} y={75 + index * 30} style={px(13)}>
              {role.record}
            </text>
          </g>
        ))}
        <g className="sc-fade" style={at(0, "2s")}>
          <path d="M 14 210 H 246" className="sc-line" strokeWidth={1} />
          <text x={14} y={228} style={px(11)} fill="var(--sc-muted)">
            Decision · authorized reviewer
          </text>
        </g>
      </Card>
      {/* The roles, as initials */}
      {roles.map((role, index) => (
        <g key={role.id} transform={`translate(${role.x} ${role.y})`}>
          <g className="sc-pop" style={at(index, "0.3s")}>
            <circle r={22} fill="var(--sc-panel)" stroke={role.color} strokeWidth={2} />
            <circle r={22} fill={tint(role.color, 12)} />
            <text textAnchor="middle" y={5} style={px(14)} fontWeight={800} fill={role.color}>
              {role.id}
            </text>
            <text
              x={role.x === 320 ? 30 : 0}
              y={role.x === 320 ? 5 : 42}
              textAnchor={role.x === 320 ? "start" : "middle"}
              style={px(12)}
              fontWeight={700}
            >
              {role.name}
            </text>
          </g>
        </g>
      ))}
      <Chip x={546} y={52} text="Role-based access" tone="teal" index={6} />
      <Illustrative />
    </Scene>
  );
}

/** Evidence intelligence: records scattered across source systems drawn into one authorized investigation context,
 * each keeping a tag for the system it came from, and the missing record shown as a gap. Platform, "Bring scattered
 * evidence into one authorized context", and Home step 02 (drawn large: that slot is small). */
function EvidenceContext({ label }: { label: string }) {
  const sources = [
    { name: "QMS", x: 88, y: 80, tilt: -4 },
    { name: "PLM", x: 136, y: 160, tilt: 3 },
    { name: "ERP", x: 94, y: 236, tilt: -2 },
    { name: "Supplier", x: 142, y: 312, tilt: 4 },
  ];
  const rows = ["42 alarm complaints", "Rev B · CHG-014", "Lots 003–004 · PS-2", "2 of 13 sensors high"];
  const rowY = (index: number) => 78 + index * 48;
  return (
    <Scene label={label}>
      {/* Each record travels from its system into the context */}
      {sources.map((source, index) => (
        <path
          key={`link-${source.name}`}
          d={`M ${source.x + 64} ${source.y} C ${source.x + 124} ${source.y}, 244 ${44 + rowY(index)}, 304 ${44 + rowY(index)}`}
          className="sc-link sc-draw"
          pathLength={1}
          strokeWidth={2.5}
          opacity={0.55}
          style={at(index * 2, "0.9s")}
        />
      ))}
      {/* The source systems, scattered */}
      {sources.map((source, index) => (
        <g key={source.name} transform={`translate(${source.x} ${source.y}) rotate(${source.tilt})`}>
          <g className="sc-rise" style={at(index)}>
            <rect x={-64} y={-22} width={128} height={44} rx={10} fill="var(--sc-panel)" stroke="var(--sc-line)" />
            <rect x={-64} y={-22} width={8} height={44} rx={4} fill="var(--sc-teal)" />
            <text textAnchor="middle" x={4} y={6} style={px(16)} fontWeight={800}>
              {source.name}
            </text>
          </g>
        </g>
      ))}
      {/* One authorized investigation context */}
      <Card x={290} y={44} w={326} h={306} index={3}>
        <text x={18} y={33} style={px(13, { letterSpacing: "0.06em" })} fontWeight={800} fill="var(--sc-ink-2)">
          INVESTIGATION CONTEXT
        </text>
        <g>
          <rect x={212} y={14} width={102} height={28} rx={14} fill={tint("var(--sc-teal)")} stroke="var(--sc-teal)" />
        </g>
        <path
          d="M 225 33 v -7 h 12 v 7 z M 228 26 v -3 a 3 3 0 0 1 6 0 v 3"
          fill="none"
          stroke="var(--sc-teal)"
          strokeWidth={1.8}
          strokeLinejoin="round"
        />
        <text x={244} y={33} style={px(12)} fontWeight={700} fill="var(--sc-teal)">
          Authorized
        </text>
        {rows.map((row, index) => (
          <g key={row} className="sc-rise" style={at(index * 2, "1.3s")}>
            <rect
              x={14}
              y={rowY(index) - 19}
              width={298}
              height={38}
              rx={9}
              fill={tint("var(--sc-teal)", 6)}
              stroke="var(--sc-line)"
            />
            <rect x={22} y={rowY(index) - 12} width={76} height={24} rx={12} fill={tint("var(--sc-teal)", 16)} />
            <text
              x={60}
              y={rowY(index) + 4.5}
              textAnchor="middle"
              style={px(13)}
              fontWeight={800}
              fill="var(--sc-teal)"
            >
              {sources[index].name}
            </text>
            <text x={108} y={rowY(index) + 5} style={px(15)} fontWeight={600}>
              {row}
            </text>
          </g>
        ))}
        {/* The gap: a record nobody has */}
        <g className="sc-rise" style={at(0, "2.4s")}>
          <rect
            x={14}
            y={rowY(4) - 19}
            width={298}
            height={38}
            rx={9}
            fill={tint("var(--sc-amber)", 9)}
            stroke="var(--sc-amber)"
            strokeDasharray="5 4"
          />
          <text x={108} y={rowY(4) + 5} style={px(15)} fontWeight={600} fill="var(--sc-ink-2)">
            Lot ref missing · 2
          </text>
          <text x={60} y={rowY(4) + 4.5} textAnchor="middle" style={px(13)} fontWeight={800} fill="var(--sc-amber)">
            Gap
          </text>
        </g>
        <g>
          <rect
            x={22}
            y={rowY(4) - 12}
            width={76}
            height={24}
            rx={12}
            fill="none"
            stroke="var(--sc-amber)"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            className="sc-pulse"
          />
        </g>
      </Card>
      <Illustrative />
    </Scene>
  );
}

/** Competing hypotheses: three explanations for the pressure alarms side by side, each with its assumption, the
 * evidence that contradicts it (left) and supports it (right), and its open gaps; no verdict. Platform, "Keep
 * competing explanations side by side." */
function HypothesesCompare({ label }: { label: string }) {
  const axis = 360;
  const unit = 20;
  const hypotheses = [
    { name: "Sensor supplier change", assumes: "Assumes PS-2 reads high", supports: 5, contradicts: 1, gaps: 1 },
    { name: "Firmware alarm threshold", assumes: "Assumes the limit moved", supports: 2, contradicts: 3, gaps: 2 },
    { name: "Use or handling error", assumes: "Assumes new users", supports: 1, contradicts: 2, gaps: 1 },
  ];
  const rowY = (index: number) => 118 + index * 70;
  return (
    <Scene label={label}>
      <Card x={24} y={24} w={592} h={338} index={0}>
        <HeaderBand />
        <text x={18} y={29} style={px(15)} fontWeight={800}>
          Competing hypotheses
        </text>
        <Chip x={498} y={23} text="Status, not verdict" tone="teal" index={2} />
        {/* Column heads and the centre line */}
        <g className="sc-fade" style={at(0, "0.4s")}>
          <text x={axis - 10} y={78} textAnchor="end" style={CAPS} fill="var(--sc-red)">
            CONTRADICTS
          </text>
          <text x={axis + 10} y={78} style={CAPS} fill="var(--sc-teal)">
            SUPPORTS
          </text>
          <text x={540} y={78} textAnchor="middle" style={CAPS} fill="var(--sc-muted)">
            GAPS
          </text>
          <path d={`M ${axis} 90 V 284`} className="sc-line" />
        </g>
        {hypotheses.map((hypothesis, index) => {
          const y = rowY(index);
          return (
            <g key={hypothesis.name}>
              <g className="sc-rise" style={at(index * 2, "0.5s")}>
                {index > 0 && <path d={`M 18 ${y - 35} H 574`} className="sc-line" strokeWidth={1} />}
                <text x={18} y={y - 3} style={px(14)} fontWeight={800}>
                  {hypothesis.name}
                </text>
                <text x={18} y={y + 15} style={px(11)} fill="var(--sc-muted)">
                  {hypothesis.assumes}
                </text>
                <rect x={axis - 110} y={y - 6} width={220} height={12} rx={4} fill="var(--sc-line)" opacity={0.45} />
              </g>
              {/* Contradicting evidence grows left from the centre (the group is mirrored), supporting grows right */}
              <g transform={`translate(${axis} ${y - 6}) scale(-1 1)`}>
                <rect
                  width={hypothesis.contradicts * unit}
                  height={12}
                  rx={3}
                  fill="var(--sc-red)"
                  className="sc-grow-x"
                  style={at(index * 2, "1.2s")}
                />
              </g>
              <rect
                x={axis}
                y={y - 6}
                width={hypothesis.supports * unit}
                height={12}
                rx={3}
                fill="var(--sc-teal)"
                className="sc-grow-x"
                style={at(index * 2, "1.2s")}
              />
              <g className="sc-fade" style={at(index * 2, "1.7s")}>
                <text
                  x={axis - hypothesis.contradicts * unit - 8}
                  y={y + 4.5}
                  textAnchor="end"
                  style={px(12)}
                  fontWeight={800}
                  fill="var(--sc-red)"
                >
                  {hypothesis.contradicts}
                </text>
                <text
                  x={axis + hypothesis.supports * unit + 8}
                  y={y + 4.5}
                  style={px(12)}
                  fontWeight={800}
                  fill="var(--sc-teal)"
                >
                  {hypothesis.supports}
                </text>
              </g>
              <g transform={`translate(540 ${y})`}>
                <g className="sc-pop" style={at(index, "2.1s")}>
                  <rect
                    x={-34}
                    y={-13}
                    width={68}
                    height={26}
                    rx={13}
                    fill="var(--sc-panel)"
                    stroke="var(--sc-muted)"
                    strokeDasharray="4 4"
                  />
                  <text textAnchor="middle" y={4.5} style={px(12)} fontWeight={700} fill="var(--sc-ink-2)">
                    {hypothesis.gaps} {hypothesis.gaps === 1 ? "gap" : "gaps"}
                  </text>
                </g>
              </g>
            </g>
          );
        })}
        <g className="sc-fade" style={at(0, "2.4s")}>
          <text x={18} y={322} style={px(11)} fill="var(--sc-muted)">
            Every bar opens its source records · people decide what is accepted
          </text>
        </g>
      </Card>
      <Illustrative x={606} y={390} />
    </Scene>
  );
}

/** Challenger: the leading explanation held back from becoming a conclusion by the challenges raised against it (a
 * contradiction, an alternative, a weak assumption), each linked to the gate. Platform, "Challenge the explanation
 * before it becomes a conclusion", and Home step 03 (drawn large: that slot is small). */
function ChallengeGate({ label }: { label: string }) {
  const gate = { x: 355, y: 100 };
  const challenges = [
    { kind: "CONTRADICTION", text: "Alarms on Rev A", note: "lots 001–002", color: "var(--sc-red)", x: 24 },
    { kind: "ALTERNATIVE", text: "Firmware limit", note: "not ruled out", color: "var(--sc-amber)", x: 228 },
    { kind: "ASSUMPTION", text: "13-unit sample", note: "enough to see drift?", color: "var(--sc-amber)", x: 432 },
  ];
  return (
    <Scene label={label}>
      {/* The leading explanation */}
      <Card x={24} y={40} w={250} h={120} index={0}>
        <text x={16} y={28} style={px(12, { letterSpacing: "0.06em" })} fontWeight={800} fill="var(--sc-teal)">
          LEADING EXPLANATION
        </text>
        <text x={16} y={62} style={px(19)} fontWeight={800}>
          Sensor supplier
        </text>
        <text x={16} y={86} style={px(19)} fontWeight={800}>
          change · PS-2
        </text>
        <text x={16} y={108} style={px(12)} fill="var(--sc-ink-2)">
          Supports 5 · contradicts 1
        </text>
      </Card>
      <path
        d={`M 274 ${gate.y} H ${gate.x - 54}`}
        className="sc-link sc-draw"
        pathLength={1}
        strokeWidth={3}
        style={at(0, "0.4s")}
      />
      {/* Not yet a conclusion */}
      <g className="sc-fade" style={at(0, "2.2s")}>
        <path d={`M ${gate.x + 54} ${gate.y} H 428`} stroke="var(--sc-muted)" strokeWidth={2.5} strokeDasharray="4 6" />
        <path
          d={`M 421 ${gate.y - 7} L 429 ${gate.y} L 421 ${gate.y + 7}`}
          fill="none"
          stroke="var(--sc-muted)"
          strokeWidth={2.5}
          strokeLinecap="round"
        />
        <rect
          x={436}
          y={40}
          width={180}
          height={120}
          rx={12}
          fill="var(--sc-panel)"
          stroke="var(--sc-muted)"
          strokeWidth={1.5}
          strokeDasharray="6 5"
        />
        <text
          x={526}
          y={84}
          textAnchor="middle"
          style={px(12, { letterSpacing: "0.06em" })}
          fontWeight={800}
          fill="var(--sc-muted)"
        >
          CONCLUSION
        </text>
        <text x={526} y={114} textAnchor="middle" style={px(20)} fontWeight={800} fill="var(--sc-amber)">
          Not yet
        </text>
      </g>
      {/* Each challenge, linked up to the gate */}
      {challenges.map((challenge, index) => {
        const cx = challenge.x + 92;
        return (
          <path
            key={`link-${challenge.kind}`}
            d={`M ${cx} 226 C ${cx} 170, ${gate.x} 200, ${gate.x} ${gate.y + 17}`}
            stroke={challenge.color}
            strokeWidth={2.5}
            strokeLinecap="round"
            fill="none"
            className="sc-draw"
            pathLength={1}
            style={at(index, "1.3s")}
          />
        );
      })}
      {challenges.map((challenge, index) => (
        <Card key={challenge.kind} x={challenge.x} y={226} w={184} h={124} index={index + 2}>
          <g>
            <rect x={0} y={14} width={5} height={96} rx={2.5} fill={challenge.color} />
          </g>
          <text x={18} y={30} style={px(12, { letterSpacing: "0.06em" })} fontWeight={800} fill={challenge.color}>
            {challenge.kind}
          </text>
          <text x={18} y={66} style={px(17)} fontWeight={800}>
            {challenge.text}
          </text>
          <text x={18} y={92} style={px(13)} fill="var(--sc-ink-2)">
            {challenge.note}
          </text>
        </Card>
      ))}
      {/* The gate the explanation has to pass */}
      <circle cx={gate.x} cy={gate.y} r={40} fill="none" stroke="var(--sc-amber)" strokeWidth={2} className="sc-ping" />
      <g transform={`translate(${gate.x} ${gate.y})`}>
        <g className="sc-pop" style={at(0, "1.9s")}>
          <rect
            x={-54}
            y={-16}
            width={108}
            height={32}
            rx={16}
            fill="var(--sc-panel)"
            stroke="var(--sc-amber)"
            strokeWidth={2}
          />
          <rect x={-54} y={-16} width={108} height={32} rx={16} fill={tint("var(--sc-amber)", 16)} />
          <text textAnchor="middle" y={5} style={px(14)} fontWeight={800} fill="var(--sc-amber)">
            Challenged
          </text>
        </g>
      </g>
      <Illustrative />
    </Scene>
  );
}

/** Unknowns radar: around the investigation, what is established (solid) and what is not (dashed), each unknown
 * paired with the request that would close it; a faint sweep turns slowly. Platform, "See what the investigation
 * still cannot establish." */
function UnknownsRadar({ label }: { label: string }) {
  const cx = 320;
  const cy = 200;
  const known = [
    // Each link stops at its chip's edge (end), so no line runs through a label.
    { text: "Complaints · 42", x: 320, y: 132, end: [320, 145] },
    { text: "CHG-014", x: 210, y: 226, end: [246, 226] },
    { text: "Lots 003–004", x: 430, y: 226, end: [377, 226] },
  ];
  const unknowns = [
    { text: "Lot ref missing · 2", close: "Ask: complaint follow-up", x: 150, y: 100 },
    { text: "Returns not tested", close: "Request: return analysis", x: 490, y: 100 },
    { text: "Kestrel lot data", close: "Request: supplier CoA", x: 130, y: 300 },
    { text: "Firmware log", close: "Request: device logs", x: 510, y: 300 },
  ];
  const sweep = 32 * (Math.PI / 180);
  return (
    <Scene label={label}>
      {/* The radar: rings and a slow sweep */}
      <g className="sc-fade">
        {[60, 110, 160].map((r) => (
          <circle key={r} cx={cx} cy={cy} r={r} className="sc-line" strokeDasharray="2 7" />
        ))}
        <path
          d={`M ${cx - 160} ${cy} H ${cx + 160} M ${cx} ${cy - 160} V ${cy + 160}`}
          className="sc-line"
          strokeWidth={1}
          opacity={0.6}
        />
      </g>
      <g className="sc-fade" style={at(0, "1.2s")}>
        <g className="sc-orbit">
          <path
            d={`M ${cx} ${cy} L ${cx + 160} ${cy} A 160 160 0 0 0 ${cx + 160 * Math.cos(sweep)} ${cy - 160 * Math.sin(sweep)} Z`}
            fill={tint("var(--sc-teal)", 9)}
          />
          <path d={`M ${cx} ${cy} L ${cx + 160} ${cy}`} stroke="var(--sc-teal)" strokeWidth={1.5} opacity={0.4} />
        </g>
      </g>
      <text x={24} y={44} style={px(15)} fontWeight={800}>
        Unknowns radar
      </text>
      <Chip x={546} y={40} text="4 unknowns open" tone="amber" index={8} />
      {/* What is established: solid links */}
      {known.map((item, index) => (
        <path
          key={`link-${item.text}`}
          d={`M ${cx} ${cy} L ${item.end[0]} ${item.end[1]}`}
          className="sc-link sc-draw"
          pathLength={1}
          style={at(index, "0.4s")}
        />
      ))}
      {/* What is not: dashed links */}
      {unknowns.map((item, index) => (
        <g key={`link-${item.text}`} className="sc-fade" style={at(index, "1.2s")}>
          <path
            d={`M ${cx} ${cy} L ${item.x} ${item.y + (item.y < cy ? 13 : -13)}`}
            stroke="var(--sc-muted)"
            strokeWidth={1.5}
            strokeDasharray="4 5"
          />
        </g>
      ))}
      <g transform={`translate(${cx} ${cy})`}>
        <g className="sc-pop">
          <circle r={30} fill="var(--sc-panel)" stroke="var(--sc-teal)" strokeWidth={2.5} />
          <text textAnchor="middle" y={4} style={px(11)} fontWeight={800} fill="var(--sc-teal)">
            INV-031
          </text>
        </g>
      </g>
      {known.map((item, index) => (
        <Chip key={item.text} x={item.x} y={item.y} text={item.text} tone="teal" index={index + 3} />
      ))}
      {unknowns.map((item, index) => {
        const w = item.text.length * 7 + 44;
        return (
          <g key={item.text} transform={`translate(${item.x} ${item.y})`}>
            <g className="sc-pop" style={at(index, "1.4s")}>
              <rect
                x={-w / 2}
                y={-13}
                width={w}
                height={26}
                rx={13}
                fill="var(--sc-panel)"
                stroke="var(--sc-amber)"
                strokeWidth={1.5}
                strokeDasharray="4 4"
              />
              <circle cx={-w / 2 + 15} r={8} fill={tint("var(--sc-amber)", 22)} />
              <text x={-w / 2 + 15} y={4} textAnchor="middle" style={px(11)} fontWeight={800} fill="var(--sc-amber)">
                ?
              </text>
              <text x={12} y={4.5} textAnchor="middle" style={px(12)} fontWeight={600} fill="var(--sc-ink-2)">
                {item.text}
              </text>
            </g>
            <g className="sc-fade" style={at(index, "2s")}>
              <text
                y={item.y < cy ? -21 : 30}
                textAnchor="middle"
                style={px(11)}
                fontWeight={700}
                fill="var(--sc-teal)"
              >
                {item.close}
              </text>
            </g>
          </g>
        );
      })}
      {/* Legend */}
      <g className="sc-fade" style={at(0, "2.4s")}>
        <circle cx={30} cy={380} r={5} fill="var(--sc-teal)" />
        <text x={41} y={384} style={px(11)} fill="var(--sc-ink-2)">
          Established
        </text>
        <circle cx={128} cy={380} r={5} fill="none" stroke="var(--sc-amber)" strokeWidth={1.5} strokeDasharray="2 2" />
        <text x={139} y={384} style={px(11)} fill="var(--sc-ink-2)">
          Not established
        </text>
      </g>
      <Illustrative />
    </Scene>
  );
}

/** Failure chain: a candidate path from the change, through the sensor, the lots and the failure mode, to the
 * complaint, each link with the strength of its evidence and its source; the last link is not yet supported. Platform,
 * "Trace a possible failure path, link by link." */
function FailureChain({ label }: { label: string }) {
  const nodes = [
    { kind: "CHANGE", value: "CHG-014 · Rev B" },
    { kind: "COMPONENT", value: "PS-2 · Kestrel" },
    { kind: "LOTS", value: "Lots 003–004" },
    { kind: "FAILURE MODE", value: "Reads 4–6% high" },
    { kind: "COMPLAINT", value: "Pressure alarms" },
  ];
  const links = [
    { status: "Supported", source: "Change record CHG-014", strength: 4, color: "var(--sc-teal)" },
    { status: "Supported", source: "Lot build records", strength: 4, color: "var(--sc-teal)" },
    { status: "Partly supported", source: "Inspection · 2 of 13 high", strength: 2, color: "var(--sc-amber)" },
    { status: "Not yet supported", source: "Need: returned-device analysis", strength: 0, color: "var(--sc-red)" },
  ];
  const top = (index: number) => 40 + index * 70;
  const step = 0.45;
  return (
    <Scene label={label}>
      <g className="sc-fade">
        <text x={326} y={52} style={px(15)} fontWeight={800}>
          Failure chain · INV-031
        </text>
      </g>
      {/* The links: connector, leader and evidence strength */}
      {links.map((link, index) => {
        const y = top(index) + 55;
        const open = link.strength === 0;
        return (
          <g key={link.source}>
            {open ? (
              <g className="sc-fade" style={at(0, `${0.45 + index * step}s`)}>
                <path d={`M 52 ${y - 15} V ${y + 15}`} stroke={link.color} strokeWidth={2.5} strokeDasharray="3 4" />
              </g>
            ) : (
              <path
                d={`M 52 ${y - 15} V ${y + 13}`}
                stroke={link.color}
                strokeWidth={link.strength > 2 ? 3.5 : 2.5}
                fill="none"
                className="sc-draw"
                pathLength={1}
                style={at(0, `${0.45 + index * step}s`)}
              />
            )}
            <g className="sc-fade" style={at(0, `${0.6 + index * step}s`)}>
              <path d={`M 72 ${y} H 316`} className="sc-line" strokeWidth={1.5} strokeDasharray="2 5" />
              <text x={326} y={y - 2} style={px(13)} fontWeight={800} fill={link.color}>
                {link.status}
              </text>
              <text x={326} y={y + 15} style={px(11)} fill="var(--sc-muted)">
                {link.source}
              </text>
              {[0, 1, 2, 3, 4].map((segment) => (
                <rect
                  key={segment}
                  x={478 + segment * 23}
                  y={y - 12}
                  width={18}
                  height={9}
                  rx={2}
                  fill={segment < link.strength ? link.color : "none"}
                  stroke={segment < link.strength ? "none" : open ? link.color : "var(--sc-line)"}
                  strokeDasharray={open ? "2 2" : undefined}
                />
              ))}
            </g>
          </g>
        );
      })}
      {/* The unsupported link's open question */}
      <g transform={`translate(52 ${top(3) + 55})`}>
        <g className="sc-pop" style={at(0, `${0.6 + 3 * step}s`)}>
          <circle r={10} fill="var(--sc-panel)" stroke="var(--sc-red)" strokeWidth={2} />
          <text textAnchor="middle" y={4} style={px(12)} fontWeight={800} fill="var(--sc-red)">
            ?
          </text>
        </g>
      </g>
      <circle
        cx={52}
        cy={top(3) + 55}
        r={10}
        fill="none"
        stroke="var(--sc-red)"
        strokeWidth={1.5}
        className="sc-ping"
      />
      {/* The chain's steps, top to bottom */}
      {nodes.map((node, index) => (
        <Card key={node.kind} x={24} y={top(index)} w={270} h={40} index={index * 3}>
          <g>
            <rect
              x={0}
              y={10}
              width={5}
              height={20}
              rx={2.5}
              fill={index === 4 ? "var(--sc-amber)" : index === 3 ? "var(--sc-ink-2)" : "var(--sc-teal)"}
            />
          </g>
          <text x={18} y={25} style={CAPS} fill="var(--sc-muted)">
            {node.kind}
          </text>
          <text x={134} y={25} style={px(14)} fontWeight={800}>
            {node.value}
          </text>
        </Card>
      ))}
      <Illustrative />
    </Scene>
  );
}

export const investigationScenes: Record<string, SceneComponent> = {
  "medtech-product-versioning": RevisionCompare,
  "medtech-timeline-intelligence": TimelineViews,
  "medtech-ask-mdarix": AskCited,
  "medtech-investigation-team": TeamWorkspace,
  "medtech-evidence-intelligence-hero": EvidenceContext,
  "medtech-hypotheses-hero": HypothesesCompare,
  "medtech-hero-challenger": ChallengeGate,
  "medtech-unknowns-hero": UnknownsRadar,
  "medtech-failure-chain-hero": FailureChain,
};
