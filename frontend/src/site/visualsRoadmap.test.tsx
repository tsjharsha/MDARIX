import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LifecyclePage, RoadmapPage } from "./pages";
import { capabilityStatus } from "./content";

describe("what you get, as a roadmap (the /roadmap page)", () => {
  it("shows every stage with its badge, each capability with its explanation, and the free trial", () => {
    const html = renderToStaticMarkup(<RoadmapPage />);
    for (const status of capabilityStatus) {
      expect(html).toContain(status.label);
      expect(html).toContain(status.badge);
      expect(html).toContain(status.promise);
      for (const item of status.items) expect(html).toContain(item.title);
    }
    expect(html).toContain("Included in your free trial");
    expect(capabilityStatus.map((status) => status.badge)).toEqual(["Live now", "Next", "Planned"]);
    // Later stages say what they add and the running total.
    const [today, next, planned] = capabilityStatus.map((status) => status.items.length);
    expect(html).toContain(`${today} capabilities`);
    expect(html).toContain(`+${next} more · ${today + next} in total`);
    expect(html).toContain(`+${planned} more · ${today + next + planned} in total`);
  });
});

describe("design and development phases", () => {
  it("draws phases 0 to 6 with their records instead of the old picture", () => {
    const html = renderToStaticMarkup(<LifecyclePage />);
    for (let phase = 0; phase <= 6; phase++) expect(html).toContain(`Phase ${phase}`);
    for (const record of ["User needs", "Design inputs", "Design outputs", "Verification", "Validation"])
      expect(html).toContain(record);
    expect(html).toContain("Risk file");
    expect(html).toContain("MDARIX starts here");
    expect(html).not.toContain("medtech-product-lifecycle-hero");
  });
});
