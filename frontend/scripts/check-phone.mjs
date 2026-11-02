// The 390 px check (quality plan stage 5): every workspace section and tab, and the website's main pages, opened at
// 390 x 844 (a phone). It fails when the page is wider than the screen (sideways page scroll) and reports what it
// finds on the way: a code (UPPER_SNAKE) or a raw id (a UUID, 32 hex characters) in the visible text, and the
// controls smaller than 44 px. It needs a running app and a signed-in trial session, e.g.
//
//   npx vite --port 5177 (with the API)   then
//   MDARIX_SESSION=<the mdarix_session cookie> npm run check:phone -- [<base-url>] [--shots <folder>]
//
// Without MDARIX_SESSION only the website is checked. A customer's own problem codes (the complaint list shows them as
// recorded, e.g. the sample's SPO2_DROPOUT_HARM) are their data, not MDARIX's codes: pass them in MDARIX_DATA_CODES
// (comma separated) to leave them out of the report. Exits 1 when a page scrolls sideways or shows a code.
import { mkdirSync } from "node:fs";
import { chromium } from "@playwright/test";

const args = process.argv.slice(2);
const shotsAt = args.indexOf("--shots");
const shots = shotsAt >= 0 ? args.splice(shotsAt, 2)[1] : null;
const BASE = (args[0] || "http://127.0.0.1:5177").replace(/\/$/, "");
const SESSION = process.env.MDARIX_SESSION || "";
const DATA_CODES = new Set((process.env.MDARIX_DATA_CODES || "").split(",").filter(Boolean));
const SITE = ["/", "/platform", "/solutions", "/trust", "/resources", "/questions", "/company", "/contact", "/signup"];
const slug = (text) =>
  text
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
const failures = [];
const notes = [];

async function settle(page) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(600);
  const ack = page.getByRole("button", { name: "Acknowledge", exact: true }).first();
  if (await ack.isVisible().catch(() => false)) await ack.click().catch(() => {});
}

async function check(page, name) {
  const found = await page.evaluate(() => {
    const text = document.body.innerText;
    let small = 0;
    for (const el of document.querySelectorAll("main button, main a[href], main select, main [role=tab]")) {
      const box = el.getBoundingClientRect();
      if (
        box.width &&
        box.height &&
        (box.height < 44 || box.width < 44) &&
        getComputedStyle(el).visibility !== "hidden"
      )
        small++;
    }
    return {
      wide: document.documentElement.scrollWidth > window.innerWidth + 1,
      width: document.documentElement.scrollWidth,
      codes: [...new Set(text.match(/\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/g) || [])],
      ids: [
        ...new Set(
          text.match(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b[0-9a-f]{32}\b/g) || [],
        ),
      ],
      small,
    };
  });
  const codes = found.codes.filter((code) => !DATA_CODES.has(code));
  if (found.wide) failures.push(`${name}: the page is ${found.width} px wide at 390`);
  if (codes.length || found.ids.length) failures.push(`${name}: shows ${[...codes, ...found.ids].join(", ")}`);
  if (found.small) notes.push(`${name}: ${found.small} controls under 44 px`);
  if (shots) await page.screenshot({ path: `${shots}/${name}-390.png`, fullPage: true });
}

const browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || "chrome" });
try {
  if (shots) mkdirSync(shots, { recursive: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  if (SESSION) await context.addCookies([{ name: "mdarix_session", value: SESSION, url: BASE }]);
  const page = await context.newPage();
  for (const route of SITE) {
    await page.goto(`${BASE}${route}`);
    await settle(page);
    await check(page, `site${slug(route) ? `-${slug(route)}` : ""}`);
  }
  if (SESSION) {
    await page.goto(`${BASE}/app?section=${encodeURIComponent("Getting started")}`);
    await settle(page);
    const sections = await page.locator("nav.ac-nav button strong").allInnerTexts();
    for (const section of sections) {
      await page.goto(`${BASE}/app?section=${encodeURIComponent(section)}`);
      await settle(page);
      const tabs = page.locator("main [role=tablist]").first().getByRole("tab");
      const count = await tabs.count();
      if (!count) await check(page, slug(section));
      for (let i = 0; i < count; i++) {
        await page.goto(`${BASE}/app?section=${encodeURIComponent(section)}`);
        await settle(page);
        const tab = page.locator("main [role=tablist]").first().getByRole("tab").nth(i);
        const label = (await tab.innerText()).split("\n")[0];
        await tab.click();
        await settle(page);
        await check(page, `${slug(section)}--${slug(label)}`);
      }
    }
  }
} finally {
  await browser.close();
}
for (const line of notes) console.log("note:", line);
for (const line of failures) console.log("FAIL:", line);
console.log(failures.length ? `${failures.length} problem(s)` : "Every page fits 390 px and shows no code.");
process.exit(failures.length ? 1 : 0);
