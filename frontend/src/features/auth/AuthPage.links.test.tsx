import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FirstRecoveryCodes, spentLinkMessage } from "./AuthPage";

// Release 0.10.35: a spent link says so before the form (DEV-004); the first recovery codes can be saved (UX-12).
describe("one-time links", () => {
  afterEach(() => vi.unstubAllGlobals());

  const answer = (status: number, body: unknown) =>
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));

  it("says a used or withdrawn invitation cannot be used, before any password is typed", async () => {
    answer(200, { usable: false, code: "INVALID_ACTIVATION" });
    expect(await spentLinkMessage("abc", "activation")).toContain(
      "This invitation link has expired or was already used",
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/auth/link-status",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ token: "abc", kind: "activation" }) }),
    );
  });

  it("says a used reset link cannot be used", async () => {
    answer(200, { usable: false, code: "INVALID_RESET" });
    expect(await spentLinkMessage("abc", "reset")).toBe(
      "This reset link has expired or was already used. Request a new one below.",
    );
  });

  it("keeps the form when the link works or the check cannot be made", async () => {
    answer(200, { usable: true });
    expect(await spentLinkMessage("abc", "activation")).toBeNull();
    answer(429, { detail: { code: "RATE_LIMITED" } });
    expect(await spentLinkMessage("abc", "activation")).toBeNull();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    expect(await spentLinkMessage("abc", "reset")).toBeNull();
  });
});

describe("first recovery codes", () => {
  it("offers Copy all and Download next to continue, and no longer asks to print", () => {
    const html = renderToStaticMarkup(
      <FirstRecoveryCodes codes={["aaaa-bbbb", "cccc-dddd"]} account="asha@example.com" message="" onDone={() => {}} />,
    );
    expect(html).toContain("Copy all");
    expect(html).toContain("Download");
    expect(html).toContain("I have saved these codes, continue");
    expect(html).toContain("aaaa-bbbb");
    expect(html).not.toContain("print them");
  });
});
