import { useState } from "react";
import { Download } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { Table, errorText, formatDate, useResource, type Column } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { OVERSIGHT } from "../oversight";
import { useCan, useValueCentre } from "../workspaceContext";
import { InlineError } from "./boardParts";

type Summary = { count: number; median: number | null; p90: number | null };
export type ValueMetric = {
  code: string;
  label: string;
  unit: "hours" | "days" | "percent";
  definition: string;
  baseline: Summary | null;
  months: (Summary & { month: string })[];
  imported: Summary | null;
};
export type ValueCentreData = {
  go_live: string | null;
  baseline: { from: string | null; to: string | null; fixed: boolean };
  metrics: ValueMetric[];
};

const UNITS = { hours: "h", days: "days", percent: "%" } as const;

/** "8.0 h (90 % within 10.0 h, 12 records)"; "Not measured yet" when no record has both timestamps. */
export function summaryText(item: Summary | null | undefined, unit: ValueMetric["unit"]): string {
  if (!item || !item.count || item.median === null) return "Not measured yet";
  const mark = UNITS[unit];
  const value = (number: number | null) => (unit === "percent" ? `${number}${mark}` : `${number} ${mark}`);
  const within = unit === "percent" ? "90 % at or below" : "90 % within";
  return `${value(item.median)} (${within} ${value(item.p90)}, ${item.count} record${item.count === 1 ? "" : "s"})`;
}

const COLUMNS: Column<ValueMetric>[] = [
  {
    key: "label",
    label: "Measure",
    render: (row) => (
      <span>
        <strong>{row.label}</strong>
        <br />
        <small className="ac-muted">{row.definition}</small>
      </span>
    ),
  },
  { key: "baseline", label: "Your baseline", render: (row) => summaryText(row.baseline, row.unit) },
  {
    key: "month",
    label: "Latest month",
    render: (row) => `${row.months[0] ? `${row.months[0].month}: ` : ""}${summaryText(row.months[0], row.unit)}`,
  },
  {
    key: "imported",
    label: "From your QMS export, before MDARIX",
    render: (row) => (row.imported ? summaryText(row.imported, row.unit) : "—"),
  },
];

/** B6a P2 Value Centre v0: four outcome numbers from the timestamps the records already hold (median and 90th
 * percentile), against the baseline of the first 30 days after go-live; the QMS's own history apart. No person's
 * time, and no figure for anyone outside the organization. Flat (G-2). */
export function ValueCentre() {
  const on = useValueCentre();
  const canExport = useCan("data.export");
  const data = useResource<ValueCentreData>(on ? `${OVERSIGHT}/value-centre` : null);
  const [error, setError] = useState("");
  if (!on) return null;
  const view = data.data;
  const download = () =>
    void downloadFile(`${OVERSIGHT}/value-centre.csv`, { fallbackName: "mdarix-value-centre.csv" }).catch((reason) =>
      setError(errorText(reason, "The numbers could not be downloaded.")),
    );
  return (
    <Panel
      eyebrow="Value Centre"
      title="Outcome numbers"
      source={data}
      action={
        canExport ? (
          <button type="button" className="ac-secondary" onClick={download}>
            <Download size={15} aria-hidden="true" /> CSV
          </button>
        ) : undefined
      }
    >
      {view && (
        <>
          <p className="ac-muted">
            Measured from the timestamps your records already hold: no one&apos;s working time is tracked, and nothing
            here is shared outside your organization.{" "}
            {view.baseline.from
              ? view.baseline.fixed
                ? `Your baseline: the first 30 days after go-live (${formatDate(view.baseline.from)} to ${formatDate(view.baseline.to)}), fixed.`
                : `Your baseline is still being measured: the first 30 days after go-live, until ${formatDate(view.baseline.to)}.`
              : ""}
          </p>
          <Table
            rows={view.metrics}
            columns={COLUMNS}
            rowKey={(row) => row.code}
            caption="Outcome numbers: median, 90th percentile and count"
            empty={{ title: "No numbers yet", detail: "They appear as your own records go through MDARIX." }}
          />
        </>
      )}
      <InlineError text={error} />
    </Panel>
  );
}
