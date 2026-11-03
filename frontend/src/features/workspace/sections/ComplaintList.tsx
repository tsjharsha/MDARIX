import { useState } from "react";
import { Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { SearchBox, Table, idColumn, listOf, sourceIdColumn, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { sortParams, useServerSort } from "../../../app/tableSort";
import { displayId } from "../../../app/displayId";
import {
  investigationRequestFor,
  sectionAllowed,
  useOpenInvestigation,
  useTabFilters,
  useWorkspace,
} from "../workspaceContext";
import { StatusBadge, listTitle } from "./common";
import { DeadlineChip, HarmChip } from "../../../app/chips";
import { marketLabel } from "../../../app/labels";
import { ProblemCode, problemCodeParts, problemCodeText, useImdrfLinks, type ImdrfLinks } from "./ProblemCode";
import { isLegalDeadline } from "../home";
import {
  EMPTY_COMPLAINT_FILTERS,
  complaintFilterValues,
  complaintListPath,
  hasComplaintFilters,
  sourceChoices,
  sourceText,
  versionChoices,
  versionValue,
  type ComplaintListFilters,
  type ComplaintVersionChoice,
} from "../complaintList";

// The complaint list's columns the server sorts across every page (GET /api/v1/complaints sort/order).
const COMPLAINT_SORTS = [
  "business_id",
  "complaint_identifier",
  "product",
  "description",
  "received",
  "severity",
  "status",
  "cases",
] as const;

/**
 * Every complaint in the organization, across products: search, filter by product, status, version, lot, problem code,
 * country and, in a free trial with the sample data, only the imported or only the sample complaints; page through. `initialFilters` comes from a link (Getting started › Automatic insights).
 */
export function ComplaintList({
  eyebrow = "Signals",
  initialFilters,
  work: sixColumns = false,
  view,
}: {
  eyebrow?: string;
  initialFilters?: ComplaintListFilters;
  /** The new navigation's list (0.10.68): six columns, each complaint opening its own page. */
  work?: boolean;
  /** A list view the server filters (0.10.74, C2: listViews.ts SERVER_VIEWS): its name and code; no filter bar. */
  view?: { name: string; code: string };
}) {
  const { work, open, session, dataSource } = useWorkspace();
  const canImport = sectionAllowed(
    "Import data",
    session?.allowed_menu,
    session?.business_permissions,
    session?.sample_only,
  );
  const openInvestigation = useOpenInvestigation();
  // While the top bar chooses the data (0.10.80), a link's own data filter is its; the list's filters leave it out.
  const [filters, setFilters] = useState<ComplaintListFilters>(() => ({
    ...(initialFilters ?? EMPTY_COMPLAINT_FILTERS),
    ...(dataSource ? { source: "" } : {}),
  }));
  const [page, setPage] = useState(1);
  const { sort, onSort } = useServerSort(() => setPage(1));
  // The top bar's "Sample data · Your data" (0.10.80) decides the data while a trial has both; else the list's own.
  const shown = { ...filters, source: dataSource || filters.source };
  const list = useResource<any>(
    `${complaintListPath(shown, page, sortParams(sort))}${sixColumns || view ? "&work=1" : ""}${
      view ? `&view=${encodeURIComponent(view.code)}` : ""
    }`,
  );
  const links = useImdrfLinks(sixColumns || view ? listOf(list.data?.items).map((row: any) => row.problem_code) : []);
  const openRow = (row: any) =>
    open("Complaint", `Summary?${new URLSearchParams({ ref: row.complaint_identifier ?? row.id })}`);
  const pages = list.data?.pages ?? 1;
  // The filters are part of the address (Complaint list?country=US): a change replaces it, so refresh keeps them.
  const keepFilters = useTabFilters();
  const set = (change: Partial<ComplaintListFilters>) => {
    const next = { ...filters, ...change };
    setFilters(next);
    keepFilters(complaintFilterValues(next));
    setPage(1);
  };
  return (
    // Named like the other lists, "Complaint list · 4,993": the count after "Complaints in your organization" read as a
    // stray "· 4993" (0.10.43), and it is the count of the filters chosen, not of the whole organization.
    <Panel eyebrow={eyebrow} title={listTitle(view?.name ?? "Complaint list", list.data?.total)} source={list}>
      {!view && (
        <ComplaintFilterBar
          // A new lot filter (cleared, or from a link) starts the lot field afresh.
          key={filters.lot}
          filters={filters}
          data={list.data}
          products={work.products}
          onChange={set}
          sourceChosen={!!dataSource}
        />
      )}
      <Table
        caption={view?.name ?? "Complaint list"}
        rows={listOf(list.data?.items)}
        rowKey={(row) => String(row.id)}
        empty={
          view
            ? { title: "Nothing in this view", detail: "No complaint matches it today. Choose another list view." }
            : hasComplaintFilters(filters)
              ? {
                  title: "No complaints match these filters",
                  detail: "Clear a filter to see more complaints.",
                  action: (
                    <button type="button" className="ac-secondary" onClick={() => set(EMPTY_COMPLAINT_FILTERS)}>
                      Clear the filters
                    </button>
                  ),
                }
              : {
                  title: "No complaints found",
                  detail: "Complaints arrive through imports.",
                  action: canImport ? (
                    <button type="button" className="ac-secondary" onClick={() => open("Import data")}>
                      Import your data
                    </button>
                  ) : undefined,
                }
        }
        serverSort={{ sort, onSort, keys: COMPLAINT_SORTS }}
        {...(sixColumns || view ? { onRowClick: openRow, chooserUnderMore: true, className: "uw-clist" } : {})}
        columns={
          sixColumns || view
            ? workColumns(links, openRow)
            : [
                idColumn("Complaint ID", "complaint_identifier"),
                sourceIdColumn("complaint_identifier"),
                {
                  key: "product",
                  label: "Product",
                  fields: ["product_name", "product_identifier", "version"],
                  render: (row) => `${row.product_name}${row.version ? ` · ${row.version}` : ""}`,
                },
                { key: "description", label: "Description", render: (row) => row.description ?? "—" },
                {
                  key: "received",
                  label: "Received",
                  fields: ["received_date"],
                  render: (row) => formatDay(row.received_date ?? row.event_date),
                },
                {
                  key: "severity",
                  label: "Severity",
                  fields: ["severity", "patient_involved", "serious_injury", "death"],
                  render: (row) => (
                    <span className="ca-person">
                      <span>{row.severity ? titleCase(String(row.severity)) : "—"}</span>
                      {(row.death || row.serious_injury) && (
                        <small className="uw-flag-critical">Serious injury or death</small>
                      )}
                      {!row.death && !row.serious_injury && row.patient_involved && <small>Patient involved</small>}
                    </span>
                  ),
                },
                { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
                {
                  key: "cases",
                  label: "Investigations",
                  numeric: true,
                  fields: ["investigations"],
                  render: (row) => row.investigations,
                },
                ...(openInvestigation
                  ? [
                      {
                        key: "open-investigation",
                        label: "",
                        render: (row: any) => {
                          const request = investigationRequestFor(row);
                          return request ? (
                            <button
                              type="button"
                              className="ac-link"
                              aria-label={`Open an investigation for ${displayId(row, "complaint_identifier", "this complaint")}`}
                              onClick={() => openInvestigation(request)}
                            >
                              Open investigation
                            </button>
                          ) : null;
                        },
                      },
                    ]
                  : []),
              ]
        }
      />
      {pages > 1 && (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span className="ac-muted">
            Page {page} of {pages}
          </span>
          <button type="button" className="ac-secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      )}
    </Panel>
  );
}

/** The list's filters (exported so its test renders it without the list's data). */
export function ComplaintFilterBar({
  filters,
  data,
  products,
  onChange,
  sourceChosen = false,
}: {
  filters: ComplaintListFilters;
  data: any;
  products: { id: string; name: string | null }[];
  onChange: (change: Partial<ComplaintListFilters>) => void;
  /** The top bar chooses the data (0.10.80): no Data choice here. */
  sourceChosen?: boolean;
}) {
  // The lot number as typed; the list asks for it when the person presses Enter or leaves the field.
  const [lotText, setLotText] = useState(filters.lot);
  const versions = versionChoices(listOf(data?.versions) as ComplaintVersionChoice[], filters.productId);
  const sources = sourceChosen ? [] : sourceChoices(listOf(data?.sources), filters.source);
  // The IMDRF codes the problem codes map to (G2a, approved links only), shown in the problem-code choice.
  const problemCodes = listOf(data?.problem_codes) as string[];
  const imdrf = useResource<{ links: ImdrfLinks }>(
    problemCodes.length
      ? `/api/v1/regulatory-reference/imdrf/links?${new URLSearchParams(problemCodes.map((code) => ["code", code]))}`
      : null,
  );
  const applyLot = () => {
    if (lotText.trim() !== filters.lot) onChange({ lot: lotText.trim() });
  };
  return (
    <div className="cc-toolbar">
      <SearchBox value={filters.q} onChange={(value) => onChange({ q: value })} label="Search complaint ID or text" />
      <select
        aria-label="Product"
        value={filters.productId}
        // A version of another product no longer applies.
        onChange={(event) => onChange({ productId: event.target.value, version: "" })}
      >
        <option value="">All products</option>
        {products.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      <select
        aria-label="Version"
        value={filters.version}
        onChange={(event) => onChange({ version: event.target.value })}
      >
        <option value="">All versions</option>
        {filters.version && !versions.some((item) => versionValue(item) === filters.version) && (
          <option value={filters.version}>{filters.version}</option>
        )}
        {versions.map((item) => (
          <option key={item.id} value={versionValue(item)}>
            {item.label}
          </option>
        ))}
      </select>
      <input
        type="search"
        aria-label="Lot number"
        placeholder="Lot number"
        value={lotText}
        maxLength={120}
        onChange={(event) => {
          setLotText(event.target.value);
          if (!event.target.value.trim() && filters.lot) onChange({ lot: "" });
        }}
        onBlur={applyLot}
        onKeyDown={(event) => {
          if (event.key === "Enter") applyLot();
        }}
      />
      <FacetSelect
        label="Problem code"
        all="All problem codes"
        value={filters.problemCode}
        values={problemCodes}
        labels={imdrfLabels(problemCodes, imdrf.data?.links)}
        onChange={(value) => onChange({ problemCode: value })}
      />
      <FacetSelect
        label="Country"
        all="All countries"
        value={filters.country}
        values={listOf(data?.countries)}
        onChange={(value) => onChange({ country: value })}
      />
      <select aria-label="Status" value={filters.status} onChange={(event) => onChange({ status: event.target.value })}>
        <option value="">All statuses</option>
        {listOf(data?.statuses).map((value: string) => (
          <option key={value} value={value}>
            {titleCase(value)}
          </option>
        ))}
      </select>
      {sources.length > 0 && (
        <select aria-label="Data" value={filters.source} onChange={(event) => onChange({ source: event.target.value })}>
          <option value="">All data</option>
          {sources.map((value) => (
            <option key={value} value={value}>
              {sourceText(value)}
            </option>
          ))}
        </select>
      )}
      {hasComplaintFilters(filters) && (
        <button type="button" className="ac-link" onClick={() => onChange(EMPTY_COMPLAINT_FILTERS)}>
          Clear filters
        </button>
      )}
    </div>
  );
}

/**
 * The problem-code choice's labels: "Protective Measures Problem (IMDRF A16) · your code PRESSURE_ALARM" (exported for
 * its test). A code with no approved IMDRF link keeps its own text; the customer's code is never altered.
 */
export function imdrfLabels(codes: string[], links: ImdrfLinks | undefined): Record<string, string> {
  return Object.fromEntries(
    codes.filter((code) => links?.[code]?.length).map((code) => [code, problemCodeText(code, links ?? {})]),
  );
}

/** One deadline or target of a complaint (backend/app/oversight/router.py complaint_work). */
type WorkDue = {
  key: string;
  category?: string;
  category_label?: string;
  title: string;
  market: string | null;
  due_at: string;
  due_label?: string;
  state: string;
  hours_left: number;
};

/** What the new navigation's list shows of a complaint's work, as its page shows it. */
export type ComplaintWork = {
  owner_name: string | null;
  stage: string;
  next: string | null;
  due: WorkDue[];
  markets: string[];
};

const harmOf = (row: any) =>
  row.death
    ? ({ harm: "critical", label: "Death" } as const)
    : row.serious_injury
      ? ({ harm: "serious", label: "Serious injury" } as const)
      : null;

/**
 * The six columns of the new navigation's lists (7.5; 0.10.85, D3.1): Legal clock · What happened · Product, version,
 * lot · Incident country · Owner · Stage. The reference is the row's one action, and the whole row opens the
 * complaint's page; the problem reads as its IMDRF term (U-16), the customer's code only in its tooltip.
 */
export function workColumns(links: ImdrfLinks, onOpen: (row: any) => void) {
  const work = (row: any): ComplaintWork | null => row.work ?? null;
  return [
    {
      key: "urgency",
      label: "Legal clock",
      render: (row: any) => {
        const due = work(row)?.due ?? [];
        const legal = (item: WorkDue) => isLegalDeadline({ key: item.key, category: item.category ?? "" });
        const nearest = due.find(legal) ?? due[0];
        // An overdue target of the organization's own (a reply, the triage) shows beside the legal clock: it is why
        // the row is first.
        const late = due.find((item) => item !== nearest && !legal(item) && item.state === "OVERDUE");
        const harm = harmOf(row);
        return (
          <span className="uw-urgency">
            {nearest ? <DeadlineChip item={nearest} /> : <span className="ac-muted">No deadline</span>}
            {late && <DeadlineChip item={late} prefix={late.category_label ?? "Target"} />}
            {harm && <HarmChip harm={harm.harm} label={harm.label} />}
          </span>
        );
      },
    },
    {
      key: "what",
      label: "What happened",
      render: (row: any) => (
        <span className="uw-what">
          <button type="button" className="ac-link" onClick={() => onOpen(row)}>
            <strong>{row.complaint_identifier ?? row.business_id}</strong>
          </button>{" "}
          <span className="uw-what-text">{row.description ?? "No description recorded"}</span>
          <ImdrfTerm code={row.problem_code} links={links} />
        </span>
      ),
    },
    {
      key: "product",
      label: "Product, version, lot",
      render: (row: any) => (
        <>
          {[row.product_name, row.version].filter(Boolean).join(" · ") || "—"}
          {row.lot && <span className="uw-lot"> · Lot {row.lot}</span>}
        </>
      ),
    },
    {
      key: "country",
      label: "Incident country",
      render: (row: any) => String(row.country ?? "").trim() || <span className="ac-muted">Asked at the tree</span>,
    },
    { key: "owner", label: "Owner", render: (row: any) => work(row)?.owner_name ?? "Not named" },
    { key: "stage", label: "Stage", render: (row: any) => work(row)?.stage ?? "—" },
  ];
}

/** A problem as its IMDRF term, or "No IMDRF term yet"; the customer's own code only in the tooltip (U-16). */
export function ImdrfTerm({ code, links }: { code: string | null | undefined; links: ImdrfLinks }) {
  if (!code) return <small className="ac-muted">No problem recorded</small>;
  const term = problemCodeParts(code, links).term;
  return term ? (
    <small className="uw-imdrf" title={`Your code: ${code}`}>
      {term}
    </small>
  ) : (
    <small className="ac-muted" title={`Your code: ${code}`}>
      No IMDRF term yet
    </small>
  );
}

function FacetSelect({
  label,
  all,
  value,
  values,
  labels,
  onChange,
}: {
  label: string;
  all: string;
  value: string;
  values: string[];
  /** What an option reads, where it is more than the value. */
  labels?: Record<string, string>;
  onChange: (value: string) => void;
}) {
  const known = values.includes(value);
  return (
    <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{all}</option>
      {value && !known && <option value={value}>{value}</option>}
      {values.map((item) => (
        <option key={item} value={item}>
          {labels?.[item] ?? item}
        </option>
      ))}
    </select>
  );
}
