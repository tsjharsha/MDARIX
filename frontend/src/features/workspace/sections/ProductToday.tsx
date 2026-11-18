import type { RefObject } from "react";
import { ArrowLeftRight, ChevronRight } from "lucide-react";
import { listOf, useResource } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
import { greeting, inData, PERSONA_GREETING } from "../home";
import { hubTab } from "../productHub";
import { trendPath, type TrendBoard, type TrendItem } from "../signalAi";
import { VersionCompareCard, compareTab, earlierVersion } from "./VersionCompare";

/** The version rising most against what was expected (pure, for its test): the PQE's Today opens on it. */
export function risingVersion(items: readonly TrendItem[] | null | undefined): TrendItem | null {
  return (items ?? [])
    .filter((row) => (row.result === "SIGNIFICANT" || row.result === "ELEVATED") && row.product_version)
    .reduce<TrendItem | null>((best, row) => (!best || (row.ratio ?? 0) > (best.ratio ?? 0) ? row : best), null);
}

/** "003–008" from the lots' identifiers (their last part), in order. */
const lotRange = (lots: readonly string[]) => {
  const short = [...lots].map((lot) => lot.split("-").pop() ?? lot).sort();
  return short.length > 2 ? `${short[0]}–${short[short.length - 1]}` : short.join(" · ");
};

/**
 * The Product Quality Engineer's Today (UX3, Persona Blueprint wave C): the Product Lifecycle Twin on the version rising
 * most against what was expected, pre-selected. Three rows say what changed, which lots carry the rise and how many
 * complaints against how many expected, each opening its records; the one main button compares the version with the
 * one before it. Read from the trend check by version and the product's own records; MDARIX infers no cause.
 */
export function ProductToday({ heading }: { heading: RefObject<HTMLHeadingElement | null> }) {
  const { session, open, dataSource } = useWorkspace();
  const trends = useResource<TrendBoard>(trendPath("version"));
  const rows = (trends.data?.items ?? []).filter((row) => inData(row.product.identifier, dataSource));
  const top = risingVersion(rows);
  const product = top?.product.identifier ?? null;
  const version = top?.product_version?.version_identifier ?? null;
  const name = (session?.display_name ?? "").split(/\s+/)[0];
  const at = (view: string) =>
    product && open("Product 360", hubTab({ tab: "Product 360", product, version, view: view as never }));
  // The version before the rising one, for the one main button (the same read as the twin card below).
  const view = useResource<{ versions?: unknown[] }>(
    product
      ? `/api/v1/products/${encodeURIComponent(product)}/product-360?light=1${
          version ? `&version_id=${encodeURIComponent(version)}` : ""
        }`
      : null,
  );
  const earlier = earlierVersion(listOf(view.data?.versions) as Record<string, any>[], version);
  const change = top?.changes?.[0];
  const lots = top?.lots ?? [];
  return (
    <div className="uw-home uw-product-today">
      <header className="uw-home-head">
        <div>
          <h1 ref={heading} tabIndex={-1}>
            {greeting()}
            {name ? `, ${name}` : ""}
          </h1>
          <p>{PERSONA_GREETING.pqe}</p>
        </div>
      </header>
      {trends.state === "loading" ? (
        <p className="ac-muted" role="status">
          Reading which versions are rising…
        </p>
      ) : !top ? (
        <section className="uw-card uw-card-pad">
          <h2>No version is rising against what was expected</h2>
          <p className="ac-muted">
            The trend check compares each version's recent complaints with its history or the version it replaced.
          </p>
          <div className="ca-action-row">
            <button type="button" className="ac-primary" onClick={() => open("Product 360")}>
              Open your products <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
        </section>
      ) : (
        <>
          <section className="uw-card uw-card-pad" aria-labelledby="pqe-rising">
            <span className="ac-eyebrow">Rising against what was expected</span>
            <h2 id="pqe-rising">
              {top.product.name} · {version}
            </h2>
            <ul className="uw-home-list" aria-label="What the rise rests on">
              <li>
                <button type="button" className="uw-home-row" onClick={() => at("Changes")}>
                  <span className="uw-home-what">
                    <b>What changed: {change ? change.title : "no change recorded on its parts"}</b>
                    <small>
                      {change
                        ? `${change.identifier} · the newest change recorded against a part of ${version}`
                        : `Changes recorded against a part of ${version}`}
                    </small>
                  </span>
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </li>
              <li>
                <button type="button" className="uw-home-row" onClick={() => at("Lots")}>
                  <span className="uw-home-what">
                    <b>Lots with recent complaints: {lots.length ? lotRange(lots) : "none recorded"}</b>
                    <small>The lots of the complaints the trend check counted in its recent window</small>
                  </span>
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="uw-home-row"
                  onClick={() =>
                    open("Trends", `Trend check?${new URLSearchParams({ product: top.product.identifier ?? "" })}`)
                  }
                >
                  <span className="uw-home-what">
                    <b>
                      Complaints: {top.recent} against {top.expected} expected
                      {top.ratio ? ` (${top.ratio}×)` : ""}
                    </b>
                    <small>
                      Complaints on {version} in the last {top.recent_days} days, against what its history (or the
                      version it replaced) leads one to expect
                    </small>
                  </span>
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </li>
            </ul>
            {earlier && version && product && (
              <div className="ca-action-row">
                <button
                  type="button"
                  className="ac-primary"
                  onClick={() => open("Product 360", compareTab(product, version, earlier.version_identifier))}
                >
                  <ArrowLeftRight size={15} aria-hidden="true" /> Compare {earlier.version_identifier} and {version}
                </button>
              </div>
            )}
          </section>
          <VersionCompareCard product={product} productName={top.product.name} version={version} compare={false} />
        </>
      )}
    </div>
  );
}
