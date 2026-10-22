import postcss from "postcss";
import { describe, expect, it } from "vitest";

// 0.10.43: list headings showed "About The Request" for "About the request": the global rule for th in styles.css
// capitalizes every word, and the lists' own heading rule (.ac-table th) did not undo it. Every list heading is written
// in sentence case (Table columns, app/tableSort.tsx), so the lists show them as written. Read as files: the test run
// does not load stylesheets.
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const read = (path: string): string => fs.readFileSync(new URL(path, import.meta.url), "utf8");

const transforms = (css: string, selector: string) => {
  const found: string[] = [];
  postcss.parse(css).walkRules((rule) => {
    if (!rule.selectors.includes(selector)) return;
    rule.walkDecls("text-transform", (decl) => {
      found.push(decl.value);
    });
  });
  return found;
};

describe("list headings", () => {
  it("are shown as written, not with every word capitalized", () => {
    // The global rule is still there for the older screens' own tables ...
    expect(transforms(read("../../../styles.css"), "th")).toContain("capitalize");
    // ... and the lists' heading rule overrides it.
    expect(transforms(read("./admin-console.css"), ".ac-table th")).toEqual(["none"]);
  });
});
