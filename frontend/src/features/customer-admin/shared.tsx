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
import { SortableHeader, nodeText, useSortedRows, type SortState } from "../../app/tableSort";
import { ApiError, describeError, requestJson } from "../../app/apiClient";
import { Empty, Panel, type PanelState } from "../admin/console/charts";
import { ColumnChooser, ColumnScope } from "../tables/ColumnChooser";
import { useColumnControls, useColumnLayout } from "../tables/useColumnControls";
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

/** How often, and for how long, a resource is read again while ``refreshWhile`` says its data is not final yet. */
export const REFRESH_MS = 3_000;
export const REFRESH_FOR_MS = 120_000;

/** Whether a loaded resource is to be read again: its data is there and ``refreshWhile`` says it is not final. */
export function stillUnfinished<T>(
  result: { state: PanelState; data: T | null },
  refreshWhile?: (data: T) => boolean,
): boolean {
  return result.state === "ready" && result.data !== null && !!refreshWhile?.(result.data);
}

export function useResource<T>(
  path: string | null,
  options: {
    /** Read again (in the background) every few seconds while this is true of the data, for two minutes at most:
     * for example while an import's signals are still being found. */
    refreshWhile?: (data: T) => boolean;
    /** A small status read (``{ pending: boolean }``) asked meanwhile instead of the resource itself, which is read
     * again once the status says it is no longer pending. */
    statusPath?: string;
  } = {},
): Resource<T> {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Omit<Resource<T>, "reload">>({ state: "loading", data: null });
  const refreshWhile = useRef(options.refreshWhile);
  refreshWhile.current = options.refreshWhile;
  const statusPath = options.statusPath;
  const unfinished = stillUnfinished(result, refreshWhile.current);
  // Background reads: a page left open does not keep its session alive (apiClient ``background``). They replace the
  // data only, so the panel never flickers back to "loading". One read at a time: the next is asked for a few seconds
  // after the last one answered, so a slow server never gets a pile of them.
  useEffect(() => {
    if (!path || !unfinished) return;
    let current = true;
    let timer: number | undefined;
    const started = Date.now();
    const reload = () =>
      requestJson<T>(path, { background: true }).then((data) => current && setResult({ state: "ready", data }));
    const read = () => {
      if (!current || Date.now() - started > REFRESH_FOR_MS) return;
      const step = statusPath
        ? requestJson<{ pending?: boolean }>(statusPath, { background: true }).then((status) =>
            status.pending ? undefined : reload(),
          )
        : reload();
      step
        .catch(() => undefined)
        .finally(() => {
          if (current) timer = window.setTimeout(read, REFRESH_MS);
        });
    };
    timer = window.setTimeout(read, REFRESH_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [path, version, unfinished, statusPath]);
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

/**
 * Sorting done by the server for a list it sends one page at a time (app/tableSort.tsx useServerSort): a heading
 * click asks for that order across every page. Only the columns in `keys` can be sorted this way; their headings are
 * plain text otherwise, so no heading pretends to sort what it cannot.
 */
export type ServerSort = { sort: SortState; onSort: (key: string) => void; keys: readonly string[] };

type TableProps<T> = {
  rows: T[];
  columns: Column<T>[];
  empty: { title: string; detail: string };
  rowKey: (row: T, index: number) => string;
  caption: string;
  /** The server sorts and pages this list; the rows are one page, already in order. */
  serverSort?: ServerSort;
  /** All rows are here: the table sorts them all and then shows them this many at a time. */
  pageSize?: number;
  /** What one row is, for the page summary ("120 users"). */
  pageNoun?: string;
};

/**
 * A list. Inside a ColumnScope (every page of both administrator consoles) it also offers "Columns": every field the rows
 * carry can be shown, hidden and put in order, and the choice is remembered per list in this browser.
 */
export function Table<T>(props: TableProps<T>) {
  const scope = useContext(ColumnScope);
  return scope ? <ChoosableTable {...props} scope={scope} /> : <PlainTable {...props} />;
}

function ChoosableTable<T>({
  rows,
  columns,
  empty,
  rowKey,
  caption,
  scope,
  ...paging
}: TableProps<T> & { scope: string }) {
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
  // Column widths set by dragging a heading's edge; "Reset to default" clears them with the field choice.
  const { layout, commit } = useColumnLayout(id);
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
  const choose = (next: string[] | null) => {
    setSaved(next);
    saveSelection(id, next);
  };
  return (
    <>
      <ColumnChooser
        caption={caption}
        options={options}
        selection={selection}
        defaults={defaults}
        resized={Boolean(layout.widths && Object.keys(layout.widths).length)}
        onChange={(next) => {
          choose(next);
          if (next === null) commit({});
        }}
      />
      {/* Dragging a heading reorders the shown fields, the same order the chooser keeps. */}
      <PlainTable
        {...paging}
        rows={rows}
        columns={shown}
        empty={empty}
        rowKey={rowKey}
        caption={caption}
        layoutId={id}
        onReorder={choose}
      />
    </>
  );
}

function PlainTable<T>({
  rows,
  columns,
  empty,
  rowKey,
  caption,
  layoutId,
  onReorder,
  serverSort,
  pageSize,
  pageNoun = "row",
}: TableProps<T> & { layoutId?: string; onReorder?: (keys: string[]) => void }) {
  const named = columns.filter((column) => column.label.trim());
  const pinned = columns.filter((column) => !column.label.trim());
  const controls = useColumnControls({
    id: layoutId ?? `list:${caption}`,
    keys: named.map((column) => column.key),
    pinned: pinned.map((column) => column.key),
    onReorder,
  });
  // Sorted here (all the rows), or by the server (the rows are one page in its order).
  const local = useSortedRows(serverSort ? [] : rows, (row, key) => {
    const column = columns.find((item) => item.key === key);
    return column ? columnSortValue(column, row) : undefined;
  });
  const sorted = serverSort ? rows : local.sorted;
  const sort = serverSort ? serverSort.sort : local.sort;
  const [page, setPage] = useState(1);
  const toggle = (key: string) => {
    setPage(1); // a new order starts from its first page
    if (serverSort) serverSort.onSort(key);
    else local.toggle(key);
  };
  if (!rows.length) return <Empty title={empty.title} detail={empty.detail} />;
  const pages = pageSize ? Math.max(1, Math.ceil(sorted.length / pageSize)) : 1;
  const current = Math.min(page, pages);
  const visible = pageSize ? sorted.slice((current - 1) * pageSize, current * pageSize) : sorted;
  const shown = [
    ...controls.order
      .map((key) => named.find((column) => column.key === key))
      .filter((column): column is Column<T> => column !== undefined),
    ...pinned,
  ];
  // Row keys keep the server's position, so a row keeps its identity (and focus) when the list is re-sorted.
  const position = new Map(rows.map((row, index) => [row, index] as const));
  return (
    <>
      {!onReorder && controls.customized && (
        <div className="tc-bar">
          <button type="button" className="ac-link" onClick={controls.reset}>
            Reset columns
          </button>
        </div>
      )}
      <div className="ac-table-wrap">
        <table className={`ac-table ${controls.tableClassName}`.trim()} style={controls.tableStyle}>
          <caption className="ca-sr-only">{caption}</caption>
          {controls.colgroup}
          <thead>
            <tr ref={controls.headRowRef}>
              {shown.map((column) => {
                if (!column.label.trim())
                  return (
                    <th
                      scope="col"
                      key={column.key}
                      className={column.numeric ? "num" : undefined}
                      {...controls.pinnedProps(column.key)}
                    >
                      <span className="ca-sr-only">Actions</span>
                    </th>
                  );
                const header = controls.header(column.key, column.label);
                if (serverSort && !serverSort.keys.includes(column.key))
                  return (
                    <th
                      scope="col"
                      key={column.key}
                      {...header.thProps}
                      className={[column.numeric ? "num" : "", header.className].filter(Boolean).join(" ") || undefined}
                    >
                      <span className="table-sort-static" title="This column cannot be sorted across all pages">
                        {column.label}
                      </span>
                      {header.grip}
                    </th>
                  );
                return (
                  <SortableHeader
                    key={column.key}
                    label={column.label}
                    sortKey={column.key}
                    sort={sort}
                    onSort={toggle}
                    className={[column.numeric ? "num" : "", header.className].filter(Boolean).join(" ")}
                    thProps={header.thProps}
                    onKeyDown={header.onKeyDown}
                  >
                    {header.grip}
                  </SortableHeader>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, index) => (
              <tr key={rowKey(row, position.get(row) ?? index)}>
                {shown.map((column) => (
                  <td key={column.key} className={column.numeric ? "num" : undefined}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageSize && pages > 1 && (
        <nav className="tc-pager" aria-label={`${caption} pages`}>
          <button type="button" className="ac-secondary" disabled={current <= 1} onClick={() => setPage(current - 1)}>
            Previous
          </button>
          <span>
            Page {current} of {pages} · {sorted.length} {sorted.length === 1 ? pageNoun : `${pageNoun}s`}
          </span>
          <button
            type="button"
            className="ac-secondary"
            disabled={current >= pages}
            onClick={() => setPage(current + 1)}
          >
            Next
          </button>
        </nav>
      )}
    </>
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
  /** Ask for the current code from the administrator's authenticator app (the server decides whether it is needed). */
  mfaCode?: boolean;
  run: (reason: string, password: string, acknowledged: boolean, mfaCode: string) => Promise<unknown>;
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
  const [code, setCode] = useState("");
  useEffect(() => {
    setBusy(false);
    setError("");
    setReason("");
    setPassword("");
    setAcknowledged(false);
    setCode("");
  }, [request]);
  if (!request) return null;
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await request.run(reason.trim(), password, acknowledged, code.trim());
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
        {request.mfaCode && (
          <label className="ca-field">
            Code from your authenticator app
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="6 digits"
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
              (!!request.mfaCode && code.length > 0 && code.length < 6) ||
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
  counts,
  children,
}: {
  tabs: readonly T[];
  active: T;
  onChange: (tab: T) => void;
  label: string;
  /** A number to show on a tab (how many items it holds); tabs without one show none. */
  counts?: Partial<Record<string, number | null>>;
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
            {typeof counts?.[tab] === "number" && (
              <>
                {" "}
                <span className="ac-tab-count">{counts[tab]}</span>
              </>
            )}
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
