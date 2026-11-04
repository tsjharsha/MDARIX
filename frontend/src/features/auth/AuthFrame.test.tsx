import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AuthFrame, READY_LINES } from "./AuthFrame";

describe("the sign-up page's frame", () => {
  it("says how soon the workspace is ready as the server approves requests, its default until site-info answers", () => {
    const html = renderToStaticMarkup(
      <AuthFrame mode="signup">
        <p>form</p>
      </AuthFrame>,
    );
    // Release 0.10.48: personal addresses are approved at once too, by default.
    expect(html).toContain(
      "Ready within minutes with a company or personal email, isolated from every other customer.",
    );
    expect(READY_LINES["company-domains"]).toBe(
      "Ready within minutes with a company email, isolated from every other customer.",
    );
    expect(READY_LINES.off).not.toContain("within minutes");
  });

  it("leaves the other pages' points as they were", () => {
    const html = renderToStaticMarkup(
      <AuthFrame mode="signin">
        <p>form</p>
      </AuthFrame>,
    );
    // 0.10.85, D3.12: sign-in says in one line what MDARIX does for a QA/RA team.
    expect(html).toContain("Every complaint triaged, decided and reported on time, with the record to prove it.");
    expect(html).not.toContain("Ready within minutes");
  });
});
