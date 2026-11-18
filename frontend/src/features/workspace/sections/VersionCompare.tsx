import { ArrowLeftRight, ChevronRight } from "lucide-react";
import { formatDay } from "../../../app/dates";
import { listOf, useResource } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
import { hubTab, productTab } from "../productHub";

type Row = Record<string, any>;

/** The product's page with a version beside the one before it (Product 360 › Configuration, compare). */
export const compareTab = (product: string, version: string, earlier: string) =>
  hubTab({ tab: "Product 360", product, version, view: "Configuration", compare: earlier });

/** The version before `version` in the product's release order, or null (pure, for its test). */
export function earlierVersion(versions: Row[] | null | undefined, version: string | null | undefined): Row | null {
  const list = versions ?? [];
  const index = list.findIndex((item) => item.version_identifier === version || item.id === version);
  return index > 0 ? list[index - 1] : null;
}

/**
 * A product version and what changed since the one before it (UX3): the Product Lifecycle Twin's first question, on
 * the investigation cockpit's Product reality step and on the Product Quality Engineer's Today. One click opens the two
 * versions side by side (the configuration diff, supplier and inspection rows highlighted), another the product's
 * page. MDARIX lists what was recorded; it does not infer a cause.
 */
export function VersionCompareCard({
  product,
  productName,
  version,
  primary = false,
}: {
  product: string | null;
  productName?: string | null;
  version: string | null;
  /** On Today the comparison is the screen's one main button. */
  primary?: boolean;
}) {
  const { open } = useWorkspace();
  const view = useResource<Row>(
    product
      ? `/api/v1/products/${encodeURIComponent(product)}/product-360?light=1${
          version ? `&version_id=${encodeURIComponent(version)}` : ""
        }`
      : null,
  );
  if (!product)
    return (
      <section className="uw-card uw-card-pad" aria-label="Product reality">
        <p className="ac-muted">This investigation names no product, so there is no version to compare.</p>
      </section>
    );
  const data = view.data;
  const shown = (data?.selected_version?.version_identifier as string | undefined) ?? version;
  const earlier = earlierVersion(listOf(data?.versions), shown);
  const changes = listOf(data?.changes).slice(-3).reverse();
  const name = productName ?? (data?.product?.name as string | undefined) ?? product;
  return (
    <section className="uw-card uw-card-pad uw-version-compare" aria-labelledby="version-compare-title">
      <p className="ac-eyebrow">Product Lifecycle Twin</p>
      <h3 id="version-compare-title">
        {name}
        {shown ? ` · ${shown}` : ""}
      </h3>
      {view.state === "loading" ? (
        <p className="ac-muted" role="status">
          Reading the product's versions and changes…
        </p>
      ) : (
        <>
          <dl className="uw-hl-fields">
            <div>
              <dt>Versions</dt>
              <dd>
                {listOf(data?.versions)
                  .map((item) => item.version_identifier)
                  .join(" → ") || "None recorded"}
              </dd>
            </div>
            <div>
              <dt>Lots made</dt>
              <dd>{data?.overview?.lot_count ?? "—"}</dd>
            </div>
            <div>
              <dt>Complaints on {shown ?? "this version"}</dt>
              <dd>
                {data?.overview?.complaint_count ?? "—"}
                <small> every complaint recorded on this version</small>
              </dd>
            </div>
          </dl>
          <p className="ac-eyebrow">What changed</p>
          {changes.length ? (
            <ul className="uw-version-changes">
              {changes.map((change) => (
                <li key={String(change.id ?? change.change_identifier)}>
                  <strong>{change.change_identifier ?? "Change"}</strong> {change.description ?? ""}
                  {change.effective_timestamp || change.event_timestamp ? (
                    <small className="ac-muted">
                      {" "}
                      · {formatDay(change.effective_timestamp ?? change.event_timestamp)}
                    </small>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="ac-muted">No change recorded for this product.</p>
          )}
          <div className="ca-action-row">
            {earlier && shown && (
              <button
                type="button"
                className={primary ? "ac-primary" : "ac-secondary"}
                onClick={() => open("Product 360", compareTab(product, shown, earlier.version_identifier))}
              >
                <ArrowLeftRight size={15} aria-hidden="true" /> Compare {earlier.version_identifier} and {shown}
              </button>
            )}
            <button
              type="button"
              className="ac-secondary"
              onClick={() => open("Product 360", productTab(product, shown))}
            >
              Open the product <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
        </>
      )}
    </section>
  );
}
