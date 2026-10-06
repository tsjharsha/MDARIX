import { useMemo, useState } from "react";
import { BarList, ColumnChart, Panel } from "../../admin/console/charts";
import { chartWindowEnd, dailyCounts, titleCase, type Slice } from "../../admin/console/dashboardModel";
import { SearchBox, Table, Tabs, listOf, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { useWorkspace } from "../workspaceContext";
import { Stage2Experience } from "../../stage2/Stage2Experience";
import { Embedded, NeedsProduct, RecordTable, StatusBadge } from "./common";

const TABS = ["Product complaints", "Complaint list", "All signals", "Trends"] as const;
type Tab = (typeof TABS)[number];

export function SignalsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Product complaints",
  );
  return (
    <>
      <p className="ca-lede">Signals are recorded observations. They are not conclusions about cause.</p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Signal sections">
        {active === "Product complaints" && (
          <NeedsProduct>
            {(view) => (
              <Panel eyebrow={view.product.name ?? "Product"} title="Complaints for the selected version">
                <RecordTable
                  caption="Complaints"
                  rows={view.complaints}
                  columns={["complaint_identifier", "event_timestamp", "recorded_timestamp", "status"]}
                  empty={{
                    title: "No complaints recorded",
                    detail: "Complaints for this product version appear here.",
                  }}
                />
              </Panel>
            )}
          </NeedsProduct>
        )}
        {active === "All signals" && (
          <Embedded>
            <Stage2Experience mode="signals" />
          </Embedded>
        )}
        {active === "Complaint list" && <ComplaintList />}
        {active === "Trends" && <Trends />}
      </Tabs>
    </>
  );
}

function Trends() {
  const signals = useResource<any>("/api/v1/analytics/signals");
  const rows = listOf(signals.data?.signals);
  const model = useMemo(() => {
    const bySeverity = new Map<string, number>();
    for (const row of rows) {
      const key = row.severity ? titleCase(String(row.severity)) : "Not recorded";
      bySeverity.set(key, (bySeverity.get(key) ?? 0) + 1);
    }
    const severity: Slice[] = [...bySeverity.entries()]
      .map(([label, count]) => ({ key: label, label, count, tone: "neutral" as const }))
      .sort((a, b) => b.count - a.count);
    const timestamps = rows.map((row) => row.event_timestamp);
    const span = chartWindowEnd(timestamps, 30);
    return {
      severity,
      trend: dailyCounts(timestamps, 30, span.end),
      // Older data: show the 30 days up to the latest signal, and say so in the title.
      title: span.shifted
        ? `Signals by event date · 30 days to ${span.end.toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
            timeZone: "UTC",
          })} (latest signal)`
        : "Signals by event date · last 30 days",
    };
  }, [signals.data]);
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Signals" title={model.title} source={signals}>
        <ColumnChart data={model.trend} unit="signals" caption="latest 100 recorded signals" />
      </Panel>
      <Panel eyebrow="Signals" title="By recorded severity" source={signals}>
        {model.severity.length ? (
          <BarList items={model.severity} colour="series" />
        ) : (
          <p className="ac-muted">No signals recorded yet.</p>
        )}
        <p className="ac-note">Severity is shown only when the source system recorded it.</p>
      </Panel>
    </div>
  );
}

/** Every complaint in the organization, across products: search, filter by product and status, page through. */
function ComplaintList() {
  const { work } = useWorkspace();
  const [query, setQuery] = useState("");
  const [product, setProduct] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), page_size: "50" });
  if (query.trim()) params.set("q", query.trim());
  if (product) params.set("product_id", product);
  if (status) params.set("status", status);
  const list = useResource<any>(`/api/v1/complaints?${params}`);
  const pages = list.data?.pages ?? 1;
  const reset = (apply: () => void) => {
    apply();
    setPage(1);
  };
  return (
    <Panel
      eyebrow="Signals"
      title={`Complaints in your organization${list.data ? ` · ${list.data.total}` : ""}`}
      source={list}
    >
      <div className="cc-toolbar">
        <SearchBox
          value={query}
          onChange={(value) => reset(() => setQuery(value))}
          label="Search complaint ID or text"
        />
        <select aria-label="Product" value={product} onChange={(event) => reset(() => setProduct(event.target.value))}>
          <option value="">All products</option>
          {work.products.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select aria-label="Status" value={status} onChange={(event) => reset(() => setStatus(event.target.value))}>
          <option value="">All statuses</option>
          {listOf(list.data?.statuses).map((value: string) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </div>
      <Table
        caption="Complaint list"
        rows={listOf(list.data?.items)}
        rowKey={(row) => String(row.id)}
        empty={{ title: "No complaints found", detail: "Complaints arrive through connectors and imports." }}
        columns={[
          {
            key: "id",
            label: "Complaint",
            fields: ["complaint_identifier"],
            render: (row) => <strong>{row.complaint_identifier}</strong>,
          },
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
                <span>{row.severity ?? "—"}</span>
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
