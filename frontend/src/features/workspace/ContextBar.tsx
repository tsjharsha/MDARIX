import { useWorkspace } from "./workspaceContext";
import type { TemporalMode } from "../../app/types";
import { displayId } from "../../app/displayId";

const MODES: Array<{ value: TemporalMode; label: string; hint: string }> = [
  { value: "current", label: "Current", hint: "Latest recorded state" },
  { value: "event", label: "As it happened", hint: "State at the event date" },
  { value: "known", label: "As known then", hint: "Only what was known on the date" },
];

/** One compact row that sets the product, version, case and point in time for every section below it. */
export function ContextBar() {
  const { work } = useWorkspace();
  const product = work.products.find((item) => item.id === work.productId);
  if (work.state === "error" && !work.products.length)
    return (
      <p className="ca-inline-error" role="alert">
        Product data is unavailable: {work.error}
      </p>
    );
  if (!work.products.length)
    return work.state === "loading" ? (
      <p className="ac-muted" role="status">
        Loading your products…
      </p>
    ) : null;
  return (
    <section className="uw-context" aria-label="Working context">
      <label>
        Product
        <select value={work.productId} onChange={(event) => work.setProductId(event.target.value)}>
          {work.products.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Version
        <select value={work.version} onChange={(event) => work.setVersion(event.target.value)}>
          {(product?.available_versions ?? []).map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
      <label>
        Investigation
        <select
          value={work.investigationId}
          onChange={(event) => work.setInvestigationId(event.target.value)}
          disabled={!work.investigations.length}
        >
          {!work.investigations.length && <option value="">No investigations</option>}
          {work.investigations.map((item) => (
            <option key={String(item.id)} value={String(item.id ?? "")}>
              {displayId(item, "investigation_identifier", "Investigation")} · {item.status ?? "unknown"}
            </option>
          ))}
        </select>
      </label>
      <label>
        As of
        <input
          type="date"
          value={work.asOf}
          onChange={(event) => event.target.value && work.setAsOf(event.target.value)}
        />
      </label>
      <div className="uw-modes" role="radiogroup" aria-label="Time view">
        {MODES.map((mode) => (
          <button
            type="button"
            role="radio"
            key={mode.value}
            aria-checked={work.mode === mode.value}
            title={mode.hint}
            className={work.mode === mode.value ? "selected" : ""}
            onClick={() => work.setMode(mode.value)}
          >
            {mode.label}
          </button>
        ))}
      </div>
    </section>
  );
}
