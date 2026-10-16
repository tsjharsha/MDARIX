/**
 * "A new version of MDARIX is available": a tab opened before a deploy keeps running the JavaScript it loaded. Every
 * few minutes, and when the tab is shown again, it asks the server which version it runs (GET /api/v1/public/version,
 * the repository's VERSION file) and compares it with the version this bundle was built as (the same file, embedded by
 * vite.config.ts as __MDARIX_VERSION__). Only a newer server version counts: while a deploy rolls out, a new page may
 * briefly meet the old API, and that is no reason to reload. Nothing is said when either version is unknown, offline,
 * or on an error, and the page is never reloaded for the person (they may be typing).
 */

export const VERSION_PATH = "/api/v1/public/version";
/** How often an open tab asks. */
export const CHECK_EVERY_MS = 5 * 60_000;
/** A tab shown again asks at once, but not more often than this. */
export const MIN_GAP_MS = 60_000;
const TIMEOUT_MS = 10_000;

/** The version this bundle was built as; empty when the build did not embed one. */
export const BUILT_VERSION: string =
  typeof __MDARIX_VERSION__ === "string" ? __MDARIX_VERSION__.trim().replace(/^v/i, "") : "";

/** "0.10.13" (or "v0.10.13") as [0, 10, 13]; null for anything else. */
export function parseVersion(value: unknown): number[] | null {
  if (typeof value !== "string") return null;
  const match = value.trim().match(/^v?(\d+)\.(\d+)\.(\d+)$/i);
  return match ? match.slice(1, 4).map(Number) : null;
}

/** Whether the server runs a newer version than this bundle; false when either is unknown. */
export function isNewerVersion(server: unknown, built: unknown): boolean {
  const a = parseVersion(server);
  const b = parseVersion(built);
  if (!a || !b) return false;
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] > b[index];
  }
  return false;
}

/** Whether a check is due now: the tab is shown, online, and the last check is at least ``gap`` ago. */
export function checkDue(now: number, lastCheck: number, gap: number, visible: boolean, online: boolean): boolean {
  return visible && online && now - lastCheck >= gap;
}

/** Whether the notice is shown at all here: a built version is known and this is not a test or automated browser. */
export function versionCheckEnabled(built: string, mode: string, automated: boolean): boolean {
  return Boolean(parseVersion(built)) && mode !== "test" && !automated;
}

/**
 * The version the server runs, or null (offline, an error, an unexpected answer). A plain fetch, not the API client:
 * this background question must not count as activity, so it never keeps an idle session signed in.
 */
export async function fetchServerVersion(fetcher: typeof fetch = fetch): Promise<string | null> {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), TIMEOUT_MS) : null;
  try {
    const response = await fetcher(VERSION_PATH, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: controller?.signal,
    });
    if (!response.ok) return null;
    const body: unknown = await response.json();
    const version = typeof body === "object" && body !== null ? (body as { version?: unknown }).version : null;
    return parseVersion(version) ? String(version).trim() : null;
  } catch {
    return null;
  } finally {
    if (timer) clearTimeout(timer);
  }
}
