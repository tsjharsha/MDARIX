import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import type { Tone } from "../../admin/console/dashboardModel";
import { useWorkspace } from "../workspaceContext";
import { formatCount } from "./common";

/** The pieces the review boards share (Complaints, Records): the summary banner, filters and paging. */

export function ProductFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { work } = useWorkspace();
  return (
    <select aria-label="Product" value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">All products</option>
      {work.products.map((item) => (
        <option key={item.id} value={item.id}>
          {item.name}
        </option>
      ))}
    </select>
  );
}

export function Pager({ page, pages, onPage }: { page: number; pages: number; onPage: (page: number) => void }) {
  if (pages <= 1) return null;
  return (
    <div className="ca-action-row">
      <button type="button" className="ac-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span className="ac-muted">
        Page {page} of {pages}
      </span>
      <button type="button" className="ac-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </button>
    </div>
  );
}

export function Hero({
  tone,
  icon,
  eyebrow,
  title,
  detail,
  children,
}: {
  tone: Tone;
  icon: ReactNode;
  eyebrow: string;
  title: string;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <section className={`ac-hero uw-cr-hero tone-${tone}`} aria-live="polite">
      <div className="ac-hero-status">
        <span className="ac-hero-icon" aria-hidden="true">
          {icon}
        </span>
        <div>
          <p className="ac-eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p>{detail}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

/** One-of-many filter chips with their counts (a radio group). */
export function ChipFilter<T extends string>({
  label,
  options,
  value,
  counts,
  onChange,
}: {
  label: string;
  options: ReadonlyArray<{ value: T; label: string }>;
  value: T;
  counts?: Partial<Record<T, number | undefined>>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="ca-chips" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          role="radio"
          key={option.value}
          aria-checked={value === option.value}
          className={value === option.value ? "selected" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {typeof counts?.[option.value] === "number" && (
            <span className="ac-tab-count">{formatCount(counts[option.value] as number)}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function InlineError({ text }: { text: string }) {
  if (!text) return null;
  return (
    <p className="ca-inline-error" role="alert">
      <AlertTriangle size={15} aria-hidden="true" /> {text}
    </p>
  );
}
