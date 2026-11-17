import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TrialOrganizations, trialFromAddress } from "./TrialOrganizations";

// Hero review 2, fix pass 3: a trial's page stands alone (F-T1) and can be opened from the address (F-T5).

describe("F-T1 / F-T5: a trial's own page", () => {
  it("reads the trial from the address", () => {
    expect(trialFromAddress("?trial=t-1")).toBe("t-1");
    expect(trialFromAddress("?x=1")).toBeNull();
    expect(trialFromAddress("")).toBeNull();
  });

  it("leaves out the list's tiles while a trial is open, and shows them on the list", () => {
    const list = renderToStaticMarkup(<TrialOrganizations section="Trials" onSection={() => undefined} />);
    expect(list).toContain("Trials at a glance");
    const page = renderToStaticMarkup(
      <TrialOrganizations section="Trials" onSection={() => undefined} initialTrial="t-1" />,
    );
    expect(page).not.toContain("Trials at a glance");
  });
});
