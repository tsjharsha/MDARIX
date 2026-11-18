import { useEffect } from "react";
import { Activity, GitCompareArrows, PenLine, Scale } from "lucide-react";

/* The website's screenshots and motion. Screenshots are the free trial's sample data, captured from the app; motion is
   CSS, SVG and the Web Animations API only, and none of it runs when the reader asks for reduced motion. */

export const SAMPLE_LABEL = "Illustrative · synthetic sample data";

/** A screen of the app, from the trial's sample data, in a browser frame. ``priority`` for the hero only (the LCP). */
export function Shot({
  src,
  alt,
  address,
  priority = false,
  className = "",
}: {
  src: string;
  alt: string;
  address: string;
  priority?: boolean;
  className?: string;
}) {
  return (
    <figure className={`ms-shot ${className}`}>
      <div className="ms-shot-frame">
        <div className="ms-shot-bar" aria-hidden="true">
          <span />
          <span />
          <span />
          <em>{address}</em>
        </div>
        <img
          src={src}
          alt={alt}
          width={1600}
          height={1000}
          decoding="async"
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : "auto"}
        />
      </div>
      <figcaption className="ms-fig-note">{SAMPLE_LABEL}</figcaption>
    </figure>
  );
}

// The free trial's sample story (backend/app/trial/sample_data.py): OrbitCare 300 Rev B moved its pressure sensor to a
// new supplier (SAMPLE-CHG-014); pressure-alarm complaints rise afterwards (4 in the 15 weeks before, 15 in the 11
// after); the investigation weighs the evidence for and against; a person signs the decision.
const FLOW = [
  { key: "signal", Icon: Activity, title: "Signal", text: "15 pressure-alarm complaints after Rev B, 4 before" },
  {
    key: "version",
    Icon: GitCompareArrows,
    title: "Product version",
    text: "Rev B: new sensor supplier, SAMPLE-CHG-014",
  },
  { key: "evidence", Icon: Scale, title: "Evidence", text: "For and against, side by side" },
  { key: "signed", Icon: PenLine, title: "Decision", text: "Signed by a person, never by AI" },
] as const;

/** The hero's story graphic: the signal pulses, flows to the product version, the evidence fills in, a signature
 * lands. Its resting state (no animation, reduced motion, no JavaScript) is the finished story. */
export function HeroStory() {
  return (
    <figure className="ms-flow" aria-labelledby="flow-title">
      <div className="ms-flow-head">
        <span id="flow-title">The sample story · OrbitCare 300</span>
        <span className="ms-flow-live" aria-hidden="true" />
      </div>
      <div className="ms-flow-body">
        <div className="ms-flow-track" aria-hidden="true">
          <span className="ms-flow-fill" />
          <span className="ms-flow-pulse" />
        </div>
        <ol>
          {FLOW.map(({ key, Icon, title, text }) => (
            <li key={key} className={`ms-flow-step is-${key}`}>
              <span className="ms-flow-icon">
                <Icon size={18} aria-hidden="true" />
              </span>
              <strong>{title}</strong>
              <small>{text}</small>
              {key === "signal" && (
                <svg className="ms-flow-spark" viewBox="0 0 100 28" aria-hidden="true">
                  <path d="M0,24 L12,22 L24,24 L36,21 L48,23 L58,14 L68,17 L78,8 L88,12 L100,3" pathLength={1} />
                </svg>
              )}
              {key === "evidence" && (
                <span className="ms-flow-bars" aria-hidden="true">
                  <i className="is-for" />
                  <i className="is-against" />
                </span>
              )}
              {key === "signed" && (
                <svg className="ms-flow-sign" viewBox="0 0 100 28" aria-hidden="true">
                  <path
                    d="M2,20 C10,4 16,4 18,16 C20,26 26,10 32,12 C38,14 36,22 44,18 C52,14 56,8 62,14"
                    pathLength={1}
                  />
                  <path className="ms-flow-tick" d="M74,14 L82,22 L98,4" pathLength={1} />
                </svg>
              )}
            </li>
          ))}
        </ol>
      </div>
      <figcaption className="ms-fig-note">{SAMPLE_LABEL}</figcaption>
    </figure>
  );
}

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** Counts a revealed number up from zero once (``data-count`` holds the shown text, such as "9.3×"). */
function countUp(element: HTMLElement) {
  const shown = element.dataset.count ?? element.textContent ?? "";
  const match = shown.match(/^(\d+(?:\.\d+)?)(.*)$/);
  if (!match) return;
  const [, number, rest] = match;
  const target = Number(number);
  const decimals = number.includes(".") ? number.split(".")[1].length : 0;
  const started = performance.now();
  const step = (now: number) => {
    const progress = Math.min(1, (now - started) / 900);
    const eased = 1 - (1 - progress) ** 3;
    element.textContent = `${(target * eased).toFixed(decimals)}${rest}`;
    if (progress < 1) requestAnimationFrame(step);
    else element.textContent = shown;
  };
  requestAnimationFrame(step);
}

/**
 * Reveals ``.ms-reveal`` blocks as they scroll into view (a short rise and fade), draws their charts and counts their
 * numbers up. Blocks already on screen are left as they are, so nothing the reader sees flickers, and without
 * JavaScript or with reduced motion every block simply shows. ``key`` re-runs it for a new page.
 */
export function useReveal(key: string) {
  useEffect(() => {
    if (reducedMotion() || !("IntersectionObserver" in window)) return;
    const blocks = [...document.querySelectorAll<HTMLElement>(".mdx-site .ms-reveal:not(.is-in)")];
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const block = entry.target as HTMLElement;
          block.classList.add("is-in");
          block.querySelectorAll<HTMLElement>("[data-count]").forEach(countUp);
          observer.unobserve(block);
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    for (const block of blocks) {
      if (block.getBoundingClientRect().top < window.innerHeight) continue;
      block.classList.add("is-waiting");
      observer.observe(block);
    }
    return () => observer.disconnect();
  }, [key]);
}
