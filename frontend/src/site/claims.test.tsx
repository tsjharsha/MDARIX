import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CompanyPage, HomePage, PlatformPage, TrustPage } from "./pages";
import { TRIAL_VIDEOS } from "./videos";
import { renderPage } from "./prerender";
import { INDEXED_PATHS } from "./seo";

// What the website says about itself matches what MDARIX does (the final pre-launch review, 0.10.33; site refresh).
describe("website claims", () => {
  it("claims no certification, no price, no customers and no measured results it does not have", () => {
    for (const path of INDEXED_PATHS) {
      const html = renderPage(path);
      // Certification is only ever mentioned to say MDARIX does not claim or hold it (Trust and Security pages).
      const claims = html.replace(/MDARIX does not (claim|hold)[^.]*\./g, "");
      expect(claims, path).not.toMatch(/SOC ?2|ISO 27001 certifi|Part 11 compliant|HIPAA compliant|certified/i);
      expect(html, path).not.toMatch(/[$€£₹]\s?\d|\bUSD\b|\bINR\b|per month|per year/);
      expect(html, path).not.toMatch(/trusted by|customers? like|\d+% (faster|fewer|less)|ROI/i);
    }
    const trust = renderToStaticMarkup(<TrustPage />);
    expect(trust).toContain("MDARIX is not yet a validated (GxP) system.");
    expect(trust).toContain("MDARIX does not claim ISO 27001 certification");
  });

  it("says a person decides and submits, and that AI only proposes", () => {
    for (const page of [<HomePage key="h" />, <PlatformPage key="p" />, <TrustPage key="t" />]) {
      const html = renderToStaticMarkup(page);
      expect(html).not.toMatch(/MDARIX (files|submits) (the|your|every) report/i);
    }
    expect(renderToStaticMarkup(<TrustPage />)).toContain("An AI proposal is never a signature.");
    expect(renderToStaticMarkup(<HomePage />)).toContain("AI may propose; a person reviews.");
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
    const platform = renderToStaticMarkup(<PlatformPage />);
    // Every pilot already has its own database, so nothing plans one (owner decision 2026-10-19).
    expect(platform).toContain("A dedicated database for your organization");
    expect(platform).not.toContain("own cloud");
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
