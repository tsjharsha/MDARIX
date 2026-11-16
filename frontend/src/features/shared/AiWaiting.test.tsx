import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AiWaiting, waitingLine } from "./AiWaiting";

// Hero front end (WHIF): a live AI call that takes seconds shows a counter and a skeleton, not a frozen word.
describe("waiting for a live AI answer", () => {
  it("says what it is doing with the seconds so far, over three skeleton lines", () => {
    const html = renderToStaticMarkup(<AiWaiting label="Writing the summary" />);
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain("Writing the summary · 0 s");
    expect(html.match(/class="ac-skeleton/g)).toHaveLength(3);
    expect(waitingLine("Suggesting IMDRF codes", 4)).toBe("Suggesting IMDRF codes · 4 s");
  });
});
