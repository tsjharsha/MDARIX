import type { ReactNode } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { HarmChip, StateChip, type Harm } from "../../../app/chips";
import { Table, formatDate, idColumn, type Column } from "../../customer-admin/shared";
import { hideUuid, isUuid, safeText } from "../../../app/displayId";
import { formatDay } from "../../../app/dates";
import type { Product360 } from "../../../app/types";
import { sectionAllowed, useWorkspace } from "../workspaceContext";
import { Upload } from "lucide-react";

/** A count with en-US grouping, whatever the browser's language: "4,993" (DEV-025). */
export const formatCount = (count: number) => count.toLocaleString("en-US");

/** A list's heading: its name, then how many it holds once read ("Signal inbox · 2", "Complaint list · 4,993"). */
export const listTitle = (name: string, total: number | null | undefined) =>
  typeof total === "number" ? `${name} · ${formatCount(total)}` : name;

/** "1 complaint", "3 complaints": a count with its noun in the right number. */
export const countOf = (count: number, noun: string, plural = `${noun}s`) =>
  `${formatCount(count)} ${count === 1 ? noun : plural}`;

/** Render children only once the shared Product 360 context is available; otherwise say why not. */
export function NeedsProduct({ children }: { children: (view: Product360) => ReactNode }) {
  const { work, session, open } = useWorkspace();
  const canImport = sectionAllowed("Import data", session?.allowed_menu, session?.business_permissions);
  if (work.view) return <>{children(work.view)}</>;
  if (work.state === "loading")
    return (
      <Panel title="Loading your products" state="loading">
        {null}
      </Panel>
    );
  if (work.state === "empty")
    return (
      <Panel title="No products yet">
        <Empty
          title="No products are connected"
          detail={
            canImport
              ? "Import your products, lots and complaints as CSV files, or ask your administrator to connect your systems."
              : "Products appear once your administrator connects your systems or imports your data."
          }
        />
        {canImport && (
          <div className="ca-action-row">
            <button type="button" className="ac-primary" onClick={() => open("Import data")}>
              <Upload size={16} aria-hidden="true" /> Import data
            </button>
          </div>
        )}
      </Panel>
    );
  return (
    <Panel title="Product data unavailable" state="error" error={work.error} onRetry={work.refreshProducts}>
      {null}
    </Panel>
  );
}

/** Said once, at each point where a person signs or submits (V5), instead of disclaimers across the screen. */
export const DECIDE_AND_SIGN =
  "You decide and sign. MDARIX prepared this from your records; it never decides or submits.";

export function DecideAndSign() {
  return <p className="ms-decide">{DECIDE_AND_SIGN}</p>;
}

/** A record's other ID, in its details only: the screen shows one (the customer's own reference, J18). */
export function AlsoKnownAs({ id, shown }: { id?: string | null; shown?: string | null }) {
  if (!id || id === shown) return null;
  return (
    <p className="uw-cr-meta">
      Also known as <span className="ms-id">{id}</span>
    </p>
  );
}

// Severities read as harm (an outlined chip with its shape); every other status is a neutral state (V1).
const SEVERITY_HARM: Record<string, Harm> = {
  CRITICAL: "critical",
  HIGH: "serious",
  MAJOR: "serious",
  SERIOUS: "serious",
  MEDIUM: "none",
  MINOR: "none",
  LOW: "none",
};

export function StatusBadge({ value }: { value: unknown }) {
  const key = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/ /g, "_");
  if (!key) return <span className="ac-muted">—</span>;
  const harm = SEVERITY_HARM[key];
  return harm ? <HarmChip harm={harm} label={titleCase(key)} /> : <StateChip label={titleCase(key)} />;
}

const DATE_KEY = /(_at|_time|timestamp)$/;
// Calendar dates (received_date, due_date …): a day, never a time of day the record does not have.
const DAY_KEY = /_date$/;
const STATUS_KEY = /(status|severity)$/;

/**
 * Field keys of a record that can be listed as columns: never its UUID or a reference to another record's UUID, and
 * never business_id (the ID column shows it). For lists whose columns follow the records' own fields.
 */
export const recordFieldKeys = (row: Record<string, unknown> | undefined, fallback: string[]): string[] =>
  row
    ? Object.keys(row).filter((key) => key !== "business_id" && key !== "id" && !/_id$/.test(key) && !isUuid(row[key]))
    : fallback;

/**
 * A readable table for record lists whose columns are chosen by the caller. With `idLabel` ("Lot ID") and records
 * that carry their MDARIX ID, the list starts with that ID and the record's own `*_identifier` (the first column, the
 * number in the customer's system) is shown as its "Source ID". A UUID is never shown.
 */
export function RecordTable({
  rows,
  columns,
  caption,
  empty,
  idLabel,
  labels,
  codes,
}: {
  rows: Array<Record<string, unknown>>;
  columns: string[];
  caption: string;
  empty: { title: string; detail: string };
  idLabel?: string;
  /** Plain-English column headings for field keys whose generated heading would read as a database name. */
  labels?: Record<string, string>;
  /** Field keys whose values are codes (PRODUCT_VERSION): shown as words (Product Version). */
  codes?: string[];
}) {
  const withId = !!idLabel && rows.some((row) => safeText(row.business_id));
  const sourceKey = withId && columns[0]?.endsWith("_identifier") ? columns[0] : null;
  const fields: Column<Record<string, unknown>>[] = columns
    .filter((key) => key !== "business_id")
    .map((key) => ({
      key,
      label: key === sourceKey ? "Source ID" : (labels?.[key] ?? titleCase(key.replace(/_identifier$/, " id"))),
      render: (row: Record<string, unknown>) =>
        STATUS_KEY.test(key) ? (
          <StatusBadge value={row[key]} />
        ) : DAY_KEY.test(key) ? (
          formatDay(row[key] as string, String(row[key]))
        ) : DATE_KEY.test(key) ? (
          formatDate(row[key])
        ) : safeText(row[key]) === null ? (
          <span className="ac-muted">—</span>
        ) : codes?.includes(key) ? (
          titleCase(String(row[key]))
        ) : (
          hideUuid(row[key])
        ),
    }));
  return (
    <Table
      caption={caption}
      rows={rows}
      // Relationship lists repeat a record (a supplier once per component it supplies): the position keeps keys unique.
      rowKey={(row, index) => `${row.id ?? row.event_id ?? "row"}:${index}`}
      empty={empty}
      columns={
        withId && idLabel ? [idColumn<Record<string, unknown>>(idLabel, sourceKey ?? undefined), ...fields] : fields
      }
    />
  );
}

/** How each source value was matched to an MDARIX record (Evidence › Provenance, Trust & Audit › Data limitations). */
export function ProvenanceTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <RecordTable
      caption="Provenance"
      rows={rows}
      columns={["canonical_entity_type", "source_value", "resolution_rule", "resolution_status"]}
      labels={{
        canonical_entity_type: "Record type",
        source_value: "Value in your system",
        resolution_rule: "How it was matched",
        resolution_status: "Match status",
      }}
      codes={["canonical_entity_type", "resolution_rule"]}
      empty={{
        title: "No provenance records",
        detail: "Once data is imported, each source value and the MDARIX record it was matched to appear here.",
      }}
    />
  );
}

/** Existing full-page screens carry their own page padding; this trims it inside a workspace section. */
export function Embedded({ children }: { children: ReactNode }) {
  return <div className="uw-embedded">{children}</div>;
}
