import { useEffect, useRef, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { sceneFor } from "./scenes";
import { Enlargeable } from "./enlarge";

/** Fade/slide content in as it scrolls into view. Visible immediately when motion is reduced or unsupported. */
export function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
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
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={ref} className={`ms-reveal ${className}`} style={delay ? { transitionDelay: `${delay}ms` } : undefined}>
      {children}
    </div>
  );
}

/** A photo with a slow "living" zoom, or, where one has been drawn, the animated scene that replaces it
 * (scenes/index.ts), in the same frame, with the photo's alt text as its accessible name. */
export function Photo({
  src,
  alt,
  caption,
  className = "",
}: {
  src: string;
  alt: string;
  caption?: string;
  className?: string;
}) {
  const Scene = sceneFor(src);
  const frame = (
    <div className="ms-photo-frame">
      {Scene ? <Scene label={alt} /> : <img src={src} alt={alt} loading="lazy" decoding="async" />}
    </div>
  );
  return (
    <figure className={`ms-photo ${className}`}>
      {Scene && ENLARGEABLE.some((name) => src.endsWith(`/${name}.webp`)) ? (
        <Enlargeable
          label={alt}
          enlarged={() => (
            <div className="ms-enlarged-scene">
              <Scene label={alt} />
            </div>
          )}
        >
          {frame}
        </Enlargeable>
      ) : (
        frame
      )}
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}

// The complex scenes, which also open full-screen (Enlarge): the product reality graph and the cross-functional
// investigation. "Your QMS keeps the complaint record" (visuals.tsx SourceFlow) has the same button.
const ENLARGEABLE = ["medtech-product-reality-graph-hero", "medtech-investigation-team"];

/** Steps joined by animated connectors; a light pulse travels along the chain. */
export function FlowChain({ steps, label }: { steps: string[]; label: string }) {
  return (
    <ol className="ms-flow" aria-label={label}>
      {steps.map((step, index) => (
        <li key={step} style={{ animationDelay: `${index * 0.35}s` }}>
          <span>{step}</span>
          {index < steps.length - 1 && <ChevronRight aria-hidden="true" size={16} />}
        </li>
      ))}
    </ol>
  );
}

/**
 * Illustrative product animation for the home hero, following the free trial's sample story (OrbitCare 300 Rev B):
 * a complaint signal rises after the release, evidence is gathered,
 * competing hypotheses are weighed, unknowns stay visible, and an authorized person signs. Synthetic example data.
 */
export function InvestigationAnimation() {
  return (
    <div
      className="ms-demo"
      role="img"
      aria-label="Illustration: an investigation moving from a complaint signal to evidence, competing hypotheses and a signed human decision"
    >
      <div className="ms-demo-bar">
        <span className="ms-dot" />
        <span className="ms-dot" />
        <span className="ms-dot" />
        <strong>Investigation · OrbitCare 300 pressure alarms</strong>
        <em>Illustrative · synthetic data</em>
      </div>
      <div className="ms-demo-body">
        <section className="ms-demo-chart" aria-hidden="true">
          <header>
            <small>Complaint signal</small>
            <b>Pressure alarms per week</b>
          </header>
          <svg viewBox="0 0 320 120" preserveAspectRatio="none">
            <line x1="0" y1="110" x2="320" y2="110" className="ms-axis" />
            <line x1="170" y1="8" x2="170" y2="110" className="ms-marker" />
            <path
              className="ms-line"
              d="M0 98 L30 96 L60 99 L90 95 L120 97 L150 94 L170 92 L190 80 L210 62 L230 48 L250 40 L270 36 L290 30 L320 26"
            />
          </svg>
          {/* In HTML, not in the stretched chart, so it keeps its size and shape. */}
          <span className="ms-marker-label">Rev B released</span>
        </section>
        <section className="ms-demo-evidence" aria-hidden="true">
          <small>Evidence gathered</small>
          <ul>
            <li style={{ animationDelay: "1.2s" }}>
              <i className="tag-change" /> Supplier change · pressure sensor
            </li>
            <li style={{ animationDelay: "1.8s" }}>
              <i className="tag-lot" /> 2 lots built with the new sensor
            </li>
            <li style={{ animationDelay: "2.4s" }}>
              <i className="tag-test" /> Incoming inspection · lots 003-004
            </li>
            <li style={{ animationDelay: "3s" }}>
              <i className="tag-gap" /> 2 complaints without lot reference
            </li>
          </ul>
        </section>
        <section className="ms-demo-hypotheses" aria-hidden="true">
          <small>Competing hypotheses</small>
          <div className="ms-hyp" style={{ animationDelay: "3.6s" }}>
            <span>Pressure sensor supplier change</span>
            <span className="ms-bar">
              <i className="support" style={{ width: "64%" }} />
              <i className="contra" style={{ width: "12%" }} />
            </span>
          </div>
          <div className="ms-hyp" style={{ animationDelay: "4.1s" }}>
            <span>Firmware alarm threshold</span>
            <span className="ms-bar">
              <i className="support" style={{ width: "22%" }} />
              <i className="contra" style={{ width: "40%" }} />
            </span>
          </div>
          <p className="ms-legend">
            <i className="support" /> supports <i className="contra" /> contradicts
          </p>
        </section>
        <section className="ms-demo-decision" aria-hidden="true">
          <div>
            <small>Human decision</small>
            <b>Request additional evidence</b>
            <span>Unknowns remain · AI advisory shown separately</span>
          </div>
          <span className="ms-stamp">Signed · Quality Approver</span>
        </section>
      </div>
    </div>
  );
}
