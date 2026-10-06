import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import guide from "./PILOT_GUIDE.md?raw";
import { PilotGuidePage, guideBlocks } from "./PilotGuidePage";

describe("pilot guide page", () => {
  it("covers what a pilot needs: roles, first steps, the workflow, sign-off, exports and help", () => {
    const { title, blocks } = guideBlocks(guide);
    expect(title).toBe("MDARIX pilot guide");
    const headings = blocks.filter((block) => block.kind === "heading").map((block) => block.text);
    for (const section of ["Roles", "investigation workflow", "sign-off", "Exports", "Getting help"])
      expect(headings.some((heading) => heading.includes(section))).toBe(true);
  });

  it("renders sections as h2 under the page's single h1, with safe links only", () => {
    const html = renderToStaticMarkup(
      <PilotGuidePage source={"# Guide\n\n## First\n\nSee [docs](javascript:alert(1)) and **this**.\n"} />,
    );
    expect(html.match(/<h1/g)).toHaveLength(1);
    expect(html).toContain("<h2>First</h2>");
    expect(html).toContain("<strong>this</strong>");
    expect(html).not.toContain("javascript:");
  });
});
