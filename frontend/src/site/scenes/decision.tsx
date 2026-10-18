import { Card, Chip, Illustrative, Scene, at } from "./kit";
import type { SceneComponent } from "./index";

// Scenes for the decision pictures, by picture name (see kit.tsx for the rules every scene follows).

/** A switch drawn at (x, y): teal with the knob to the right when on, grey with the knob to the left when off. */
function Toggle({ x, y, on }: { x: number; y: number; on: boolean }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width={34} height={18} rx={9} fill={on ? "var(--sc-teal)" : "var(--sc-line)"} />
      <circle cx={on ? 25 : 9} cy={9} r={6.5} fill="var(--sc-panel)" stroke={on ? "none" : "var(--sc-muted)"} />
    </g>
  );
}

/** A tick in a filled circle, centred on (x, y); on a dark stage pass a dark `mark` so the tick stays visible. */
function Tick({
  x,
  y,
  r = 9,
  tone = "var(--sc-teal)",
  mark = "var(--sc-panel)",
}: {
  x: number;
  y: number;
  r?: number;
  tone?: string;
  mark?: string;
}) {
  const s = r / 9;
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle r={r} fill={tone} />
      <path
        d={`M ${-4 * s} 0 L ${-1 * s} ${3 * s} L ${4.5 * s} ${-3.5 * s}`}
        fill="none"
        stroke={mark}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  );
}

/** Counterfactual analysis: a scenario switch excludes lots 003–004 (built with the new sensor), and the complaint
 * trend is redrawn without them beside the baseline: the rise after Rev B does not hold, which sharpens the scope
 * without proving cause. "Ask what would change if the facts were different." */
function CounterfactualScenario({ label }: { label: string }) {
  const toggles = [
    { text: "Exclude lots 003–004", note: "Built with sensor PS-2", on: true },
    { text: "Exclude Rev A lots", note: "Lots 001–002", on: false },
    { text: "After CHG-014 only", note: "Time window", on: false },
  ];
  // Pressure-alarm complaints per 1,000 units by quarter: all lots, and the scenario without lots 003–004.
  const all = [1.1, 1.3, 1.2, 2.6, 3.8, 4.6];
  const without = [1.1, 1.3, 1.2, 1.4, 1.3, 1.5];
  const px = (index: number) => 44 + index * 59.2;
  const py = (value: number) => 186 - (value / 5) * 130;
  const line = (values: number[]) => values.map((v, i) => `${i ? "L" : "M"} ${px(i)} ${py(v)}`).join(" ");
  return (
    <Scene label={label}>
      {/* The scenario: which facts are changed */}
      <Card x={24} y={40} w={212} h={316} title="Scenario" index={0}>
        {toggles.map((row, index) => (
          <g key={row.text} className="sc-rise" style={at(index, "0.2s")}>
            <Toggle x={14} y={44 + index * 56} on={row.on} />
            <text
              x={58}
              y={53 + index * 56}
              fontSize={12}
              fontWeight={700}
              fill={row.on ? undefined : "var(--sc-ink-2)"}
            >
              {row.text}
            </text>
            <text x={58} y={69 + index * 56} className="sc-note">
              {row.note}
            </text>
          </g>
        ))}
        <path d="M 14 214 H 198" className="sc-line" strokeWidth={1} />
        <g className="sc-fade" style={at(0, "0.8s")}>
          <text x={14} y={238} className="sc-card-title">
            Assumptions
          </text>
          <text x={14} y={260} className="sc-note">
            Complaint coding unchanged
          </text>
          <text x={14} y={278} className="sc-note">
            Units in field known per lot
          </text>
          <text x={14} y={296} className="sc-note">
            Data to Q6 · recorded with it
          </text>
        </g>
      </Card>
      {/* The comparison: baseline and scenario side by side */}
      <Card x={248} y={40} w={368} h={316} title="Pressure-alarm complaints" index={1}>
        <text x={354} y={22} className="sc-note" textAnchor="end">
          per 1,000 units
        </text>
        {[1, 2, 3, 4].map((v) => (
          <path key={v} d={`M 44 ${py(v)} H 340`} className="sc-line" strokeWidth={1} opacity={0.6} />
        ))}
        <path d="M 44 186 H 340" className="sc-line" />
        {/* Rev B marker */}
        <path d={`M 192 56 V 186`} className="sc-line" strokeDasharray="3 4" strokeWidth={1.5} />
        <text x={198} y={64} className="sc-note">
          Rev B · CHG-014
        </text>
        {all.map((_, index) => (
          <text key={index} x={px(index)} y={204} className="sc-note" textAnchor="middle">
            Q{index + 1}
          </text>
        ))}
        {/* Baseline (all lots), then the scenario redrawn over it */}
        <path
          className="sc-link sc-link-amber sc-draw"
          pathLength={1}
          d={line(all)}
          strokeWidth={2.5}
          style={at(0, "0.5s")}
        />
        <path className="sc-link sc-draw" pathLength={1} d={line(without)} strokeWidth={2.5} style={at(0, "1.4s")} />
        <g className="sc-pop" style={at(0, "1.3s")}>
          <circle cx={px(5)} cy={py(4.6)} r={4.5} fill="var(--sc-amber)" />
        </g>
        <g className="sc-pop" style={at(0, "2.2s")}>
          <circle cx={px(5)} cy={py(1.5)} r={4.5} fill="var(--sc-teal)" />
        </g>
        <g transform={`translate(${px(5)} ${py(1.5)})`}>
          <circle r={9} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={2} style={at(1)} />
        </g>
        {/* Legend */}
        <g className="sc-fade" style={at(0, "0.6s")}>
          <path d="M 14 230 H 34" className="sc-link sc-link-amber" strokeWidth={2.5} />
          <text x={40} y={234} fontSize={12} fill="var(--sc-ink-2)">
            All lots
          </text>
          <path d="M 120 230 H 140" className="sc-link" strokeWidth={2.5} />
          <text x={146} y={234} fontSize={12} fill="var(--sc-ink-2)">
            Without lots 003–004
          </text>
        </g>
        {/* What the comparison says, and what it does not */}
        <Chip x={14 + 225 / 2} y={266} width={225} text="Rise not seen without 003–004" tone="teal" index={17} />
        <g className="sc-fade" style={at(0, "2.7s")}>
          <text x={14} y={300} className="sc-note">
            Sharpens the scope · does not prove cause
          </text>
        </g>
      </Card>
      <Illustrative x={616} y={384} />
    </Scene>
  );
}

/** Decision Center: the evidence summary on one side and the decision on the other. A controlled option is chosen,
 * the reviewer re-authenticates with password and authenticator code, and the signature stamp lands. The optional AI
 * advisory stays apart and cannot decide. "Make the decision where all the evidence is." (also Home step 04). */
function DecisionCenter({ label }: { label: string }) {
  const summary = [
    { text: "Findings", value: "6 linked", tone: "var(--sc-teal)" },
    { text: "Hypotheses", value: "3 compared", tone: "var(--sc-teal)" },
    { text: "Contradictions", value: "1 resolved", tone: "var(--sc-teal)" },
    { text: "Unknowns", value: "None material", tone: "var(--sc-teal)" },
    { text: "Limitations", value: "2 recorded", tone: "var(--sc-amber)" },
  ];
  const options = ["Continue investigation", "Request evidence", "Escalate to CAPA"];
  const code = ["4", "8", "2", "1", "9", "7"];
  return (
    <Scene label={label}>
      {/* Everything the decision rests on */}
      <Card x={24} y={30} w={290} h={340} title="Evidence" index={0}>
        <Chip x={290 - 14 - 127 / 2} y={18} width={127} text="Ready to decide" tone="teal" index={14} />
        {summary.map((row, index) => (
          <g key={row.text} className="sc-rise" style={at(index, "0.3s")}>
            <Tick x={24} y={60 + index * 46} r={8} tone={row.tone} />
            <text x={42} y={64 + index * 46} fontSize={13} fontWeight={700}>
              {row.text}
            </text>
            <text x={276} y={64 + index * 46} fontSize={12} fill="var(--sc-ink-2)" textAnchor="end">
              {row.value}
            </text>
            <path d={`M 14 ${82 + index * 46} H 276`} className="sc-line" strokeWidth={1} />
          </g>
        ))}
        {/* The optional advisory, kept apart */}
        <g className="sc-fade" style={at(0, "1.1s")}>
          <rect
            x={14}
            y={284}
            width={262}
            height={44}
            rx={8}
            fill="none"
            stroke="var(--sc-muted)"
            strokeDasharray="4 4"
          />
          <text x={28} y={302} fontSize={12} fontWeight={700} fill="var(--sc-muted)">
            AI advisory · optional
          </text>
          <text x={28} y={318} className="sc-note">
            Shown apart · cannot decide
          </text>
        </g>
      </Card>
      {/* The decision and its signature */}
      <Card x={326} y={30} w={290} h={340} title="Decision" index={2}>
        {options.map((text, index) => (
          <g key={text} className="sc-rise" style={at(index, "0.6s")}>
            <circle
              cx={24}
              cy={48 + index * 26}
              r={7}
              fill="var(--sc-panel)"
              stroke="var(--sc-ink-2)"
              strokeWidth={1.5}
            />
            <text
              x={40}
              y={52.5 + index * 26}
              fontSize={13}
              fontWeight={index === 2 ? 800 : 500}
              fill={index === 2 ? undefined : "var(--sc-ink-2)"}
            >
              {text}
            </text>
          </g>
        ))}
        <g className="sc-pop" style={at(0, "1.2s")}>
          <circle cx={24} cy={100} r={3.8} fill="var(--sc-teal)" />
        </g>
        <g className="sc-fade" style={at(0, "1.2s")}>
          <text x={14} y={134} className="sc-note">
            Rationale
          </text>
          <rect x={70} y={128} width={196} height={6} rx={3} fill="var(--sc-line)" />
          <rect x={14} y={142} width={230} height={6} rx={3} fill="var(--sc-line)" />
        </g>
        {/* Re-authenticate, then sign */}
        <g className="sc-rise" style={at(0, "1.4s")}>
          <rect
            x={12}
            y={164}
            width={266}
            height={162}
            rx={10}
            fill="color-mix(in srgb, var(--sc-teal) 7%, transparent)"
            stroke="var(--sc-line)"
          />
          <text x={26} y={186} fontSize={12} fontWeight={800}>
            Re-authenticate to sign
          </text>
          <text x={26} y={206} className="sc-note">
            Password
          </text>
          <rect x={26} y={212} width={140} height={24} rx={6} fill="var(--sc-panel)" stroke="var(--sc-line)" />
          <text x={26} y={254} className="sc-note">
            Authenticator code
          </text>
          {code.map((_, index) => (
            <rect
              key={index}
              x={26 + index * 24}
              y={260}
              width={20}
              height={24}
              rx={5}
              fill="var(--sc-panel)"
              stroke="var(--sc-line)"
            />
          ))}
        </g>
        {Array.from({ length: 8 }, (_, index) => (
          <g key={index} className="sc-fade" style={at(index, "1.6s")}>
            <circle cx={38 + index * 12} cy={224} r={3} fill="var(--sc-ink)" />
          </g>
        ))}
        {code.map((digit, index) => (
          <g key={index} className="sc-fade" style={at(index, "1.9s")}>
            <text x={36 + index * 24} y={276.5} fontSize={13} fontWeight={800} textAnchor="middle">
              {digit}
            </text>
          </g>
        ))}
        <g className="sc-fade" style={at(0, "2.3s")}>
          <rect x={26} y={294} width={140} height={24} rx={12} fill="var(--sc-teal)" />
          <text x={96} y={310} fontSize={12} fontWeight={800} fill="#ffffff" textAnchor="middle">
            Sign decision
          </text>
        </g>
        {/* The signature stamp lands */}
        <g transform="translate(224 250)">
          <circle r={38} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={2} style={at(2)} />
        </g>
        <g transform="translate(224 250) rotate(-12)">
          <g className="sc-pop" style={at(0, "2.6s")}>
            <circle r={38} fill="var(--sc-panel)" stroke="var(--sc-teal)" strokeWidth={2.5} />
            <circle r={31} fill="none" stroke="var(--sc-teal)" strokeWidth={1} strokeDasharray="2 3" />
            <path
              d="M -6 -15 L -2 -11 L 6 -19"
              fill="none"
              stroke="var(--sc-teal)"
              strokeWidth={2.2}
              strokeLinecap="round"
            />
            <text y={4} fontSize={12} fontWeight={800} letterSpacing="0.08em" fill="var(--sc-teal)" textAnchor="middle">
              SIGNED
            </text>
            <text y={19} fontSize={11} fontWeight={600} fill="var(--sc-teal)" textAnchor="middle">
              QA lead
            </text>
          </g>
        </g>
      </Card>
      <g className="sc-fade" style={at(0, "2.8s")}>
        <text x={24} y={388} className="sc-note">
          Author: investigator · Approver: QA lead
        </text>
      </g>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** Investigation brief: one versioned document assembles section by section (signal, scope, evidence, hypotheses,
 * limitations, conclusion), each with its sources; then it passes from its author to a different reviewer.
 * "Hand over the investigation as one reviewable brief." */
function InvestigationBrief({ label }: { label: string }) {
  const sections = [
    { title: "Signal", text: "Pressure alarms up after Rev B", sources: "3 sources" },
    { title: "Scope", text: "OrbitCare 300 · lots 003–004", sources: "2 sources" },
    { title: "Evidence", text: "14 records · 2 gaps stated", sources: "14 sources" },
    { title: "Hypotheses", text: "3 compared · sensor PS-2 leads", sources: "5 sources" },
    { title: "Limitations", text: "Field data to 30 Sep", sources: "1 source" },
    { title: "Conclusion", text: "Proposed: escalate to CAPA", sources: "For review" },
  ];
  return (
    <Scene label={label}>
      {/* The brief */}
      <Card x={40} y={30} w={340} h={340} index={0}>
        <rect x={0} y={0} width={340} height={50} rx={12} fill="color-mix(in srgb, var(--sc-teal) 9%, transparent)" />
        <text x={18} y={24} fontSize={15} fontWeight={800}>
          Investigation brief
        </text>
        <text x={18} y={40} className="sc-note">
          INV-0042 · OrbitCare 300
        </text>
        <Chip x={340 - 14 - 60} y={25} width={120} text="v3 · In review" tone="amber" index={3} />
        {sections.map((section, index) => (
          <g key={section.title} className="sc-rise" style={at(index * 2, "0.3s")}>
            <text x={18} y={78 + index * 44} className="sc-card-title">
              {section.title}
            </text>
            <text
              x={322}
              y={78 + index * 44}
              className="sc-note"
              textAnchor="end"
              fill={index === 5 ? "var(--sc-amber)" : undefined}
            >
              {section.sources}
            </text>
            <text x={18} y={96 + index * 44} fontSize={12.5} fontWeight={index === 5 ? 800 : 500}>
              {section.text}
            </text>
            {index < sections.length - 1 && (
              <path d={`M 18 ${106 + index * 44} H 322`} className="sc-line" strokeWidth={1} />
            )}
          </g>
        ))}
      </Card>
      {/* Author hands over to a different reviewer */}
      <Card x={404} y={60} w={212} h={78} title="Author" index={12}>
        <text x={14} y={48} fontSize={14} fontWeight={800}>
          Investigator
        </text>
        <text x={14} y={66} className="sc-note">
          Submitted v3 · 12 Oct
        </text>
      </Card>
      <g className="sc-fade" style={at(0, "1.9s")}>
        <path d="M 510 144 V 186" className="sc-link sc-link-dashed sc-flow" strokeWidth={2.5} />
        <path
          d="M 503 182 L 510 191 L 517 182"
          fill="none"
          stroke="var(--sc-teal)"
          strokeWidth={2.5}
          strokeLinecap="round"
        />
      </g>
      <Card x={404} y={196} w={212} h={78} title="Reviewer" index={15}>
        <text x={14} y={48} fontSize={14} fontWeight={800}>
          QA lead
        </text>
        <text x={14} y={66} className="sc-note">
          Reading v3 · can challenge
        </text>
      </Card>
      <Chip x={510} y={304} width={141} text="Author ≠ reviewer" tone="teal" index={18} />
      <g className="sc-fade" style={at(0, "2.7s")}>
        <text x={510} y={342} className="sc-note" textAnchor="middle">
          Every statement keeps its source
        </text>
      </g>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** AI assurance: an advisory draft that cites its records and states its limits, beside the checks that bound it,
 * ending in the human review it always needs. The switch shows AI off until it is validated (the free trial runs
 * by hand). "Inspect how advisory intelligence is bounded and reviewed." (also Trust, "Grounded intelligence"). */
function AiAssurance({ label }: { label: string }) {
  const statements = [
    { text: "Complaints rise after Rev B", cite: "1" },
    { text: "Most come from lots 003–004", cite: "2" },
    { text: "Cause not established", cite: "!" },
  ];
  const checks = [
    { text: "Cites its evidence", state: "" },
    { text: "States its limits", state: "" },
    { text: "No root-cause claims", state: "" },
    { text: "Stays in tenant scope", state: "" },
    { text: "Human review required", state: "Always" },
    { text: "Off until validated", state: "Trial: off" },
  ];
  return (
    <Scene label={label}>
      {/* The advisory draft */}
      <Card x={24} y={30} w={280} h={340} title="AI advisory" index={0}>
        <Chip x={280 - 14 - 53} y={18} width={106} text="Advises only" tone="muted" index={3} />
        {statements.map((row, index) => (
          <g key={row.text} className="sc-rise" style={at(index, "0.4s")}>
            <text x={14} y={66 + index * 28} fontSize={12.5} fontWeight={600}>
              {row.text}
            </text>
            <rect
              x={224}
              y={53 + index * 28}
              width={42}
              height={18}
              rx={9}
              fill={
                row.cite === "!"
                  ? "color-mix(in srgb, var(--sc-amber) 16%, transparent)"
                  : "color-mix(in srgb, var(--sc-teal) 14%, transparent)"
              }
              stroke={row.cite === "!" ? "var(--sc-amber)" : "var(--sc-teal)"}
            />
            <text
              x={245}
              y={66 + index * 28}
              fontSize={11}
              fontWeight={800}
              textAnchor="middle"
              fill={row.cite === "!" ? "var(--sc-amber)" : "var(--sc-teal)"}
            >
              {row.cite === "!" ? "limit" : `[${row.cite}]`}
            </text>
          </g>
        ))}
        <g className="sc-rise" style={at(0, "0.9s")}>
          <rect
            x={14}
            y={148}
            width={252}
            height={74}
            rx={8}
            fill="color-mix(in srgb, var(--sc-amber) 8%, transparent)"
            stroke="var(--sc-line)"
          />
          <rect x={14} y={148} width={4} height={74} rx={2} fill="var(--sc-amber)" />
          <text x={30} y={170} className="sc-card-title">
            Limits stated
          </text>
          <text x={30} y={190} className="sc-note">
            Field data only to 30 Sep
          </text>
          <text x={30} y={208} className="sc-note">
            Lots 005–006 not yet tested
          </text>
        </g>
        <path d="M 14 248 H 266" className="sc-line" strokeWidth={1} />
        <g className="sc-fade" style={at(0, "1.2s")}>
          <Toggle x={14} y={266} on={false} />
          <text x={58} y={279} fontSize={13} fontWeight={800}>
            Off until validated
          </text>
          <text x={58} y={298} className="sc-note">
            Free trial: every step by hand
          </text>
          <text x={58} y={315} className="sc-note">
            Design partners: after validation
          </text>
        </g>
      </Card>
      {/* The checks that bound it */}
      <Card x={320} y={30} w={296} h={340} title="Assurance checks" index={2}>
        {checks.map((check, index) => {
          const y = 60 + index * 42;
          const human = check.state === "Always";
          const off = check.state === "Trial: off";
          return (
            <g key={check.text}>
              <g className="sc-pop" style={at(index * 2, "0.8s")}>
                {off ? (
                  <Toggle x={11} y={y - 9} on={false} />
                ) : human ? (
                  <g transform={`translate(28 ${y})`}>
                    <circle
                      r={11}
                      fill="color-mix(in srgb, var(--sc-amber) 18%, transparent)"
                      stroke="var(--sc-amber)"
                    />
                    <circle cy={-3.5} r={3.2} fill="var(--sc-amber)" />
                    <path d="M -6 7 Q 0 -1 6 7" fill="var(--sc-amber)" />
                  </g>
                ) : (
                  <Tick x={28} y={y} r={11} />
                )}
              </g>
              <g className="sc-rise" style={at(index * 2, "0.9s")}>
                <text x={54} y={y + 4.5} fontSize={13} fontWeight={700}>
                  {check.text}
                </text>
                {check.state && (
                  <text
                    x={282}
                    y={y + 4.5}
                    fontSize={11}
                    fontWeight={700}
                    textAnchor="end"
                    fill={human ? "var(--sc-amber)" : "var(--sc-muted)"}
                  >
                    {check.state}
                  </text>
                )}
              </g>
              {index < checks.length - 1 && (
                <path d={`M 14 ${y + 21} H 282`} className="sc-line" strokeWidth={1} opacity={0.7} />
              )}
            </g>
          );
        })}
        {/* Gentle pulse on the human review mark */}
        <g transform="translate(28 228)">
          <circle r={15} className="sc-ping" fill="none" stroke="var(--sc-amber)" strokeWidth={1.5} style={at(2)} />
        </g>
        <Chip x={148} y={316} width={200} text="People decide and sign" tone="teal" index={19} />
      </Card>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** AI provenance: an AI-assisted insight with numbered links back to the exact records it was built from (one
 * record it did not use stays unlinked), and the model, time view and scope recorded beside it. "Trace every
 * insight back to its evidence context." */
function AiProvenance({ label }: { label: string }) {
  const records = [
    { title: "Complaint C-1187", note: "Pressure alarm · lot 004" },
    { title: "Lot 004 build record", note: "Sensor PS-2 fitted" },
    { title: "Change CHG-014", note: "Rev A → Rev B" },
    { title: "Supplier record", note: "Kestrel Sensors · PS-2" },
  ];
  const ports = [126, 156, 186, 216];
  const context = [
    ["Model", "Advisory model v1"],
    ["Time view", "12 Oct 2026"],
    ["Scope", "OrbitCare 300 Rev B"],
  ];
  return (
    <Scene label={label}>
      {/* Source records */}
      {records.map((record, index) => (
        <Card key={record.title} x={24} y={34 + index * 66} w={214} h={50} index={index}>
          <text x={14} y={22} fontSize={13} fontWeight={800}>
            {record.title}
          </text>
          <text x={14} y={39} className="sc-note">
            {record.note}
          </text>
          <circle
            cx={194}
            cy={25}
            r={9}
            fill="color-mix(in srgb, var(--sc-teal) 14%, transparent)"
            stroke="var(--sc-teal)"
          />
          <text x={194} y={29} fontSize={11} fontWeight={800} textAnchor="middle" fill="var(--sc-teal)">
            {index + 1}
          </text>
        </Card>
      ))}
      <g>
        <Card x={24} y={298} w={214} h={50} index={4}>
          <text x={14} y={22} fontSize={13} fontWeight={800} fill="var(--sc-muted)">
            Service log S-22
          </text>
          <text x={14} y={39} className="sc-note">
            Not used
          </text>
        </Card>
      </g>
      {/* Lines from each record to the insight */}
      {records.map((record, index) => {
        const y = 59 + index * 66;
        return (
          <path
            key={record.title}
            className="sc-link sc-draw"
            pathLength={1}
            d={`M 238 ${y} C 300 ${y}, 305 ${ports[index]}, 363 ${ports[index]}`}
            style={at(index, "1.1s")}
          />
        );
      })}
      {/* The insight and its recorded context */}
      <Card x={372} y={70} w={244} h={260} title="AI-assisted insight" index={5}>
        <circle cx={226} cy={18} r={5} fill="var(--sc-teal)" />
        <g transform="translate(226 18)">
          <circle r={7} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={1.5} style={at(2)} />
        </g>
        <text x={18} y={50} fontSize={13} fontWeight={800}>
          Alarm complaints cluster
        </text>
        <text x={18} y={68} fontSize={13} fontWeight={800}>
          in lots built with PS-2
        </text>
        <text x={18} y={88} className="sc-note">
          Cites records 1–4
        </text>
        <path d="M 18 100 H 230" className="sc-line" strokeWidth={1} />
        {context.map(([key, value], index) => (
          <g key={key}>
            <text x={18} y={124 + index * 24} className="sc-note">
              {key}
            </text>
            <text x={230} y={124 + index * 24} fontSize={12} fontWeight={600} textAnchor="end">
              {value}
            </text>
          </g>
        ))}
        <path d="M 18 190 H 230" className="sc-line" strokeWidth={1} />
        <Chip x={18 + 66} y={222} width={132} text="Review pending" tone="amber" index={18} />
      </Card>
      {/* Numbered ports where each record enters the insight */}
      {ports.map((y, index) => (
        <g key={y} transform={`translate(372 ${y})`}>
          <g className="sc-pop" style={at(index, "1.7s")}>
            <circle r={9} fill="var(--sc-teal)" />
            <text y={4} fontSize={11} fontWeight={800} fill="#ffffff" textAnchor="middle">
              {index + 1}
            </text>
          </g>
        </g>
      ))}
      <g className="sc-fade" style={at(0, "2.6s")}>
        <text x={372} y={356} className="sc-note">
          Inputs, model and time view kept for review
        </text>
      </g>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** Human review at the decision boundary (Trust hero, dark): evidence, contradictions, unknowns and remarks cross the
 * boundary to a named reviewer who signs; the AI suggestion stops at the line, because only people sign. "Evidence
 * before inference. Challenge before conclusion." / "Keep accountable people at the decision boundary." */
function HumanReviewBoundary({ label }: { label: string }) {
  const inputs = [
    { title: "Evidence", note: "14 records linked" },
    { title: "Contradiction", note: "1 raised · answered" },
    { title: "Unknowns", note: "2 open · stated" },
    { title: "Reviewer remarks", note: "3 attached" },
  ];
  const rows = [
    ["Decision", "Escalate to CAPA"],
    ["Author", "Investigator"],
    ["Version", "Brief v3"],
    ["Meaning", "Approved"],
  ];
  return (
    <Scene label={label} tone="dark">
      <text x={30} y={56} className="sc-card-title">
        Evidence &amp; suggestions
      </text>
      <text x={380} y={56} className="sc-card-title">
        Accountable decision
      </text>
      {/* What reaches the boundary */}
      {inputs.map((input, index) => (
        <Card key={input.title} x={30} y={70 + index * 58} w={236} h={46} index={index}>
          <text x={14} y={20} fontSize={13} fontWeight={800}>
            {input.title}
          </text>
          <text x={14} y={36} className="sc-note">
            {input.note}
          </text>
        </Card>
      ))}
      <g className="sc-rise" style={at(4)}>
        <rect
          x={30}
          y={302}
          width={236}
          height={46}
          rx={12}
          fill="none"
          stroke="var(--sc-muted)"
          strokeDasharray="4 4"
        />
        <text x={44} y={322} fontSize={13} fontWeight={800} fill="var(--sc-ink-2)">
          AI suggestion
        </text>
        <text x={44} y={338} className="sc-note">
          Advisory only · cannot sign
        </text>
      </g>
      {/* The boundary */}
      <path d="M 330 40 V 356" className="sc-link sc-draw" pathLength={1} strokeWidth={2} style={at(0, "0.6s")} />
      {/* Evidence crosses the boundary to the reviewer */}
      {inputs.map((input, index) => {
        const y = 93 + index * 58;
        return (
          <path
            key={input.title}
            className="sc-link sc-draw"
            pathLength={1}
            d={`M 266 ${y} C 318 ${y}, 330 210, 380 210`}
            opacity={0.6}
            style={at(index, "1.0s")}
          />
        );
      })}
      {/* The suggestion stops at the line */}
      <path
        d="M 266 325 H 316"
        className="sc-link sc-draw"
        pathLength={1}
        stroke="var(--sc-muted)"
        style={at(0, "1.5s")}
      />
      <g className="sc-fade" style={at(0, "1.9s")}>
        <path d="M 318 314 V 336" stroke="var(--sc-amber)" strokeWidth={3} strokeLinecap="round" />
      </g>
      {/* The person who signs */}
      <Card x={380} y={70} w={236} h={278} index={9}>
        <circle cx={34} cy={30} r={8} fill="var(--sc-teal)" />
        <path d="M 20 52 Q 34 34 48 52 Z" fill="var(--sc-teal)" />
        <text x={60} y={36} fontSize={14} fontWeight={800}>
          QA lead
        </text>
        <text x={60} y={52} className="sc-note">
          Approval authority
        </text>
        <path d="M 14 70 H 222" className="sc-line" strokeWidth={1} />
        {rows.map(([key, value], index) => (
          <g key={key}>
            <text x={14} y={96 + index * 26} className="sc-note">
              {key}
            </text>
            <text x={222} y={96 + index * 26} fontSize={12.5} fontWeight={600} textAnchor="end">
              {value}
            </text>
          </g>
        ))}
        <g transform="translate(14 196)">
          <g className="sc-pop" style={at(0, "2.3s")}>
            <rect
              width={208}
              height={64}
              rx={10}
              fill="color-mix(in srgb, var(--sc-teal) 16%, transparent)"
              stroke="var(--sc-teal)"
            />
            <Tick x={28} y={32} r={13} mark="#0f2233" />
            <text x={52} y={28} fontSize={14} fontWeight={800}>
              Signed
            </text>
            <text x={52} y={46} className="sc-note">
              Re-authenticated · 15:20
            </text>
          </g>
        </g>
        <g transform="translate(42 228)">
          <circle r={14} className="sc-ping" fill="none" stroke="var(--sc-teal)" strokeWidth={2} style={at(2)} />
        </g>
      </Card>
      <g className="sc-fade" style={at(0, "2.6s")}>
        <text x={330} y={376} className="sc-card-title" textAnchor="middle">
          Decision boundary · only people sign
        </text>
      </g>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** Audit trail: an append-only, chained timeline of what changed, who acted, when and why, appearing event by event
 * and ending in the signed decision. "Preserve the story of what changed, who acted, and why." */
function AuditTrail({ label }: { label: string }) {
  const events = [
    { when: "12 Oct 09:14", who: "Investigator", what: "Linked lot 004 records", version: "", why: "New sensor scope" },
    {
      when: "12 Oct 10:02",
      who: "Investigator",
      what: "Updated hypothesis H2",
      version: "v1 → v2",
      why: "Supplier data added",
    },
    { when: "12 Oct 11:30", who: "QA reviewer", what: "Challenged H2", version: "", why: "Contradiction raised" },
    { when: "12 Oct 14:05", who: "Investigator", what: "Submitted brief", version: "v3", why: "Ready for review" },
    { when: "12 Oct 15:20", who: "QA lead", what: "Signed decision", version: "Brief v3", why: "Escalate to CAPA" },
  ];
  const columns: [number, string][] = [
    [56, "When"],
    [156, "Who"],
    [268, "What"],
    [446, "Why"],
  ];
  return (
    <Scene label={label}>
      <Card x={24} y={24} w={592} h={346} index={0}>
        <text x={18} y={32} fontSize={15} fontWeight={800}>
          Audit trail · INV-0042
        </text>
        <Chip x={592 - 14 - 85} y={27} width={170} text="Append-only · chained" tone="teal" index={3} />
        {columns.map(([x, text]) => (
          <text key={text} x={x} y={68} className="sc-card-title">
            {text}
          </text>
        ))}
        <path d="M 18 78 H 574" className="sc-line" strokeWidth={1} />
        {/* The timeline spine */}
        <path d="M 30 90 V 284" className="sc-line sc-draw" pathLength={1} style={at(0, "0.3s")} />
        {events.map((event, index) => {
          const y = 100 + index * 46;
          const signed = index === events.length - 1;
          return (
            <g key={event.when}>
              <g className="sc-rise" style={at(index * 3, "0.4s")}>
                {!signed && (
                  <circle cx={30} cy={y - 4} r={6} fill="var(--sc-panel)" stroke="var(--sc-teal)" strokeWidth={2} />
                )}
                <text x={56} y={y} fontSize={12} fill="var(--sc-ink-2)">
                  {event.when}
                </text>
                <text x={156} y={y} fontSize={13} fontWeight={800}>
                  {event.who}
                </text>
                <text
                  x={268}
                  y={y}
                  fontSize={13}
                  fontWeight={signed ? 800 : 500}
                  fill={signed ? "var(--sc-teal)" : undefined}
                >
                  {event.what}
                </text>
                {event.version && (
                  <text x={268} y={y + 16} className="sc-note">
                    {event.version}
                  </text>
                )}
                <text x={446} y={y} fontSize={12} fill="var(--sc-ink-2)">
                  {event.why}
                </text>
              </g>
              {signed && (
                <>
                  <g className="sc-pop" style={at(index * 3, "0.7s")}>
                    <Tick x={30} y={y - 4} r={9} />
                  </g>
                  <g transform={`translate(30 ${y - 4})`}>
                    <circle
                      r={10}
                      className="sc-ping"
                      fill="none"
                      stroke="var(--sc-teal)"
                      strokeWidth={2}
                      style={at(2)}
                    />
                  </g>
                </>
              )}
            </g>
          );
        })}
        <path d="M 18 312 H 574" className="sc-line" strokeWidth={1} />
        <g className="sc-fade" style={at(0, "2.6s")}>
          <text x={18} y={332} className="sc-note">
            Who · when · what changed · why — ready to export with the evidence package
          </text>
        </g>
      </Card>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

/** Enterprise administration: one control plane, with a customer and its tenants (one suspended) on the left and the
 * tiles an administrator governs on the right: roles, MFA, connectors and mappings. "Operate tenants, access,
 * integrations, and configuration from one governed control plane." */
function EnterpriseControlPlane({ label }: { label: string }) {
  const tenants = [
    { name: "Production", state: "Active", tone: "var(--sc-teal)" },
    { name: "Validation", state: "Active", tone: "var(--sc-teal)" },
    { name: "Sandbox", state: "Suspended", tone: "var(--sc-amber)" },
  ];
  const roles = ["Investigator", "Reviewer", "Approver", "Read-only"];
  const connectors = [
    { name: "Complaints", state: "Synced", tone: "var(--sc-green)" },
    { name: "ERP lots", state: "Synced", tone: "var(--sc-green)" },
    { name: "Supplier portal", state: "Off", tone: "var(--sc-line)" },
  ];
  const mappings = [
    ["lot_no", "Lot"],
    ["part_id", "Component"],
    ["defect", "Complaint"],
  ];
  return (
    <Scene label={label}>
      <text x={24} y={44} className="sc-card-title">
        Customer → tenants
      </text>
      <Card x={24} y={56} w={202} h={62} index={0}>
        <text x={14} y={27} fontSize={14} fontWeight={800}>
          Customer A
        </text>
        <text x={14} y={45} className="sc-note">
          Pilot plan · 12 seats
        </text>
      </Card>
      {/* Tenants under the customer */}
      <path
        d="M 44 118 V 288 M 44 156 H 70 M 44 222 H 70 M 44 288 H 70"
        className="sc-line sc-draw"
        pathLength={1}
        style={at(0, "0.5s")}
      />
      {tenants.map((tenant, index) => (
        <g key={tenant.name} transform={`translate(70 ${136 + index * 66})`}>
          <g className="sc-rise" style={at(index, "0.9s")}>
            <rect width={156} height={40} rx={10} fill="var(--sc-panel)" stroke="var(--sc-line)" />
            <text x={14} y={25} fontSize={13} fontWeight={700}>
              {tenant.name}
            </text>
            <text x={144} y={24} fontSize={11} fontWeight={700} textAnchor="end" fill={tenant.tone}>
              {tenant.state}
            </text>
          </g>
        </g>
      ))}
      <g className="sc-fade" style={at(0, "1.4s")}>
        <text x={24} y={350} className="sc-note">
          Boundary enforced on every query
        </text>
      </g>
      {/* The governed tiles */}
      <Card x={246} y={40} w={180} h={150} title="Roles & access" index={8}>
        {roles.map((role, index) => (
          <g key={role}>
            <circle cx={20} cy={44 + index * 22} r={3.5} fill="var(--sc-teal)" />
            <text x={30} y={48 + index * 22} fontSize={12} fontWeight={600}>
              {role}
            </text>
          </g>
        ))}
        <text x={14} y={138} className="sc-note">
          + 3 more workflow roles
        </text>
      </Card>
      <Card x={436} y={40} w={180} h={150} title="MFA" index={9}>
        <path
          d="M 30 38 L 44 44 V 58 Q 44 70 30 76 Q 16 70 16 58 V 44 Z"
          fill="color-mix(in srgb, var(--sc-teal) 14%, transparent)"
          stroke="var(--sc-teal)"
          strokeWidth={2}
        />
        <path d="M 24 57 L 29 62 L 37 52" fill="none" stroke="var(--sc-teal)" strokeWidth={2} strokeLinecap="round" />
        <text x={56} y={54} fontSize={12} fontWeight={700}>
          Authenticator app
        </text>
        <text x={56} y={71} fontSize={12} fontWeight={800} fill="var(--sc-teal)">
          Required
        </text>
        <text x={14} y={112} className="sc-note">
          Session limits
        </text>
        <text x={14} y={130} className="sc-note">
          Signed out on suspension
        </text>
      </Card>
      <Card x={246} y={206} w={180} h={150} title="Connectors" index={10}>
        {connectors.map((connector, index) => (
          <g key={connector.name}>
            <text x={14} y={50 + index * 26} fontSize={12} fontWeight={600}>
              {connector.name}
            </text>
            {index === 0 ? (
              <circle cx={158} cy={46} r={4.5} fill={connector.tone} className="sc-pulse" />
            ) : (
              <circle cx={158} cy={46 + index * 26} r={4.5} fill={connector.tone} />
            )}
          </g>
        ))}
        <text x={14} y={138} className="sc-note">
          Last sync 09:00 · 0 errors
        </text>
      </Card>
      <Card x={436} y={206} w={180} h={150} title="Mappings" index={11}>
        {mappings.map(([from, to], index) => (
          <g key={from}>
            <text x={14} y={50 + index * 26} fontSize={12} fill="var(--sc-ink-2)">
              {from}
            </text>
            <path d={`M 66 ${46 + index * 26} H 80`} className="sc-link" strokeWidth={1.5} />
            <path
              d={`M 76 ${42 + index * 26} L 81 ${46 + index * 26} L 76 ${50 + index * 26}`}
              className="sc-link"
              strokeWidth={1.5}
            />
            <text x={88} y={50 + index * 26} fontSize={12} fontWeight={700}>
              {to}
            </text>
          </g>
        ))}
        <text x={14} y={138} className="sc-note">
          Version 4 · change recorded
        </text>
      </Card>
      <Illustrative x={616} y={388} />
    </Scene>
  );
}

export const decisionScenes: Record<string, SceneComponent> = {
  "medtech-counterfactual-hero": CounterfactualScenario,
  "medtech-decision-center-hero": DecisionCenter,
  "medtech-investigation-brief-hero": InvestigationBrief,
  "medtech-hero-ai-assurance": AiAssurance,
  "medtech-hero-ai-provenance": AiProvenance,
  "medtech-hero-human-review": HumanReviewBoundary,
  "medtech-hero-audit-trail": AuditTrail,
  "medtech-hero-enterprise-administration": EnterpriseControlPlane,
};
