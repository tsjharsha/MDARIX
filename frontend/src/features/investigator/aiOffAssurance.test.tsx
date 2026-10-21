import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { InvestigationTabSummary, noAiOutputText } from "./InvestigationWorkspacePanel";
import { aiStatusBanner } from "../workspace/intelligence";

// 0.10.41 (DEV-010): with AI off, "How MDARIX checks AI output" says so in a plain sentence instead of reading empty.

const summary = (aiBanner: ReturnType<typeof aiStatusBanner>) =>
  renderToStaticMarkup(
    <InvestigationTabSummary
      activeTab="assurance"
      workspace={null}
      analysis={null}
      hypothesisSet={null}
      unknownSet={null}
      failureChains={null}
      brief={null}
      onOpenDecision={() => undefined}
      aiBanner={aiBanner}
    />,
  );

describe("How MDARIX checks AI output, with AI off", () => {
  it("says there is no AI output to check, in the words of the AI-off banner", () => {
    const trial = aiStatusBanner({ enabled: false, trial: true });
    expect(trial && noAiOutputText(trial)).toBe(
      "AI is off for free trials, so there is no AI output on this case to check.",
    );
    const off = aiStatusBanner({ enabled: false });
    expect(off && noAiOutputText(off)).toBe(
      "AI is switched off for your organization, so there is no AI output on this case to check.",
    );
    const html = summary(trial);
    expect(html).toContain("How MDARIX checks AI output");
    expect(html).toContain("AI is off for free trials, so there is no AI output on this case to check.");
    expect(html).toContain("No AI output to check");
  });

  it("reads as before while AI can run", () => {
    const html = summary(null);
    expect(html).toContain("What MDARIX checks in every AI result before you see it.");
    expect(html).toContain("Every AI result is checked");
    expect(html).not.toContain("no AI output");
  });
});
