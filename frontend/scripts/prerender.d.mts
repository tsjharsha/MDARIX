// Types for scripts/prerender.mjs, so src/site/prerender.test.ts can import its helpers.
export const DIST: string;
export const RENDERER: string;
export const SITE_URL: string;
export const HOME_FILE: string;
export function outputFile(path: string): string;
export function headTags(head: { title: string; description: string; robots: string; url: string | null }): string[];
export function pageHtml(
  template: string,
  head: { title: string; description: string; robots: string; url: string | null },
  markup: string,
  stylesheet?: string | null,
): string;
export function sitemapPaths(xml: string): string[];
export function visibleText(markup: string): string;
export function moveInlineStyles(markup: string, classes: Map<string, string>): string;
export function inlineStylesheet(classes: Map<string, string>): string;
