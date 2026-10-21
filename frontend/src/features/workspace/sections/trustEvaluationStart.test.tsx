import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TrustEvaluation } from "./TrustEvaluation";

// 0.10.41 (SEC-08): only a Platform Administrator starts a golden evaluation (the server refuses anyone else), so
// the workspace's Trust page shows the published result alone and Platform Admin > AI > Evaluations offers the run.

describe("who is offered to start an evaluation", () => {
  it("offers the run in Platform Admin only", () => {
    const workspace = renderToStaticMarkup(<TrustEvaluation />);
    expect(workspace).toContain("How the AI performs on our test cases");
    expect(workspace).not.toContain("Start evaluation");
    expect(renderToStaticMarkup(<TrustEvaluation canStart />)).toContain("Start evaluation");
  });
});
