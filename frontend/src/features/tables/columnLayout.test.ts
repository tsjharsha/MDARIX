import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_COLUMN_WIDTH,
  MAX_COLUMN_WIDTH,
  MIN_COLUMN_WIDTH,
  clampWidth,
  loadLayout,
  moveKeyBy,
  moveKeyTo,
  orderKeys,
  storeLayout,
  subscribeLayout,
  totalWidth,
} from "./columnLayout";

describe("orderKeys", () => {
  it("keeps the default order when nothing is saved", () => {
    expect(orderKeys(["a", "b", "c"], null)).toEqual(["a", "b", "c"]);
    expect(orderKeys(["a", "b", "c"], [])).toEqual(["a", "b", "c"]);
  });
  it("follows the saved order and drops columns the list no longer has", () => {
    expect(orderKeys(["a", "b", "c"], ["c", "x", "a", "b"])).toEqual(["c", "a", "b"]);
  });
  it("puts a new column after the column it follows by default", () => {
    expect(orderKeys(["a", "b", "new", "c"], ["c", "b", "a"])).toEqual(["c", "b", "new", "a"]);
    expect(orderKeys(["new", "a", "b"], ["b", "a"])).toEqual(["new", "b", "a"]);
  });
  it("ignores duplicate saved keys", () => {
    expect(orderKeys(["a", "b"], ["b", "b", "a"])).toEqual(["b", "a"]);
  });
});

describe("moving a column", () => {
  it("drops a column before or after another", () => {
    expect(moveKeyTo(["a", "b", "c", "d"], "a", "c", "before")).toEqual(["b", "a", "c", "d"]);
    expect(moveKeyTo(["a", "b", "c", "d"], "a", "c", "after")).toEqual(["b", "c", "a", "d"]);
    expect(moveKeyTo(["a", "b", "c", "d"], "d", "a", "before")).toEqual(["d", "a", "b", "c"]);
  });
  it("leaves the order alone for a drop on itself or an unknown column", () => {
    const order = ["a", "b"];
    expect(moveKeyTo(order, "a", "a", "after")).toBe(order);
    expect(moveKeyTo(order, "a", "x", "after")).toBe(order);
  });
  it("moves one place left or right, never past either end", () => {
    expect(moveKeyBy(["a", "b", "c"], "b", -1)).toEqual(["b", "a", "c"]);
    expect(moveKeyBy(["a", "b", "c"], "b", 1)).toEqual(["a", "c", "b"]);
    const order = ["a", "b"];
    expect(moveKeyBy(order, "a", -1)).toBe(order);
    expect(moveKeyBy(order, "b", 1)).toBe(order);
  });
});

describe("widths", () => {
  it("keeps widths within the allowed range, in whole pixels", () => {
    expect(clampWidth(10)).toBe(MIN_COLUMN_WIDTH);
    expect(clampWidth(5000)).toBe(MAX_COLUMN_WIDTH);
    expect(clampWidth(150.6)).toBe(151);
    expect(clampWidth(Number.NaN)).toBe(MIN_COLUMN_WIDTH);
  });
  it("adds the default width for columns without one", () => {
    expect(totalWidth(["a", "b"], { a: 100 })).toBe(100 + DEFAULT_COLUMN_WIDTH);
  });
});

describe("saved layouts", () => {
  // The unit tests run without a browser: a small in-memory localStorage stands in for it.
  beforeAll(() => {
    const store = new Map<string, string>();
    const localStorage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
      removeItem: (key: string) => void store.delete(key),
      clear: () => store.clear(),
    };
    (globalThis as any).window ??= { localStorage };
  });
  beforeEach(() => window.localStorage.clear());

  it("round-trips a layout and tells open copies of the list", () => {
    const heard: string[] = [];
    const stop = subscribeLayout((id) => heard.push(id));
    storeLayout("admin:Customers", { order: ["b", "a"], widths: { a: 120 } });
    stop();
    expect(loadLayout("admin:Customers")).toEqual({ order: ["b", "a"], widths: { a: 120 } });
    expect(heard).toEqual(["admin:Customers"]);
  });
  it("removes the saved entry when the layout is reset", () => {
    storeLayout("list:x", { widths: { a: 120 } });
    storeLayout("list:x", {});
    expect(window.localStorage.getItem("mdarix.columnLayout.list:x")).toBeNull();
    expect(loadLayout("list:x")).toEqual({});
  });
  it("ignores a damaged saved value", () => {
    window.localStorage.setItem("mdarix.columnLayout.list:y", '{"widths":{"a":"wide"}}');
    expect(loadLayout("list:y")).toEqual({});
    window.localStorage.setItem("mdarix.columnLayout.list:z", "not json");
    expect(loadLayout("list:z")).toEqual({});
  });
});
