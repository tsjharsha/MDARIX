// The application's look for 0.11.07 (owner, 19 Nov 2026): the rail tells the story, figures count up once (never with
// reduced motion), and the canvas is centred and fluid to 1680 px. The layout itself is measured in the browser
// (e2e/app-wide-layout.spec.ts).
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NavRail, TAB_STORY } from "./HybridShell";
import { CountUp } from "./UserWorkspace";

const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const css: string = fs.readFileSync(new URL("./appLook.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");
const caseHeader: string = fs.readFileSync(new URL("./sections/CaseHeader.tsx", import.meta.url), "utf8");
const tokens: string = fs.readFileSync(new URL("../../tokens.css", import.meta.url), "utf8");
const appSet = tokens.slice(tokens.indexOf(':root:not([data-theme="dark"]):has(.uw-hybrid) {'));
const colour = (name: string) => new RegExp(`--ms-${name}:\\s*(#[0-9a-f]{6})`, "i").exec(appSet)![1];
const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const f = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

describe("the story rail", () => {
  it("names each work area as before and adds what happens there, hidden from screen readers", () => {
    const rail = renderToStaticMarkup(
      <NavRail
        tabs={["home", "complaints", "investigations", "products", "decisions"]}
        current="complaints"
        open={vi.fn()}
      />,
    );
    const labels = [...rail.matchAll(/<span class="uw-tab-label">([^<]*)<\/span>/g)].map((match) => match[1]);
    expect(labels).toEqual(["Today", "Cases", "Investigations", "Products", "Decisions &amp; Reports"]);
    for (const story of Object.values(TAB_STORY))
      expect(rail).toContain(`<small class="uw-tab-sub" aria-hidden="true">${story.replace("&", "&amp;")}</small>`);
  });
});

describe("the application's palette", () => {
  it("keeps WCAG AA for its text on its grounds, and white text on its brand fill", () => {
    for (const text of ["teal", "teal-dark", "navy"])
      for (const ground of ["ground", "subtle", "mint"])
        expect(contrast(colour(text), colour(ground)), `${text} on ${ground}`).toBeGreaterThanOrEqual(4.5);
    expect(contrast(colour("teal"), "#ffffff")).toBeGreaterThanOrEqual(4.5);
    for (const ground of ["rail", "rail-2", "hero", "hero-2"]) {
      expect(contrast("#d2dcea", colour(ground)), `rail text on ${ground}`).toBeGreaterThanOrEqual(4.5);
      expect(contrast("#8d9cb3", colour(ground)), `muted rail text on ${ground}`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(colour("glow"), colour(ground)), `glow on ${ground}`).toBeGreaterThanOrEqual(4.5);
    }
    // The hero band's teal end: the band's muted text (on-dark-muted) stays readable there.
    expect(contrast("#c5d3df", "#0b5560")).toBeGreaterThanOrEqual(4.5);
  });
});

describe("one hero per screen", () => {
  it("hides the page band from sight while an investigation's own header is on screen, never from screen readers", () => {
    expect(caseHeader).toContain(
      'className="uw-card uw-highlights uw-inv-head" aria-label="The investigation at a glance"',
    );
    const rule = /\.uw-hybrid \.ac-main:has\(\.uw-inv-head\) > \.ac-page-head \{([^}]*)\}/.exec(css);
    expect(rule?.[1]).toContain("clip-path: inset(50%)");
    expect(rule?.[1]).not.toMatch(/display: none|visibility: hidden/);
  });
});

describe("figures that count up", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("start from 0 and count up", () => {
    vi.stubGlobal("window", { matchMedia: () => ({ matches: false }) });
    expect(renderToStaticMarkup(<CountUp value={7} />)).toBe("0");
  });

  it("show the value at once with reduced motion", () => {
    vi.stubGlobal("window", { matchMedia: () => ({ matches: true }) });
    expect(renderToStaticMarkup(<CountUp value={7} />)).toBe("7");
  });
});

describe("the canvas and the motion", () => {
  it("centres the work canvas, fluid to 1680 px, instead of pinning it left at 1340 px", () => {
    expect(css).toMatch(/\.uw-hybrid \.ac-main \{\s*width: 100%;\s*max-width: 1680px;\s*margin-inline: auto;/);
  });

  it("moves only without a reduced-motion preference", () => {
    const motion = css.slice(css.indexOf("@media (prefers-reduced-motion: no-preference)"));
    expect(motion).toContain("animation: uw-rise");
    expect(css.slice(0, css.indexOf("@media (prefers-reduced-motion: no-preference)"))).not.toMatch(/animation:/);
    expect(css).not.toContain("infinite");
  });
});
