import { isValidElement, useMemo, useState, type KeyboardEvent, type ReactNode, type ThHTMLAttributes } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

/**
 * Click-to-sort for every list in the app. A heading click sorts ascending, a second click descending, a third
 * restores the order the server gave. Numbers sort as numbers, dates as dates, text naturally ("Tenant 2" before
 * "Tenant 10"), and empty values always go last whichever the direction.
 */

export type SortDirection = "ascending" | "descending";
export type SortState = { key: string; direction: SortDirection } | null;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** The text a rendered cell shows, for cells whose value is only known as React output. */
export function nodeText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number" || typeof node === "bigint") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join(" ").trim();
  if (isValidElement<{ children?: ReactNode; value?: unknown; label?: unknown }>(node)) {
    const { children, value, label } = node.props;
    const inner = nodeText(children);
    if (inner) return inner;
    // Badges and similar components receive what they show as a prop rather than as children.
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (typeof label === "string" || typeof label === "number") return String(label);
  }
  return "";
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === "string" && !value.trim()) || value === "—";
}

function comparable(value: unknown): number | string {
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (value instanceof Date) return value.getTime();
  const text = String(value).trim();
  if (ISO_DATE.test(text)) {
    const time = Date.parse(text);
    if (!Number.isNaN(time)) return time;
  }
  // "1,234", "12.5 %", "-3": numeric text sorts by its number.
  const numeric = text.replace(/[,%\s]/g, "");
  if (numeric && /^-?\d+(\.\d+)?$/.test(numeric)) return Number(numeric);
  return text;
}

/** Compare two cell values for an ascending sort (empty values are handled by the caller). */
export function compareValues(left: unknown, right: unknown): number {
  const a = comparable(left);
  const b = comparable(right);
  if (typeof a === "number" && typeof b === "number") return a - b;
  return collator.compare(String(a), String(b));
}

/** Rows in the chosen order; a stable sort, so equal values keep the server's order. */
export function sortRows<T>(rows: T[], sort: SortState, valueFor: (row: T, key: string) => unknown): T[] {
  if (!sort) return rows;
  const factor = sort.direction === "ascending" ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, value: valueFor(row, sort.key) }))
    .sort((a, b) => {
      const emptyA = isEmpty(a.value);
      const emptyB = isEmpty(b.value);
      if (emptyA || emptyB) return emptyA === emptyB ? a.index - b.index : emptyA ? 1 : -1;
      return compareValues(a.value, b.value) * factor || a.index - b.index;
    })
    .map((item) => item.row);
}

/** The next state after a click on a heading: ascending, then descending, then the original order. */
export function nextSort(current: SortState, key: string): SortState {
  if (!current || current.key !== key) return { key, direction: "ascending" };
  return current.direction === "ascending" ? { key, direction: "descending" } : null;
}

export function useSortedRows<T>(rows: T[], valueFor: (row: T, key: string) => unknown) {
  const [sort, setSort] = useState<SortState>(null);
  // valueFor is usually a new function each render; the rows and the chosen sort decide the order.
  const sorted = useMemo(() => sortRows(rows, sort, valueFor), [rows, sort]);
  return { sorted, sort, toggle: (key: string) => setSort((current) => nextSort(current, key)) };
}

/** A column heading that sorts its list when clicked; announces the order to screen readers (aria-sort). */
export function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  className,
  thProps,
  onKeyDown,
  children,
}: {
  label: ReactNode;
  sortKey: string;
  sort: SortState;
  onSort: (key: string) => void;
  className?: string;
  /** Extra heading attributes (moving a column: features/tables/useColumnControls.tsx). */
  thProps?: ThHTMLAttributes<HTMLTableCellElement> & Record<`data-${string}`, string>;
  onKeyDown?: (event: KeyboardEvent<HTMLButtonElement>) => void;
  /** Shown after the heading's button (the edge that resizes the column). */
  children?: ReactNode;
}) {
  const active = sort?.key === sortKey ? sort.direction : null;
  const Icon = active === "ascending" ? ArrowUp : active === "descending" ? ArrowDown : ArrowUpDown;
  const text = nodeText(label);
  return (
    <th scope="col" {...thProps} className={className || undefined} aria-sort={active ?? "none"}>
      <button
        type="button"
        className={`table-sort${active ? " active" : ""}`}
        onClick={() => onSort(sortKey)}
        onKeyDown={onKeyDown}
        title={
          (active === "ascending"
            ? `Sorted by ${text}, ascending. Click for descending.`
            : active === "descending"
              ? `Sorted by ${text}, descending. Click to restore the original order.`
              : `Sort by ${text}`) +
          (thProps?.draggable ? " Drag the heading to move the column (or Alt+Left / Alt+Right)." : "")
        }
      >
        <span>{label}</span>
        <Icon size={13} aria-hidden="true" className="table-sort-icon" />
      </button>
      {children}
    </th>
  );
}

/**
 * Sorting done by the server, for lists it sends one page at a time: a heading click asks the server for that order
 * across every page (the `sort` and `order` request parameters) instead of reordering the rows on screen.
 * `onChange` runs on every change, typically to go back to the first page.
 */
export function useServerSort(onChange?: () => void, initial: SortState = null) {
  const [sort, setSort] = useState<SortState>(initial);
  return {
    sort,
    onSort: (key: string) => {
      setSort((current) => nextSort(current, key));
      onChange?.();
    },
  };
}

/** The request parameters for a server sort (none when the list keeps its usual order). */
export function sortParams(sort: SortState): Record<string, string> {
  return sort ? { sort: sort.key, order: sort.direction === "ascending" ? "asc" : "desc" } : {};
}
