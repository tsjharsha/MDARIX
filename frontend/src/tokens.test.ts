import { describe, expect, it } from "vitest";

// The design tokens (tokens.css) and the WCAG 2.1 AA contrast of every text and control colour pair they allow. Read as
// files: the test run does not load stylesheets.
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const read = (path: string): string => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const css = read("./tokens.css");
const SHEETS: Record<string, string> = Object.fromEntries(
  (fs.readdirSync(new URL("./", import.meta.url), { recursive: true }) as string[])
    .map((path) => path.split("\\").join("/"))
    .filter((path) => path.endsWith(".css") && path !== "tokens.css" && path !== "base.css")
    .map((path) => [path, read(`./${path}`)]),
);
const FONTS: string[] = fs.readdirSync(new URL("./assets/fonts/", import.meta.url));
const licence = (name: string): string => read(`../public/fonts/${name}-OFL.txt`);
// The light theme's tokens (the :root block); the dark theme's are the block switched off in 0.10.90.
const darkCss = css.slice(css.indexOf(':root[data-theme="dark"] {'));
const lightCss = css.slice(0, css.indexOf(':root[data-theme="dark"] {'));
const token = (name: string, sheet = lightCss): string => {
  const found = new RegExp(`--ms-${name}:\\s*(#[0-9a-f]{6})`, "i").exec(sheet);
  if (!found) throw new Error(`no colour token --ms-${name}`);
  return found[1];
};

const luminance = (hex: string) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const f = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const LIGHT_GROUNDS = [
  "surface",
  "subtle",
  "ground",
  "mint",
  "crit-bg",
  "warn-bg",
  "good-bg",
  "info-bg",
  "ai-bg",
  "harm-bg",
];
const TEXT = ["ink", "ink-2", "muted", "navy", "teal", "teal-dark", "crit", "warn", "good", "info", "ai", "harm"];
const DARK_GROUNDS = ["navy", "navy-deep", "ink", "rail", "rail-2", "hero", "hero-2"];
const TEXT_ON_DARK = [
  "surface",
  "on-dark-muted",
  "teal-bright",
  "mint",
  "rail-fg",
  "rail-muted",
  "hero-fg",
  "hero-muted",
  "glow",
];
const FILLS = ["teal", "teal-dark", "crit", "good", "info", "ai", "navy", "muted", "harm"];
const CONTROLS = ["line-control", "teal", "warn-fill", "crit", "good", "info", "series"];

const pairs = (fgs: string[], bgs: string[]) => fgs.flatMap((fg) => bgs.map((bg) => [fg, bg] as const));
const failing = (list: ReadonlyArray<readonly [string, string]>, minimum: number, sheet = lightCss) =>
  list
    .map(([fg, bg]) => ({ fg, bg, ratio: Math.round(contrast(token(fg, sheet), token(bg, sheet)) * 100) / 100 }))
    .filter((pair) => pair.ratio < minimum);

describe("design tokens meet WCAG 2.1 AA", () => {
  it("computes contrast as WCAG does", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#6b7c8b", "#ffffff")).toBeCloseTo(4.3, 1); // the old muted grey failed
  });

  it("text on every light ground is at least 4.5:1", () => {
    expect(failing(pairs(TEXT, LIGHT_GROUNDS), 4.5)).toEqual([]);
  });

  it("text on the dark grounds (the app bar, the website's navy bands) is at least 4.5:1", () => {
    expect(failing(pairs(TEXT_ON_DARK, DARK_GROUNDS), 4.5)).toEqual([]);
  });

  it("white text on every button and chip fill is at least 4.5:1", () => {
    expect(failing(pairs(["surface"], FILLS), 4.5)).toEqual([]);
  });

  it("control edges and chart marks are at least 3:1 against the light grounds", () => {
    expect(failing(pairs(CONTROLS, ["surface", "subtle", "ground", "mint"]), 3)).toEqual([]);
  });

  it("muted text is the darker grey (V-a11y: #6b7c8b was 4.30:1; 0.10.90 the hero design's, darker still)", () => {
    expect(token("muted")).toBe("#56647b");
    expect(contrast(token("muted"), "#ffffff")).toBeGreaterThan(contrast("#5c6d7c", "#ffffff"));
  });

  it("the white text and the rail's own text on the dark rail and monitor band are at least 4.5:1", () => {
    expect(failing(pairs(["rail-fg", "rail-muted", "glow"], ["rail", "rail-2"]), 4.5)).toEqual([]);
    expect(
      failing(pairs(["hero-fg", "hero-muted", "glow", "h-crit", "h-warn", "h-good"], ["hero", "hero-2"]), 4.5),
    ).toEqual([]);
  });
});

describe("the dark theme (0.10.91)", () => {
  const sources = (fs.readdirSync(new URL("./", import.meta.url), { recursive: true }) as string[])
    .map((path) => path.split("\\").join("/"))
    .filter((path) => /\.(tsx?|css|html)$/.test(path) && !path.endsWith(".test.ts") && !path.endsWith(".test.tsx"));

  it("gives each text 4.5:1 or more on each dark ground, each state's text on its own ground", () => {
    expect(darkCss).toContain("--ms-surface: #0f1a2d");
    const text = ["ink", "ink-2", "muted", "navy", "teal", "teal-dark", "crit", "warn", "good", "info", "ai", "harm"];
    expect(failing(pairs(text, ["surface", "subtle", "ground"]), 4.5, darkCss)).toEqual([]);
    const own: Array<[string, string]> = [
      ["crit", "crit-bg"],
      ["warn", "warn-bg"],
      ["good", "good-bg"],
      ["info", "info-bg"],
      ["ai", "ai-bg"],
      ["harm", "harm-bg"],
      ["teal-dark", "mint"],
      ["ink", "mint"],
    ];
    expect(failing(own, 4.5, darkCss)).toEqual([]);
  });

  it("turns each fill under white text light, with the dark ground as its text, at 4.5:1 or more", () => {
    const fills = ["teal", "teal-dark", "crit", "good", "info", "ai", "harm", "muted", "warn-fill"];
    expect(failing(pairs(["surface"], fills), 4.5, darkCss)).toEqual([]);
  });

  it("keeps the light set on the panels that are navy in both themes, so their text never turns dark on dark", () => {
    // The quality loop on Records, the monthly trend on Import, the pilot band on Next steps, Home's side panel.
    expect(lightCss).toMatch(
      /:root,\s*:root\[data-theme="dark"\] :is\(\.ql-hero, \.uw-ins-hero, \.uw-ns-talk, \.uw-home-hero-side\) \{/,
    );
  });

  it("gives the amber dots' dark ink 4.5:1 on the amber mark in both themes", () => {
    for (const sheet of [lightCss, darkCss])
      expect(contrast(token("glow-ink", lightCss), token("warn-mark", sheet))).toBeGreaterThan(4.5);
  });

  it("keeps white white on the grounds that stay dark: the rail, the band and the navy fill", () => {
    expect(token("white")).toBe("#ffffff");
    for (const ground of ["rail", "rail-2", "hero", "hero-2", "navy-fill"])
      expect(contrast("#ffffff", token(ground, darkCss)), ground).toBeGreaterThan(4.5);
    expect(failing(pairs(["line-control", "teal-mark", "crit-mark", "good-mark"], ["surface"]), 3, darkCss)).toEqual(
      [],
    );
  });

  it("is switched on only by the new navigation's shell: no colour-scheme query, one module sets data-theme", () => {
    // The website and the classic navigation stay light: the system's setting is read in theme.tsx, not in CSS.
    expect(css).not.toMatch(/@media[^{]*prefers-color-scheme/);
    const setters = sources.filter(
      (path) => /data-theme|dataset\.theme/.test(read(`./${path}`)) && !["tokens.css"].includes(path),
    );
    expect(setters).toEqual(["features/workspace/theme.tsx"]);
  });
});

describe("one token file", () => {
  const sheets = Object.keys(SHEETS);
  expect(sheets.length).toBeGreaterThan(15);

  it("no other style sheet defines colours at :root or redefines a --ms- token", () => {
    const offenders = sheets.filter((path) => {
      const text = SHEETS[path];
      return (
        /--ms-[\w-]+\s*:/.test(text.replace(/--ms-(focus|max)\s*:/g, "")) || /:root\s*\{[^}]*#[0-9a-f]{3,6}/i.test(text)
      );
    });
    expect(offenders).toEqual([]);
  });

  it("font sizes are those of the scale (or a fluid display size on the website)", () => {
    const sizes = new Set<string>();
    for (const path of sheets)
      for (const match of SHEETS[path].matchAll(/font-size:\s*([^;}]+)/g)) {
        const value = match[1].replace("!important", "").trim();
        if (
          !/^var\(--ms-fs-(12|13|14|16|20|24|26|32|34|48|64)\)$|clamp\(|max\(|inherit|^\d+(\.\d+)?em$|^1em$|^0$/.test(
            value,
          )
        )
          sizes.add(value);
      }
    expect([...sizes].filter((value) => !/^(4[1-9]|[5-9]\d)px$|^[0-8](\.\d+)?px$/.test(value))).toEqual([]);
  });

  it("Inter, Archivo and IBM Plex Mono are self-hosted, each with its licence, and no font comes from elsewhere", () => {
    expect(css).toContain('url("./assets/fonts/Inter-Regular.woff2")');
    expect(css).toContain("font-weight: 700");
    expect(FONTS.filter((name) => name.endsWith(".woff2")).sort()).toEqual([
      "Archivo-Latin.woff2",
      "Archivo-LatinExt.woff2",
      "IBMPlexMono-Medium.woff2",
      "IBMPlexMono-Regular.woff2",
      "IBMPlexMono-SemiBold.woff2",
      "Inter-Bold.woff2",
      "Inter-Regular.woff2",
      "Inter-SemiBold.woff2",
    ]);
    for (const file of FONTS.filter((name) => name.endsWith(".woff2")))
      expect(css, file).toContain(`url("./assets/fonts/${file}")`);
    expect(css).toContain("font-stretch: 100% 125%");
    for (const name of ["Inter", "Archivo", "IBMPlexMono"])
      expect(licence(name), name).toContain("SIL Open Font License");
    const index = read("../index.html");
    expect(index + css + Object.values(SHEETS).join("")).not.toMatch(/fonts\.(googleapis|gstatic)\.com/);
  });
});
