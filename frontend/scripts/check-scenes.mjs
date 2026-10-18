// Checks the website's animated scenes (src/site/scenes) for labels that do not fit: SVG text overlapping other
// text, running past the edge of the card or pill it sits in, crowding a pill it does not belong to, or leaving the
// scene. Every page with a scene is opened at six views: the laptops the page scale (styles.css) draws at 80% and 90%,
// two desktops, and a narrow window where the text floor reaches its cap (scenes/kit.tsx MAX_FLOOR); every Enlarge
// view is opened too. It needs a running site, e.g. the production bundle:
//
//   npm run build && npx vite preview --port 4173      (in another terminal)
//   npm run check:scenes -- [<base-url> [<view>,… [<page>,…]]]   (default http://127.0.0.1:4173, every view and page)
//
// The pages load /api/v1/public/* (site info, testimonials); without an API those parts stay empty, which does not
// change the scenes. Exits 1 when anything is found. Uses the machine's Chrome (PLAYWRIGHT_CHANNEL overrides it).
// It measures boxes, so it cannot judge looks: also look at the scenes after changing one.
import { chromium } from "@playwright/test";

const [baseArg, viewsArg, pagesArg] = process.argv.slice(2);
const BASE = (baseArg || "http://127.0.0.1:4173").replace(/\/$/, "");
const ALL_PAGES = [
  "/",
  "/platform",
  "/platform/product-360",
  "/platform/investigations",
  "/platform/decisions",
  "/platform/trust",
  "/roadmap",
  "/solutions",
  "/product-lifecycle",
  "/trust",
  "/trust/regulations",
  "/resources",
  "/company",
  "/videos",
  "/signup",
  "/signin",
];
const ALL_VIEWS = [
  // 1,280 CSS px at 150% display scaling: the page scale draws at 80%.
  { name: "laptop-1280@1.5", viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 },
  { name: "laptop-1366@1.25", viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1.25 },
  // 1,536 CSS px at 125%: drawn at 90%.
  { name: "laptop-1536@1.25", viewport: { width: 1536, height: 864 }, deviceScaleFactor: 1.25 },
  { name: "1440", viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
  { name: "1920", viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 },
  // A narrow window: frames about 490 px wide, where the floor reaches its largest (kit.tsx MAX_FLOOR).
  { name: "narrow-540", viewport: { width: 540, height: 900 }, deviceScaleFactor: 1 },
];

const PAGES = pagesArg ? pagesArg.split(",") : ALL_PAGES;
const VIEWS = viewsArg ? ALL_VIEWS.filter((view) => viewsArg.split(",").includes(view.name)) : ALL_VIEWS;

/** Runs in the page: the problems in every scene inside `root`. Distances are on-screen CSS px. */
function scanScenes(root) {
  const out = [];
  for (const svg of root.querySelectorAll(".sc svg")) {
    const scene = svg.closest("[role=img]")?.getAttribute("aria-label")?.slice(0, 60) || "?";
    const found = [];
    const texts = [...svg.querySelectorAll("text")]
      .filter((t) => t.textContent.trim() && t.getBoundingClientRect().width > 0)
      .map((el) => ({ el, t: el.textContent.trim().slice(0, 40), r: el.getBoundingClientRect() }));
    const rects = [...svg.querySelectorAll("rect")]
      .map((el) => {
        const r = el.getBoundingClientRect();
        // A pill: a chip (kit.tsx Chip), or any rect rounded to half its height.
        const pill =
          el.closest(".sc-chip") !== null || Number(el.getAttribute("rx")) * 2 >= el.height.baseVal.value - 1;
        return { el, r, pill };
      })
      .filter(({ r }) => r.width > 20 && r.height > 12);
    const vOverlap = (a, b) => Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    // Text overlapping text.
    for (let i = 0; i < texts.length; i++)
      for (let j = i + 1; j < texts.length; j++) {
        const a = texts[i].r;
        const b = texts[j].r;
        const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        if (w > 2 && vOverlap(a, b) > Math.min(a.height, b.height) * 0.35)
          found.push(`overlap: "${texts[i].t}" × "${texts[j].t}" (${Math.round(w)}px)`);
      }
    for (const { t, r } of texts) {
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      // A box holds the text when the text's centre is well inside it (a badge on a card's border sits in neither).
      const holds = (q) => cx >= q.left + 4 && cx <= q.right - 4 && cy >= q.top && cy <= q.bottom;
      // The smallest card or pill the text sits in: the text stays inside it.
      const box = rects
        .filter(({ r: q }) => holds(q))
        .sort((m, n) => m.r.width * m.r.height - n.r.width * n.r.height)[0];
      if (box) {
        const over = Math.max(r.right - box.r.right, box.r.left - r.left);
        if (over > 1.5) found.push(`past edge: "${t}" by ${Math.round(over)}px`);
        // A label in a pill keeps clear of its ends.
        else if (box.pill && over > -2) found.push(`tight in pill: "${t}"`);
      }
      // A pill the text does not sit in keeps at least 3 px from it.
      for (const p of rects) {
        if (!p.pill || holds(p.r)) continue;
        const gap = Math.max(p.r.left - r.right, r.left - p.r.right);
        if (gap < 3 && vOverlap(r, p.r) > r.height * 0.35)
          found.push(`crowds pill: "${t}" × "${p.el.parentElement.textContent.trim().slice(0, 30)}"`);
      }
      const s = svg.getBoundingClientRect();
      if (r.right > s.right + 1 || r.left < s.left - 1) found.push(`outside scene: "${t}"`);
    }
    if (found.length) out.push(`[${scene}]`, ...new Set(found));
  }
  return out;
}

const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || "chrome" });
const totals = {};
for (const view of VIEWS) {
  const context = await browser.newContext({
    viewport: view.viewport,
    deviceScaleFactor: view.deviceScaleFactor,
    reducedMotion: "reduce",
  });
  totals[view.name] = 0;
  for (const path of PAGES) {
    const page = await context.newPage();
    await page.goto(BASE + path, { waitUntil: "networkidle" }).catch(() => {});
    // Bring every scene into view, so it is laid out and measures its frame.
    await page.evaluate(async () => {
      for (let y = 0; y < document.body.scrollHeight; y += 500) {
        window.scrollTo(0, y);
        await new Promise((resolve) => setTimeout(resolve, 60));
      }
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(500);
    const issues = await page.evaluate(scanScenes, await page.evaluateHandle(() => document.body));
    // Each Enlarge view, full-screen.
    const enlarge = page.locator(".ms-enlarge");
    for (let i = 0; i < (await enlarge.count()); i++) {
      if (!(await enlarge.nth(i).isVisible())) continue;
      await enlarge.nth(i).click();
      const dialog = page.locator("dialog.ms-enlarged");
      await dialog.waitFor();
      await page.waitForTimeout(400);
      const found = await dialog.evaluate(scanScenes);
      issues.push(...found.map((line) => (line.startsWith("[") ? `[Enlarged] ${line}` : line)));
      await page.keyboard.press("Escape");
      await dialog.waitFor({ state: "detached" });
    }
    const count = issues.filter((line) => !line.startsWith("[")).length;
    totals[view.name] += count;
    if (count) {
      console.log(`== ${view.name} ${path}: ${count}`);
      for (const line of issues) console.log(line.startsWith("[") ? `   ${line}` : `      ${line}`);
    }
    await page.close();
  }
  await context.close();
}
await browser.close();
console.log("TOTAL", JSON.stringify(totals));
process.exit(Object.values(totals).some((n) => n > 0) ? 1 : 0);
