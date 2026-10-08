import { useEffect, useRef } from "react";

// Open dialogs, newest last: Escape closes only the one on top, and only the top one keeps Tab inside itself.
const openDialogs: symbol[] = [];

const FOCUSABLE =
  'input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

/**
 * Where Tab should go to stay inside a dialog: from the last control back to the first (Shift+Tab: first to last),
 * and into the dialog when focus has left it. Null means "let the browser move focus as usual".
 */
export function trapTab<T>(controls: T[], active: T | null, backwards: boolean): T | null {
  if (!controls.length) return null;
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (active === null || !controls.includes(active)) return backwards ? last : first;
  if (!backwards && active === last) return first;
  if (backwards && active === first) return last;
  return null;
}

/**
 * Keyboard behavior for a modal dialog, placed as the first child of its backdrop: focus moves into the dialog when
 * it opens, Tab and Shift+Tab stay inside it, Escape closes it from anywhere on the page, and focus returns to what
 * opened it when it closes.
 */
export function DialogBehaviour({ onClose }: { onClose: () => void }) {
  const marker = useRef<HTMLSpanElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const id = Symbol("dialog");
    openDialogs.push(id);
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const backdrop = marker.current?.parentElement ?? null;
    const dialog =
      backdrop?.querySelector<HTMLElement>('[role="dialog"], [role="alertdialog"]') ?? backdrop ?? undefined;
    const first = dialog?.querySelector<HTMLElement>(FOCUSABLE);
    if (first) first.focus();
    else if (dialog) {
      if (!dialog.hasAttribute("tabindex")) dialog.setAttribute("tabindex", "-1");
      dialog.focus();
    }
    const onKey = (event: KeyboardEvent) => {
      if (openDialogs[openDialogs.length - 1] !== id) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      // Controls are read on every key press: a dialog's content changes (an error appears, a step advances).
      const controls = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => !element.closest("[hidden]") && element.getClientRects().length > 0,
      );
      if (!controls.length) {
        event.preventDefault(); // nothing to move to: focus stays on the dialog itself
        return;
      }
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const target = trapTab(controls, active, event.shiftKey);
      if (target) {
        event.preventDefault();
        target.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      openDialogs.splice(openDialogs.indexOf(id), 1);
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  return <span ref={marker} hidden />;
}
