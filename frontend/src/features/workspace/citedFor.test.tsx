import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { focusText, type CitationOption } from "./sections/CitedFor";
import { ChapterRow } from "./sections/GettingStarted";
import type { StoryChapter } from "./trialStory";

const options: CitationOption[] = [
  {
    code: "CAPA_EFFECTIVENESS",
    label: "CAPAs closed without verifying they were effective",
    reference: "ISO 13485 8.5.2",
    chapter: "CAPA_EFFECTIVE",
  },
  { code: "RISK_FILE", label: "Risk file not updated", reference: "ISO 14971 clause 10", chapter: "RISK_FILE" },
];

describe("what the organization was cited for", () => {
  it("says the chosen themes in story order", () => {
    expect(focusText(["RISK_FILE", "CAPA_EFFECTIVENESS"], options)).toBe(
      "CAPAs closed without verifying they were effective; Risk file not updated",
    );
    expect(focusText([], options)).toBe("");
  });

  it("marks the chapters that answer it", () => {
    const chapter: StoryChapter = {
      code: "CAPA_EFFECTIVE",
      number: 6,
      title: "Prove each CAPA worked",
      promise: "p",
      pain: "q",
      opens: { section: "Records", tab: "Effectiveness checks" },
      finding: { value: 1, text: "1 CAPA closed without a check", state: "CRITICAL" },
      acted: { done: false, count: 0 },
      cited: true,
    };
    const html = renderToStaticMarkup(<ChapterRow chapter={chapter} isNext allowed onOpen={() => undefined} />);
    expect(html).toContain("You were cited for this");
    expect(
      renderToStaticMarkup(
        <ChapterRow chapter={{ ...chapter, cited: false }} isNext={false} allowed onOpen={() => undefined} />,
      ),
    ).not.toContain("You were cited for this");
  });
});
