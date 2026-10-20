import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ColleagueWelcome, showWelcome, welcomeText } from "./sections/ColleagueWelcome";

const HOUR = 3600 * 1000;
const now = Date.parse("2026-10-20T12:00:00Z");
const colleague = {
  joined_at: new Date(now - HOUR).toISOString(),
  invited_by: "Asha Rao",
  organization: "MDARIX Validation Org",
};

describe("the greeting for an invited colleague (UX-26)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("names who invited them and to whose trial", () => {
    expect(welcomeText(colleague)).toBe("Asha Rao invited you to MDARIX Validation Org's free trial.");
    expect(welcomeText({ ...colleague, organization: "Orbit Medical Devices" })).toBe(
      "Asha Rao invited you to Orbit Medical Devices' free trial.",
    );
    expect(welcomeText({ ...colleague, organization: null })).toBe("Asha Rao invited you to this MDARIX free trial.");
    // The trial owner is not greeted as invited.
    expect(welcomeText({ ...colleague, invited_by: null })).toBeNull();
  });

  it("shows once: in the colleague's first days, until they close it", () => {
    expect(showWelcome(colleague, false, now)).toBe(true);
    expect(showWelcome(colleague, true, now)).toBe(false);
    expect(showWelcome({ ...colleague, joined_at: new Date(now - 3 * 24 * HOUR).toISOString() }, false, now)).toBe(
      false,
    );
    expect(showWelcome({ ...colleague, invited_by: null }, false, now)).toBe(false);
  });

  it("renders the greeting with a way to close it", () => {
    vi.stubGlobal("window", { localStorage: { getItem: () => null, setItem: () => undefined } });
    const html = renderToStaticMarkup(<ColleagueWelcome me={{ ...colleague, joined_at: new Date().toISOString() }} />);
    expect(html).toContain("Asha Rao invited you to MDARIX Validation Org&#x27;s free trial.");
    expect(html).toContain("Got it");
    vi.stubGlobal("window", { localStorage: { getItem: () => "1", setItem: () => undefined } });
    expect(renderToStaticMarkup(<ColleagueWelcome me={colleague} />)).toBe("");
  });
});
