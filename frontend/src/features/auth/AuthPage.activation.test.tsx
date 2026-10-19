import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthPage } from "./AuthPage";

// An invited person sees how their account data is used before they activate it (CMP-15).
describe("account activation page", () => {
  afterEach(() => vi.unstubAllGlobals());

  const render = (mode: string) => {
    vi.stubGlobal("window", { location: { search: "?token=abc", origin: "https://mdarix.in", hash: "" } });
    return renderToStaticMarkup(<AuthPage mode={mode} />);
  };

  it("links the privacy policy, in a new tab, before the account is activated", () => {
    const html = render("activate-account");
    expect(html).toContain("Activate your MDARIX account");
    expect(html).toContain('href="/privacy" target="_blank" rel="noopener"');
    expect(html).toContain("Your account is processed as described in our");
    expect(html).toContain("stores only a salted hash of your password");
  });

  it("keeps the notice off the password reset page", () => {
    expect(render("reset-password")).not.toContain("Your account is processed as described in our");
  });
});
