import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Maximize2, X } from "lucide-react";

/**
 * A complex diagram with an "Enlarge" button that opens it full-screen. The enlarged copy is a modal dialog: focus
 * moves into it, Escape or Close shuts it (so does a click outside the diagram), and focus returns to the button.
 * `enlarged` draws the copy shown in the dialog (a second, larger rendering of the same diagram).
 */
export function Enlargeable({
  label,
  children,
  enlarged,
}: {
  /** The diagram's name: the dialog's title and the button's accessible name ("Enlarge: …"). */
  label: string;
  children: ReactNode;
  enlarged: () => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  useEffect(() => {
    const node = dialog.current;
    if (open && node && !node.open) node.showModal();
  }, [open]);
  const close = () => {
    // Leave the modal state first: while the dialog is modal, the rest of the page cannot take focus.
    dialog.current?.close();
    setOpen(false);
    button.current?.focus();
  };
  return (
    <div className="ms-enlargeable">
      {children}
      <button
        ref={button}
        type="button"
        className="ms-enlarge"
        aria-haspopup="dialog"
        aria-label={`Enlarge: ${label}`}
        onClick={() => setOpen(true)}
      >
        <Maximize2 size={15} aria-hidden="true" /> Enlarge
      </button>
      {open && (
        <dialog
          ref={dialog}
          className="ms-enlarged"
          aria-labelledby={titleId}
          // Escape: the browser cancels the dialog; close it the same way as the button does.
          onCancel={(event) => {
            event.preventDefault();
            close();
          }}
          onClick={(event) => event.target === event.currentTarget && close()}
        >
          <div className="ms-enlarged-bar">
            <strong id={titleId}>{label}</strong>
            <button type="button" className="ms-btn ms-btn-outline" onClick={close} autoFocus>
              <X size={16} aria-hidden="true" /> Close
            </button>
          </div>
          <div className="ms-enlarged-body">{enlarged()}</div>
        </dialog>
      )}
    </div>
  );
}
