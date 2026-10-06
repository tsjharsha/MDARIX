import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { AlertTriangle, Search, X } from "lucide-react";
import { SortableHeader, nodeText, useSortedRows } from "../../app/tableSort";
import { ApiError, describeError, requestJson } from "../../app/apiClient";
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
import { DialogBehaviour } from "../shared/DialogBehaviour";
import { nextTabIndex } from "../shared/focus";
import { formatDateTime, formatDay, isDateOnly } from "../../app/dates";
import { businessId, hideUuid, referenceId } from "../../app/displayId";

// Every call goes through requestJson: same-origin session cookie, no tenant id from the browser.
// The server derives the tenant from the authenticated session for every request.

export type Resource<T> = {
  state: PanelState;
  data: T | null;
  error?: string;
  /** The server's error code, e.g. TRIAL_ENDED (a 403 that is not about the person's role). */
  code?: string;
  /** The id the server logged a failure under, shown with the error for a problem report. */
  requestId?: string;
  reload: () => void;
};

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
            code: reason instanceof ApiError ? reason.code : undefined,
            requestId: reason instanceof ApiError ? reason.requestId : undefined,
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

/** The server's message for a failed change, with the reference to quote to support when there is one. */
export const errorText = (reason: unknown, fallback: string) => describeError(reason, fallback);

export const humanize = (value: unknown) =>
  value === null || value === undefined || value === ""
    ? "—"
    : String(value)
        .toLowerCase()
        .replace(/_/g, " ")
        .replace(/^\w/, (letter) => letter.toUpperCase());

/** A date and time with its time zone (app/dates.ts); a calendar date alone ("2026-03-04") as a day, without an
 * invented midnight; an unreadable value is shown as it is. */
export const formatDate = (value: unknown) => {
  if (!value) return "—";
  return isDateOnly(value) ? formatDay(String(value), String(value)) : formatDateTime(String(value), String(value));
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
    <Panel title={title} eyebrow={eyebrow} source={resource} action={action}>
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
  // What the column sorts by when its heading is clicked; by default the row's field of the same key, then the
  // first of `fields`, then the text the cell shows. Columns without a heading (row actions) never sort.
  sortValue?: (row: T) => unknown;
};

/** The value a column sorts by (see Column.sortValue). */
export function columnSortValue<T>(column: Column<T>, row: T): unknown {
  if (column.sortValue) return column.sortValue(row);
  const record = row as unknown as Record<string, unknown> | null;
  for (const key of [column.key, ...(column.fields ?? [])]) {
    const value = record && typeof record === "object" ? record[key] : undefined;
    if (value !== undefined && (value === null || typeof value !== "object" || value instanceof Date)) return value;
  }
  return nodeText(column.render(row));
}

/**
 * The first identifying column of a list: the record's MDARIX ID (business_id), labelled for the object ("Customer
 * ID", "Complaint ID"). Until a response carries business_id it shows the record's source number (`sourceKey`), never
 * the UUID. Business IDs sort naturally (CMP000002 before CMP000010). T defaults to any so the column fits whichever
 * row type the list infers from its rows.
 */
export function idColumn<T = any>(label: string, sourceKey?: string): Column<T> {
  return {
    key: "business_id",
    label,
    fields: ["business_id"],
    render: (row) => businessId(row as object, sourceKey) ?? "—",
    sortValue: (row) => businessId(row as object, sourceKey),
  };
}

/**
 * The ID column of a list whose rows describe another record (a license row for a subscription): that record's
 * `<role>_business_id`, else the row's own fields named in `fallbackKeys`, never a UUID.
 */
export function referenceIdColumn<T = any>(label: string, role: string, ...fallbackKeys: string[]): Column<T> {
  const value = (row: T) => {
    const record = row as unknown as Record<string, unknown>;
    return referenceId(record, role, ...fallbackKeys.map((key) => record?.[key]));
  };
  return { key: `${role}_business_id`, label, fields: [`${role}_business_id`], render: value, sortValue: value };
}

/** "Source ID": the number a record has in the customer system it was imported from (complaint_identifier, …). */
export function sourceIdColumn<T = any>(key: string, label = "Source ID"): Column<T> {
  return {
    key,
    label,
    render: (row) => hideUuid((row as unknown as Record<string, unknown>)?.[key]),
  };
}

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
  const { sorted, sort, toggle } = useSortedRows(rows, (row, key) => {
    const column = columns.find((item) => item.key === key);
    return column ? columnSortValue(column, row) : undefined;
  });
  if (!rows.length) return <Empty title={empty.title} detail={empty.detail} />;
  // Row keys keep the server's position, so a row keeps its identity (and focus) when the list is re-sorted.
  const position = new Map(rows.map((row, index) => [row, index] as const));
  return (
    <div className="ac-table-wrap">
      <table className="ac-table">
        <caption className="ca-sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) =>
              column.label.trim() ? (
                <SortableHeader
                  key={column.key}
                  label={column.label}
                  sortKey={column.key}
                  sort={sort}
                  onSort={toggle}
                  className={column.numeric ? "num" : undefined}
                />
              ) : (
                <th scope="col" key={column.key} className={column.numeric ? "num" : undefined}>
                  <span className="ca-sr-only">Actions</span>
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, index) => (
            <tr key={rowKey(row, position.get(row) ?? index)}>
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
  /** A statement the administrator must tick before the change is allowed (sent to the server as acknowledged). */
  acknowledge?: string;
  run: (reason: string, password: string, acknowledged: boolean) => Promise<unknown>;
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
  const [acknowledged, setAcknowledged] = useState(false);
  useEffect(() => {
    setBusy(false);
    setError("");
    setReason("");
    setPassword("");
    setAcknowledged(false);
  }, [request]);
  if (!request) return null;
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await request.run(reason.trim(), password, acknowledged);
      onDone(request.done);
    } catch (reason) {
      setError(errorText(reason, "The change was not applied."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
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
        {request.acknowledge && (
          <label className="ca-check ca-acknowledge">
            <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />
            {request.acknowledge}
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
              (!!request.password && !password) ||
              (!!request.acknowledge && !acknowledged)
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
      <DialogBehaviour onClose={onClose} />
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

const slug = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

/**
 * Tabs that follow the WAI-ARIA pattern: the arrow keys (and Home, End) move between tabs and open them, only the
 * selected tab is in the Tab order, and the content below is the selected tab's labelled tabpanel.
 */
export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
  children,
}: {
  tabs: readonly T[];
  active: T;
  onChange: (tab: T) => void;
  label: string;
  /** The selected tab's content, rendered as its tabpanel. */
  children?: ReactNode;
}) {
  const base = `tabs-${slug(label)}`;
  const tabId = (tab: T) => `${base}-${slug(tab)}`;
  const list = useRef<HTMLDivElement>(null);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = nextTabIndex(event.key, Math.max(0, tabs.indexOf(active)), tabs.length);
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next]);
    list.current?.querySelector<HTMLButtonElement>(`#${CSS.escape(tabId(tabs[next]))}`)?.focus();
  };
  return (
    <>
      <div className="ac-tabs" role="tablist" aria-label={label} ref={list} onKeyDown={onKeyDown}>
        {tabs.map((tab) => (
          <button
            type="button"
            role="tab"
            key={tab}
            id={tabId(tab)}
            aria-selected={active === tab}
            aria-controls={`${base}-panel`}
            tabIndex={active === tab ? 0 : -1}
            className={active === tab ? "selected" : ""}
            onClick={() => onChange(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      {children !== undefined && (
        <div role="tabpanel" id={`${base}-panel`} aria-labelledby={tabId(active)} className="ac-tabpanel">
          {children}
        </div>
      )}
    </>
  );
}
