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
const licence = read("../public/fonts/Inter-OFL.txt");
const token = (name: string): string => {
  const found = new RegExp(`--ms-${name}:\\s*(#[0-9a-f]{6})`, "i").exec(css);
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

const LIGHT_GROUNDS = ["surface", "subtle", "ground", "mint", "crit-bg", "warn-bg", "good-bg", "info-bg", "ai-bg"];
const TEXT = ["ink", "ink-2", "muted", "navy", "teal-dark", "crit", "warn", "good", "info", "ai"];
const DARK_GROUNDS = ["navy", "navy-deep", "ink"];
const TEXT_ON_DARK = ["surface", "on-dark-muted", "teal-bright", "mint"];
const FILLS = ["teal", "teal-dark", "crit", "good", "info", "ai", "navy", "muted"];
const CONTROLS = ["line-control", "teal", "warn-fill", "crit", "good", "info"];

const pairs = (fgs: string[], bgs: string[]) => fgs.flatMap((fg) => bgs.map((bg) => [fg, bg] as const));
const failing = (list: ReadonlyArray<readonly [string, string]>, minimum: number) =>
  list
    .map(([fg, bg]) => ({ fg, bg, ratio: Math.round(contrast(token(fg), token(bg)) * 100) / 100 }))
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

  it("muted text is the darker grey (V-a11y: #6b7c8b was 4.30:1)", () => {
    expect(token("muted")).toBe("#5c6d7c");
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

  it("font sizes are the six of the scale (or a fluid display size on the website)", () => {
    const sizes = new Set<string>();
    for (const path of sheets)
      for (const match of SHEETS[path].matchAll(/font-size:\s*([^;}]+)/g)) {
        const value = match[1].replace("!important", "").trim();
        if (!/^var\(--ms-fs-(12|14|16|20|24|32)\)$|clamp\(|max\(|inherit|^\d+(\.\d+)?em$|^1em$|^0$/.test(value))
          sizes.add(value);
      }
    expect([...sizes].filter((value) => !/^(4[1-9]|[5-9]\d)px$|^[0-8](\.\d+)?px$/.test(value))).toEqual([]);
  });

  it("Inter is self-hosted, with its licence", () => {
    expect(css).toContain('url("./assets/fonts/Inter-Regular.woff2")');
    expect(css).toContain("font-weight: 700");
    expect(FONTS.filter((name) => name.endsWith(".woff2")).sort()).toEqual([
      "Inter-Bold.woff2",
      "Inter-Regular.woff2",
      "Inter-SemiBold.woff2",
    ]);
    expect(licence).toContain("SIL Open Font License");
  });
});
