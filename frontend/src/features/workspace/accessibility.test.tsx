import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ChipFilter, Hero } from "./sections/boardParts";

// Stage 5 accessibility (G). Read as files where a screen needs a session: the sign-out buttons and the drawer
// headings.
const fs = await import(/* @vite-ignore */ ["node", "fs"].join(":"));
const read = (path: string): string => fs.readFileSync(new URL(path, import.meta.url), "utf8");

describe("accessibility", () => {
  it("a chip filter is one Tab stop: only the chosen chip is focusable (roving tabindex)", () => {
    const html = renderToStaticMarkup(
      <ChipFilter
        label="Which events"
        options={[
          { value: "open", label: "To triage" },
          { value: "done", label: "Triaged" },
        ]}
        value="done"
        onChange={() => undefined}
      />,
    );
    expect(html).toContain('role="radiogroup"');
    expect(html).toMatch(/aria-checked="false" tabindex="-1"[^>]*>To triage/);
    expect(html).toMatch(/aria-checked="true" tabindex="0"[^>]*>Triaged/);
  });

  it("a hero announces its headline when it changes, not the whole section again", () => {
    const html = renderToStaticMarkup(<Hero tone="good" icon={null} eyebrow="Triage" title="4 events" detail="Long" />);
    expect(html).toContain('<h2 aria-live="polite">4 events</h2>');
    expect(html).not.toMatch(/<section[^>]*aria-live/);
  });

  it("the sign-out button's name is its visible text", () => {
    for (const path of [
      "./UserWorkspace.tsx",
      "../customer-admin/CustomerAdminControlPlane.tsx",
      "../admin/SimplifiedPlatformAdminScreen.tsx",
    ]) {
      const source = read(path);
      expect(source).not.toContain("Sign out of MDARIX");
      expect(source).not.toMatch(/>Logout</);
      expect(source).toContain('aria-label="Sign out"');
      expect(source).toContain('<span className="ac-hide-sm">Sign out</span>');
    }
  });

  it("workspace drawers go from h2 to h3, never h4", () => {
    const sections = fs.readdirSync(new URL("./sections/", import.meta.url)) as string[];
    const withH4 = sections.filter((name) => name.endsWith(".tsx") && /<h4\b/.test(read(`./sections/${name}`)));
    expect(withH4).toEqual([]);
    expect(read("../customer-admin/customer-admin.css")).toMatch(/\.ca-drawer h3 \{[^}]*font-weight: 600/);
  });
});
