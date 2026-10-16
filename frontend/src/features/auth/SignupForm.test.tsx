import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SignupForm } from "./SignupForm";
import { GUIDE_STEPS } from "../help/trialGuide";

describe("free trial request form", () => {
  it("says before the request that two-factor sign-in needs an authenticator app", () => {
    const html = renderToStaticMarkup(<SignupForm />);
    expect(html).toContain("Have your phone ready.");
    expect(html).toContain("two-factor sign-in (MFA)");
    expect(html).toContain("authenticator app on your phone");
    // The trial guide's first step says it too, so people reading the guide first are ready.
    expect(GUIDE_STEPS[0].actions.join(" ")).toContain("authenticator app on your phone");
  });
});
