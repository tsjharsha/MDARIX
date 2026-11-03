import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type DragEvent,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type ThHTMLAttributes,
} from "react";
import {
  DEFAULT_COLUMN_WIDTH,
  MAX_COLUMN_WIDTH,
  MIN_COLUMN_WIDTH,
  RESIZE_STEP,
  RESIZE_STEP_LARGE,
  clampWidth,
  loadLayout,
  moveKeyBy,
  moveKeyTo,
  orderKeys,
  storeLayout,
  subscribeLayout,
  totalWidth,
  type ColumnLayout,
} from "./columnLayout";
import "./columns.css";

/** A list's saved layout, kept in step with every other open copy of the same list. */
export function useColumnLayout(id: string) {
  const [layout, setLayout] = useState<ColumnLayout>(() => loadLayout(id));
  useEffect(() => {
    setLayout(loadLayout(id));
    return subscribeLayout((changed, next) => {
      if (changed === id) setLayout(next);
    });
  }, [id]);
  return {
    layout,
    /** Show a layout without keeping it (while a column edge is being dragged). */
    preview: setLayout,
    /** Keep a layout in this browser. */
    commit: (next: ColumnLayout) => storeLayout(id, next),
  };
}

export type HeaderControls = {
  thProps: ThHTMLAttributes<HTMLTableCellElement> & Record<`data-${string}`, string>;
  className: string;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  grip: ReactNode;
};

type DragState = { key: string; over?: string; side?: "before" | "after" };

/** The scale the page is drawn at (styles.css, "Page scale"): screen distances divide by it to become CSS widths. */
function pageZoom(): number {
  return Number.parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
}

/**
 * Lets people arrange a list's columns: drag a heading onto another to move it (or Alt+Left / Alt+Right on the
 * heading), and drag the right edge of a heading to change its width (or arrow keys on that edge; a double-click
 * there returns every column to its automatic width). The arrangement is remembered per list in this browser.
 *
 * `keys` are the movable columns in their current order; `pinned` columns (row actions) stay last and are neither
 * moved nor resized. When `onReorder` is given the caller keeps the order (the field chooser does); otherwise the
 * order is saved here.
 */
export function useColumnControls({
  id,
  keys,
  pinned = [],
  onReorder,
}: {
  id: string;
  keys: string[];
  pinned?: string[];
  onReorder?: (keys: string[]) => void;
}) {
  const { layout, preview, commit } = useColumnLayout(id);
  const headRow = useRef<HTMLTableRowElement>(null);
  const resizing = useRef(false);
  const [drag, setDrag] = useState<DragState | null>(null);

  const order = onReorder ? keys : orderKeys(keys, layout.order);
  const all = [...order, ...pinned];
  const widths = layout.widths && Object.keys(layout.widths).length ? layout.widths : null;

  const reorder = (next: string[], focusKey?: string) => {
    if (next === order || next.every((key, index) => key === order[index])) return;
    if (onReorder) onReorder(next);
    else commit({ ...layout, order: next });
    if (focusKey) {
      // Moving a heading can move its button in the page; keep the keyboard on it.
      window.requestAnimationFrame(() =>
        headRow.current?.querySelector<HTMLElement>(`th[data-col="${CSS.escape(focusKey)}"] button`)?.focus(),
      );
    }
  };

  /** The widths the columns have on screen now, as the starting point for fixed widths. */
  const measured = (): Record<string, number> => {
    const result: Record<string, number> = {};
    headRow.current?.querySelectorAll<HTMLElement>("th[data-col]").forEach((cell) => {
      const key = cell.dataset.col;
      if (key) result[key] = clampWidth(cell.getBoundingClientRect().width / pageZoom());
    });
    return result;
  };
  const currentWidths = () => {
    const base = widths ? { ...widths } : measured();
    for (const key of all) base[key] ??= DEFAULT_COLUMN_WIDTH;
    return base;
  };

  const startResize = (key: string, event: ReactPointerEvent<HTMLSpanElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    resizing.current = true;
    const grip = event.currentTarget;
    const base = currentWidths();
    const startX = event.clientX;
    const startWidth = base[key];
    let latest = base;
    grip.setPointerCapture(event.pointerId);
    const move = (moveEvent: PointerEvent) => {
      latest = { ...base, [key]: clampWidth(startWidth + (moveEvent.clientX - startX) / pageZoom()) };
      preview({ ...layout, widths: latest });
    };
    const end = () => {
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", end);
      grip.removeEventListener("pointercancel", end);
      resizing.current = false;
      commit({ ...layout, widths: latest });
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", end);
    grip.addEventListener("pointercancel", end);
  };

  const resizeByKey = (key: string, event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    const base = currentWidths();
    const step = (event.shiftKey ? RESIZE_STEP_LARGE : RESIZE_STEP) * (event.key === "ArrowLeft" ? -1 : 1);
    commit({ ...layout, widths: { ...base, [key]: clampWidth(base[key] + step) } });
  };

  const header = (key: string, label: string): HeaderControls => {
    const movable = order.length > 1;
    const width = widths?.[key] ?? DEFAULT_COLUMN_WIDTH;
    const classes = [
      movable ? "col-movable" : "",
      drag?.key === key ? "col-dragging" : "",
      drag && drag.over === key ? `col-drop-${drag.side}` : "",
    ]
      .filter(Boolean)
      .join(" ");
    return {
      className: classes,
      thProps: {
        "data-col": key,
        draggable: movable,
        onDragStart: (event: DragEvent<HTMLTableCellElement>) => {
          if (resizing.current) {
            event.preventDefault();
            return;
          }
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", label);
          setDrag({ key });
        },
        onDragOver: (event: DragEvent<HTMLTableCellElement>) => {
          if (!drag || drag.key === key) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          const box = event.currentTarget.getBoundingClientRect();
          const side = event.clientX < box.left + box.width / 2 ? "before" : "after";
          if (drag.over !== key || drag.side !== side) setDrag({ ...drag, over: key, side });
        },
        onDrop: (event: DragEvent<HTMLTableCellElement>) => {
          event.preventDefault();
          if (drag && drag.key !== key) reorder(moveKeyTo(order, drag.key, key, drag.side ?? "before"));
          setDrag(null);
        },
        onDragEnd: () => setDrag(null),
      },
      onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => {
        if (!event.altKey || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
        event.preventDefault();
        reorder(moveKeyBy(order, key, event.key === "ArrowLeft" ? -1 : 1), key);
      },
      grip: (
        <span
          className="col-grip"
          role="separator"
          aria-orientation="vertical"
          aria-label={`Width of ${label}`}
          aria-valuemin={MIN_COLUMN_WIDTH}
          aria-valuemax={MAX_COLUMN_WIDTH}
          // A focusable separator needs its value (0.10.85, D3.8): the automatic width reads as the smallest.
          aria-valuenow={widths && width ? width : MIN_COLUMN_WIDTH}
          tabIndex={0}
          title="Drag to change the width (arrow keys also work). Double-click to return all columns to automatic widths."
          draggable={false}
          onPointerDown={(event) => startResize(key, event)}
          onKeyDown={(event) => resizeByKey(key, event)}
          onDoubleClick={(event) => {
            event.stopPropagation();
            commit({ ...layout, widths: undefined });
          }}
          onClick={(event) => event.stopPropagation()}
        />
      ),
    };
  };

  const tableStyle: CSSProperties | undefined = widths ? { width: totalWidth(all, widths) } : undefined;
  return {
    /** Movable columns in the order to show them. */
    order,
    headRowRef: headRow,
    /** True once the person moved (lists without a chooser) or resized columns. */
    customized: Boolean(widths || (!onReorder && layout.order?.length)),
    reset: () => commit({}),
    tableClassName: widths ? "col-fixed" : "",
    tableStyle,
    colgroup: widths ? (
      <colgroup>
        {all.map((key) => (
          <col key={key} style={{ width: widths[key] ?? DEFAULT_COLUMN_WIDTH }} />
        ))}
      </colgroup>
    ) : null,
    header,
    /** Header attributes for a pinned column, so its width is measured with the others. */
    pinnedProps: (key: string) => ({ "data-col": key }),
  };
}
