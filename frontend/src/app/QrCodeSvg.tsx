import { qrCode } from "./qrCode";

/**
 * A QR code drawn as one SVG path (dark modules) on a white square with the standard quiet zone of four modules, so
 * phone cameras read it on any background. Renders nothing when the text is too long for a QR code here.
 */
export function QrCodeSvg({ text, size = 184, label }: { text: string; size?: number; label: string }) {
  const grid = text ? qrCode(text) : null;
  if (!grid) return null;
  const quiet = 4;
  const span = grid.length + quiet * 2;
  let path = "";
  grid.forEach((row, y) =>
    row.forEach((dark, x) => {
      if (dark) path += `M${x + quiet} ${y + quiet}h1v1h-1z`;
    }),
  );
  return (
    <svg
      className="qr-code"
      width={size}
      height={size}
      viewBox={`0 0 ${span} ${span}`}
      role="img"
      aria-label={label}
      shapeRendering="crispEdges"
    >
      <rect width={span} height={span} fill="#ffffff" />
      <path d={path} fill="#0b2540" />
    </svg>
  );
}
