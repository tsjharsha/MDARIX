import { useArtId } from "./HeroVisuals";

/*
 * The hero design's illustrations (0.10.90, drawn for MDARIX in the approved mock-up): the bedside scene, a patient
 * monitor, an infusion pump and the signed-record seal. Line art in the band's own colours; the ECG trace moves only
 * when the reader allows motion (hero.css).
 */

const NIGHT = "#0a1830";
const PATIENT = "#13284a";
const AMBER = "#f6b443";
const GLOW = "#3fe0d6";
const MONO = "IBM Plex Mono, monospace";

function Glow({ id }: { id: string }) {
  return (
    <defs>
      <radialGradient id={id} cx="50%" cy="50%" r="60%">
        <stop offset="0" stopColor={GLOW} stopOpacity=".35" />
        <stop offset="1" stopColor={GLOW} stopOpacity="0" />
      </radialGradient>
    </defs>
  );
}

/** A hospital bedside: the patient monitor, an infusion pump, a respiratory controller and a signed record. */
export function BedsideScene({ className }: { className?: string }) {
  const glow = useArtId("hx-scene-glow");
  const s = { stroke: "currentColor", strokeLinecap: "round" as const };
  return (
    <svg
      className={`hx-art hx-scene${className ? ` ${className}` : ""}`}
      viewBox="0 0 600 320"
      role="img"
      aria-label="Illustration: a hospital bedside with a patient monitor, an infusion pump and a respiratory controller"
    >
      <Glow id={glow} />
      <ellipse cx="300" cy="292" rx="290" ry="16" className="hx-art-soft" />
      {/* Wall monitor */}
      <circle cx="140" cy="88" r="92" fill={`url(#${glow})`} />
      <path d="M150 18v18" {...s} strokeWidth="3" />
      <rect x="66" y="36" width="168" height="108" rx="14" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <rect x="78" y="48" width="144" height="84" rx="6" className="hx-art-screen" />
      <path
        className="hx-ecg"
        d="M84 72h22l5-13 7 26 6-19 4 6h16l5-13 7 26 6-19 4 6h16l5-13 7 26 6-19 4 6h12"
        fill="none"
        stroke={GLOW}
        strokeWidth="2.4"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <path
        d="M84 108c8-14 14-14 20 0s14 14 20 0 14-14 20 0 14 14 20 0 14-14 20 0"
        fill="none"
        stroke={AMBER}
        strokeWidth="2"
        strokeLinecap="round"
        opacity=".9"
      />
      <rect x="190" y="98" width="26" height="26" rx="4" fill="rgba(63,224,214,.14)" />
      <text x="203" y="115" textAnchor="middle" fontFamily={MONO} fontSize="9" fontWeight="600" fill={GLOW}>
        SpO2
      </text>
      <path d="M120 144c0 40 60 52 132 54" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="3 4" />
      {/* Respiratory controller on its cart */}
      <rect x="34" y="196" width="96" height="72" rx="10" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <circle cx="62" cy="230" r="14" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path d="M62 230l7-7" stroke={GLOW} strokeWidth="2.4" strokeLinecap="round" />
      <rect x="88" y="214" width="30" height="16" rx="3" fill="rgba(63,224,214,.18)" />
      <path d="M88 242h30" {...s} strokeWidth="2" />
      <circle cx="50" cy="278" r="6" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <circle cx="114" cy="278" r="6" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path d="M130 214c40-10 70-6 96-6" fill="none" {...s} strokeWidth="3" strokeDasharray="5 4" />
      {/* Bed */}
      <rect x="176" y="168" width="14" height="110" rx="5" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <rect x="458" y="196" width="12" height="82" rx="5" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <rect x="186" y="214" width="280" height="22" rx="11" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <path d="M200 236v36M452 236v36" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="200" cy="280" r="6" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <circle cx="452" cy="280" r="6" fill="none" stroke="currentColor" strokeWidth="2.2" />
      {/* Patient */}
      <ellipse cx="232" cy="206" rx="34" ry="11" fill={PATIENT} stroke="currentColor" strokeWidth="2" />
      <circle cx="240" cy="190" r="15" fill={PATIENT} stroke="currentColor" strokeWidth="2.2" />
      <path
        d="M258 214c18-26 74-28 104-22 34 6 70 6 96 22z"
        fill="rgba(63,224,214,.13)"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <circle cx="312" cy="200" r="4" fill={GLOW} />
      {/* IV pole and pump */}
      <path d="M520 30v248M500 278h40" {...s} strokeWidth="2.5" />
      <path d="M506 34h28" {...s} strokeWidth="2.5" />
      <rect
        x="504"
        y="40"
        width="32"
        height="46"
        rx="10"
        fill="rgba(140,190,255,.12)"
        stroke="currentColor"
        strokeWidth="2.2"
      />
      <path d="M510 66h20" stroke="currentColor" strokeWidth="1.6" opacity=".6" />
      <path d="M520 86v26" stroke="currentColor" strokeWidth="2" />
      <rect x="494" y="112" width="52" height="66" rx="8" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <rect x="502" y="120" width="36" height="18" rx="3" className="hx-art-screen" />
      <path d="M506 129h28" stroke={GLOW} strokeWidth="2" strokeLinecap="round" />
      <circle cx="510" cy="152" r="3.5" fill="currentColor" />
      <circle cx="530" cy="152" r="3.5" fill="currentColor" />
      <rect x="506" y="162" width="28" height="7" rx="3.5" fill={AMBER} opacity=".8" />
      <path d="M520 178c0 30-40 34-110 30" fill="none" stroke="currentColor" strokeWidth="1.8" />
      {/* A signed record */}
      <g transform="translate(330 28)">
        <rect
          width="132"
          height="96"
          rx="12"
          fill="rgba(255,255,255,.06)"
          stroke="rgba(160,190,230,.3)"
          strokeWidth="1.5"
        />
        <rect x="14" y="16" width="56" height="8" rx="4" fill="currentColor" opacity=".55" />
        <rect x="14" y="32" width="104" height="6" rx="3" fill="currentColor" opacity=".25" />
        <rect x="14" y="44" width="88" height="6" rx="3" fill="currentColor" opacity=".25" />
        <path
          d="M16 74c5-8 9-9 10-4s-2 9 2 8 6-12 10-10 0 9 4 9 6-5 9-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="104" cy="72" r="14" fill={NIGHT} stroke={GLOW} strokeWidth="2" />
        <path
          d="m97 72 5 5 9-9"
          fill="none"
          stroke={GLOW}
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}

/** A patient monitor with its ECG and SpO2 traces. */
export function PatientMonitorArt({ className }: { className?: string }) {
  const glow = useArtId("hx-monitor-glow");
  return (
    <svg
      className={`hx-art hx-device-art${className ? ` ${className}` : ""}`}
      viewBox="0 0 180 200"
      role="img"
      aria-label="Illustration: a patient monitor"
    >
      <Glow id={glow} />
      <circle cx="90" cy="80" r="80" fill={`url(#${glow})`} />
      <rect x="14" y="20" width="152" height="112" rx="16" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <rect x="26" y="32" width="128" height="88" rx="6" className="hx-art-screen" />
      <path
        className="hx-ecg"
        d="M32 60h16l4-11 6 22 5-16 4 5h14l4-11 6 22 5-16 4 5h14l4-11 6 22 5-16 3 5"
        fill="none"
        stroke={GLOW}
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M32 98c7-12 12-12 18 0s12 12 18 0 12-12 18 0 12 12 18 0"
        fill="none"
        stroke={AMBER}
        strokeWidth="2"
        strokeLinecap="round"
      />
      <rect x="112" y="84" width="34" height="28" rx="4" fill="rgba(246,180,67,.16)" />
      <text x="129" y="102" textAnchor="middle" fontFamily={MONO} fontSize="10" fontWeight="600" fill={AMBER}>
        SpO2
      </text>
      <path d="M90 132v34M58 170h64" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <path
        d="M150 140c18 10 20 30 6 44-8 8-22 6-24-2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeDasharray="3 4"
      />
      <rect x="118" y="176" width="22" height="14" rx="7" fill={PATIENT} stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

/** An infusion pump on its pole, with its bag and line. */
export function InfusionPumpArt({ className }: { className?: string }) {
  const glow = useArtId("hx-pump-glow");
  return (
    <svg
      className={`hx-art hx-device-art${className ? ` ${className}` : ""}`}
      viewBox="0 0 180 200"
      role="img"
      aria-label="Illustration: an infusion pump"
    >
      <Glow id={glow} />
      <circle cx="96" cy="100" r="80" fill={`url(#${glow})`} />
      <path d="M40 14v176M18 190h44M26 18h28" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
      <rect
        x="26"
        y="24"
        width="28"
        height="42"
        rx="9"
        fill="rgba(140,190,255,.12)"
        stroke="currentColor"
        strokeWidth="2.2"
      />
      <path d="M32 48h16" stroke="currentColor" strokeWidth="1.6" opacity=".6" />
      <path d="M40 66v18c0 8 6 12 14 12h14" fill="none" stroke="currentColor" strokeWidth="2" />
      <rect x="68" y="70" width="98" height="92" rx="14" fill={NIGHT} stroke="currentColor" strokeWidth="2.5" />
      <rect x="80" y="82" width="74" height="30" rx="5" className="hx-art-screen" />
      <path
        className="hx-ecg"
        d="M86 98h12l4-8 6 14 4-8h36"
        fill="none"
        stroke={GLOW}
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M84 126h14M84 140h14M108 126h14M108 140h14"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <rect x="134" y="122" width="20" height="24" rx="4" fill={AMBER} opacity=".8" />
      <path d="M84 162v12M150 162v12" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

/** A signed record with its seal: the person's signature, kept. */
export function SignedSeal({ size = 76, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={`hx-seal${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 96 96"
      role="img"
      aria-label="Illustration: a signed record with its seal"
    >
      <rect x="14" y="8" width="54" height="70" rx="7" fill="currentColor" opacity=".08" />
      <rect x="14" y="8" width="54" height="70" rx="7" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <path
        d="M24 22h34M24 31h34M24 40h22"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        opacity=".55"
      />
      <path
        d="M23 60c4-6 7-7 8-3s-2 7 1 6 5-9 8-8 0 7 3 7 5-4 7-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M66 82l-4 12 8-4 8 4-4-12" fill="currentColor" opacity=".5" />
      <circle cx="70" cy="70" r="16" fill="var(--ms-surface)" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="70" cy="70" r="11" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2 2.5" />
      <path
        d="m64 70 4.5 4.5L77 66"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
