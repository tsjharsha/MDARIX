import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CompanyPage, HomePage, PlatformPage, ResourcesPage, SolutionsPage, TrustPage } from "../pages";
import { compactScenes } from "./compact";
import { SCENES } from "./index";

describe("animated scenes", () => {
  it("each draws with the picture's alt text as its accessible name", () => {
    for (const [name, Scene] of Object.entries({ ...SCENES, ...compactScenes })) {
      const html = renderToStaticMarkup(<Scene label={`alt for ${name}`} />);
      expect(html, name).toContain('role="img"');
      expect(html, name).toContain(`aria-label="alt for ${name}"`);
      expect(html, name).toContain('<svg viewBox="0 0 640 400"');
    }
  });

  it("have replaced every illustration on the website pages", () => {
    for (const Page of [HomePage, PlatformPage, SolutionsPage, TrustPage, ResourcesPage, CompanyPage]) {
      const html = renderToStaticMarkup(<Page />);
      expect(html, Page.name).not.toMatch(/<img[^>]+src="\/site\//);
    }
  });
});
