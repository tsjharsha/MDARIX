import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  BUILT_VERSION,
  CHECK_EVERY_MS,
  MIN_GAP_MS,
  VERSION_PATH,
  checkDue,
  fetchServerVersion,
  isNewerVersion,
  parseVersion,
  versionCheckEnabled,
} from "./appVersion";
import { NewVersionNotice, NewVersionNoticeView } from "./NewVersionNotice";

const noop = () => undefined;
const answer = (status: number, body: unknown) =>
  (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;

describe("A new version of MDARIX is available: the comparison", () => {
  it("reads versions as the VERSION file and the API write them", () => {
    expect(parseVersion("0.10.13")).toEqual([0, 10, 13]);
    expect(parseVersion(" v1.2.3 ")).toEqual([1, 2, 3]);
    for (const value of ["", "latest", "2026.10", "0.10.13-rc1", null, undefined, 13]) {
      expect(parseVersion(value)).toBeNull();
    }
  });

  it("counts only a newer server version, compared number by number", () => {
    expect(isNewerVersion("0.10.13", "0.10.12")).toBe(true);
    expect(isNewerVersion("0.11.0", "0.10.99")).toBe(true);
    expect(isNewerVersion("0.10.10", "0.10.9")).toBe(true); // not compared as text
    expect(isNewerVersion("0.10.12", "0.10.12")).toBe(false);
    // A deploy rolling out: the new page meets the old API for a moment. No reason to reload.
    expect(isNewerVersion("0.10.12", "0.10.13")).toBe(false);
  });

  it("says nothing when either side is unknown", () => {
    expect(isNewerVersion(null, "0.10.12")).toBe(false);
    expect(isNewerVersion("0.10.13", "")).toBe(false);
    expect(isNewerVersion("unknown", "0.10.12")).toBe(false);
  });

  it("asks every few minutes, at once when the tab is shown again, never hidden or offline", () => {
    expect(CHECK_EVERY_MS).toBe(5 * 60_000);
    const last = 1_000_000;
    expect(checkDue(last + MIN_GAP_MS, last, MIN_GAP_MS, true, true)).toBe(true);
    expect(checkDue(last + MIN_GAP_MS - 1, last, MIN_GAP_MS, true, true)).toBe(false); // not more than once a minute
    expect(checkDue(last + CHECK_EVERY_MS, last, MIN_GAP_MS, false, true)).toBe(false); // a hidden tab waits
    expect(checkDue(last + CHECK_EVERY_MS, last, MIN_GAP_MS, true, false)).toBe(false); // offline
  });

  it("is off in tests, in automated browsers and without a built version", () => {
    expect(versionCheckEnabled("0.10.13", "production", false)).toBe(true);
    expect(versionCheckEnabled("0.10.13", "development", false)).toBe(true);
    expect(versionCheckEnabled("0.10.13", "test", false)).toBe(false);
    expect(versionCheckEnabled("0.10.13", "production", true)).toBe(false);
    expect(versionCheckEnabled("", "production", false)).toBe(false);
  });

  it("embeds the repository's VERSION in the bundle", () => {
    expect(parseVersion(BUILT_VERSION)).not.toBeNull();
  });

  it("reads the server's version, and gives none on an error, a strange answer or no network", async () => {
    const asked: [string, RequestInit | undefined][] = [];
    const recording = (async (path: string, init?: RequestInit) => {
      asked.push([path, init]);
      return new Response(JSON.stringify({ version: "0.10.13" }), { status: 200 });
    }) as unknown as typeof fetch;
    expect(await fetchServerVersion(recording)).toBe("0.10.13");
    expect(asked[0][0]).toBe(VERSION_PATH);
    expect(asked[0][1]?.cache).toBe("no-store");
    expect(await fetchServerVersion(answer(503, { version: "0.10.13" }))).toBeNull();
    expect(await fetchServerVersion(answer(200, { version: "soon" }))).toBeNull();
    expect(await fetchServerVersion(answer(200, ["0.10.13"]))).toBeNull();
    const offline = (async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    expect(await fetchServerVersion(offline)).toBeNull();
  });
});

describe("A new version of MDARIX is available: the notice", () => {
  it("says so politely with a Reload button and a way to dismiss it", () => {
    const html = renderToStaticMarkup(<NewVersionNoticeView onReload={noop} onDismiss={noop} />);
    expect(html).toContain("A new version of MDARIX is available.");
    expect(html).toContain('<button type="button" class="new-version-reload">Reload</button>');
    expect(html).toContain('aria-label="Dismiss for now"');
  });

  it("starts as an empty status region: nothing is shown before a newer version is seen", () => {
    const html = renderToStaticMarkup(<NewVersionNotice />);
    expect(html).toBe('<div class="new-version-region" role="status" aria-live="polite"></div>');
  });
});
