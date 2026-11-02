import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";

/** A row's further actions behind ⋯ (7.5: one visible action plus ⋯). Escape or a click outside closes it. */
export function RowMenu({ label, items }: { label: string; items: Array<{ label: string; onSelect: () => void }> }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node))
        setOpen(false);
    };
    window.addEventListener("keydown", close);
    window.addEventListener("pointerdown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("pointerdown", close);
    };
  }, [open]);
  if (!items.length) return null;
  return (
    <span className="uw-row-menu" ref={root}>
      <button
        type="button"
        className="ac-secondary"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <MoreHorizontal size={16} aria-hidden="true" />
      </button>
      {open && (
        <ul className="uw-row-menu-list">
          {items.map((item) => (
            <li key={item.label}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
