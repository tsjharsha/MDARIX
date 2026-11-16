import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  MASKING_SUMMARY,
  aiAcknowledgement,
  aiFeaturePayload,
  aiSettingsPayload,
  featureLock,
  providerLabel,
} from "./aiSettings";
import { AiFeatures } from "./sections/Security";
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
