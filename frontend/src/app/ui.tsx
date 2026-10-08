import React from "react";
import { ClipboardList } from "lucide-react";
import { fmt } from "./format";
import { SortableHeader, useSortedRows } from "./tableSort";

export type AnalysisItem = {
  item_id: string;
  semantic_type: string;
  statement: string;
  grounding_status: string;
  source_references: unknown[];
};

export function AnalysisPanel({ title, items }: { title: string; items: AnalysisItem[] }) {
  return (
    <Panel title={title} icon={<ClipboardList />}>
      <div className="analysis-list">
        {items.length === 0 && <p className="empty">No items for this analysis.</p>}
        {items.map((item) => (
          <article key={item.item_id}>
            <span>
              {item.semantic_type} | {item.grounding_status} | sources {item.source_references.length}
            </span>
            <p>{item.statement}</p>
          </article>
        ))}
      </div>
    </Panel>
  );
}

export function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: unknown }) {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{String(value)}</strong>
    </div>
  );
}

export function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="section-title">
        {icon}
        {title}
      </div>
      {children}
    </section>
  );
}

export function DenseTable({ rows, columns }: { rows: Array<Record<string, string | null>>; columns: string[] }) {
  const { sorted, sort, toggle } = useSortedRows(rows, (row, key) => row[key]);
  if (!rows.length) return <p className="empty">No records for this view.</p>;
  return (
    <table>
      <thead>
        <tr>
          {columns.map((column) => (
            <SortableHeader
              key={column}
              label={column.replace(/_/g, " ")}
              sortKey={column}
              sort={sort}
              onSort={toggle}
            />
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row, index) => (
          <tr key={index}>
            {columns.map((column) => (
              <td key={column}>{fmt(row[column]) === "Not recorded" ? (row[column] ?? "—") : fmt(row[column])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
