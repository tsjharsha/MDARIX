import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SECOND_LOOK_STARTERS, starterProblem } from "./starters";
import { Starters } from "./sections/Starters";

describe("sentence starters for reasons", () => {
  it("never accepts a starter as the reason: it must be finished in the person's own words", () => {
    const starters = SECOND_LOOK_STARTERS.CONFIRMED;
    expect(starterProblem("Meets our complaint definition because ", starters)).toContain("own words");
    expect(starterProblem("Meets our complaint definition because harm", starters)).toContain("own words");
    expect(starterProblem("Meets our complaint definition because the patient was injured", starters)).toBeNull();
    expect(starterProblem("The patient was injured during infusion", starters)).toBeNull();
  });

  it("offers the starters as buttons that start the sentence", () => {
    const html = renderToStaticMarkup(<Starters starters={SECOND_LOOK_STARTERS.DISMISSED} onPick={() => undefined} />);
    expect(html).toContain("Start with:");
    expect(html).toContain("Not a complaint because…");
    expect(renderToStaticMarkup(<Starters starters={[]} onPick={() => undefined} />)).toBe("");
  });
});
