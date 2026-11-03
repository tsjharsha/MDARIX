// 0.10.81: the functional, usability, security and navigation reviews' findings that show on screen.
import { renderToStaticMarkup } from "react-dom/server";
import css from "./workspace.css?raw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awarenessText, formatDay } from "../../app/dates";
import { reportHits } from "./HybridShell";
import { DUE_WEEK_PATH, DUE_WEEK_VIEW } from "./home";
import { SERVER_VIEWS } from "./listViews";
import { HomeSection, LegalClocks } from "./sections/Home";
import { AlertsBell } from "./sections/Reminders";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";

const workspace = (persona = "admin") =>
  ({
    session: { business_permissions: [], persona, current_tenant: { tenant_name: "Test" } },
    persona,
    open: vi.fn(),
    notify: vi.fn(),
    work: {},
  }) as unknown as WorkspaceApi;

describe("Home while it reads (U-07)", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app/my-work", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("never says all clear before the data has arrived", () => {
    const html = renderToStaticMarkup(
      <WorkspaceContext.Provider value={workspace()}>
        <HomeSection heading={{ current: null }} />
      </WorkspaceContext.Provider>,
    );
    expect(html).toContain("Reading…");
    expect(html).not.toContain("Nothing past its time");
    const clocks = renderToStaticMarkup(<LegalClocks clocks={[]} onOpen={() => undefined} reading />);
    expect(clocks).toContain("Reading the legal clocks…");
    expect(clocks).not.toContain("No legal clock is running.");
    expect(renderToStaticMarkup(<LegalClocks clocks={[]} onOpen={() => undefined} />)).toContain(
      "No legal clock is running.",
    );
  });
});

describe("a day-only awareness (U-06)", () => {
  it("reads as the day given, with no invented time", () => {
    expect(awarenessText("2026-10-29T12:00:00+00:00", true)).toBe(
      `${formatDay(new Date(2026, 9, 29))}, time not recorded`,
    );
    expect(awarenessText("2026-10-29T12:00:00+00:00", false)).not.toContain("time not recorded");
    expect(awarenessText(null, true)).toBe("—");
  });
});

describe("search's report hits (navigation M2)", () => {
  it("never links a report that is not started (no id) to /app/reports?report=null", () => {
    const items = [
      { id: null, complaint_ref: "NAV-0002", form_title: "Form FDA 3500A worksheet (eMDR)" },
      { id: "r1", complaint_ref: "NAV-0002", form_title: "Form FDA 3500A worksheet (eMDR)" },
      { id: "r2", complaint_ref: "SAMPLE-RV-09", form_title: "Form FDA 3500A worksheet (eMDR)" },
    ];
    expect(reportHits(items, "nav-0002").map((item) => item.id)).toEqual(["r1"]);
  });
});

describe("the bell on the new navigation (navigation H1)", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      location: { pathname: "/app/my-work", search: "", hash: "", origin: "https://mdarix.test" },
      localStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
      sessionStorage: { getItem: () => null, setItem: () => undefined, removeItem: () => undefined },
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("opens Home, which holds the reminders and escalations", () => {
    const home = renderToStaticMarkup(
      <WorkspaceContext.Provider value={workspace()}>
        <HomeSection heading={{ current: null }} />
      </WorkspaceContext.Provider>,
    );
    expect(home).toContain('id="home-reminders"');
    expect(home).toContain("Reminders and escalations");
    expect(renderToStaticMarkup(<AlertsBell place="Home" onOpen={() => undefined} />)).toContain(
      "Reminders and escalations: open Home",
    );
  });

  it("stays in the top bar on a phone", () => {
    const phone = css.slice(css.indexOf("@media (max-width: 640px) {\n  /* The bell stays"));
    expect(phone.slice(0, phone.indexOf("}"))).not.toContain(".uw-top-bell");
  });
});

describe("Due this week, one number (navigation M1)", () => {
  it("is read from the Complaints list view of that name, which the tile opens", () => {
    expect(DUE_WEEK_PATH).toBe("/api/v1/complaints?view=due-week&page=1&page_size=1");
    expect(SERVER_VIEWS[DUE_WEEK_VIEW].code).toBe("due-week");
  });
});
