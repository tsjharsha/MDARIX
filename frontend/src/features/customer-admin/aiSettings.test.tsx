import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MASKING_SUMMARY,
  aiAcknowledgement,
  aiFeaturePayload,
  aiSettingsPayload,
  featureLock,
  providerLabel,
  withLockVersion,
} from "./aiSettings";
import { AiFeatures, releaseGateBlocks, saveAiSettings } from "./sections/Security";
import { ConfirmDialog } from "./shared";

describe("AI processing switch", () => {
  it("sends acknowledgement: true only when turning AI on, after the person confirmed", () => {
    expect(aiSettingsPayload(true, "Pilot needs Ask MDARIX", true)).toEqual({
      ai_processing_allowed: true,
      reason: "Pilot needs Ask MDARIX",
      acknowledgement: true,
    });
    expect(aiSettingsPayload(false, "Pilot finished", false)).toEqual({
      ai_processing_allowed: false,
      reason: "Pilot finished",
    });
    expect(aiSettingsPayload(false, "Pilot finished", true)).not.toHaveProperty("acknowledgement");
    expect(() => aiSettingsPayload(true, "No confirmation", false)).toThrow(/acknowledgement/);
  });

  it("names the provider the content goes to, and says masking comes first", () => {
    expect(aiAcknowledgement("Anthropic")).toBe(
      "I acknowledge that records our AI features need for an answer will be sent to Anthropic, after personal information is masked.",
    );
    expect(aiAcknowledgement(null)).toContain("the AI provider configured for this server");
    expect(aiAcknowledgement("Anthropic", "Acme Medical")).toMatch(/^On Acme Medical's instruction/);
    expect(providerLabel("  ")).toBe("the AI provider configured for this server");
  });

  it("does not claim that every name is masked", () => {
    expect(MASKING_SUMMARY).toMatch(/names that are labelled or follow a title or role word/);
    expect(MASKING_SUMMARY).toMatch(/not always recognised/);
  });

  it("shows the acknowledgement as a checkbox and keeps the change disabled until it is ticked", () => {
    const html = renderToStaticMarkup(
      <ConfirmDialog
        request={{
          title: "Turn AI processing on?",
          body: "Body",
          confirmLabel: "Turn AI on",
          acknowledge: aiAcknowledgement("Anthropic"),
          run: async () => undefined,
          done: "On",
        }}
        onClose={() => undefined}
        onDone={() => undefined}
      />,
    );
    expect(html).toContain('type="checkbox"');
    expect(html).toContain("will be sent to Anthropic");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Turn AI on<\/button>/);
  });
});

describe("re-authentication and per-feature switches (C6, C12)", () => {
  it("sends the password and authenticator code when a customer administrator turns AI on", () => {
    expect(aiSettingsPayload(true, "Pilot needs AI now", true, { password: "pw", mfaCode: " 123456 " })).toEqual({
      ai_processing_allowed: true,
      reason: "Pilot needs AI now",
      acknowledgement: true,
      password: "pw",
      mfa_code: "123456",
    });
    expect(aiSettingsPayload(true, "Trial tries AI", true, { password: "pw", mfaCode: "" }, true)).toMatchObject({
      trial_acknowledgement: true,
    });
    expect(aiSettingsPayload(false, "Pilot paused AI", false, { password: "pw", mfaCode: "1" })).toEqual({
      ai_processing_allowed: false,
      reason: "Pilot paused AI",
    });
  });

  it("turns one feature on with the proof, off without it, and keeps AI processing as it is", () => {
    expect(aiFeaturePayload(true, "ask", true, "Turn on Ask", { password: "pw", mfaCode: "1" })).toEqual({
      ai_processing_allowed: true,
      reason: "Turn on Ask",
      features: { ask: true },
      password: "pw",
      mfa_code: "1",
    });
    expect(aiFeaturePayload(false, "ask", false, "Turn off Ask")).toEqual({
      ai_processing_allowed: false,
      reason: "Turn off Ask",
      features: { ask: false },
    });
    expect(() => aiFeaturePayload(true, "ask", true, "Turn on Ask")).toThrow(/password/);
  });

  it("locks a feature the service does not offer or allow, and shows it off", () => {
    const base = { key: "x", label: "X", intended_use: "u", never: "n", risk: "LOW" as const, enabled: false };
    expect(featureLock({ ...base, offered: false, platform_allowed: false })).toBe("Not offered");
    expect(featureLock({ ...base, offered: true, platform_allowed: false })).toBe("Not available on this service");
    expect(featureLock({ ...base, offered: true, platform_allowed: true })).toBeNull();
    const html = renderToStaticMarkup(
      <AiFeatures
        features={[
          {
            ...base,
            key: "regulatory_drafting",
            label: "Regulatory drafting",
            offered: false,
            platform_allowed: false,
          },
          { ...base, key: "ask", label: "Ask MDARIX", offered: true, platform_allowed: true },
        ]}
        onSwitch={() => undefined}
      />,
    );
    expect(html).toContain("Off · Not offered");
    expect(html).toContain("Off · turn on");
  });
});

describe("a change tied to the settings' version (D3)", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("sends the version the screen read, and nothing for an older server", () => {
    const change = aiSettingsPayload(false, "Pausing AI for the review", false);
    expect(withLockVersion(change, 4)).toEqual({ ...change, lock_version: 4 });
    expect(withLockVersion(change, null)).toEqual(change);
    expect(withLockVersion(change, 0).lock_version).toBe(0);
  });
  it("loads the current settings and shows the server's words when someone changed them meanwhile (409)", async () => {
    const body = { detail: { code: "STALE_RECORD", message: "Someone changed the AI settings since you opened them" } };
    const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 409 }));
    vi.stubGlobal("window", {
      location: { pathname: "/app/settings", search: "", replace: vi.fn() },
      setTimeout,
      clearTimeout,
    });
    vi.stubGlobal("fetch", fetch);
    const reload = vi.fn();
    await expect(
      saveAiSettings({ ai_processing_allowed: false, reason: "Pausing AI", lock_version: 3 }, reload),
    ).rejects.toMatchObject({ status: 409, code: "STALE_RECORD", message: body.detail.message });
    expect(reload).toHaveBeenCalledTimes(1);
    expect(
      JSON.parse(
        String((fetch.mock.calls[0] as unknown[])[1] && ((fetch.mock.calls[0] as unknown[])[1] as RequestInit).body),
      ),
    ).toMatchObject({
      lock_version: 3,
    });
  });
});

describe("the pilot release gate and a free trial (0.11.05 release, 18 Nov 2026)", () => {
  const closed = { enforced: true, ready: false } as never;

  it("does not keep a free trial's Turn AI on disabled: the server skips that gate for trials", () => {
    expect(releaseGateBlocks({ free_trial: true, release_gate: closed }, false)).toBe(false);
  });

  it("still blocks a paid organization until the gate is met, and never blocks turning AI off", () => {
    expect(releaseGateBlocks({ free_trial: false, release_gate: closed }, false)).toBe(true);
    expect(releaseGateBlocks({ free_trial: false, release_gate: closed }, true)).toBe(false);
  });
});
