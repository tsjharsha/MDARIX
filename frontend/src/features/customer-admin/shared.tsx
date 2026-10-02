import { useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Search, X } from "lucide-react";
import { ApiError, requestJson } from "../../app/apiClient";
import { Empty, Panel, type PanelState } from "../admin/console/charts";
import { ColumnChooser, ColumnScope } from "../tables/ColumnChooser";
import {
  availableFieldKeys,
  fieldLabel,
  formatFieldValue,
  loadSelection,
  resolveSelection,
  saveSelection,
} from "../tables/columnModel";

// Every call goes through requestJson: same-origin session cookie, no tenant id from the browser.
// The server derives the tenant from the authenticated session for every request.

export type Resource<T> = { state: PanelState; data: T | null; error?: string; reload: () => void };

export function useResource<T>(path: string | null): Resource<T> {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Omit<Resource<T>, "reload">>({ state: "loading", data: null });
  useEffect(() => {
    if (!path) return;
    let current = true;
    setResult((previous) => ({ ...previous, state: previous.data ? previous.state : "loading" }));
    requestJson<T>(path)
      .then((data) => current && setResult({ state: "ready", data }))
      .catch(
        (reason) =>
          current &&
          setResult({
            state: reason instanceof ApiError && reason.status === 403 ? "forbidden" : "error",
            data: null,
            error: reason instanceof Error ? reason.message : undefined,
          }),
      );
    return () => {
      current = false;
    };
  }, [path, version]);
  const reload = useCallback(() => setVersion((value) => value + 1), []);
  return { ...result, reload };
}

export const listOf = (value: any): any[] =>
  Array.isArray(value) ? value : (value?.items ?? value?.results ?? value?.records ?? []);

export async function send<T = any>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body?: unknown) {
  return requestJson<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
}

export const errorText = (reason: unknown, fallback: string) => (reason instanceof Error ? reason.message : fallback);

export const humanize = (value: unknown) =>
  value === null || value === undefined || value === ""
    ? "—"
    : String(value)
        .toLowerCase()
        .replace(/_/g, " ")
        .replace(/^\w/, (letter) => letter.toUpperCase());

export const formatDate = (value: unknown) => {
  if (!value) return "—";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
};

/** Section card bound to one resource: shows loading / error / forbidden, then the content. */
export function ResourcePanel<T>({
  resource,
  title,
  eyebrow,
  action,
  children,
}: {
  resource: Resource<T>;
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  return (
    <Panel title={title} eyebrow={eyebrow} state={resource.state} error={resource.error} action={action}>
      {resource.data !== null && children(resource.data)}
    </Panel>
  );
}

export type Column<T> = {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
  // The data fields this column already shows (so the field chooser does not offer them again).
  fields?: string[];
};

type TableProps<T> = {
  rows: T[];
  columns: Column<T>[];
  empty: { title: string; detail: string };
  rowKey: (row: T, index: number) => string;
  caption: string;
};

/**
 * A list. Inside a ColumnScope (every page of both administrator consoles) it also offers "Columns": every field the rows
 * carry can be shown, hidden and put in order, and the choice is remembered per list in this browser.
 */
export function Table<T>(props: TableProps<T>) {
  const scope = useContext(ColumnScope);
  return scope ? <ChoosableTable {...props} scope={scope} /> : <PlainTable {...props} />;
}

function ChoosableTable<T>({ rows, columns, empty, rowKey, caption, scope }: TableProps<T> & { scope: string }) {
  const id = `${scope}:${caption}`;
  // Columns without a heading (row actions such as Open or Change) always stay, at the end.
  const pinned = columns.filter((column) => !column.label.trim());
  const named = columns.filter((column) => column.label.trim());
  const defaults = named.map((column) => column.key);
  const extraKeys = useMemo(
    () =>
      availableFieldKeys(
        rows as unknown[],
        columns.flatMap((column) => [column.key, ...(column.fields ?? [])]),
      ),
    [rows, columns],
  );
  const [saved, setSaved] = useState<string[] | null>(() => loadSelection(id));
  if (!rows.length) return <Empty title={empty.title} detail={empty.detail} />;
  const options = [
    ...named.map((column) => ({ key: column.key, label: column.label })),
    ...extraKeys.map((key) => ({ key, label: fieldLabel(key) })),
  ];
  const selection = resolveSelection(
    defaults,
    options.map((option) => option.key),
    saved,
  );
  const extraColumn = (key: string): Column<T> => {
    const sample = (rows as unknown as Array<Record<string, unknown>>).find((row) => row?.[key] != null)?.[key];
    return {
      key,
      label: fieldLabel(key),
      numeric: typeof sample === "number",
      render: (row) => formatFieldValue((row as unknown as Record<string, unknown>)[key]),
    };
  };
  const shown = [...selection.map((key) => named.find((column) => column.key === key) ?? extraColumn(key)), ...pinned];
  return (
    <>
      <ColumnChooser
        caption={caption}
        options={options}
        selection={selection}
        defaults={defaults}
        onChange={(next) => {
          setSaved(next);
          saveSelection(id, next);
        }}
      />
      <PlainTable rows={rows} columns={shown} empty={empty} rowKey={rowKey} caption={caption} />
    </>
  );
}

function PlainTable<T>({ rows, columns, empty, rowKey, caption }: TableProps<T>) {
  if (!rows.length) return <Empty title={empty.title} detail={empty.detail} />;
  return (
    <div className="ac-table-wrap">
      <table className="ac-table">
        <caption className="ca-sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th scope="col" key={column.key} className={column.numeric ? "num" : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {columns.map((column) => (
                <td key={column.key} className={column.numeric ? "num" : undefined}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SearchBox({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <label className="ca-search">
      <Search size={15} aria-hidden="true" />
      <input aria-label={label} placeholder={label} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

export const matches = (row: unknown, query: string) =>
  !query.trim() || JSON.stringify(row).toLowerCase().includes(query.trim().toLowerCase());

export type Confirmation = {
  title: string;
  body: string;
  confirmLabel: string;
  danger?: boolean;
  /** Ask for a written reason, stored with the audit event (the server enforces the same minimum). */
  reason?: { label: string; min: number };
  /** Ask the signed-in administrator to re-enter their password (the server verifies it). */
  password?: boolean;
  run: (reason: string, password: string) => Promise<unknown>;
  done: string;
};

/** Every change that affects access or data flow is confirmed in a dialog that states its effect. */
export function ConfirmDialog({
  request,
  onClose,
  onDone,
}: {
  request: Confirmation | null;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  useEffect(() => {
    setBusy(false);
    setError("");
    setReason("");
    setPassword("");
  }, [request]);
  if (!request) return null;
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await request.run(reason.trim(), password);
      onDone(request.done);
    } catch (reason) {
      setError(errorText(reason, "The change was not applied."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation" onKeyDown={(event) => event.key === "Escape" && onClose()}>
      <section className="ac-modal" role="alertdialog" aria-modal="true" aria-labelledby="ca-confirm-title">
        <p className="ac-eyebrow">Confirm change · recorded in the audit trail</p>
        <h2 id="ca-confirm-title">{request.title}</h2>
        <p>{request.body}</p>
        {request.reason && (
          <label className="ca-field">
            {request.reason.label}
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              minLength={request.reason.min}
              placeholder={`At least ${request.reason.min} characters`}
            />
          </label>
        )}
        {request.password && (
          <label className="ca-field">
            Your password (to confirm it is you)
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        )}
        {error && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy} autoFocus>
            Cancel
          </button>
          <button
            type="button"
            className={request.danger ? "ca-danger" : "ac-primary"}
            onClick={() => void confirm()}
            disabled={
              busy ||
              (!!request.reason && reason.trim().length < request.reason.min) ||
              (!!request.password && !password)
            }
          >
            {busy ? "Working…" : request.confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

export function Drawer({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div
      className="ca-drawer-backdrop"
      role="presentation"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <aside className="ca-drawer" role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <h2>{title}</h2>
          <button type="button" className="ac-link" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>
        {children}
      </aside>
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: readonly T[];
  active: T;
  onChange: (tab: T) => void;
  label: string;
}) {
  return (
    <div className="ac-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          type="button"
          role="tab"
          key={tab}
          aria-selected={active === tab}
          className={active === tab ? "selected" : ""}
          onClick={() => onChange(tab)}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
