// Light and dark. The product opens dark (Clinical Signal); the person's choice (Light, Dark or System), kept in this
// browser and never failing on a browser without storage; the top bar's menu; and only the shell switching it.
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_THEME, ThemeMenu, effectiveTheme, readTheme, saveTheme } from "./theme";
import type { SessionContext } from "./workspaceContext";
import userWorkspace from "./UserWorkspace.tsx?raw";

const session = { user_id: "u1" } as SessionContext;
const memory = () => {
  const kept = new Map<string, string>();
  return {
    getItem: (key: string) => kept.get(key) ?? null,
    setItem: (key: string, value: string) => void kept.set(key, value),
    removeItem: (key: string) => void kept.delete(key),
    kept,
  };
};

afterEach(() => vi.unstubAllGlobals());

describe("the person's theme", () => {
  it("follows the system when System is chosen, and the choice once made", () => {
    expect(effectiveTheme("system", true)).toBe("dark");
    expect(effectiveTheme("system", false)).toBe("light");
    expect(effectiveTheme("dark", false)).toBe("dark");
    expect(effectiveTheme("light", true)).toBe("light");
  });

  it("is dark until a person chooses, then kept per person in this browser; the default keeps nothing", () => {
    const storage = memory();
    vi.stubGlobal("window", { localStorage: storage });
    expect(DEFAULT_THEME).toBe("dark");
    expect(readTheme(session)).toBe("dark");
    saveTheme(session, "light");
    expect(storage.kept.get("mdarix.theme.u1")).toBe("light");
    expect(readTheme(session)).toBe("light");
    expect(readTheme({ user_id: "u2" } as SessionContext)).toBe("dark");
    saveTheme(session, "system");
    expect(readTheme(session)).toBe("system");
    saveTheme(session, "dark");
    expect(storage.kept.has("mdarix.theme.u1")).toBe(false);
    storage.setItem("mdarix.theme.u1", "purple");
    expect(readTheme(session)).toBe("dark");
  });

  it("never fails where the browser refuses storage", () => {
    const refused = () => {
      throw new Error("denied");
    };
    vi.stubGlobal("window", { localStorage: { getItem: refused, setItem: refused, removeItem: refused } });
    expect(readTheme(session)).toBe("dark");
    expect(() => saveTheme(session, "light")).not.toThrow();
  });
});

describe("the top bar's theme menu", () => {
  it("names the choice and what shows now, and offers Light, Dark and System with the current one checked", () => {
    const closed = renderToStaticMarkup(<ThemeMenu choice="system" theme="dark" onChoose={vi.fn()} />);
    expect(closed).toContain('aria-label="Theme: System (dark now)"');
    expect(closed).toContain('aria-haspopup="menu"');
    const open = renderToStaticMarkup(<ThemeMenu choice="dark" theme="dark" onChoose={vi.fn()} defaultOpen />);
    expect([...open.matchAll(/role="menuitemradio" aria-checked="(true|false)"/g)].map((m) => m[1])).toEqual([
      "false",
      "true",
      "false",
    ]);
    for (const label of ["Light", "Dark", "System"]) expect(open).toContain(`<span>${label}</span>`);
  });

  it("is applied by the new navigation's shell only, and sits on its top bar", () => {
    expect(userWorkspace).toContain("const look = useTheme(session, fresh);");
    expect(userWorkspace).toContain("<ThemeMenu choice={look.choice} theme={look.theme} onChoose={look.choose} />");
  });
});
