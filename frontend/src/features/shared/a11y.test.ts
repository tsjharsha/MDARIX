import { describe, expect, it } from "vitest";
import { noticeDue } from "./ConsentBanner";
import { nextTabIndex } from "./focus";
import { trapTab } from "./DialogBehaviour";

const storeOf = (values: Record<string, string>) => ({ getItem: (key: string) => values[key] ?? null });

describe("privacy notice", () => {
  it("shows until acknowledged on this device, and stays hidden for the session once dismissed", () => {
    expect(noticeDue({ local: storeOf({}), session: storeOf({}) })).toBe(true);
    expect(noticeDue({ local: storeOf({ "mdarix-compliance-consent": "accepted" }), session: storeOf({}) })).toBe(
      false,
    );
    expect(noticeDue({ local: storeOf({}), session: storeOf({ "mdarix-compliance-notice-dismissed": "1" }) })).toBe(
      false,
    );
  });
  it("shows the notice when storage cannot be read", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
    };
    expect(noticeDue({ local: broken, session: null })).toBe(true);
  });
});

describe("tab keyboard navigation", () => {
  it("moves with the arrow keys, wraps around, and jumps with Home and End", () => {
    expect(nextTabIndex("ArrowRight", 0, 3)).toBe(1);
    expect(nextTabIndex("ArrowRight", 2, 3)).toBe(0);
    expect(nextTabIndex("ArrowLeft", 0, 3)).toBe(2);
    expect(nextTabIndex("Home", 2, 3)).toBe(0);
    expect(nextTabIndex("End", 0, 3)).toBe(2);
    expect(nextTabIndex("Enter", 0, 3)).toBeNull();
    expect(nextTabIndex("ArrowRight", 0, 0)).toBeNull();
  });
});

describe("dialog focus trap", () => {
  const first = { id: "first" };
  const last = { id: "last" };
  it("wraps Tab from the last control to the first, and Shift+Tab from the first to the last", () => {
    expect(trapTab([first, last], last, false)).toBe(first);
    expect(trapTab([first, last], first, true)).toBe(last);
  });
  it("brings focus back into the dialog when it is outside", () => {
    expect(trapTab([first, last], { id: "page" }, false)).toBe(first);
    expect(trapTab([first, last], null, true)).toBe(last);
  });
  it("leaves Tab alone inside the dialog", () => {
    expect(trapTab([first, { id: "middle" }, last], first, false)).toBeNull();
    expect(trapTab([], first, false)).toBeNull();
  });
});
