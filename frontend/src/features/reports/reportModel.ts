import { titleCase } from "../admin/console/dashboardModel";
import { isUuid } from "../../app/displayId";

/** One entry of GET /api/v1/reports/catalog. */
export type CatalogReport = { code: string; label: string; formats: string[] };

/** The formats a report or case record can be downloaded in (JSON is shown on screen). */
export type FileFormat = "CSV" | "PDF";
export type RecordFormat = "pdf" | "csv" | "json";

export const reportPath = (code: string, format: "JSON" | FileFormat) =>
  `/api/v1/stage3/reports/${encodeURIComponent(code)}?output_format=${format}`;

export const recordPath = (investigationId: string, format: RecordFormat) =>
  `/api/v1/stage3/investigations/${encodeURIComponent(investigationId)}/record?format=${format}`;

/** The name a downloaded file gets when the server does not name it. */
export const reportFallbackName = (code: string, format: FileFormat) =>
  `mdarix-${code.toLowerCase().replace(/_/g, "-")}.${format.toLowerCase()}`;

export type PreviewSection =
  | {
      key: string;
      label: string;
      kind: "table";
      columns: string[];
      rows: Array<Record<string, unknown>>;
      total: number;
    }
  | { key: string; label: string; kind: "facts"; facts: Array<[string, string]> }
  | { key: string; label: string; kind: "value"; value: string }
  | { key: string; label: string; kind: "empty" };

const isScalar = (value: unknown) => value === null || ["string", "number", "boolean"].includes(typeof value);

/** A cell or fact as text: scalars as they are, lists by their length, objects as "n fields". Never "[object Object]". */
export function cellText(value: unknown): string {
  if (value === null || value === undefined || value === "" || isUuid(value)) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (isScalar(value)) return String(value);
  if (Array.isArray(value))
    return value.every(isScalar) ? value.map((item) => cellText(item)).join(", ") : `${value.length} items`;
  return `${Object.keys(value as object).length} fields`;
}

/**
 * The report's content (its ``context``) as sections a screen can show without knowing each report's layout: a list
 * of records becomes a table of its first rows (scalar columns only, at most six, the MDARIX ID first and never a
 * column of UUIDs), a mapping becomes label/value facts, anything else one value. The full content is in the CSV and
 * PDF downloads.
 */
export function previewSections(context: unknown, maxRows = 10, maxColumns = 6): PreviewSection[] {
  if (!context || typeof context !== "object" || Array.isArray(context)) return [];
  return Object.entries(context as Record<string, unknown>)
    .filter(([key]) => key !== "data_cut_off")
    .map(([key, value]): PreviewSection => {
      const label = titleCase(key);
      if (Array.isArray(value)) {
        if (!value.length) return { key, label, kind: "empty" };
        if (value.every((item) => item && typeof item === "object" && !Array.isArray(item))) {
          const rows = (value as Array<Record<string, unknown>>).slice(0, maxRows);
          // Technical keys (UUIDs) are left out; people read the business_id instead.
          const technical = new Set(
            rows.flatMap((row) =>
              Object.entries(row)
                .filter(([, cell]) => isUuid(cell))
                .map(([column]) => column),
            ),
          );
          const columns: string[] = rows.some((row) => row.business_id) ? ["business_id"] : [];
          for (const row of rows)
            for (const [column, cell] of Object.entries(row))
              if (isScalar(cell) && !technical.has(column) && !columns.includes(column) && columns.length < maxColumns)
                columns.push(column);
          return { key, label, kind: "table", columns, rows, total: value.length };
        }
        return { key, label, kind: "value", value: cellText(value) };
      }
      if (value && typeof value === "object")
        return {
          key,
          label,
          kind: "facts",
          facts: Object.entries(value as Record<string, unknown>).map(([name, item]) => [
            titleCase(name),
            cellText(item),
          ]),
        };
      return { key, label, kind: "value", value: cellText(value) };
    });
}
