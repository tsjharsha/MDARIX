// 0.10.88 (DEV-10): the session ends while the person saves something. The browser journey found that what they had
// typed was gone after signing in again, while the sign-in page promised "continue where you left off".
import { afterEach, describe, expect, it, vi } from "vitest";
import { signInNotice } from "../features/auth/AuthPage";

const ended = () =>
  vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ detail: { code: "SESSION_EXPIRED", message: "Session expired" } }), {
        status: 401,
      }),
    );

async function redirectAfter(method: string) {
  vi.resetModules();
  const replace = vi.fn();
  vi.stubGlobal("window", {
    setTimeout,
    clearTimeout,
    location: { pathname: "/app/complaints", search: "?tab=To+triage", replace },
  });
  vi.stubGlobal("fetch", ended());
  const { requestJson } = await import("./apiClient");
  await expect(requestJson("/api/v1/triage/x", { method, body: "{}" })).rejects.toMatchObject({ status: 401 });
  return new URLSearchParams(String(replace.mock.calls[0]?.[0]).split("?")[1]);
}

afterEach(() => vi.unstubAllGlobals());

describe("the session ends during a save", () => {
  it("says the change was not saved, and still returns to the same screen", async () => {
    const query = await redirectAfter("POST");
    expect(query.get("returnTo")).toBe("/app/complaints?tab=To+triage");
    expect(signInNotice(query)).toMatch(/your last change was not saved/i);
  });

  it("keeps the usual words when only a read was refused", async () => {
    const query = await redirectAfter("GET");
    expect(signInNotice(query)).toBe("Your session has ended. Sign in again to continue where you left off.");
  });
});
