import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CompanyPage, HomePage, ResourcesPage, RoadmapPage } from "./pages";
import { postMarketResources } from "./legacyContent";
import { TRIAL_VIDEOS } from "./videos";

// What the website says about itself matches what MDARIX does (the final pre-launch review, 0.10.33).
describe("website claims", () => {
  it("does not say the inspection checks are drawn from 2026 FDA warning letters alone (CMP-09)", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).not.toContain("drawn from 2026 FDA warning letters");
    // The website names no warning letters at all (owner rule, 0.10.45).
    expect(html).not.toMatch(/warning letter/i);
    expect(html).toContain("shaped by what FDA inspections cite");
    expect(html).toContain("EU, UK and Canadian vigilance rules");
  });

  it("states the real approval rule for trial requests (CMP-19)", () => {
    const html = renderToStaticMarkup(<CompanyPage />);
    expect(html).not.toContain("We review every request");
    expect(html).toContain("approved automatically and ready within minutes, up to a daily limit");
    // Since 0.10.48 a personal address is approved automatically too; a disposable one is reviewed (owner decision).
    expect(html).toContain("With a company or personal email your trial is approved automatically");
    expect(html).toContain("requests from disposable email addresses are reviewed by the MDARIX team");
    expect(html).not.toContain("requests from personal email addresses are reviewed");
    expect(TRIAL_VIDEOS.map((video) => video.summary).join(" ")).not.toContain("prepared for you at once");
  });

  it("agrees on the dedicated database: every pilot has one, trials share the platform (CMP-20)", () => {
    const company = renderToStaticMarkup(<CompanyPage />);
    expect(company).toContain("dedicated MDARIX transactional database");
    expect(company).toContain("Free trials share the MDARIX platform");
    // The paid step after the trial is a pilot wherever a customer reads it (UX-09).
    expect(company).toContain("Then a pilot on your real data.");
    expect(company).not.toContain("MVP");
    const roadmap = renderToStaticMarkup(<RoadmapPage />);
    // Every pilot already has its own database, so the roadmap plans no database item (owner decision 2026-10-19).
    expect(roadmap).not.toContain("A dedicated database for each customer");
    expect(roadmap).not.toContain("own cloud");
  });

  it("lists the FDA AI guidance under its official title (CMP-23)", () => {
    const guidance = postMarketResources.find((item) => item.href.includes("artificial-intelligence-enabled"));
    expect(guidance?.title).toBe(
      "Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations (draft guidance)",
    );
    expect(renderToStaticMarkup(<ResourcesPage />)).toContain("Lifecycle Management and Marketing Submission");
  });

  it("names no warning letters and no class actions anywhere in the website's source (owner rule, 0.10.47)", async () => {
    // Read as files, so text that only some pages render (the videos' summaries, scenes, the share card) is covered.
    // The legal documents (legal/*.md) are not here: they are versioned by their hash and change only with a lawyer.
    const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
    const files = (folder: URL, pattern: RegExp): string[] =>
      fs
        .readdirSync(folder, { withFileTypes: true, recursive: true })
        .filter((entry: { isFile(): boolean; name: string }) => entry.isFile() && pattern.test(entry.name))
        .map((entry: { name: string; parentPath: string }) => `${entry.parentPath}/${entry.name}`);
    const sources = [
      ...files(new URL("./", import.meta.url), /^(?!.*\.test\.).*\.(tsx?|css)$/),
      ...files(new URL("../../public/", import.meta.url), /\.(txt|xml|svg|html|css)$/),
      new URL("../../index.html", import.meta.url),
    ];
    expect(sources.length).toBeGreaterThan(20);
    const mentions = sources.filter((file) =>
      /warning[\s-]+letter|class[\s-]+action/i.test(fs.readFileSync(file, "utf8")),
    );
    expect(mentions.map(String)).toEqual([]);
  });
});
