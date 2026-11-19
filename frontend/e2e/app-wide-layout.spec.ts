import { test, expect, type Page } from "@playwright/test";
import { randomBytes } from "node:crypto";
import { mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { MAIL_DIR, PHONE, acknowledgePrivacy, person, settle } from "./support/journey";
import { signedUpOwner } from "./support/story";

/*
 * The application on wide screens (owner, 19 Nov 2026: "a lot of space on the right side of the page"): on a
 * 1920x1080 screen the work canvas sits in the middle of the room beside the rail, with balanced gutters, and no
 * screen scrolls sideways at 1280x720 (projector), 1440x900, 1920x1080 or on a 390x844 phone.
 *
 * A trial owner signs up (the sample data loads with the trial) and opens the main screens. Run like
 * persona-journeys.spec.ts: scripts/journey_api.py with E2E_MAIL_DIR and MDARIX_APP_URL the dev server's address.
 * UX_SHOTS names a folder for a screenshot of each main screen at each size (with UX_SHOTS_TAG in the file names);
 * without it only Today, Cases and the cockpit are opened.
 */

const RUN = randomBytes(3).toString("hex");
const SHOTS = process.env.UX_SHOTS ?? "";
const TAG = process.env.UX_SHOTS_TAG ?? "";
const owner = person(`quality.lead@aw${RUN}-devices.com`, "Meera Nair");

const WIDE = { width: 1920, height: 1080 };
const SIZES = [WIDE, { width: 1440, height: 900 }, { width: 1280, height: 720 }];

type Screen = { name: string; path: string; then?: (page: Page) => Promise<void>; balanced?: boolean };

const step = (name: RegExp) => async (page: Page) => {
  const steps = page.getByRole("navigation", { name: "Investigation steps" });
  await steps.getByRole("button", { name }).click();
  await settle(page);
};

/** Today with its data read: the three figures are numbers and no panel still says it is loading or reading. */
async function todayRead(page: Page) {
  await expect(page.locator(".uw-home-stats .uw-home-num")).toHaveText([/^\d+$/, /^\d+$/, /^\d+$/], {
    timeout: 60_000,
  });
  await expect(page.locator("main")).not.toContainText(/Loading…|Reading (the|what)/, { timeout: 60_000 });
}

/** The page's own hero band: its height (0 when the page has none; 1 px when it is kept for screen readers only). */
const bandHeight = (page: Page) =>
  page.evaluate(() => document.querySelector(".ac-main > .ac-page-head")?.getBoundingClientRect().height ?? 0);

const SCREENS: Screen[] = [
  { name: "today", path: "/app/my-work", balanced: true, then: todayRead },
  { name: "cases", path: "/app/complaints", balanced: true },
  { name: "cases-to-triage", path: "/app/complaints?tab=To+triage" },
  { name: "cases-reporting", path: "/app/complaints?tab=Reporting" },
  {
    // The list of investigations, as a person reaches it from an open one ("Where you are" > Investigations).
    name: "investigations",
    path: "/app/investigations?case=SAMPLE-INV-001",
    balanced: true,
    then: async (page) => {
      await page
        .getByRole("navigation", { name: "Where you are" })
        .getByRole("button", { name: "Investigations" })
        .click();
      await settle(page);
    },
  },
  { name: "cockpit-signal", path: "/app/investigations?case=SAMPLE-INV-001", balanced: true },
  { name: "cockpit-product", path: "/app/investigations?case=SAMPLE-INV-001", then: step(/Product reality/) },
  { name: "cockpit-evidence", path: "/app/investigations?case=SAMPLE-INV-001", then: step(/Evidence/) },
  { name: "cockpit-causes", path: "/app/investigations?case=SAMPLE-INV-001", then: step(/Possible causes/) },
  { name: "cockpit-brief", path: "/app/investigations?case=SAMPLE-INV-001", then: step(/Brief/) },
  { name: "cockpit-decision", path: "/app/investigations?case=SAMPLE-INV-001", then: step(/Decision & action/) },
  { name: "products", path: "/app/products" },
  {
    name: "products-rev-a-b",
    path: "/app/products",
    then: async (page) => {
      const compare = page.getByRole("button", { name: "Compare Rev A and Rev B" });
      if (await compare.isVisible().catch(() => false)) await compare.click();
      await settle(page);
    },
  },
  { name: "approvals", path: "/app/approvals" },
  { name: "reports", path: "/app/reports" },
  { name: "records", path: "/app/records" },
  { name: "administration", path: "/app/customer-admin" },
  { name: "getting-started", path: "/app/getting-started" },
];

/** The canvas's gutters: from the rail (or the window's left edge) to the content's first pixel, and from its last
 * pixel to the window's right edge; plus whether the page scrolls sideways. */
async function layout(page: Page) {
  return page.evaluate(() => {
    const main = document.querySelector(".ac-main");
    if (!main) return null;
    const rail = document.querySelector(".uw-navrail");
    const railRight = rail && rail.getClientRects().length ? rail.getBoundingClientRect().right : 0;
    const width = document.documentElement.clientWidth;
    let left = Infinity;
    let right = -Infinity;
    for (const child of Array.from(main.children)) {
      const box = child.getBoundingClientRect();
      // Not drawn, fixed, or kept for screen readers only (1 px).
      if (box.width <= 1 || box.height <= 1 || getComputedStyle(child).position === "fixed") continue;
      left = Math.min(left, box.left);
      right = Math.max(right, box.right);
    }
    return {
      leftGutter: Math.round(left - railRight),
      rightGutter: Math.round(width - right),
      content: Math.round(right - left),
      sideways: document.documentElement.scrollWidth - width,
    };
  });
}

async function open(page: Page, screen: Screen) {
  await page.goto(screen.path);
  await settle(page);
  // A cold dev server can fail its first lazy import ("Something went wrong"); a person would press Refresh.
  if (await page.getByRole("heading", { name: "Something went wrong" }).isVisible()) {
    await page.reload();
    await settle(page);
  }
  await acknowledgePrivacy(page);
  const gotIt = page.getByRole("button", { name: "Got it" });
  if (await gotIt.isVisible().catch(() => false)) await gotIt.click();
  if (screen.then) await screen.then(page);
  await page.evaluate(() => window.scrollTo(0, 0));
}

async function capture(page: Page, name: string) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  // The blocks have risen in (320 ms, staggered to 200 ms) before the picture is taken.
  await page.waitForTimeout(700);
  const { width, height } = page.viewportSize()!;
  await page.screenshot({ path: path.join(SHOTS, `${TAG}${name}-${width}x${height}.png`) });
}

test.describe("The application on wide screens", () => {
  test.skip(!MAIL_DIR, "Set E2E_MAIL_DIR to the journey API's mail folder (scripts/journey_api.py).");
  test.skip(({ isMobile }) => isMobile, "Runs on the desktop project; it sets each size itself.");
  test.afterAll(() => rmSync(owner.state, { force: true }));

  test("each main screen fills a 1920 screen with balanced gutters and never scrolls sideways", async ({ browser }) => {
    // The check: Today, Cases and the cockpit; with UX_SHOTS, every main screen (a tour of about 25 minutes).
    // UX_SCREENS (comma-separated name prefixes, e.g. "today,cockpit-") narrows the tour to those screens.
    const only = (process.env.UX_SCREENS ?? "").split(",").filter(Boolean);
    const toured = only.length ? SCREENS.filter((one) => only.some((name) => one.name.startsWith(name))) : SCREENS;
    const screens = SHOTS ? toured : SCREENS.filter((one) => one.balanced);
    test.setTimeout(SHOTS ? 2_400_000 : 600_000);
    const page = await signedUpOwner(browser, owner, `Wide Layout ${RUN.toUpperCase()}`, WIDE);
    for (const screen of screens) {
      for (const size of SIZES) {
        await page.setViewportSize(size);
        await open(page, screen);
        await capture(page, screen.name);
        const box = await layout(page);
        expect(box, `${screen.name} has a work canvas`).not.toBeNull();
        // One hero per screen: an open investigation's own dark header, never the page's band above it as well.
        if (screen.name.startsWith("cockpit-"))
          expect.soft(await bandHeight(page), `${screen.name}: the page band is hidden`).toBeLessThanOrEqual(1);
        if (screen.name === "investigations")
          expect.soft(await bandHeight(page), "the investigations list keeps its band").toBeGreaterThan(40);
        expect.soft(box!.sideways, `${screen.name} at ${size.width} scrolls sideways`).toBeLessThanOrEqual(0);
        if (screen.balanced && size.width === WIDE.width) {
          // Centred: the gutters differ by no more than 32 px, and the canvas uses the room (at least 1360 px).
          expect
            .soft(Math.abs(box!.leftGutter - box!.rightGutter), `${screen.name} gutters ${JSON.stringify(box)}`)
            .toBeLessThanOrEqual(32);
          expect.soft(box!.content, `${screen.name} canvas width at 1920`).toBeGreaterThanOrEqual(1360);
        }
      }
    }
    // The phone: the same screens, nothing wider than the screen.
    await page.setViewportSize(PHONE);
    for (const screen of (SHOTS ? toured : SCREENS).filter((one) => one.balanced)) {
      await open(page, screen);
      await capture(page, screen.name);
      const box = await layout(page);
      expect.soft(box?.sideways ?? 0, `${screen.name} on the phone scrolls sideways`).toBeLessThanOrEqual(0);
    }
    await page.context().close();
  });
});
