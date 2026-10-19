import postcss from "postcss";
import { describe, expect, it } from "vitest";

// The confirmation dialog's red button takes its colour from --ca-danger. Every console root carries the class
// admin-console (user workspace, platform administration, customer administration), so the token must be defined
// there: in 0.10.29 it was defined only for the customer console, and the workspace's "Remove from trial" button
// was white text on no background. Read as a file: the test run does not load stylesheets.
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const css: string = fs.readFileSync(new URL("./customer-admin.css", import.meta.url), "utf8");

describe("console colour tokens", () => {
  it("defines the danger colour on every console root, so red confirm buttons are visible everywhere", () => {
    const roots: string[] = [];
    postcss.parse(css).walkRules((rule) => {
      if (rule.nodes.some((node) => node.type === "decl" && node.prop === "--ca-danger")) roots.push(...rule.selectors);
    });
    expect(roots).toContain(".admin-console");
  });
});
