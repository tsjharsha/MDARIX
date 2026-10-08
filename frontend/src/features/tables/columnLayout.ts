// Moving and resizing the columns of a list: the order people chose, the widths they set, and where both are kept.

export type ColumnLayout = {
  /** Column keys in the order the person chose (lists without a field chooser only). */
  order?: string[];
  /** Width in pixels per column key; once any width is set the list uses fixed widths for every column. */
  widths?: Record<string, number>;
};

export const MIN_COLUMN_WIDTH = 56;
export const MAX_COLUMN_WIDTH = 900;
/** Width of a column that appears after the widths were set (a field added later). */
export const DEFAULT_COLUMN_WIDTH = 160;
/** Keyboard resize steps: arrow keys, and arrow keys with Shift. */
export const RESIZE_STEP = 16;
export const RESIZE_STEP_LARGE = 64;

export const clampWidth = (width: number) =>
  Math.round(Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, Number.isFinite(width) ? width : 0)));

/**
 * The list's columns in the saved order. Saved keys the list no longer has are dropped; columns the saved order does
 * not know (a new column) keep their place after the column they follow by default.
 */
export const orderKeys = (keys: string[], saved?: string[] | null): string[] => {
  if (!saved?.length) return keys;
  const result = saved.filter((key, index) => keys.includes(key) && saved.indexOf(key) === index);
  keys.forEach((key, index) => {
    if (result.includes(key)) return;
    const before = keys
      .slice(0, index)
      .reverse()
      .find((previous) => result.includes(previous));
    result.splice(before === undefined ? 0 : result.indexOf(before) + 1, 0, key);
  });
  return result;
};

/** Drop `key` before or after `target` (dragging a heading onto another). */
export const moveKeyTo = (order: string[], key: string, target: string, side: "before" | "after"): string[] => {
  if (key === target || !order.includes(key) || !order.includes(target)) return order;
  const rest = order.filter((item) => item !== key);
  const at = rest.indexOf(target) + (side === "after" ? 1 : 0);
  return [...rest.slice(0, at), key, ...rest.slice(at)];
};

/** Move `key` one place left (-1) or right (+1). */
export const moveKeyBy = (order: string[], key: string, delta: -1 | 1): string[] => {
  const from = order.indexOf(key);
  const to = from + delta;
  if (from < 0 || to < 0 || to >= order.length) return order;
  const next = [...order];
  [next[from], next[to]] = [next[to], next[from]];
  return next;
};

/** Total width of a fixed-width list: the set widths, and the default for columns without one. */
export const totalWidth = (keys: string[], widths: Record<string, number>) =>
  keys.reduce((sum, key) => sum + (widths[key] ?? DEFAULT_COLUMN_WIDTH), 0);

const STORAGE_PREFIX = "mdarix.columnLayout.";

const isLayout = (value: unknown): value is ColumnLayout => {
  if (!value || typeof value !== "object") return false;
  const { order, widths } = value as ColumnLayout;
  if (order !== undefined && !(Array.isArray(order) && order.every((key) => typeof key === "string"))) return false;
  if (widths !== undefined && (typeof widths !== "object" || widths === null)) return false;
  return Object.values(widths ?? {}).every((width) => typeof width === "number" && Number.isFinite(width));
};

/** The layout saved for a list in this browser (a convenience; it may be missing). */
export const loadLayout = (id: string): ColumnLayout => {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + id);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return isLayout(parsed) ? parsed : {};
  } catch {
    return {};
  }
};

type Listener = (id: string, layout: ColumnLayout) => void;
const listeners = new Set<Listener>();

/** Keep a list's layout (an empty layout removes it) and tell every open copy of that list. */
export const storeLayout = (id: string, layout: ColumnLayout) => {
  const empty = !layout.order?.length && !Object.keys(layout.widths ?? {}).length;
  try {
    if (empty) window.localStorage.removeItem(STORAGE_PREFIX + id);
    else window.localStorage.setItem(STORAGE_PREFIX + id, JSON.stringify(layout));
  } catch {
    // Storage can be unavailable (private window, blocked site data); the layout then lasts for this visit.
  }
  listeners.forEach((listener) => listener(id, empty ? {} : layout));
};

export const subscribeLayout = (listener: Listener) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
