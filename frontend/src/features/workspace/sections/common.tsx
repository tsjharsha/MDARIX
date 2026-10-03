import type { ReactNode } from "react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase, type Tone } from "../../admin/console/dashboardModel";
import { Table, formatDate } from "../../customer-admin/shared";
import type { Product360 } from "../../../app/types";
import { useWorkspace } from "../workspaceContext";

/** Render children only once the shared Product 360 context is available; otherwise say why not. */
export function NeedsProduct({ children }: { children: (view: Product360) => ReactNode }) {
  const { work } = useWorkspace();
  if (work.view) return <>{children(work.view)}</>;
  if (work.state === "loading")
    return (
      <Panel title="Loading product context" state="loading">
        {null}
      </Panel>
    );
  if (work.state === "empty")
    return (
      <Panel title="No products yet">
        <Empty title="No products are connected" detail="Products appear once your organization's data is connected." />
      </Panel>
    );
  return (
    <Panel title="Product data unavailable" state="error" error={work.error}>
      {null}
    </Panel>
  );
}

const STATUS_TONE: Record<string, Tone> = {
  OPEN: "warning",
  IN_PROGRESS: "warning",
  CLOSED: "good",
  RESOLVED: "good",
  ACTIVE: "good",
  RELEASED: "good",
  APPROVED: "good",
  REJECTED: "critical",
  CRITICAL: "critical",
  HIGH: "serious",
  MAJOR: "serious",
  MEDIUM: "warning",
  MINOR: "neutral",
  LOW: "neutral",
};

export function StatusBadge({ value }: { value: unknown }) {
  const key = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/ /g, "_");
  if (!key) return <span className="ac-muted">—</span>;
  return <ToneBadge tone={STATUS_TONE[key] ?? "neutral"} label={titleCase(key)} />;
}

const DATE_KEY = /(_at|_time|timestamp|_date)$/;
const STATUS_KEY = /(status|severity)$/;

/** A readable table for record lists whose columns are chosen by the caller. */
export function RecordTable({
  rows,
  columns,
  caption,
  empty,
}: {
  rows: Array<Record<string, unknown>>;
  columns: string[];
  caption: string;
  empty: { title: string; detail: string };
}) {
  return (
    <Table
      caption={caption}
      rows={rows}
      // Relationship lists repeat a record (a supplier once per component it supplies): the position keeps keys unique.
      rowKey={(row, index) => `${row.id ?? row.event_id ?? "row"}:${index}`}
      empty={empty}
      columns={columns.map((key) => ({
        key,
        label: titleCase(key.replace(/_identifier$/, " id")),
        render: (row: Record<string, unknown>) =>
          STATUS_KEY.test(key) ? (
            <StatusBadge value={row[key]} />
          ) : DATE_KEY.test(key) ? (
            formatDate(row[key])
          ) : row[key] === null || row[key] === undefined || row[key] === "" ? (
            <span className="ac-muted">—</span>
          ) : (
            String(row[key])
          ),
      }))}
    />
  );
}

/** Existing full-page screens carry their own page padding; this trims it inside a workspace section. */
export function Embedded({ children }: { children: ReactNode }) {
  return <div className="uw-embedded">{children}</div>;
}
