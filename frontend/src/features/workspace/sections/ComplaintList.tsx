import { useState } from "react";
import { Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { SearchBox, Table, idColumn, listOf, sourceIdColumn, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { sortParams, useServerSort } from "../../../app/tableSort";
import { displayId } from "../../../app/displayId";
import { investigationRequestFor, useOpenInvestigation, useWorkspace } from "../workspaceContext";
import { StatusBadge, listTitle } from "./common";
import {
  EMPTY_COMPLAINT_FILTERS,
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
}: {
  eyebrow?: string;
  initialFilters?: ComplaintListFilters;
}) {
  const { work } = useWorkspace();
  const openInvestigation = useOpenInvestigation();
  const [filters, setFilters] = useState<ComplaintListFilters>(() => initialFilters ?? EMPTY_COMPLAINT_FILTERS);
  const [page, setPage] = useState(1);
  const { sort, onSort } = useServerSort(() => setPage(1));
  const list = useResource<any>(complaintListPath(filters, page, sortParams(sort)));
  const pages = list.data?.pages ?? 1;
  const set = (change: Partial<ComplaintListFilters>) => {
    setFilters((current) => ({ ...current, ...change }));
    setPage(1);
  };
  return (
    // Named like the other lists, "Complaint list · 4,993": the count after "Complaints in your organization" read as a
    // stray "· 4993" (0.10.43), and it is the count of the filters chosen, not of the whole organization.
    <Panel eyebrow={eyebrow} title={listTitle("Complaint list", list.data?.total)} source={list}>
      <ComplaintFilterBar
        // A new lot filter (cleared, or from a link) starts the lot field afresh.
        key={filters.lot}
        filters={filters}
        data={list.data}
        products={work.products}
        onChange={set}
      />
      <Table
        caption="Complaint list"
        rows={listOf(list.data?.items)}
        rowKey={(row) => String(row.id)}
        empty={
          hasComplaintFilters(filters)
            ? { title: "No complaints match these filters", detail: "Clear a filter to see more complaints." }
            : { title: "No complaints found", detail: "Complaints arrive through connectors and imports." }
        }
        serverSort={{ sort, onSort, keys: COMPLAINT_SORTS }}
        columns={[
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
        ]}
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
}: {
  filters: ComplaintListFilters;
  data: any;
  products: { id: string; name: string | null }[];
  onChange: (change: Partial<ComplaintListFilters>) => void;
}) {
  // The lot number as typed; the list asks for it when the person presses Enter or leaves the field.
  const [lotText, setLotText] = useState(filters.lot);
  const versions = versionChoices(listOf(data?.versions) as ComplaintVersionChoice[], filters.productId);
  const sources = sourceChoices(listOf(data?.sources), filters.source);
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
        values={listOf(data?.problem_codes)}
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

/** A filter over the values the complaints record; a value from a link that the list does not offer stays chosen. */
function FacetSelect({
  label,
  all,
  value,
  values,
  onChange,
}: {
  label: string;
  all: string;
  value: string;
  values: string[];
  onChange: (value: string) => void;
}) {
  const known = values.includes(value);
  return (
    <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{all}</option>
      {value && !known && <option value={value}>{value}</option>}
      {values.map((item) => (
        <option key={item} value={item}>
          {item}
        </option>
      ))}
    </select>
  );
}
