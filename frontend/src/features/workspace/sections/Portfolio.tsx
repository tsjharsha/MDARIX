import type { RefObject } from "react";
import { Panel } from "../../admin/console/charts";
import { Table, useResource, type Column } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
import { greeting } from "../home";
import { hubTab, inDataShown, productTab, type Origin, type RecordKind } from "../productHub";

/** One product's exposure (GET /api/v1/portfolio, backend/app/product360/portfolio.py). */
export type PortfolioRow = {
  id: string;
  product_identifier: string;
  name: string;
  origin?: Origin | null;
  lots: number;
  units_released: number | null;
  units_shipped: number | null;
  open_complaints: number;
  reportable: number;
  open_investigations: number;
  awaiting_decision: number;
  signed_decisions: number;
};
type Portfolio = { definitions: Record<string, string>; products: PortfolioRow[] };

/** "1,240", or why there is none: units are never guessed. */
export const unitsText = (value: number | null) => (value === null ? "Not recorded" : value.toLocaleString("en-IN"));

/** The investigation status in words: what waits for a decision, else what is signed. */
export function decisionText(
  row: Pick<PortfolioRow, "open_investigations" | "awaiting_decision" | "signed_decisions">,
) {
  if (row.awaiting_decision) return `${row.awaiting_decision} awaiting a signed decision`;
  if (row.open_investigations) return "Open, decision signed";
  if (row.signed_decisions) return `${row.signed_decisions} decision${row.signed_decisions === 1 ? "" : "s"} signed`;
  return "No investigation";
}

/**
 * The Executive's Today (UX2, Persona Blueprint wave D): exposure per product, read-only, from the records only:
 * lots and units, open complaints, reportable complaints and the investigations' decision status. No story button
 * and no action: every figure opens the records it counts, on the product's page, and says what it counts.
 */
export function PortfolioToday({ heading }: { heading: RefObject<HTMLHeadingElement | null> }) {
  const { session, open, dataSource } = useWorkspace();
  const read = useResource<Portfolio>("/api/v1/portfolio");
  const rows = (read.data?.products ?? []).filter((row) => inDataShown(row.origin, dataSource));
  const define = read.data?.definitions ?? {};
  const name = (session?.display_name ?? "").split(/\s+/)[0];
  const records = (row: PortfolioRow, list: RecordKind) =>
    open("Product 360", hubTab({ tab: "Product 360", product: row.product_identifier, view: "Records", list }));
  const count = (row: PortfolioRow, value: number, list: RecordKind, what: string) => (
    <button type="button" className="ac-link" onClick={() => records(row, list)} aria-label={`${value} ${what}`}>
      {value}
    </button>
  );
  const columns: Column<PortfolioRow>[] = [
    {
      key: "name",
      label: "Product",
      render: (row) => (
        <button
          type="button"
          className="ac-link"
          onClick={() => open("Product 360", productTab(row.product_identifier))}
        >
          {row.name}
        </button>
      ),
    },
    { key: "lots", label: "Lots", numeric: true, render: (row) => row.lots },
    { key: "units_shipped", label: "Units shipped", numeric: true, render: (row) => unitsText(row.units_shipped) },
    {
      key: "open_complaints",
      label: "Open complaints",
      numeric: true,
      render: (row) => count(row, row.open_complaints, "complaints", `open complaints on ${row.name}`),
    },
    {
      key: "reportable",
      label: "Reportable",
      numeric: true,
      render: (row) => count(row, row.reportable, "reports", `reportable complaints on ${row.name}`),
    },
    {
      key: "open_investigations",
      label: "Investigations",
      render: (row) => (
        <button type="button" className="ac-link" onClick={() => records(row, "investigations")}>
          {row.open_investigations} open · {decisionText(row)}
        </button>
      ),
    },
  ];
  return (
    <div className="uw-home uw-portfolio">
      <header className="uw-home-head">
        <div>
          <h1 ref={heading} tabIndex={-1}>
            {greeting()}
            {name ? `, ${name}` : ""}
          </h1>
          <p>Product exposure today: what is in the field, what is open and what is decided. Read-only.</p>
        </div>
      </header>
      <Panel title="Product exposure" eyebrow="Today · Management" source={read}>
        <Table
          caption="Product exposure"
          rows={rows}
          columns={columns}
          rowKey={(row) => row.id}
          empty={{ title: "No products yet", detail: "Products appear here once they are imported." }}
        />
        <dl className="uw-pf-defs">
          {["lots", "units_shipped", "open_complaints", "reportable", "awaiting_decision"].map(
            (key) =>
              define[key] && (
                <div key={key}>
                  <dt>{LABELS[key]}</dt>
                  <dd>{define[key]}</dd>
                </div>
              ),
          )}
        </dl>
      </Panel>
    </div>
  );
}

const LABELS: Record<string, string> = {
  lots: "Lots",
  units_shipped: "Units shipped",
  open_complaints: "Open complaints",
  reportable: "Reportable",
  awaiting_decision: "Awaiting decision",
};
