import { useEffect, useRef } from "react";

// Open dialogs, newest last: Escape closes only the one on top.
const openDialogs: symbol[] = [];

const FOCUSABLE =
  'input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

/**
 * Keyboard behaviour for a modal dialog, placed as the first child of its backdrop: focus moves into the dialog when
 * it opens, Escape closes it from anywhere on the page, and focus returns to what opened it when it closes.
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
      if (event.key !== "Escape" || openDialogs[openDialogs.length - 1] !== id) return;
      event.preventDefault();
      close.current();
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
