import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronRight, Plus, X } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import {
  Drawer,
  SearchBox,
  Table,
  errorText,
  listOf,
  send,
  useResource,
  type Column,
} from "../../customer-admin/shared";
import { displayId, safeText } from "../../../app/displayId";
import { sectionAllowed, useCan, useWorkspace } from "../workspaceContext";
import { pageText } from "../tasks";
import {
  EMPTY_NEW_SIGNAL,
  PRIORITY_REASON_MAX,
  SIGNAL_COLUMN_SORTS,
  SIGNAL_ORIGINS,
  SIGNAL_PRIORITIES,
  SIGNAL_SORTS,
  ageText,
  newSignalBody,
  newSignalProblem,
  nextSignalSort,
  rankSignals,
  signalListPath,
  signalOriginLabel,
  signalPriority,
  signalPriorityLabel,
  signalProductText,
  signalStatusLabel,
  signalTableSort,
  signalsTab,
  statusChips,
  statusFilterLabel,
  triageCountTiles,
  DETECTION_STATUS_PATH,
  type NewSignalForm,
  type SignalFilters,
  type SignalList,
  type SignalSort,
  type SignalSummary,
  type StatusFilter,
  type TriageSummary,
} from "../signals";
import { StatusBadge } from "./common";
import { SignalDetailView, SignalDue, SignalPriorityCell, SignalStatusBadge } from "./SignalDetail";

/** The inbox's line while an import's signals are being found. */
export const FINDING_SIGNALS =
  "Finding signals in the complaints you just imported… The list updates by itself when they are ready.";

/** What the inbox says when it lists no signal: they are still being found, none match, or there are none. */
export function inboxEmpty(filters: SignalFilters, finding: boolean): { title: string; detail: string } {
  if (finding) return { title: "Finding signals…", detail: "The signals from your import appear here in a moment." };
  if (filters.q || filters.priorities.length || filters.productId || filters.origin || filters.owner)
    return { title: "No matching signals", detail: "Change the filters or the search to see more." };
  return {
    title: `No ${filters.status === "ALL" ? "" : `${statusFilterLabel(filters.status).toLowerCase()} `}signals`,
    detail: "Signals appear when the detection rule finds a pattern, or when someone creates one.",
  };
}

const PAGE_SIZE = 50;
// The "Sort by" choice that stands for a column heading's sort.
const HEADING_SORT = "heading";

/**
 * The signal inbox: every signal of the organization, filtered and sorted by the server and read a page at a time. A
 * signal opens in place (its detail view); "New signal" groups complaints into a signal by hand.
 */
export function SignalInbox({
  initialFilters,
  initialSignal,
  onSignalClosed,
}: {
  initialFilters: SignalFilters;
  initialSignal: string | null;
  onSignalClosed?: () => void;
}) {
  const { work } = useWorkspace();
  const canTriage = useCan("signal.triage");
  const [filters, setFilters] = useState<SignalFilters>(initialFilters);
  const [query, setQuery] = useState(initialFilters.q);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(initialSignal);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = query.trim();
      if (next === filters.q) return;
      setFilters((current) => ({ ...current, q: next }));
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query]);
  // Opened right after an import, its signals may still be being found: the list is read again until they are.
  const list = useResource<SignalList>(signalListPath(filters, page, PAGE_SIZE), {
    refreshWhile: (data) => !!data.detection_pending,
    statusPath: DETECTION_STATUS_PATH,
  });
  const finding = !!list.data?.detection_pending;
  const change = (next: Partial<SignalFilters>) => {
    setFilters((current) => ({ ...current, ...next }));
    setPage(1);
  };
  // The server filters (overdue signals included) and sorts every page; the rows are one page, already in order.
  const rows = listOf(list.data?.items) as SignalSummary[];
  const columns = signalColumns(setSelected);
  const tableSort = signalTableSort(filters);
  const headingSort = filters.order ? columns.find((column) => column.key === filters.sort) : undefined;
  const total = list.data?.total ?? rows.length;
  const pages = Math.max(1, Math.ceil(total / (list.data?.page_size || PAGE_SIZE)));
  const chips = statusChips(list.data?.counts_by_status, filters.status);

  if (selected)
    return (
      <SignalDetailView
        key={selected}
        reference={selected}
        onBack={() => {
          setSelected(null);
          onSignalClosed?.();
          list.reload();
        }}
        onOpenSignal={setSelected}
      />
    );

  return (
    <>
      <Panel
        eyebrow="Signals"
        title={`Signal inbox${list.data ? ` · ${list.data.total}` : ""}`}
        source={list}
        action={
          canTriage ? (
            <button type="button" className="ac-primary" onClick={() => setCreating(true)}>
              <Plus size={16} aria-hidden="true" /> New signal
            </button>
          ) : undefined
        }
      >
        <div className="ca-chips uw-signal-chips" role="radiogroup" aria-label="Signal status">
          {chips.map((chip) => (
            <button
              type="button"
              role="radio"
              key={chip.value}
              aria-checked={filters.status === chip.value}
              className={filters.status === chip.value ? "selected" : ""}
              onClick={() => change({ status: chip.value as StatusFilter })}
            >
              {chip.label}
              {chip.count !== null && <span className="ac-tab-count">{chip.count}</span>}
            </button>
          ))}
        </div>
        <div className="ca-toolbar uw-signal-toolbar">
          <SearchBox value={query} onChange={setQuery} label="Search signal ID, title or problem" />
          <select
            aria-label="Priority"
            value={filters.priorities.join(",")}
            onChange={(event) =>
              change({
                priorities: event.target.value ? (event.target.value.split(",") as SignalFilters["priorities"]) : [],
              })
            }
          >
            <option value="">All priorities</option>
            <option value="HIGH,CRITICAL">High and critical</option>
            {[...SIGNAL_PRIORITIES].reverse().map((priority) => (
              <option key={priority} value={priority}>
                {signalPriorityLabel(priority)}
              </option>
            ))}
            {filters.priorities.length > 1 && filters.priorities.join(",") !== "HIGH,CRITICAL" && (
              <option value={filters.priorities.join(",")}>
                {filters.priorities.map(signalPriorityLabel).join(" and ")}
              </option>
            )}
          </select>
          <select
            aria-label="Product"
            value={filters.productId}
            onChange={(event) => change({ productId: event.target.value })}
          >
            <option value="">All products</option>
            {work.products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Origin"
            value={filters.origin}
            onChange={(event) => change({ origin: event.target.value })}
          >
            <option value="">Any origin</option>
            {SIGNAL_ORIGINS.map((origin) => (
              <option key={origin} value={origin}>
                {signalOriginLabel(origin)}
              </option>
            ))}
          </select>
          <select
            aria-label="Owner"
            value={filters.owner}
            onChange={(event) => change({ owner: event.target.value as SignalFilters["owner"] })}
          >
            <option value="">Any owner</option>
            <option value="me">Mine</option>
            <option value="unassigned">Unassigned</option>
          </select>
          <label className="ca-inline-select">
            Sort by
            <select
              value={filters.order ? HEADING_SORT : filters.sort}
              onChange={(event) => {
                if (event.target.value !== HEADING_SORT) change({ sort: event.target.value as SignalSort, order: "" });
              }}
            >
              {headingSort && (
                <option value={HEADING_SORT}>
                  {`${headingSort.label || "Column"} (${filters.order === "asc" ? "ascending" : "descending"})`}
                </option>
              )}
              {SIGNAL_SORTS.map((sort) => (
                <option key={sort.value} value={sort.value}>
                  {sort.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {(filters.overdue || filters.reviewDue) && (
          <ul className="ca-pill-list uw-signal-active" aria-label="Also filtered by">
            {filters.overdue && (
              <li>
                Overdue only{" "}
                <button
                  type="button"
                  className="ac-link"
                  aria-label="Show signals that are not overdue as well"
                  onClick={() => change({ overdue: false })}
                >
                  <X size={13} aria-hidden="true" />
                </button>
              </li>
            )}
            {filters.reviewDue && (
              <li>
                Monitor review due{" "}
                <button
                  type="button"
                  className="ac-link"
                  aria-label="Show every monitored signal"
                  onClick={() => change({ reviewDue: false })}
                >
                  <X size={13} aria-hidden="true" />
                </button>
              </li>
            )}
          </ul>
        )}
        {finding && (
          <p className="uw-cited-line uw-signals-finding" role="status">
            {FINDING_SIGNALS}
          </p>
        )}
        <Table
          caption="Signal inbox"
          rows={rows}
          rowKey={(row) => String(row.id)}
          empty={inboxEmpty(filters, finding)}
          columns={columns}
          serverSort={{
            sort: tableSort,
            onSort: (key) => change(nextSignalSort(filters, key)),
            keys: SIGNAL_COLUMN_SORTS,
          }}
        />
        {pages > 1 && (
          <div className="ca-action-row uw-pager">
            <span className="ac-muted">{pageText(list.data, rows.length)}</span>
            <button
              type="button"
              className="ac-secondary"
              disabled={page <= 1 || list.state === "loading"}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="ac-secondary"
              disabled={page >= pages || list.state === "loading"}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </button>
          </div>
        )}
      </Panel>
      {creating && (
        <NewSignalDrawer
          onClose={() => setCreating(false)}
          onCreated={(signal) => {
            setCreating(false);
            list.reload();
            const reference = safeText(signal?.business_id) ?? (signal?.id ? String(signal.id) : null);
            if (reference) setSelected(reference);
          }}
        />
      )}
    </>
  );
}

function signalColumns(onOpen: (reference: string) => void): Column<SignalSummary>[] {
  const reference = (row: SignalSummary) => safeText(row.business_id) ?? String(row.id);
  return [
    {
      key: "business_id",
      label: "Signal ID",
      fields: ["business_id"],
      sortValue: (row) => safeText(row.business_id),
      render: (row) => (
        <button type="button" className="ac-link" onClick={() => onOpen(reference(row))}>
          {safeText(row.business_id) ?? "Signal"}
        </button>
      ),
    },
    {
      key: "title",
      label: "Title",
      fields: ["title", "origin", "origin_label", "rule_code"],
      render: (row) => (
        <span className="ca-person">
          <strong>{safeText(row.title) ?? "Untitled signal"}</strong>
          <small>{signalOriginLabel(row.origin, row.origin_label)}</small>
        </span>
      ),
    },
    {
      key: "product",
      label: "Product / version",
      fields: ["product", "product_version"],
      sortValue: (row) => signalProductText(row),
      render: (row) => signalProductText(row),
    },
    {
      key: "problem_key",
      label: "Problem code",
      render: (row) =>
        row.problem_key === "UNSPECIFIED" ? (
          <span className="ac-muted">Not specified</span>
        ) : (
          (safeText(row.problem_key) ?? <span className="ac-muted">—</span>)
        ),
    },
    {
      key: "complaint_count",
      label: "Complaints",
      numeric: true,
      fields: ["complaint_count", "recent_complaints_7d"],
      render: (row) => (
        <span className="ca-person">
          <strong>{row.complaint_count ?? 0}</strong>
          {(row.recent_complaints_7d ?? 0) > 0 && <small>{row.recent_complaints_7d} in last 7 days</small>}
        </span>
      ),
    },
    {
      key: "highest_severity",
      label: "Severity / harm",
      fields: ["highest_severity", "serious_harm"],
      render: (row) => (
        <span className="ca-person">
          <StatusBadge value={row.highest_severity} />
          {row.serious_harm && <small className="uw-flag-critical">Serious harm reported</small>}
        </span>
      ),
    },
    {
      key: "priority",
      label: "Priority",
      fields: ["priority", "suggested_priority", "confirmed_priority"],
      sortValue: (row) => ["LOW", "MEDIUM", "HIGH", "CRITICAL"].indexOf(String(signalPriority(row).current)),
      render: (row) => <SignalPriorityCell signal={row} />,
    },
    {
      key: "status",
      label: "Status",
      fields: ["status", "status_label"],
      sortValue: (row) => signalStatusLabel(row.status, row.status_label),
      render: (row) => <SignalStatusBadge signal={row} />,
    },
    {
      key: "owner",
      label: "Owner",
      sortValue: (row) => safeText(row.owner?.name) ?? "",
      render: (row) => safeText(row.owner?.name) ?? <span className="ac-muted">Unassigned</span>,
    },
    {
      key: "due_at",
      label: "Due",
      fields: ["due_at", "overdue"],
      sortValue: (row) => row.due_at ?? "",
      render: (row) => <SignalDue signal={row} />,
    },
    {
      key: "age_days",
      label: "Age",
      numeric: true,
      sortValue: (row) => row.age_days,
      render: (row) => ageText(row.age_days),
    },
    {
      key: "open",
      label: "",
      render: (row) => (
        <button
          type="button"
          className="ac-link"
          aria-label={`Open ${safeText(row.business_id) ?? "this signal"}`}
          onClick={() => onOpen(reference(row))}
        >
          Open
        </button>
      ),
    },
  ];
}

type ProductVersionOption = { id: string; version_identifier: string };

/** Group complaints of one product into a signal by hand: the product from the context bar, or another one. */
function NewSignalDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: (signal: SignalSummary) => void }) {
  const { work, notify } = useWorkspace();
  const [form, setForm] = useState<NewSignalForm>({ ...EMPTY_NEW_SIGNAL, productId: work.productId });
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const complaints = useResource<any>(
    form.productId
      ? `/api/v1/complaints?${new URLSearchParams({ product_id: form.productId, page_size: "200" })}`
      : null,
  );
  // Versions (with their ids) are known for the product in the context bar.
  const versions: ProductVersionOption[] = useMemo(
    () =>
      form.productId && form.productId === work.productId
        ? (work.view?.versions ?? [])
            .filter((version) => version?.id && version?.version_identifier)
            .map((version) => ({ id: String(version.id), version_identifier: String(version.version_identifier) }))
        : [],
    [form.productId, work.productId, work.view],
  );
  const versionIdentifier = versions.find((version) => version.id === form.productVersionId)?.version_identifier;
  const options = (listOf(complaints.data?.items) as any[]).filter(
    (row) =>
      (!versionIdentifier || row.version === versionIdentifier) &&
      (!search.trim() ||
        `${row.business_id ?? ""} ${row.complaint_identifier ?? ""} ${row.description ?? ""}`
          .toLowerCase()
          .includes(search.trim().toLowerCase())),
  );
  const problem = newSignalProblem(form);
  const toggle = (id: string) =>
    setForm((current) => ({
      ...current,
      complaintIds: current.complaintIds.includes(id)
        ? current.complaintIds.filter((item) => item !== id)
        : [...current.complaintIds, id],
    }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem) return;
    setBusy(true);
    setError("");
    try {
      const created = await send<SignalSummary>("/api/v1/triage/signals", "POST", newSignalBody(form));
      notify(`${safeText(created?.business_id) ?? "The signal"} was created.`);
      onCreated(created);
    } catch (reason) {
      setError(errorText(reason, "The signal was not created."));
      setBusy(false);
    }
  };
  return (
    <Drawer title="New signal" onClose={onClose}>
      <form className="ca-form" onSubmit={submit}>
        <p className="ac-muted">
          Group complaints that point to the same problem. Triage then decides what to do about it.
        </p>
        <label className="ca-field">
          Title
          <input
            required
            maxLength={240}
            value={form.title}
            placeholder="e.g. Battery drains within hours of charging"
            onChange={(event) => setForm({ ...form, title: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Description (optional)
          <textarea
            rows={3}
            maxLength={4000}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Product
          <select
            required
            value={form.productId}
            onChange={(event) =>
              setForm({ ...form, productId: event.target.value, productVersionId: "", complaintIds: [] })
            }
          >
            <option value="">Choose a product</option>
            {work.products.map((product) => (
              <option key={product.id} value={product.id}>
                {product.name}
                {safeText(product.business_id) ? ` (${product.business_id})` : ""}
              </option>
            ))}
          </select>
        </label>
        {versions.length > 0 && (
          <label className="ca-field">
            Version (optional)
            <select
              value={form.productVersionId}
              onChange={(event) => setForm({ ...form, productVersionId: event.target.value })}
            >
              <option value="">Any version</option>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  Version {version.version_identifier}
                </option>
              ))}
            </select>
          </label>
        )}
        {form.productId && (
          <fieldset className="ca-fieldset uw-pick-fieldset">
            <legend>Complaints · {form.complaintIds.length} chosen</legend>
            <SearchBox value={search} onChange={setSearch} label="Search complaints" />
            {complaints.state === "loading" && !complaints.data ? (
              <p className="ac-muted">Loading complaints…</p>
            ) : complaints.state !== "ready" ? (
              <p className="ca-inline-error">{complaints.error ?? "Complaints could not be loaded."}</p>
            ) : options.length ? (
              <ul className="uw-pick-list">
                {options.map((row) => (
                  <li key={row.id}>
                    <label className="ca-check">
                      <input
                        type="checkbox"
                        checked={form.complaintIds.includes(String(row.id))}
                        onChange={() => toggle(String(row.id))}
                      />
                      <span className="ca-person">
                        <strong>
                          {displayId(row, "complaint_identifier")}
                          {row.version ? ` · version ${row.version}` : ""}
                        </strong>
                        <small>
                          {safeText(row.description) ?? "No description"}
                          {row.death || row.serious_injury ? " · serious injury or death" : ""}
                        </small>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">No complaints of this product match.</p>
            )}
          </fieldset>
        )}
        <label className="ca-field">
          Priority (optional)
          <select value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })}>
            <option value="">Let MDARIX suggest one</option>
            {[...SIGNAL_PRIORITIES].reverse().map((priority) => (
              <option key={priority} value={priority}>
                {signalPriorityLabel(priority)}
              </option>
            ))}
          </select>
        </label>
        {form.priority && (
          <label className="ca-field">
            Why this priority?
            <textarea
              required
              rows={3}
              maxLength={PRIORITY_REASON_MAX}
              value={form.reason}
              placeholder="At least 10 characters"
              onChange={(event) => setForm({ ...form, reason: event.target.value })}
            />
          </label>
        )}
        {problem && (form.title || form.complaintIds.length > 0) && <p className="uw-hint">{problem}</p>}
        {error && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {error}
          </p>
        )}
        <p className="ac-muted">Recorded in the signal's history and the audit trail.</p>
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Creating…" : "Create signal"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

/**
 * The dashboard's "Signal triage" for people who triage signals: how many signals wait in each state, each opening
 * the inbox filtered to them, and the five open signals to look at first.
 */
export function SignalTriagePanel() {
  const { session, open } = useWorkspace();
  const canTriage = useCan("signal.triage");
  const allowed = sectionAllowed("Signals", session?.allowed_menu, session?.business_permissions);
  if (!canTriage || !allowed) return null;
  return <SignalTriageSummary onOpen={(tab) => open("Signals", tab)} />;
}

function SignalTriageSummary({ onOpen }: { onOpen: (tab: string) => void }) {
  const summary = useResource<TriageSummary>("/api/v1/triage/summary");
  const top = useResource<SignalList>(signalListPath({ status: "OPEN", sort: "priority" }, 1, 5));
  const tiles = triageCountTiles(summary.data);
  const ready = summary.state === "ready";
  const signals = rankSignals(listOf(top.data?.items) as SignalSummary[]).slice(0, 5);
  return (
    <Panel
      eyebrow="Signals"
      title="Signal triage"
      source={summary}
      action={
        <button type="button" className="ac-link" onClick={() => onOpen("Signal inbox")}>
          Open <ChevronRight size={14} aria-hidden="true" />
        </button>
      }
    >
      <div className="uw-task-counts" role="group" aria-label="Signals by triage state">
        {tiles.map((tile) => (
          <button
            type="button"
            key={tile.key}
            className={`uw-task-count ${tile.urgent && (tile.value ?? 0) > 0 ? "urgent" : ""}`}
            onClick={() => onOpen(signalsTab({ filters: tile.filters }))}
          >
            <strong>{ready ? (tile.value ?? 0) : "…"}</strong>
            <span>{tile.label}</span>
          </button>
        ))}
      </div>
      {top.state === "ready" && signals.length > 0 && (
        <ul className="uw-list" aria-label="Open signals to look at first">
          {signals.map((signal) => {
            const reference = safeText(signal.business_id) ?? String(signal.id);
            return (
              <li key={signal.id}>
                <span>
                  <strong>{safeText(signal.business_id) ?? "Signal"}</strong>
                  <small>
                    {safeText(signal.title) ?? "Untitled signal"} · {signalProductText(signal)}
                  </small>
                </span>
                <SignalPriorityCell signal={signal} />
                <SignalDue signal={signal} />
                <button
                  type="button"
                  className="ac-link"
                  aria-label={`Open ${reference}`}
                  onClick={() => onOpen(signalsTab({ signal: reference }))}
                >
                  Open <ChevronRight size={14} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {top.state === "ready" && !signals.length && (
        <Empty title="No open signals" detail="Signals waiting for triage appear here." />
      )}
      {top.state === "error" && <p className="ac-muted">{top.error ?? "Open signals could not be loaded."}</p>}
    </Panel>
  );
}
