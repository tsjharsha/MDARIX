import type { ReactNode } from "react";
import type { JourneyKey } from "./trialGuide";

// The free trial guide's hero pictures: each step drawn as the screen it happens on, with the control to use
// highlighted and a pointer moving to it. Illustrations, not screenshots: names and numbers in them are examples.
// Motion is CSS (trialGuide.css) and stops under prefers-reduced-motion and in print.

const C = {
  navy: "#0b2540",
  ink: "#183249",
  muted: "#64748b",
  line: "#dbe4ec",
  page: "#f6f9fb",
  surface: "#ffffff",
  teal: "#0d9488",
  tealDark: "#0f766e",
  wash: "#ccfbf1",
  amber: "#f59e0b",
  red: "#dc2626",
  green: "#16a34a",
};

const W = 560;
const H = 330;

/** A browser window with an address, the frame every scene is drawn in. */
function Frame({ address, label, children }: { address: string; label: string; children: ReactNode }) {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="tg-scene" role="img" aria-label={label}>
      <rect x="1" y="1" width={W - 2} height={H - 2} rx="14" fill={C.page} stroke={C.line} />
      <path d={`M1 15 a14 14 0 0 1 14 -14 h${W - 30} a14 14 0 0 1 14 14 v19 h-${W - 2} z`} fill={C.surface} />
      <line x1="1" y1="34" x2={W - 1} y2="34" stroke={C.line} />
      {[18, 32, 46].map((x, index) => (
        <circle key={x} cx={x} cy="17.5" r="4.5" fill={["#f87171", "#fbbf24", "#34d399"][index]} />
      ))}
      <rect x="70" y="9" width="260" height="17" rx="8.5" fill={C.page} stroke={C.line} />
      <text x="82" y="21.5" fontSize="10.5" fill={C.muted}>
        {address}
      </text>
      {children}
    </svg>
  );
}

/** A button drawn in the scene; `focus` gives it the pulsing ring the pointer moves to. */
function Button({
  x,
  y,
  w,
  text,
  tone = "primary",
  focus = false,
}: {
  x: number;
  y: number;
  w: number;
  text: string;
  tone?: "primary" | "secondary";
  focus?: boolean;
}) {
  return (
    <g>
      {focus && (
        <rect
          className="tg-ring"
          x={x - 5}
          y={y - 5}
          width={w + 10}
          height="38"
          rx="12"
          fill="none"
          stroke={C.teal}
          strokeWidth="2.5"
        />
      )}
      <rect
        x={x}
        y={y}
        width={w}
        height="28"
        rx="8"
        fill={tone === "primary" ? C.teal : C.surface}
        stroke={tone === "primary" ? C.teal : C.line}
      />
      <text
        x={x + w / 2}
        y={y + 18}
        fontSize="11.5"
        fontWeight="700"
        textAnchor="middle"
        fill={tone === "primary" ? "#fff" : C.ink}
      >
        {text}
      </text>
    </g>
  );
}

/** The pointer: it travels to (x, y) and clicks. */
function Pointer({ x, y }: { x: number; y: number }) {
  return (
    <g className="tg-pointer" style={{ ["--tx" as string]: `${x}px`, ["--ty" as string]: `${y}px` }}>
      <path
        d="M0 0 L0 17 L4.5 13 L8 20.5 L11 19 L7.6 11.8 L13.5 11.8 Z"
        fill={C.navy}
        stroke="#fff"
        strokeWidth="1.4"
      />
    </g>
  );
}

/** A field: its label and an input box, filled with example text. */
function Field({ x, y, w, label, value }: { x: number; y: number; w: number; label: string; value?: string }) {
  return (
    <g>
      <text x={x} y={y} fontSize="9.5" fontWeight="600" fill={C.muted}>
        {label}
      </text>
      <rect x={x} y={y + 5} width={w} height="22" rx="6" fill={C.surface} stroke={C.line} />
      {value && (
        <text className="tg-type" x={x + 8} y={y + 20} fontSize="10.5" fill={C.ink}>
          {value}
        </text>
      )}
    </g>
  );
}

function Check({ x, y, r = 9, color = C.green }: { x: number; y: number; r?: number; color?: string }) {
  return (
    <g>
      <circle cx={x} cy={y} r={r} fill={color} />
      <path
        d={`M${x - r * 0.45} ${y} l${r * 0.3} ${r * 0.32} l${r * 0.6} -${r * 0.62}`}
        fill="none"
        stroke="#fff"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  );
}

function OpenScene() {
  return (
    <Frame address="mdarix.com" label="The MDARIX website: choose Start free trial, then fill in the two-step request">
      <rect x="1" y="35" width={W - 2} height="294" fill={C.navy} />
      <text x="30" y="88" fontSize="20" fontWeight="800" fill="#fff">
        Inspection-ready,
      </text>
      <text x="30" y="113" fontSize="20" fontWeight="800" fill="#fff">
        every day.
      </text>
      <rect x="30" y="128" width="190" height="7" rx="3.5" fill="#ffffff40" />
      <rect x="30" y="142" width="150" height="7" rx="3.5" fill="#ffffff30" />
      <Button x={30} y={168} w={130} text="Start free trial" focus />
      <g className="tg-pop" style={{ ["--d" as string]: "1.4s" }}>
        <rect x="290" y="56" width="240" height="252" rx="12" fill={C.surface} />
        <text x="308" y="82" fontSize="9" fontWeight="700" fill={C.teal} letterSpacing="1">
          REQUEST ACCESS
        </text>
        <text x="308" y="101" fontSize="15" fontWeight="800" fill={C.ink}>
          Start your free trial
        </text>
        <rect x="308" y="112" width="92" height="20" rx="10" fill={C.wash} />
        <text x="318" y="126" fontSize="9.5" fontWeight="700" fill={C.tealDark}>
          1 About you
        </text>
        <rect x="406" y="112" width="92" height="20" rx="10" fill={C.page} stroke={C.line} />
        <text x="416" y="126" fontSize="9.5" fill={C.muted}>
          2 Your trial
        </text>
        <Field x={308} y={150} w={204} label="Full name *" value="Your name" />
        <Field x={308} y={190} w={204} label="Work email *" value="you@company.com" />
        <Button x={308} y={240} w={204} text="Request free trial" />
        <text x="410" y="290" fontSize="9" textAnchor="middle" fill={C.muted}>
          30 days · 3 users · no credit card
        </text>
      </g>
      <Pointer x={146} y={188} />
    </Frame>
  );
}

function SignInScene() {
  return (
    <Frame
      address="mdarix.com/activate-account"
      label="Activate from the invitation email, choose your own password, add an authenticator app"
    >
      <g className="tg-pop" style={{ ["--d" as string]: "0.1s" }}>
        <rect x="24" y="62" width="158" height="200" rx="12" fill={C.surface} stroke={C.line} />
        <path d="M24 92 L103 140 L182 92" fill="none" stroke={C.line} strokeWidth="2" />
        <text x="40" y="84" fontSize="10.5" fontWeight="700" fill={C.ink}>
          Your MDARIX invitation
        </text>
        <rect x="40" y="152" width="126" height="6" rx="3" fill={C.line} />
        <rect x="40" y="164" width="96" height="6" rx="3" fill={C.line} />
        <Button x={40} y={190} w={126} text="Activate account" focus />
        <text x="103" y="246" fontSize="9" textAnchor="middle" fill={C.muted}>
          Link valid for 48 hours
        </text>
      </g>
      <path
        className="tg-draw"
        d="M190 162 C 210 162, 214 162, 232 162"
        stroke={C.teal}
        strokeWidth="2.5"
        fill="none"
        markerEnd="url(#tg-arrow)"
      />
      <g className="tg-pop" style={{ ["--d" as string]: "0.9s" }}>
        <rect x="240" y="62" width="150" height="200" rx="12" fill={C.surface} stroke={C.line} />
        <text x="256" y="86" fontSize="11" fontWeight="700" fill={C.ink}>
          Choose a password
        </text>
        <Field x={256} y={108} w={118} label="New password" value="••••••••••••••" />
        <rect x="256" y="146" width="118" height="5" rx="2.5" fill={C.line} />
        <rect className="tg-grow" x="256" y="146" width="118" height="5" rx="2.5" fill={C.green} />
        <text x="256" y="166" fontSize="9" fill={C.muted}>
          12+ characters. Only you
        </text>
        <text x="256" y="178" fontSize="9" fill={C.muted}>
          know it.
        </text>
        <Button x={256} y={210} w={118} text="Activate" />
      </g>
      <path
        className="tg-draw tg-late"
        d="M398 162 C 410 162, 414 162, 426 162"
        stroke={C.teal}
        strokeWidth="2.5"
        fill="none"
        markerEnd="url(#tg-arrow)"
      />
      <g className="tg-pop" style={{ ["--d" as string]: "1.7s" }}>
        <rect x="434" y="56" width="104" height="212" rx="18" fill={C.navy} />
        <rect x="442" y="72" width="88" height="180" rx="10" fill={C.surface} />
        <text x="486" y="98" fontSize="9" fontWeight="700" textAnchor="middle" fill={C.muted}>
          Authenticator
        </text>
        <text x="486" y="124" fontSize="9.5" textAnchor="middle" fill={C.ink}>
          MDARIX
        </text>
        <text x="486" y="152" fontSize="15" fontWeight="800" textAnchor="middle" fill={C.teal} letterSpacing="1">
          482 913
        </text>
        <circle cx="486" cy="190" r="14" fill="none" stroke={C.line} strokeWidth="4" />
        <circle
          className="tg-timer"
          cx="486"
          cy="190"
          r="14"
          fill="none"
          stroke={C.teal}
          strokeWidth="4"
          strokeDasharray="88"
        />
        <Check x={486} y={230} />
      </g>
      <defs>
        <marker id="tg-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L10 5 L0 10 z" fill={C.teal} />
        </marker>
      </defs>
      <Pointer x={154} y={208} />
    </Frame>
  );
}

function TeamScene() {
  const rows = [
    { initials: "YO", name: "You", role: "Trial owner", state: "Active", d: "0.1s" },
    { initials: "CH", name: "Colleague 1", role: "Complaint handling", state: "Invited", d: "1.0s" },
    { initials: "RA", name: "Colleague 2", role: "Regulatory affairs", state: "Invited", d: "1.8s" },
  ];
  return (
    <Frame
      address="mdarix.com/app · Getting started"
      label="Your team: enter a colleague's name and work email, then Invite colleague, twice"
    >
      <rect x="24" y="52" width="512" height="262" rx="12" fill={C.surface} stroke={C.line} />
      <text x="44" y="78" fontSize="9" fontWeight="700" fill={C.teal} letterSpacing="1">
        3 OF 3 USERS
      </text>
      <text x="44" y="98" fontSize="15" fontWeight="800" fill={C.ink}>
        Your team
      </text>
      {rows.map((row, index) => (
        <g key={row.initials} className="tg-pop" style={{ ["--d" as string]: row.d }}>
          <circle cx="62" cy={128 + index * 42} r="15" fill={index ? C.wash : C.teal} />
          <text
            x="62"
            y={132 + index * 42}
            fontSize="10"
            fontWeight="800"
            textAnchor="middle"
            fill={index ? C.tealDark : "#fff"}
          >
            {row.initials}
          </text>
          <text x="86" y={126 + index * 42} fontSize="11.5" fontWeight="700" fill={C.ink}>
            {row.name}
          </text>
          <text x="86" y={140 + index * 42} fontSize="9.5" fill={C.muted}>
            {row.role}
          </text>
          <rect
            x="226"
            y={118 + index * 42}
            width="56"
            height="18"
            rx="9"
            fill={row.state === "Active" ? "#dcfce7" : "#fef3c7"}
          />
          <text
            x="254"
            y={130.5 + index * 42}
            fontSize="9"
            fontWeight="700"
            textAnchor="middle"
            fill={row.state === "Active" ? C.green : "#b45309"}
          >
            {row.state}
          </text>
        </g>
      ))}
      <line x1="306" y1="70" x2="306" y2="296" stroke={C.line} />
      <Field x={326} y={96} w={190} label="Colleague's name" value="Colleague 2" />
      <Field x={326} y={140} w={190} label="Work email" value="colleague@company.com" />
      <Button x={326} y={188} w={190} text="Invite colleague" focus />
      <text x="326" y="246" fontSize="9.5" fill={C.muted}>
        They set their own password from the
      </text>
      <text x="326" y="259" fontSize="9.5" fill={C.muted}>
        email. The link is valid for 48 hours.
      </text>
      <Pointer x={498} y={206} />
    </Frame>
  );
}

function SampleScene() {
  const stations = [C.green, C.green, C.green, C.amber, C.red, C.red, C.amber, C.red, C.amber, C.red];
  const chapters = ["Routine close", "Reporting clocks", "Hidden complaints", "Trend to case", "Investigation"];
  return (
    <Frame address="mdarix.com/app · Getting started" label="The quality loop on the sample data, chapter by chapter">
      <rect x="1" y="35" width="300" height="294" fill={C.navy} />
      <circle cx="150" cy="182" r="96" fill="none" stroke="#ffffff22" strokeWidth="10" />
      <circle
        className="tg-loop"
        cx="150"
        cy="182"
        r="96"
        fill="none"
        stroke={C.teal}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray="603"
        transform="rotate(-90 150 182)"
      />
      {stations.map((color, index) => {
        const angle = (index / stations.length) * Math.PI * 2 - Math.PI / 2;
        return (
          <circle
            key={index}
            className={color === C.red ? "tg-blink" : undefined}
            cx={150 + 96 * Math.cos(angle)}
            cy={182 + 96 * Math.sin(angle)}
            r="11"
            fill={color}
            stroke={C.navy}
            strokeWidth="3"
          />
        );
      })}
      <text x="150" y="178" fontSize="26" fontWeight="800" textAnchor="middle" fill="#fff">
        3 of 10
      </text>
      <text x="150" y="198" fontSize="10.5" textAnchor="middle" fill="#cbd5e1">
        chapters tried
      </text>
      <rect x="318" y="50" width="222" height="268" rx="12" fill={C.surface} stroke={C.line} />
      <text x="334" y="74" fontSize="9" fontWeight="700" fill={C.teal} letterSpacing="1">
        YOUR STORY
      </text>
      {chapters.map((title, index) => (
        <g key={title} className="tg-pop" style={{ ["--d" as string]: `${0.3 + index * 0.35}s` }}>
          {index < 3 ? (
            <Check x={344} y={98 + index * 40} r={8} />
          ) : (
            <circle cx="344" cy={98 + index * 40} r="8" fill="none" stroke={C.line} strokeWidth="2" />
          )}
          <text x="360" y={102 + index * 40} fontSize="11" fontWeight={index === 3 ? 800 : 600} fill={C.ink}>
            {index + 1}. {title}
          </text>
          {index === 3 && (
            <rect
              className="tg-ring"
              x="334"
              y={84 + index * 40}
              width="196"
              height="28"
              rx="8"
              fill="none"
              stroke={C.teal}
              strokeWidth="2"
            />
          )}
        </g>
      ))}
      <rect x="334" y="292" width="190" height="16" rx="8" fill={C.wash} />
      <text x="429" y="303.5" fontSize="9" fontWeight="700" textAnchor="middle" fill={C.tealDark}>
        Sample data · fictional manufacturer
      </text>
    </Frame>
  );
}

function OwnDataScene() {
  const types = ["Products", "Lots", "Complaints", "Investigations", "CAPAs", "Risks"];
  return (
    <Frame
      address="mdarix.com/app · Import data"
      label="Upload your own data: your quality system's export as it comes, checked, then imported"
    >
      <rect x="24" y="52" width="512" height="262" rx="12" fill={C.surface} stroke={C.line} />
      <text x="44" y="78" fontSize="9" fontWeight="700" fill={C.teal} letterSpacing="1">
        BRING YOUR OWN DATA
      </text>
      <text x="44" y="98" fontSize="15" fontWeight="800" fill={C.ink}>
        Upload your export
      </text>
      {types.map((type, index) => {
        const x = 44 + (index % 3) * 122;
        const y = 112 + Math.floor(index / 3) * 30;
        return (
          <g key={type}>
            <rect
              x={x}
              y={y}
              width="114"
              height="22"
              rx="11"
              fill={index === 2 ? C.teal : C.page}
              stroke={index === 2 ? C.teal : C.line}
            />
            <text
              x={x + 57}
              y={y + 15}
              fontSize="10"
              fontWeight="700"
              textAnchor="middle"
              fill={index === 2 ? "#fff" : C.ink}
            >
              {index + 1}. {type}
            </text>
          </g>
        );
      })}
      <g className="tg-fly">
        <rect x="430" y="110" width="58" height="72" rx="6" fill={C.surface} stroke={C.teal} strokeWidth="2" />
        <path d="M472 110 v16 h16" fill="none" stroke={C.teal} strokeWidth="2" />
        <text x="459" y="160" fontSize="12" fontWeight="800" textAnchor="middle" fill={C.teal}>
          XLSX
        </text>
      </g>
      <rect x="44" y="188" width="358" height="1" fill={C.line} />
      <Button x={44} y={204} w={110} text="Check file" focus />
      <g className="tg-pop" style={{ ["--d" as string]: "2s" }}>
        <Check x={186} y={218} />
        <text x="202" y="222" fontSize="11" fontWeight="700" fill={C.ink}>
          240 rows checked, all pass
        </text>
        <Button x={44} y={254} w={160} text="Import 240 rows" />
        <rect x="220" y="258" width="290" height="20" rx="10" fill={C.wash} />
        <text x="365" y="272" fontSize="9.5" fontWeight="700" textAnchor="middle" fill={C.tealDark}>
          Lot quantities give per-unit trends from day one
        </text>
      </g>
      <Pointer x={142} y={222} />
    </Frame>
  );
}

function FeedbackScene() {
  return (
    <Frame
      address="mdarix.com/app · Share feedback"
      label="Share feedback: rate your experience and send it in about three minutes"
    >
      <rect x="24" y="52" width="512" height="262" rx="12" fill={C.surface} stroke={C.line} />
      <text x="44" y="78" fontSize="9" fontWeight="700" fill={C.teal} letterSpacing="1">
        2 OF 5
      </text>
      <text x="44" y="98" fontSize="15" fontWeight="800" fill={C.ink}>
        Rate your experience
      </text>
      {[0, 1, 2, 3, 4].map((index) => (
        <rect
          key={index}
          x={44 + index * 40}
          y="110"
          width="34"
          height="5"
          rx="2.5"
          fill={index < 2 ? C.teal : C.line}
        />
      ))}
      {["Overall", "Ease of use", "Value for your team"].map((label, row) => (
        <g key={label}>
          <text x="44" y={150 + row * 38} fontSize="11" fontWeight="600" fill={C.ink}>
            {label}
          </text>
          {[0, 1, 2, 3, 4].map((star) => (
            <g key={star} transform={`translate(${200 + star * 24} ${146 + row * 38})`}>
              <path
                className={star < 4 + (row === 0 ? 1 : 0) ? "tg-star" : undefined}
                style={{ ["--d" as string]: `${0.2 + row * 0.5 + star * 0.12}s` }}
                d="M0 -9 L2.6 -2.9 L9 -2.8 L4 1.2 L5.7 7.6 L0 4 L-5.7 7.6 L-4 1.2 L-9 -2.8 L-2.6 -2.9 Z"
                fill={star < 4 + (row === 0 ? 1 : 0) ? C.amber : C.line}
              />
            </g>
          ))}
        </g>
      ))}
      <Button x={44} y={268} w={130} text="Send feedback" focus />
      <g className="tg-pop" style={{ ["--d" as string]: "2.4s" }}>
        <path
          d="M352 120 h160 a12 12 0 0 1 12 12 v60 a12 12 0 0 1 -12 12 h-110 l-18 18 v-18 h-32 a12 12 0 0 1 -12 -12 v-60 a12 12 0 0 1 12 -12 z"
          fill={C.wash}
        />
        <text x="432" y="152" fontSize="13" fontWeight="800" textAnchor="middle" fill={C.tealDark}>
          Thank you
        </text>
        <text x="432" y="172" fontSize="9.5" textAnchor="middle" fill={C.ink}>
          Read by the people
        </text>
        <text x="432" y="185" fontSize="9.5" textAnchor="middle" fill={C.ink}>
          who build MDARIX
        </text>
      </g>
      <Pointer x={162} y={286} />
    </Frame>
  );
}

function DemoScene() {
  const days = Array.from({ length: 21 }, (_, index) => index);
  return (
    <Frame
      address="mdarix.com/app · Getting started"
      label="Book a one-to-one demo: times that suit, the chapters to focus on, then Request the demo"
    >
      <rect x="24" y="52" width="250" height="262" rx="12" fill={C.surface} stroke={C.line} />
      <text x="44" y="78" fontSize="9" fontWeight="700" fill={C.teal} letterSpacing="1">
        ONE-TO-ONE DEMO
      </text>
      <text x="44" y="98" fontSize="14" fontWeight="800" fill={C.ink}>
        Times that suit you
      </text>
      {days.map((day) => {
        const x = 44 + (day % 7) * 30;
        const y = 114 + Math.floor(day / 7) * 30;
        const chosen = day === 9 || day === 10;
        return (
          <g key={day}>
            <rect
              x={x}
              y={y}
              width="24"
              height="24"
              rx="6"
              fill={chosen ? C.teal : C.page}
              stroke={chosen ? C.teal : C.line}
              className={chosen ? "tg-pick" : undefined}
            />
            <text x={x + 12} y={y + 16} fontSize="9.5" textAnchor="middle" fill={chosen ? "#fff" : C.muted}>
              {day + 1}
            </text>
          </g>
        );
      })}
      <Button x={44} y={226} w={210} text="Request the demo" focus />
      <text x="149" y="282" fontSize="9" textAnchor="middle" fill={C.muted}>
        Nothing is booked until we agree a time
      </text>
      <g className="tg-pop" style={{ ["--d" as string]: "1.8s" }}>
        <rect x="292" y="52" width="244" height="262" rx="12" fill={C.navy} />
        <rect x="312" y="74" width="98" height="74" rx="10" fill="#ffffff14" />
        <circle cx="361" cy="102" r="14" fill={C.wash} />
        <rect x="341" y="120" width="40" height="18" rx="9" fill={C.wash} />
        <rect x="418" y="74" width="98" height="74" rx="10" fill="#ffffff14" />
        <circle cx="467" cy="102" r="14" fill={C.teal} />
        <rect x="447" y="120" width="40" height="18" rx="9" fill={C.teal} />
        <text x="414" y="178" fontSize="13" fontWeight="800" textAnchor="middle" fill="#fff">
          Your trial, one to one
        </text>
        <text x="414" y="198" fontSize="9.5" textAnchor="middle" fill="#cbd5e1">
          What your trial found, and how a
        </text>
        <text x="414" y="211" fontSize="9.5" textAnchor="middle" fill="#cbd5e1">
          pilot on your live data would run
        </text>
        <Check x={340} y={262} />
        <text x="356" y="266" fontSize="11.5" fontWeight="700" fill="#fff">
          Demo requested
        </text>
      </g>
      <Pointer x={240} y={244} />
    </Frame>
  );
}

const SCENES: Record<JourneyKey, () => ReactNode> = {
  open: OpenScene,
  "sign-in": SignInScene,
  team: TeamScene,
  sample: SampleScene,
  "own-data": OwnDataScene,
  feedback: FeedbackScene,
  demo: DemoScene,
};

export function GuideScene({ step }: { step: JourneyKey }) {
  const Scene = SCENES[step];
  return <Scene />;
}

/** The page's hero: the whole journey as one path, drawn step by step. */
export function JourneyHero({ titles }: { titles: readonly string[] }) {
  const points = titles.map((_, index) => {
    const x = 50 + index * ((W * 1.6 - 100) / Math.max(1, titles.length - 1));
    const y = index % 2 ? 150 : 86;
    return { x, y };
  });
  const width = W * 1.6;
  const path = points.reduce(
    (d, point, index) =>
      index === 0
        ? `M${point.x} ${point.y}`
        : `${d} C ${(points[index - 1].x + point.x) / 2} ${points[index - 1].y}, ${(points[index - 1].x + point.x) / 2} ${point.y}, ${point.x} ${point.y}`,
    "",
  );
  return (
    <svg
      viewBox={`0 0 ${width} 230`}
      className="tg-journey"
      role="img"
      aria-label={`The free trial in ${titles.length} steps: ${titles.join(", ")}`}
    >
      <path d={path} fill="none" stroke="#ffffff26" strokeWidth="6" strokeLinecap="round" />
      <path
        className="tg-journey-line"
        d={path}
        fill="none"
        stroke={C.teal}
        strokeWidth="6"
        strokeLinecap="round"
        pathLength={1}
      />
      {points.map((point, index) => (
        <g key={index} className="tg-pop" style={{ ["--d" as string]: `${0.25 + index * 0.32}s` }}>
          <circle cx={point.x} cy={point.y} r="21" fill={C.teal} stroke="#0b2540" strokeWidth="5" />
          <text x={point.x} y={point.y + 6} fontSize="17" fontWeight="800" textAnchor="middle" fill="#fff">
            {index + 1}
          </text>
          <text
            x={point.x}
            y={index % 2 ? point.y + 46 : point.y - 34}
            fontSize="12.5"
            fontWeight="700"
            textAnchor="middle"
            fill="#e2e8f0"
          >
            {shortTitle(titles[index])}
          </text>
        </g>
      ))}
    </svg>
  );
}

/** A step's title in a few words for the journey hero. */
export function shortTitle(title: string): string {
  const short: Record<string, string> = {
    "Open MDARIX and request your trial": "Request",
    "Activate your account and sign in": "Sign in",
    "Invite two colleagues": "Invite 2",
    "Experience MDARIX on the sample data": "Sample data",
    "Upload your own data": "Your data",
    "Share your feedback": "Feedback",
    "Book your one-to-one demo": "Demo",
  };
  return short[title] ?? title;
}
