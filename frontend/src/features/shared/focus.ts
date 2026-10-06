import { useEffect, useRef, type RefObject } from "react";

/**
 * Move keyboard and screen-reader focus to a page's heading when the person opens another section, so they hear
 * where they are and Tab continues from the new content instead of the navigation button they pressed. The first
 * render keeps the browser's own focus (the skip link stays first).
 */
export function useFocusOnChange(target: RefObject<HTMLElement | null>, key: unknown) {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    target.current?.focus({ preventScroll: true });
  }, [key]);
}

/** The next tab for a tab list's arrow keys, Home and End (WAI-ARIA tabs pattern); null for any other key. */
export function nextTabIndex(key: string, current: number, count: number): number | null {
  if (!count) return null;
  if (key === "ArrowRight" || key === "ArrowDown") return (current + 1) % count;
  if (key === "ArrowLeft" || key === "ArrowUp") return (current - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}
