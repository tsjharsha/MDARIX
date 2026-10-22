import { useEffect, useRef, useState } from "react";
import { compactNumber } from "./dashboardModel";

/** True when the person asked their system for less motion; every animation here then shows its end state. */
export const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;

/** Counts from the previous value to `target` (0 on first show) over `duration` ms. */
export function useCountUp(target: number | null, duration = 900) {
  const [shown, setShown] = useState<number | null>(target === null ? null : prefersReducedMotion() ? target : 0);
  const from = useRef(0);
  useEffect(() => {
    if (target === null) {
      setShown(null);
      return;
    }
    if (prefersReducedMotion()) {
      setShown(target);
      from.current = target;
      return;
    }
    const start = performance.now();
    const origin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      setShown(origin + (target - origin) * easeOutCubic(progress));
      if (progress < 1) frame = requestAnimationFrame(tick);
      else from.current = target;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return shown;
}

/** A number that counts up when it appears or changes. `suffix` (e.g. "%") is added after it. */
export function AnimatedNumber({
  value,
  suffix = "",
  compact = true,
}: {
  value: number | null;
  suffix?: string;
  compact?: boolean;
}) {
  const shown = useCountUp(value);
  if (shown === null) return <>—</>;
  const rounded = Math.round(shown);
  return (
    <>
      {/* Grouped the en-US way, "4,993", whatever the browser's language (DEV-025). */}
      {compact ? compactNumber(rounded) : rounded.toLocaleString("en-US")}
      {suffix}
    </>
  );
}
