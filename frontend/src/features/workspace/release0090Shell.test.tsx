// 0.10.90, the owner-approved hero design: the new navigation's left icon rail, its slim top bar and the phone's
// bottom bar, in place of the eleven tabs across the top. Every persona rule and route stays as it was.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  NavRail,
  PHONE_SLOTS,
  PhoneBar,
  RAIL_GROUPS,
  PERSONA_TABS,
  phoneBar,
  shownTabs,
  storyProgress,
  trialTabs,
  visibleTabs,
} from "./HybridShell";
import type { StoryRun } from "./oneStory";
import userWorkspace from "./UserWorkspace.tsx?raw";

// Read as a file: the test run does not load stylesheets (a ?raw import of CSS is empty here).
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const shellCss: string = fs.readFileSync(new URL("./heroShell.css", import.meta.url), "utf8").replace(/\r\n/g, "\n");

const ALL = [...Object.values(PERSONA_TABS).map((tab) => tab.section), "Decision trees", "Reports", "Trends"];
const trial = (persona: string[]) => visibleTabs(trialTabs(persona, true), ALL);
const labels = (markup: string) =>
  [...markup.matchAll(/<span class="uw-tab-label">([^<]*)<\/span>/g)].map((match) => match[1]);

describe("the rail", () => {
  it("lists Getting started first, then the five work areas (UX2)", () => {
    const rail = renderToStaticMarkup(
      <NavRail
        tabs={trial(Object.keys(PERSONA_TABS).filter((key) => key !== "start"))}
        current="home"
        open={vi.fn()}
        progress={3}
      />,
    );
    expect(rail).toContain('<nav class="uw-navrail" aria-label="Destinations">');
    expect(rail.indexOf("<strong>Getting started</strong>")).toBeLessThan(rail.indexOf(">Work<"));
    expect(labels(rail)).toEqual(["Today", "Cases", "Investigations", "Products", "Decisions &amp; Reports"]);
    // One group; Records, Team and the trial's Look ahead and Next steps are not destinations any more.
    expect(rail).not.toContain(">Plan<");
    expect(rail).not.toContain("uw-navrail-foot");
    expect(RAIL_GROUPS.flatMap((group) => group.tabs).sort()).toEqual(
      Object.keys(PERSONA_TABS)
        .filter((key) => key !== "start")
        .sort(),
    );
  });

  it("shows the walkthrough's progress beside Getting started: a ten-segment ring and the count", () => {
    const rail = renderToStaticMarkup(<NavRail tabs={trial(["home"])} current="home" open={vi.fn()} progress={3} />);
    expect(rail).toContain("3 of 10 completed");
    expect(rail.match(/class="hx-seg is-done"/g)).toHaveLength(3);
    // Unknown until the story is read: no count, and the step's icon rather than an empty ring that reads as loading.
    const unread = renderToStaticMarkup(<NavRail tabs={trial(["home"])} current="home" open={vi.fn()} />);
    expect(unread).not.toContain("of 10 completed");
    expect(unread).toContain("uw-navrail-ring-wait");
    expect(unread).not.toContain("hx-seg");
    // Read, even at nothing done, it is the ring: "0 of 10 completed".
    expect(
      renderToStaticMarkup(<NavRail tabs={trial(["home"])} current="home" open={vi.fn()} progress={0} />),
    ).toContain("0 of 10 completed");
  });

  it("keeps only the persona's destinations, and marks a screen opened from Getting started", () => {
    const rail = renderToStaticMarkup(
      <NavRail tabs={trial(["home", "complaints"])} current="products" open={vi.fn()} personaLabel="Handler" />,
    );
    expect(labels(rail)).toEqual(["Today", "Cases", "Products"]);
    expect(rail).toMatch(/class="uw-tab is-extra" aria-current="page" title="Opened from Getting started or a link/);
    expect(rail).toContain("(opened from Getting started; not one of your tabs)");
    // A pilot has no Getting started, Look ahead or Next steps.
    const pilot = renderToStaticMarkup(
      <NavRail tabs={visibleTabs(trialTabs(["home", "decisions"], false), ALL)} current="home" open={vi.fn()} />,
    );
    expect(pilot).not.toContain("Getting started");
    expect(labels(pilot)).toEqual(["Today", "Decisions &amp; Reports"]);
  });

  it("folds to icons, each keeping its name for screen readers and as its tooltip", () => {
    const rail = renderToStaticMarkup(<NavRail tabs={trial(["home"])} current="home" open={vi.fn()} />);
    expect(rail).toContain('aria-label="Collapse the menu" aria-expanded="true"');
    expect(rail).toMatch(/title="Today"><svg[^>]*aria-hidden="true"/);
    // Icon-only below 1240 px: the names are hidden visually, never removed.
    const narrow = shellCss.slice(shellCss.indexOf("@media (max-width: 1240px)"));
    expect(narrow).toMatch(/\.uw-navrail \.uw-tab-label \{\s*position: absolute;[^}]*clip-path: inset\(50%\)/);
    expect(narrow.slice(0, narrow.indexOf("}\n}"))).not.toMatch(/uw-tab-label[^{]*\{\s*display: none/);
  });
});

describe("the phone's bottom bar", () => {
  it("has Getting started, Today, Cases and Products, with More for the rest", () => {
    const tabs = trial(["home", "complaints", "investigations", "products", "decisions"]);
    expect(phoneBar(tabs)).toEqual({
      slots: ["start", "home", "complaints", "products"],
      more: ["investigations", "decisions"],
    });
    const bar = renderToStaticMarkup(<PhoneBar tabs={tabs} current="decisions" open={vi.fn()} />);
    expect(bar).toContain('<nav class="uw-phonebar" aria-label="Destinations">');
    expect(labels(bar)).toEqual(["Getting started", "Today", "Cases", "Products", "More"]);
    // The current screen is behind More: More is marked, and its list is closed until asked for.
    expect(bar).toMatch(/class="uw-tab is-within" aria-expanded="false"/);
    expect(PHONE_SLOTS).toHaveLength(4);
  });

  it("drops the slots the persona does not have, and More when nothing is left", () => {
    expect(phoneBar(["home", "complaints"])).toEqual({ slots: ["home", "complaints"], more: [] });
    expect(
      renderToStaticMarkup(<PhoneBar tabs={["home", "complaints"]} current="home" open={vi.fn()} />),
    ).not.toContain(">More<");
  });

  it("shows only on a phone; the rail only above it", () => {
    const phone = shellCss.slice(shellCss.indexOf("@media (max-width: 640px)"));
    expect(shellCss).toMatch(/\.uw-phonebar \{\s*display: none;/);
    expect(phone).toMatch(/\.uw-hybrid > \.uw-navrail \{\s*display: none;/);
    expect(phone).toMatch(/\.uw-phonebar \.uw-tab \{[^}]*min-height: 62px/);
  });
});

describe("the shell around it", () => {
  it("keeps a screen the persona does not list in view while it is open", () => {
    expect(shownTabs(["home"], "products")).toEqual({ tabs: ["home", "products"], extra: "products" });
    expect(shownTabs(["home"], "home")).toEqual({ tabs: ["home"], extra: null });
    expect(shownTabs(["home"], null)).toEqual({ tabs: ["home"], extra: null });
  });

  it("counts the walkthrough's steps done or not needed", () => {
    const run = {
      steps: [
        { key: "a", label: "A", done: true, skipped: false },
        { key: "b", label: "B", done: false, skipped: true },
        { key: "c", label: "C", done: false, skipped: false },
      ],
    } as unknown as StoryRun;
    expect(storyProgress(run)).toBe(2);
    expect(storyProgress(null)).toBeNull();
  });

  it("puts the brand on the rail and the organization, search, import, persona, bell, help and avatar on the top bar", () => {
    const header = userWorkspace.slice(
      userWorkspace.indexOf('<header className="ac-header uw-top">'),
      userWorkspace.indexOf("</header>"),
    );
    expect(header).not.toContain("ac-brand");
    const order = [
      "uw-org",
      "uw-sample-chip",
      "<GlobalSearch",
      "<ImportOwnData",
      "<PersonaSwitch",
      "<AlertsBell",
      "<HelpMenu",
      "<AvatarMenu",
    ];
    const at = order.map((mark) => header.indexOf(mark));
    expect(at.every((index) => index >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
    expect(userWorkspace).toContain("<NavRail");
    expect(userWorkspace).toContain("<PhoneBar");
  });
});

describe("the fixed bars never cover what is scrolled into view", () => {
  it("pads scrolling by the top bar, and on a phone by the bottom bar", () => {
    expect(shellCss).toMatch(/html:has\(\.uw-hybrid\) \{\s*scroll-padding-top: 72px;/);
    expect(shellCss).toMatch(
      /@media \(max-width: 640px\) \{\s*html:has\(\.uw-hybrid\) \{\s*scroll-padding-bottom: 96px;/,
    );
  });
});
