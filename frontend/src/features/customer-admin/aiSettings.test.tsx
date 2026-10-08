import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MASKING_SUMMARY, aiAcknowledgement, aiSettingsPayload, providerLabel } from "./aiSettings";
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
