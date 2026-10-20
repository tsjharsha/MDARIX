import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  endsSession,
  errorMessageFrom,
  lastFailedRequestId,
  onApiActivity,
  requestJson,
  signInPath,
  mfaRedirectFor,
} from "./apiClient";

describe("shared API client", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { setTimeout, clearTimeout });
  });
  afterEach(() => vi.restoreAllMocks());

  it("sends same-origin credentials and parses successful JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 })));
    await expect(requestJson<{ status: string }>("/api/v1/session/context")).resolves.toEqual({ status: "ok" });
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/session/context",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("counts a request as activity unless it is a background read, which it marks for the server", async () => {
    const ok = () => Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", vi.fn().mockImplementation(ok));
    const activity = vi.fn();
    const stop = onApiActivity(activity);
    await requestJson("/api/v1/trial/story", { background: true });
    expect(activity).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/v1/trial/story",
      expect.objectContaining({ headers: expect.objectContaining({ "X-MDARIX-Background": "1" }) }),
    );
    await requestJson("/api/v1/session/context");
    expect(activity).toHaveBeenCalledTimes(1);
    expect(vi.mocked(fetch).mock.lastCall?.[1]?.headers).not.toHaveProperty("X-MDARIX-Background");
    stop();
  });

  it("converts structured API failures into safe ApiError values", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: "TENANT_DENIED", message: "Tenant denied" } }), {
          status: 403,
          statusText: "Forbidden",
        }),
      ),
    );
    await expect(requestJson("/api/v1/admin/customers")).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
      code: "TENANT_DENIED",
      message: "Tenant denied",
    });
  });

  it("does not retry state-changing requests by default", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "Rejected" }), { status: 409, statusText: "Conflict" }),
        ),
    );
    await expect(requestJson("/api/v1/admin/customers", { method: "POST", body: "{}" })).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("carries the server's request id from the error body, or else the X-Request-ID header", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: { code: "INTERNAL_ERROR", message: "The request could not be completed.", request_id: "req-123" },
          }),
          { status: 500 },
        ),
      ),
    );
    await expect(requestJson("/api/v1/x", { retries: 0 })).rejects.toMatchObject({
      status: 500,
      code: "INTERNAL_ERROR",
      requestId: "req-123",
    });
    expect(lastFailedRequestId()).toBe("req-123");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<html>Bad gateway</html>", { status: 502, headers: { "X-Request-ID": "hdr-9" } }),
        ),
    );
    await expect(requestJson("/api/v1/x", { retries: 0 })).rejects.toMatchObject({
      status: 502,
      requestId: "hdr-9",
      message: "MDARIX is not reachable right now. Try again in a moment.",
    });
  });

  it("turns a network failure and a timeout into readable errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(requestJson("/api/v1/x", { retries: 0 })).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      code: "NETWORK_ERROR",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_path: string, init: RequestInit) =>
          new Promise((_resolve, reject) =>
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))),
          ),
      ),
    );
    await expect(requestJson("/api/v1/x", { retries: 0, timeoutMs: 5 })).rejects.toMatchObject({
      status: 0,
      code: "TIMEOUT",
    });
  });

  it("sends files as they are, without claiming JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 200 })));
    const file = new Blob(["a;b\n1;2\n"], { type: "text/csv" });
    await requestJson("/api/v1/data/import/products", {
      method: "POST",
      body: file,
      headers: { "Content-Type": "text/csv" },
    });
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(file);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("text/csv");
  });
});

describe("error messages", () => {
  it("never shows a raw object: strings, validation lists and structured details all read as text", () => {
    expect(errorMessageFrom({ detail: "Rejected" }, 409)).toBe("Rejected");
    expect(errorMessageFrom({ detail: { code: "X", message: "Readable" } }, 400)).toBe("Readable");
    expect(
      errorMessageFrom(
        { detail: [{ loc: ["body", "summary"], msg: "String should have at most 200 characters" }] },
        422,
      ),
    ).toBe("Check the form: summary: String should have at most 200 characters.");
    expect(errorMessageFrom(null, 500)).toBe("The request could not be completed (error 500).");
    expect(errorMessageFrom({ detail: { code: "ONLY_CODE" } }, 404)).toBe(
      "This item was not found in your organization.",
    );
  });
});

describe("session end", () => {
  it("treats any 401 inside the app as an ended session, except a wrong password or code", () => {
    expect(endsSession("/api/v1/products", 401, "UNAUTHENTICATED", "/app/products")).toBe(true);
    expect(endsSession("/api/v1/products", 401, "SESSION_IDLE_TIMEOUT", "/app")).toBe(true);
    expect(endsSession("/api/v1/auth/signin", 401, "INVALID_CREDENTIALS", "/app")).toBe(false);
    expect(endsSession("/api/v1/auth/mfa/verify", 401, undefined, "/app")).toBe(false);
    expect(endsSession("/api/v1/products", 403, "TENANT_DENIED", "/app")).toBe(false);
    // The public website never jumps to sign-in.
    expect(endsSession("/api/v1/public/site-info", 401, undefined, "/pricing")).toBe(false);
  });

  it("returns to the page the person was on, with the reason", () => {
    expect(signInPath("expired", { pathname: "/app/investigations", search: "?tab=x" })).toBe(
      "/signin?reason=expired&returnTo=%2Fapp%2Finvestigations%3Ftab%3Dx",
    );
    expect(signInPath("idle", { pathname: "/pricing", search: "" })).toBe("/signin?reason=idle");
    expect(signInPath(undefined, { pathname: "/", search: "" })).toBe("/signin");
  });

  it("redirects on a 401 from any API call made inside the app", async () => {
    const replace = vi.fn();
    vi.stubGlobal("window", {
      setTimeout,
      clearTimeout,
      location: { pathname: "/app/signals", search: "", replace },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: "UNAUTHENTICATED", message: "Authentication required" } }), {
          status: 401,
        }),
      ),
    );
    await expect(requestJson("/api/v1/analytics/signals", { retries: 0 })).rejects.toMatchObject({ status: 401 });
    expect(replace).toHaveBeenCalledWith("/signin?reason=expired&returnTo=%2Fapp%2Fsignals");
  });
});

describe("second-factor refusals", () => {
  it("sends an unfinished sign-in to the MFA page", () => {
    expect(mfaRedirectFor("/api/v1/investigations", 403, "MFA_REQUIRED")).toBe("/mfa");
    expect(mfaRedirectFor("/api/v1/admin/identity/users", 403, "MFA_ENROLLMENT_REQUIRED")).toBe("/mfa?setup=1");
  });

  it("leaves a signature or operator action to show its own message", () => {
    for (const path of [
      "/api/v1/regulatory/documents/abc/status",
      "/api/v1/platform-admin/tenants/abc/legal-hold",
      "/api/v1/platform-admin/users/abc/activation-link",
      "/api/v1/governance/decisions/abc/sign",
      "/api/v1/investigations/abc/decision/sign",
    ]) {
      expect(mfaRedirectFor(path, 403, "MFA_REQUIRED")).toBeNull();
      expect(mfaRedirectFor(path, 403, "MFA_ENROLLMENT_REQUIRED")).toBeNull();
    }
  });

  it("ignores other refusals", () => {
    expect(mfaRedirectFor("/api/v1/investigations", 403, "PERMISSION_DENIED")).toBeNull();
    expect(mfaRedirectFor("/api/v1/investigations", 401, "MFA_REQUIRED")).toBeNull();
  });
});
