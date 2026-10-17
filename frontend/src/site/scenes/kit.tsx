import type { CSSProperties, ReactNode } from "react";
import { useEffect, useRef } from "react";

/* Animated scenes that take the place of the website's illustrations (motion.tsx Photo). Each scene is an inline SVG
   drawn on a 640×400 canvas that fills the picture's frame (4:3, 16:10 or 16:9: the canvas is centred and the
   stage colour fills the rest). Motion starts once the scene scrolls into view (the "is-visible" class), runs once,
   with at most a gentle loop on top, and none of it runs for people who ask for reduced motion (scenes.css).

   Rules every scene follows:
   - It shows the idea of the text beside it, with synthetic, illustrative content only (the OrbitCare 300 story,
     never a real company or person), and never claims a feature the product does not have.
   - Its accessible name is the picture's alt text (role="img" on the frame); the SVG itself is hidden from assistive
     technology.
   - Text inside the SVG is short (labels, not sentences), at least 11px on the canvas.
   - Colours come from the tokens in scenes.css (--sc-*), so light and dark stages stay consistent.
   Motion classes (scenes.css): sc-rise, sc-pop, sc-fade (entrances), sc-draw (a stroke that draws itself: give the
   path pathLength="1"), sc-grow-x / sc-grow-y (bars), then loops: sc-flow (dashes moving along a sc-link-dashed
   path), sc-pulse, sc-ping (an expanding ring), sc-orbit (slow turn about the centre). Stagger with style={at(n)};
   a fixed offset with style={{ "--d": "1.2s" }}. Never animate an element that carries an SVG transform attribute:
   wrap it in a positioned <g transform> and animate the inner element. */

export const W = 640;
export const H = 400;

/** The stage a scene is drawn on: "dark" (navy, for page heroes) or "light" (white glass, for section pictures). */
export function Scene({
  label,
  tone = "light",
  children,
  className = "",
}: {
  label: string;
  tone?: "light" | "dark";
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || !("IntersectionObserver" in window)) {
      node.classList.add("is-visible");
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
      },
      { threshold: 0.25 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={ref} className={`sc sc-${tone} ${className}`} role="img" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
        {children}
      </svg>
    </div>
  );
}

/** Animation timing for a child: its stagger index (scenes.css multiplies it) and an optional fixed offset. */
export const at = (index: number, offset?: string) =>
  ({ "--i": index, ...(offset ? { "--d": offset } : {}) }) as CSSProperties;

/** A rounded label chip: a pill with centred text. */
export function Chip({
  x,
  y,
  text,
  width,
  tone = "base",
  index = 0,
  className = "",
}: {
  x: number;
  y: number;
  text: string;
  width?: number;
  tone?: "base" | "teal" | "amber" | "red" | "muted";
  index?: number;
  className?: string;
}) {
  const w = width ?? Math.max(56, text.length * 7 + 22);
  return (
    // The position is on the outer group; the motion on the inner one (a CSS transform replaces an SVG transform).
    <g transform={`translate(${x} ${y})`}>
      <g className={`sc-chip sc-chip-${tone} sc-pop ${className}`} style={at(index)}>
        <rect x={-w / 2} y={-13} width={w} height={26} rx={13} />
        <text textAnchor="middle" dy="4.5">
          {text}
        </text>
      </g>
    </g>
  );
}

/** A small card: rounded panel with an optional title line. */
export function Card({
  x,
  y,
  w,
  h,
  title,
  index = 0,
  delay,
  className = "",
  children,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  title?: string;
  index?: number;
  /** A fixed start offset added to the stagger, e.g. "1.2s". */
  delay?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <g className={`sc-card sc-rise ${className}`} style={at(index, delay)}>
        <rect width={w} height={h} rx={12} />
        {title && (
          <text className="sc-card-title" x={14} y={22}>
            {title}
          </text>
        )}
        {children}
      </g>
    </g>
  );
}

/** The "Illustrative" corner tag every scene that shows data carries. */
export function Illustrative({ x = W - 14, y = H - 12 }: { x?: number; y?: number }) {
  return (
    <text className="sc-note" x={x} y={y} textAnchor="end">
      Illustrative
    </text>
  );
}
