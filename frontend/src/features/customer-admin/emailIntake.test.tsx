import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ConsoleContext, type ConsoleApi } from "./context";
import { EmailIntakePanel, domainList } from "./sections/EmailIntake";
import { OrganizationSection } from "./sections/Organization";

// B7b (0.10.97): Organization › E-mail intake, the Customer Administrator's address (spec 4.3).

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("./shared", async (original) => ({
  ...(await original<typeof import("./shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path]) ?? null,
    reload: () => undefined,
  }),
}));

const render = (node: ReactElement, emailIntake = true) =>
  renderToStaticMarkup(
    <ConsoleContext.Provider
      value={{ context: { email_intake: emailIntake }, open: vi.fn(), confirm: vi.fn(), notify: vi.fn() } as ConsoleApi}
    >
      {node}
    </ConsoleContext.Provider>,
  );

describe("E-mail intake settings", () => {
  it("shows the address with Copy, its state, the old address, the allowlist and the daily limit", () => {
    resources.data["/api/v1/email-intake/settings"] = {
      address: "cases-7f3k9q2m@intake.mdarix.com",
      on: true,
      trial: false,
      old_addresses: [{ address: "cases-old11111@intake.mdarix.com", until: "2026-12-11T00:00:00Z" }],
      allowed_domains: ["hospital.example"],
      daily_limit: 150,
    };
    const html = render(<EmailIntakePanel />);
    expect(html).toContain("cases-7f3k9q2m@intake.mdarix.com");
    expect(html).toContain("Copy");
    expect(html).toContain("On: messages are accepted");
    expect(html).toContain("cases-old11111@intake.mdarix.com");
    expect(html).toContain('value="hospital.example"');
    expect(html).toContain('value="150"');
    expect(html).toContain("Turn off");
    expect(html).toContain("Rotate");
    expect(html).not.toMatch(/gradient|glass|glow/);
  });

  it("offers no address to a free trial, and points to the SAMPLE e-mail", () => {
    resources.data["/api/v1/email-intake/settings"] = {
      address: null,
      on: false,
      trial: true,
      allowed_domains: [],
      daily_limit: 200,
    };
    const html = render(<EmailIntakePanel />);
    expect(html).toContain("SAMPLE e-mail");
    expect(html).not.toContain("Rotate");
    expect(html).not.toContain("Turn on");
  });

  it("is in Organization only while the server has e-mail intake switched on", () => {
    expect(render(<OrganizationSection />, true)).toContain("E-mail intake");
    expect(render(<OrganizationSection />, false)).not.toContain("E-mail intake");
  });

  it("reads the allowed domains typed with commas, spaces or lines", () => {
    expect(domainList(" a.example, b.example\nc.example ;; ")).toEqual(["a.example", "b.example", "c.example"]);
  });
});
