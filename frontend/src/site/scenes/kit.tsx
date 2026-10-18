import type { CSSProperties, ReactNode } from "react";
import { createContext, useContext, useEffect, useRef, useState } from "react";

/* Animated scenes that take the place of the website's illustrations (motion.tsx Photo). Each scene is an inline SVG
   drawn on a 640×400 canvas that fills the picture's frame (4:3, 16:10 or 16:9: the canvas is centred and the
   stage colour fills the rest). Motion starts once the scene scrolls into view (the "is-visible" class), runs once,
   with at most a gentle loop on top, and none of it runs for people who ask for reduced motion (scenes.css).

   Rules every scene follows:
   - It shows the idea of the text beside it, with synthetic, illustrative content only (the OrbitCare 300 story,
     never a real company or person), and never claims a feature the product does not have.
   - Its accessible name is the picture's alt text (role="img" on the frame); the SVG itself is hidden from assistive
     technology.
   - Text inside the SVG is short (labels, not sentences). It scales with the frame, so the stage sets a floor
     (--sc-floor, see textFloor) that keeps every label at least MIN_TEXT_PX on screen: give an inline size with
     fs(), or leave the size to scenes.css; never a bare number in a style.
   - Text keeps 4.5:1 contrast: coloured text takes the ink tokens (--sc-teal-ink…), which scenes.css applies.
   - Colours come from the tokens in scenes.css (--sc-*), so light and dark stages stay consistent.
   Motion classes (scenes.css): sc-rise, sc-pop, sc-fade (entrances), sc-draw (a stroke that draws itself: give the
   path pathLength="1"), sc-grow-x / sc-grow-y (bars), then loops: sc-flow (dashes moving along a sc-link-dashed
   path), sc-pulse, sc-ping (an expanding ring), sc-orbit (slow turn about the centre). Stagger with style={at(n)};
   a fixed offset with style={{ "--d": "1.2s" }}. Never animate an element that carries an SVG transform attribute:
   wrap it in a positioned <g transform> and animate the inner element. */

export const W = 640;
export const H = 400;

/** The smallest a scene label may render on screen, in CSS px: comfortably above 13 px, so it stays at 13 px or more
 * on a laptop the page scale (0.10.22) draws at 90%. */
export const MIN_TEXT_PX = 14.5;
/** On screen at any page scale (80% on some laptops), never below this. */
const MIN_SCALED_PX = 13;
/** The largest floor, in canvas units: what the scenes' layouts hold. */
const MAX_FLOOR = 17;
/** A phone-sized frame (under 480 px) keeps the scenes' own sizes: raising them that far would break the layouts.
 * The complex scenes open full-screen there (Enlarge). */
const SMALL_FRAME = 480;
const SMALL_FRAME_FLOOR = 13;

/** The canvas font size (in units of the 640×400 canvas) that renders at least MIN_TEXT_PX in a frame of
 * width×height CSS px drawn at page zoom `zoom` (the canvas is fitted whole, preserveAspectRatio "meet"). */
export function textFloor(width: number, height: number, zoom = 1): number {
  const scale = Math.min(width / W, height / H);
  if (!(scale > 0)) return 0;
  const floor = Math.max(MIN_TEXT_PX / scale, MIN_SCALED_PX / (scale * zoom));
  return Math.round(Math.min(width < SMALL_FRAME ? SMALL_FRAME_FLOOR : MAX_FLOOR, floor) * 10) / 10;
}

const FloorContext = createContext(0);
/** The stage's text floor in canvas units (0 before its frame is measured). */
export const useTextFloor = () => useContext(FloorContext);

/** An inline font size that never falls below the stage's floor. */
export const fs = (size: number) => `max(${size}px, var(--sc-floor, 0px))`;

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
  const [floor, setFloor] = useState(0);
  // Measure the frame, and again whenever it changes size, for the text floor.
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => {
      const zoom = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
      setFloor(textFloor(node.clientWidth, node.clientHeight, zoom));
    };
    measure();
    if (!("ResizeObserver" in window)) return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
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
    <div
      ref={ref}
      className={`sc sc-${tone} ${className}`}
      role="img"
      aria-label={label}
      style={floor ? ({ "--sc-floor": `${floor}px` } as CSSProperties) : undefined}
    >
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
        <FloorContext.Provider value={floor}>{children}</FloorContext.Provider>
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
  // Wide enough for the label at the stage's text floor (12px text before the frame is measured).
  const size = Math.max(12, useTextFloor());
  const w = Math.max(width ?? 0, 56, text.length * size * 0.6 + 22);
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
