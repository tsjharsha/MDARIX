import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HomePage, SITE_LOOP } from "./pages";
import { LOOP_ORDER } from "../features/workspace/qualityLoop";

describe("website home", () => {
  it("draws the quality loop in story order with illustrative values", () => {
    expect(SITE_LOOP.map((station) => station.key)).toEqual(LOOP_ORDER.map((step) => step.code));
    expect(SITE_LOOP.filter((station) => station.done)).toHaveLength(2);
  });

  it("says the loop is synthetic and leads to the free trial and a one-to-one demo", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("Illustrative · synthetic data");
    expect(html).toContain("2 of 8 inspection checks clear");
    expect(html).toContain('href="/signup"');
    expect(html).toContain("Start free trial");
    expect(html).toContain("Book a one-to-one demo");
    expect(html).toContain('href="/request-demo"');
  });
});
