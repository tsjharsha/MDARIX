import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Empty } from "../admin/console/charts";
import { ChapterRow } from "./sections/GettingStarted";
import type { StoryChapter } from "./trialStory";

// The register's "States" (stage 5, F): an empty list says what to do next; a refusal that can be predicted is said
// beside the control before the click and read with it; only the next chapter is the primary button.
const chapter = (code: string): StoryChapter => ({
  code,
  number: 1,
  title: `Chapter ${code}`,
  promise: "What MDARIX does",
  pain: "Why it matters",
  opens: { section: "Complaints", tab: "Triage" },
  finding: { value: 1, text: "1 finding", state: "ATTENTION" },
  acted: { done: false, count: 0 },
});

describe("states", () => {
  it("an empty list offers the one thing to do next", () => {
    const html = renderToStaticMarkup(
      <Empty
        title="Nothing to triage"
        detail="Calls appear here."
        action={<button type="button">Log a call</button>}
      />,
    );
    expect(html).toContain('<div class="ac-empty-action"><button type="button">Log a call</button></div>');
    expect(renderToStaticMarkup(<Empty title="Nothing" detail="Here." />)).not.toContain("ac-empty-action");
  });

  it("a screen the role may not open says so beside the disabled button, not only in a tooltip", () => {
    const html = renderToStaticMarkup(
      <ChapterRow chapter={chapter("A")} isNext allowed={false} onOpen={() => undefined} />,
    );
    expect(html).toContain('aria-describedby="chapter-A-reason"');
    expect(html).toContain('<p class="ms-reason" id="chapter-A-reason">Your role does not include this screen.</p>');
    expect(html).not.toContain("title=");
  });

  it("only the next chapter is a primary button (V13)", () => {
    const next = renderToStaticMarkup(<ChapterRow chapter={chapter("A")} isNext allowed onOpen={() => undefined} />);
    const other = renderToStaticMarkup(
      <ChapterRow chapter={chapter("B")} isNext={false} allowed onOpen={() => undefined} />,
    );
    expect(next).toContain('class="ac-primary"');
    expect(other).not.toContain('class="ac-primary"');
    expect(other).toContain('class="ac-secondary"');
  });
});
