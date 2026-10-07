import { createContext, useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Columns3, Plus, RotateCcw, X } from "lucide-react";
import { fieldLabel, moveField } from "./columnModel";
import "./columns.css";
import { DialogBehaviour } from "../shared/DialogBehaviour";

/**
 * Turns on "choose the fields to show" for every table inside it. The value names the area (part of the key under
 * which each table's choice is remembered); tables outside a scope behave as before.
 */
export const ColumnScope = createContext<string | null>(null);

export function ColumnScopeProvider({ scope, children }: { scope: string; children: ReactNode }) {
  return <ColumnScope.Provider value={scope}>{children}</ColumnScope.Provider>;
}

export type FieldOption = { key: string; label: string };

/** The "Columns" button and the chooser it opens: available fields on one side, the shown fields (in order) on the other. */
export function ColumnChooser({
  caption,
  options,
  selection,
  defaults,
  resized = false,
  onChange,
}: {
  caption: string;
  options: FieldOption[];
  selection: string[];
  defaults: string[];
  /** Column widths were changed in the list; "Reset to default" also returns them to automatic widths. */
  resized?: boolean;
  onChange: (selection: string[] | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const labels = useMemo(() => new Map(options.map((option) => [option.key, option.label])), [options]);
  const label = (key: string) => labels.get(key) ?? fieldLabel(key);
  const term = query.trim().toLowerCase();
  const available = options.filter(
    (option) => !selection.includes(option.key) && (!term || option.label.toLowerCase().includes(term)),
  );
  const isDefault =
    !resized && selection.length === defaults.length && selection.every((key, index) => key === defaults[index]);
  return (
    <div className="tc-bar">
      <button
        type="button"
        className="ac-secondary tc-button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        title="Choose the fields this list shows"
      >
        <Columns3 size={15} aria-hidden="true" /> Columns
        <span className="tc-count">
          {selection.length} of {options.length}
        </span>
      </button>
      {open && (
        <div
          className="ac-modal-backdrop"
          role="presentation"
          onClick={(event) => event.target === event.currentTarget && setOpen(false)}
        >
          <DialogBehaviour onClose={() => setOpen(false)} />
          <div className="ac-modal tc-modal" role="dialog" aria-modal="true" aria-labelledby="tc-title">
            <p className="ac-eyebrow">{caption}</p>
            <h2 id="tc-title">Fields to show</h2>
            <p className="ac-muted">
              Add the fields you want, put them in order, and remove the ones you don&apos;t need. In the list itself
              you can also drag a column heading left or right to move it, and drag the edge of a heading to change the
              column&apos;s width.
            </p>
            <div className="tc-lists">
              <section aria-labelledby="tc-available">
                <h3 id="tc-available">Available fields</h3>
                <input
                  className="tc-search"
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search fields"
                  aria-label="Search available fields"
                />
                <ul className="tc-list" aria-label="Available fields">
                  {available.map((option) => (
                    <li key={option.key}>
                      <span>{option.label}</span>
                      <button
                        type="button"
                        className="ac-link"
                        onClick={() => onChange([...selection, option.key])}
                        aria-label={`Show ${option.label}`}
                      >
                        <Plus size={14} aria-hidden="true" /> Add
                      </button>
                    </li>
                  ))}
                  {!available.length && (
                    <li className="tc-none">{term ? "No field matches." : "All fields are shown."}</li>
                  )}
                </ul>
              </section>
              <section aria-labelledby="tc-shown">
                <h3 id="tc-shown">Shown fields</h3>
                <ol className="tc-list" aria-label="Shown fields">
                  {selection.map((key, index) => (
                    <li key={key}>
                      <span>{label(key)}</span>
                      <span className="tc-row-actions">
                        <button
                          type="button"
                          className="ac-link"
                          disabled={index === 0}
                          onClick={() => onChange(moveField(selection, key, -1))}
                          aria-label={`Move ${label(key)} up`}
                        >
                          <ArrowUp size={14} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="ac-link"
                          disabled={index === selection.length - 1}
                          onClick={() => onChange(moveField(selection, key, 1))}
                          aria-label={`Move ${label(key)} down`}
                        >
                          <ArrowDown size={14} aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          className="ac-link tc-remove"
                          disabled={selection.length === 1}
                          onClick={() => onChange(selection.filter((item) => item !== key))}
                          aria-label={`Hide ${label(key)}`}
                        >
                          <X size={14} aria-hidden="true" />
                        </button>
                      </span>
                    </li>
                  ))}
                </ol>
              </section>
            </div>
            <div className="ac-modal-actions">
              <button type="button" className="ac-secondary" disabled={isDefault} onClick={() => onChange(null)}>
                <RotateCcw size={14} aria-hidden="true" /> Reset to default
              </button>
              <button type="button" className="ac-primary" onClick={() => setOpen(false)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
