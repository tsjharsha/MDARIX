import postcss from "postcss";
import { describe, expect, it } from "vitest";

// The page scale (styles.css) and the build step that keeps viewport lengths in step with it (postcss.config.js).
// Both are read as files: the test run does not load stylesheets, and the PostCSS config is plain JavaScript.
const config = await import(/* @vite-ignore */ new URL("../../postcss.config.js", import.meta.url).href);
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const styles: string = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8");

const transform = (css: string) => postcss([config.viewportUnitsFollowPageZoom]).process(css, { from: undefined }).css;

describe("page scale", () => {
  it("draws the page at 80% or 90% only on high-density, mouse-driven laptop widths", () => {
    const bands = [...styles.matchAll(/@media ([^{]+)\{\s*:root\s*\{\s*--page-zoom: ([\d.]+);\s*zoom: ([\d.]+);/g)];
    expect(bands.map((band) => [band[2], band[3]])).toEqual([
      ["0.8", "0.8"],
      ["0.9", "0.9"],
    ]);
    for (const [, query] of bands) {
      expect(query).toContain("(pointer: fine)");
      expect(query).toContain("(min-resolution: 1.25dppx)");
    }
    expect(bands[0][1]).toContain("(min-width: 1100px) and (max-width: 1439.98px)");
    expect(bands[1][1]).toContain("(min-width: 1440px) and (max-width: 1799.98px)");
  });

  it("divides viewport lengths by the page scale so full-height panels still fill the window", () => {
    expect(transform(".a { min-height: 100vh; }")).toBe(".a { min-height: calc(100vh / var(--page-zoom, 1)); }");
    expect(transform(".a { max-height: calc(100dvh - 32px); }")).toBe(
      ".a { max-height: calc(calc(100dvh / var(--page-zoom, 1)) - 32px); }",
    );
    expect(transform(".a { margin: 0 -6vw; font-size: clamp(30px, 4.5vw, 52px); }")).toBe(
      ".a { margin: 0 calc(-6vw / var(--page-zoom, 1)); font-size: clamp(30px, calc(4.5vw / var(--page-zoom, 1)), 52px); }",
    );
  });

  it("leaves everything else alone", () => {
    for (const css of [
      ".a { width: 240px; color: #10vw0a; }",
      ":root { --page-zoom: 0.8; zoom: 0.8; }",
      "@media (min-width: 50vw) { .a { color: red; } }",
    ])
      expect(transform(css)).toBe(css);
  });
});
