import { describe, expect, it } from "vitest";
import { REVIEW_NOTICE, attachmentProblem, repliesSummary, replyBody } from "./MyWork";

describe("supplier replies", () => {
  it("sends the note and the uploaded file only when there is one", () => {
    expect(replyBody("  CoC received  ")).toEqual({ note: "CoC received" });
    expect(replyBody("CoC received", "att-1")).toEqual({ note: "CoC received", attachment_id: "att-1" });
  });

  it("accepts the file types and size the server accepts", () => {
    expect(attachmentProblem(null)).toBeNull();
    expect(attachmentProblem({ type: "application/pdf", size: 1000 })).toBeNull();
    expect(attachmentProblem({ type: "application/zip", size: 1000 })).toMatch(/PDF/);
    expect(attachmentProblem({ type: "image/png", size: 11 * 1024 * 1024 })).toMatch(/10 MB/);
  });

  it("summarizes the exchange and says replies are never evidence automatically", () => {
    expect(repliesSummary([], String)).toBe("No reply yet");
    expect(
      repliesSummary(
        [
          { id: "1", note: "a", recorded_at: "first" },
          { id: "2", note: "b", recorded_at: "second" },
        ],
        String,
      ),
    ).toBe("2 replies, latest second");
    expect(REVIEW_NOTICE).toMatch(/never accepted as evidence automatically/);
  });
});
