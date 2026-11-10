import { useState, type ReactNode, type RefObject } from "react";
import { ArrowLeftRight, Upload } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { Tabs, useResource, type Resource } from "../../customer-admin/shared";
import { DeviceIcon, MonitorBand, StatusPill, deviceKind } from "../../shared/hero/HeroVisuals";
import { formatDay } from "../../../app/dates";
import { chooseCase, useWorkspace } from "../workspaceContext";
import { countOf } from "./common";
import { ChartOrTable } from "./WowCharts";
import {
  HUB_TABS,
  PRODUCT_VIEWS,
  RECORD_KINDS,
  chosenView,
  compareConfigurations,
  correctionNote,
  hubPlace,
  hubTab,
  inDataShown,
  markersByMonth,
  monthLabel,
  productTab,
  rateText,
  supplierTab,
  type HubPlace,
  type HubTab,
  type Origin,
  type RecordKind,
} from "../productHub";
import { SuppliersTab } from "./SupplierHub";
import "../productHub.css";

// The server's rows (backend/app/product360): plain records, each with its origin.
type Row = Record<string, any>;
type Go = (tab: string, how?: "push" | "replace") => void;

/**
 * Work › Products on the new navigation (0.10.94, W1): Product 360 and Supplier 360, read-only. The tab carries the
 * product (and version) or the supplier, so every page has its own address. MDARIX lists what was recorded and why
 * each record is linked; it never infers a cause, and nothing here writes.
 */
export function ProductHubSection({ tab, heading }: { tab?: string; heading?: RefObject<HTMLHeadingElement | null> }) {
  const { shownTab, reportTab, open } = useWorkspace();
  const place = hubPlace(shownTab ?? tab);
  const go: Go = (next, how = "push") => (reportTab ? reportTab(next, how) : open("Product 360", next));
  return (
    <Tabs
      tabs={HUB_TABS}
      active={place.tab}
      onChange={(next: HubTab) => go(hubTab({ tab: next }))}
      label="Products and suppliers"
    >
      {place.tab === "Product 360" &&
        (place.product ? <ProductPage place={place} go={go} heading={heading} /> : <ProductList go={go} />)}
      {place.tab === "Supplier 360" && <SuppliersTab place={place} go={go} heading={heading} />}
    </Tabs>
  );
}

/** Where a record came from, as one chip; its detail line (system, ID, loaded on) is the chip's tooltip and is read out. */
export function OriginChip({ origin }: { origin: Origin | null | undefined }) {
  if (!origin) return null;
  return (
    <span className="uw-ph-origin" title={origin.detail}>
      {origin.label}
      <span className="sr-only"> ({origin.detail})</span>
    </span>
  );
}

/** Connect mode: a record from the customer's system is corrected there; MDARIX offers no edit here. */
export function CorrectionNote({ origin }: { origin: Origin | null | undefined }) {
  const note = correctionNote(origin);
  return note ? <p className="ac-muted uw-ph-note">{note}</p> : null;
}

/** A flat table: its caption for screen readers, its headings, its rows. */
export function FlatTable({
  caption,
  head,
  children,
}: {
  caption: string;
  head: readonly string[];
  children: ReactNode;
}) {
  return (
    <div className="uw-ph-table-wrap">
      <table className="uw-ph-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {head.map((name) => (
              <th key={name} scope="col">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/** Complaints per month of each version over twelve months, with its markers (a release, a part link, a change). */
export function MonthlyChart({ monthly, extra = [] }: { monthly: Row | null | undefined; extra?: Row[] }) {
  if (!monthly?.months?.length || !monthly.series?.length) return null;
  const months: string[] = monthly.months;
  const markers = [...(monthly.markers ?? []), ...extra];
  const marked = markersByMonth(markers);
  const max = Math.max(1, ...monthly.series.flatMap((series: Row) => series.counts as number[]));
  const name = (series: Row) => [series.product_name, series.version_identifier].filter(Boolean).join(" ");
  const markerLine = [...marked.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, labels]) => `${monthLabel(month)}: ${labels.join("; ")}`)
    .join(" · ");
  return (
    <ChartOrTable
      title="Complaints per month, by version"
      note={markerLine ? `Marked months: ${markerLine}. A marker is a recorded date, not a cause.` : undefined}
      chart={
        <div className="uw-ph-months">
          {monthly.series.map((series: Row) => (
            <div className="uw-ph-month-row" key={series.version_id}>
              <span>{name(series)}</span>
              <div className="uw-ph-month-bars" role="img" aria-label={`${name(series)}: complaints per month`}>
                {(series.counts as number[]).map((count, index) => (
                  <span
                    key={months[index]}
                    className={marked.has(months[index]) ? "is-marked" : undefined}
                    style={{ height: `${(100 * count) / max}%` }}
                    title={`${monthLabel(months[index])}: ${count}`}
                  />
                ))}
              </div>
            </div>
          ))}
          <div className="uw-ph-month-axis" aria-hidden="true">
            <span />
            {months.map((month) => (
              <span key={month}>{monthLabel(month)}</span>
            ))}
          </div>
        </div>
      }
      table={
        <FlatTable caption="Complaints per month, by version" head={["Version", ...months.map(monthLabel)]}>
          {monthly.series.map((series: Row) => (
            <tr key={series.version_id}>
              <th scope="row">{name(series)}</th>
              {(series.counts as number[]).map((count, index) => (
                <td key={months[index]}>{count}</td>
              ))}
            </tr>
          ))}
        </FlatTable>
      }
    />
  );
}

/** Opens each kind of linked record on its own page (the new navigation's newRecords addresses). */
export function useRecordOpener() {
  const { open, work, notify } = useWorkspace();
  return (kind: RecordKind, row: Row) => {
    const ref = String(row.business_id ?? row.id ?? "");
    if (kind === "complaints")
      return open("Complaint", `Summary?ref=${encodeURIComponent(row.complaint_identifier ?? ref)}`);
    if (kind === "investigations")
      return void chooseCase(work, String(row.business_id ?? row.investigation_identifier ?? row.id)).then((found) =>
        found
          ? open("Investigations", "Summary")
          : notify(`${row.investigation_identifier ?? ref} could not be opened right now.`, "critical"),
      );
    if (kind === "signals") return open("Trends", `Trends to review?${new URLSearchParams({ signal: ref })}`);
    if (kind === "capas") return open("Records", `Effectiveness checks?${new URLSearchParams({ capa: row.id })}`);
    if (kind === "risks") return open("Records", "Risk file input");
    return open("Reports", `?${new URLSearchParams({ report: row.id })}`);
  };
}

/** A linked record's one line: its reference (a link to its page) and what it is. */
export function recordLine(kind: RecordKind, row: Row): { ref: string; text: string } {
  switch (kind) {
    case "complaints":
      return {
        ref: row.complaint_identifier ?? row.business_id,
        text: [formatDay(row.event_timestamp, ""), row.problem_code, row.status].filter(Boolean).join(" · "),
      };
    case "investigations":
      return {
        ref: row.investigation_identifier ?? row.business_id,
        // PV-1 (owner, 10 Nov 2026): one spanning several versions names them all; one recording no version is listed
        // under every version as the whole product's, never given a version it does not have.
        text: [
          row.status,
          row.versions?.length
            ? row.versions.join(", ")
            : row.applies_to === "PRODUCT"
              ? "applies to the whole product"
              : row.version_identifier,
          row.investigation_question,
        ]
          .filter(Boolean)
          .join(" · "),
      };
    case "signals":
      return { ref: row.business_id ?? row.id, text: [row.title, row.status].filter(Boolean).join(" · ") };
    case "capas":
      return {
        ref: row.capa_identifier ?? row.business_id,
        text: [row.title, row.check?.label, row.basis].filter(Boolean).join(" · "),
      };
    case "risks":
      return {
        ref: row.risk_identifier ?? row.business_id,
        text: [row.description, row.applies_to === "PRODUCT" ? "whole product (no version recorded)" : null]
          .filter(Boolean)
          .join(" · "),
      };
    default:
      return {
        ref: [row.market, row.form_code].filter(Boolean).join(" ") || "Report",
        text: [row.state, row.basis, row.submitted_at ? `submitted ${formatDay(row.submitted_at)}` : null]
          .filter(Boolean)
          .join(" · "),
      };
  }
}

type ProductSummary = Row & { origin?: Origin; counts?: Row | null };

/** The products as cards (spec 3.2): the newest version's open records, each count a link to its list. */
function ProductList({ go }: { go: Go }) {
  const { dataSource, open } = useWorkspace();
  const products = useResource<ProductSummary[]>("/api/v1/products?counts=1&limit=100");
  const shown = (products.data ?? []).filter((row) => inDataShown(row.origin, dataSource));
  return (
    <Panel title={countOf(shown.length, "product")} source={products}>
      {!shown.length ? (
        <Empty
          title="No products yet"
          detail="Import your products, lots and complaints in Import your data."
          action={
            <button type="button" className="ac-secondary" onClick={() => open("Import your data")}>
              <Upload size={15} aria-hidden="true" /> Import your data
            </button>
          }
        />
      ) : (
        <ul className="uw-ph-cards">
          {shown.map((row) => (
            <ProductCard key={row.id} row={row} go={go} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function ProductCard({ row, go }: { row: ProductSummary; go: Go }) {
  const counts = row.counts;
  const ref = String(row.product_identifier ?? row.id);
  const version = counts?.version_identifier ?? null;
  const versions = [...((row.available_versions as string[]) ?? [])].reverse();
  const list = (kind: RecordKind) =>
    go(hubTab({ tab: "Product 360", product: ref, version, view: "Records", list: kind }));
  const count = (kind: RecordKind, value: number, noun: string, dot = false) => (
    <button type="button" className="ac-link" onClick={() => list(kind)}>
      <strong>{value}</strong> {noun}
      {dot && value > 0 && <i className="uw-ph-dot" aria-hidden="true" title="To review" />}
    </button>
  );
  return (
    <li className="uw-ph-card">
      <div className="uw-ph-card-top">
        <DeviceIcon kind={deviceKind(row.name)} size={40} decorative />
        <div>
          <h3>
            <button type="button" className="ac-link" onClick={() => go(productTab(ref, version))}>
              {row.name}
            </button>
          </h3>
          <span className="ac-muted">{row.product_family ?? "No family recorded"}</span>
        </div>
      </div>
      <div className="uw-ph-chips uw-ph-note">
        <OriginChip origin={row.origin} />
        {versions.length ? (
          versions.map((name) => (
            <span key={name} className="uw-ph-origin">
              {name}
            </span>
          ))
        ) : (
          <span className="ac-muted">No versions recorded</span>
        )}
      </div>
      {counts && (
        <div className="uw-ph-counts" aria-label={version ? `On ${version}` : "On the product"}>
          {count("complaints", counts.open_complaints, "open complaints")}
          {count("investigations", counts.open_investigations, "open investigations")}
          {count("signals", counts.open_signals, "trends to review", true)}
          {count("capas", counts.open_capas, "open CAPAs on the product")}
        </div>
      )}
    </li>
  );
}

/** One product's page (spec 3.3): the hero head with the version switcher, then its sections. */
function ProductPage({
  place,
  go,
  heading,
}: {
  place: HubPlace;
  go: Go;
  heading?: RefObject<HTMLHeadingElement | null>;
}) {
  const product = encodeURIComponent(place.product ?? "");
  const versionQuery = place.version ? `&version_id=${encodeURIComponent(place.version)}` : "";
  const light = useResource<Row>(`/api/v1/products/${product}/product-360?light=1${versionQuery}`);
  const view = light.data;
  const selected: Row | null = view?.selected_version ?? null;
  const versions: Row[] = view?.versions ?? [];
  const version = selected?.version_identifier ?? null;
  const links = useResource<Row>(
    view ? `/api/v1/products/${product}/links${version ? `?version=${encodeURIComponent(version)}` : ""}` : null,
  );
  const active = chosenView(PRODUCT_VIEWS, place.view);
  const at = (next: Partial<HubPlace>, how: "push" | "replace" = "push") =>
    go(hubTab({ ...place, version, ...next, tab: "Product 360" }), how);
  if (!view)
    return (
      <Panel title="The product" source={light}>
        {null}
      </Panel>
    );
  const info: Row = view.product;
  const index = versions.findIndex((item) => item.id === selected?.id);
  const earlier = index > 0 ? versions[index - 1] : null;
  return (
    <>
      <div className="uw-ph-head">
        <MonitorBand label={`${info.name} at a glance`}>
          <div className="uw-ph-headgrid">
            <DeviceIcon kind={deviceKind(info.name)} size={64} decorative />
            <div className="uw-ph-headmain">
              <p className="ac-eyebrow">
                <button type="button" className="ac-link" onClick={() => go("Product 360")}>
                  Product 360
                </button>{" "}
                · {info.product_family ?? info.product_identifier}
              </p>
              <h1 ref={heading} tabIndex={-1}>
                {info.name}
              </h1>
              <div className="uw-ph-chips">
                <OriginChip origin={info.origin} />
                {info.lifecycle_status && <StatusPill tone="none">{info.lifecycle_status}</StatusPill>}
                {earlier && (
                  <button
                    type="button"
                    className="ac-secondary"
                    onClick={() => at({ view: "Configuration", compare: earlier.version_identifier })}
                  >
                    <ArrowLeftRight size={15} aria-hidden="true" /> Compare with {earlier.version_identifier}
                  </button>
                )}
              </div>
              {versions.length ? (
                <ul className="uw-ph-versions" aria-label="Versions">
                  {[...versions].reverse().map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="uw-ph-version"
                        aria-pressed={item.id === selected?.id}
                        onClick={() => at({ version: item.version_identifier, compare: null })}
                      >
                        {item.version_identifier}
                        {item.release_timestamp && <small>{formatDay(item.release_timestamp)}</small>}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="uw-ph-note">No versions recorded</p>
              )}
              <CorrectionNote origin={info.origin} />
            </div>
          </div>
        </MonitorBand>
      </div>
      <Tabs
        tabs={PRODUCT_VIEWS}
        active={active}
        onChange={(next) => at({ view: next === "Overview" ? null : next, list: null }, "replace")}
        label={`${info.name} sections`}
      >
        {active === "Overview" && <Overview view={view} links={links} version={version} at={at} />}
        {active === "Configuration" && <Configuration view={view} place={place} go={go} />}
        {active === "Lots" && <Lots view={view} version={version} />}
        {active === "Changes" && <Changes changes={view.changes ?? []} />}
        {active === "Records" && (
          <Records
            product={product}
            version={version}
            tiles={links.data?.tiles}
            list={place.list ?? "complaints"}
            choose={(kind) => at({ view: "Records", list: kind }, "replace")}
          />
        )}
        {active === "Version story" &&
          (selected ? (
            <VersionStory productId={String(info.id)} version={selected} at={at} />
          ) : (
            <p className="ac-muted">No versions recorded, so there is no version story.</p>
          ))}
      </Tabs>
    </>
  );
}

/** The version story (spec 3.3): the same read as the classic ProductVersionStory (/versions/{id}/story), as flat
 * cards: the release, then its complaints, the investigations holding one of them and their evidence (G-2). */
export function VersionStory({
  productId,
  version,
  at,
}: {
  productId: string;
  version: Row;
  at: (next: Partial<HubPlace>, how?: "push" | "replace") => void;
}) {
  const openRecord = useRecordOpener();
  const story = useResource<Row>(
    `/api/v1/products/${encodeURIComponent(productId)}/versions/${encodeURIComponent(String(version.id))}/story`,
  );
  const data = story.data;
  const name = version.version_identifier;
  if (!data || data.status === "NOT_FOUND")
    return (
      <Panel title={`The story of ${name}`} source={story}>
        {data && <p className="ac-muted">This version is not available in your organization.</p>}
      </Panel>
    );
  const release: Row = data.version ?? {};
  const cards: Array<[string, number, Row[], (row: Row) => { ref: string; text: string }, RecordKind | null]> = [
    [
      "Complaints",
      data.counts?.complaints ?? 0,
      data.complaints ?? [],
      (row) => recordLine("complaints", row),
      "complaints",
    ],
    [
      `Investigations on ${name} or the whole product`,
      data.counts?.investigations ?? 0,
      data.investigations ?? [],
      (row) => recordLine("investigations", row),
      "investigations",
    ],
    [
      "Evidence in those investigations",
      data.counts?.evidence ?? 0,
      data.evidence ?? [],
      (row) => ({
        ref: row.evidence_identifier ?? row.business_id,
        text: [row.title, row.reliability_status].filter(Boolean).join(" · "),
      }),
      null,
    ],
  ];
  return (
    <section className="uw-ph-section" aria-label={`The story of ${name}`}>
      <p className="ac-muted">
        {[
          `${name} · ${release.lifecycle_status ?? "lifecycle not recorded"}`,
          release.release_timestamp ? `released ${formatDay(release.release_timestamp)}` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
        . MDARIX lists what was recorded; it does not infer a cause.
      </p>
      <ul className="uw-ph-tiles">
        {cards.map(([title, count, rows, line, kind]) => (
          <li key={title} className="uw-ph-tile">
            <div className="uw-ph-tile-head">
              <h3>{title}</h3>
              <span className="uw-ph-tile-count">{count}</span>
            </div>
            {rows.length ? (
              <ul>
                {rows.slice(0, 3).map((row) => {
                  const shown = line(row);
                  return (
                    <li key={shown.ref}>
                      {kind ? (
                        <button type="button" className="ac-link" onClick={() => openRecord(kind, row)}>
                          {shown.ref}
                        </button>
                      ) : (
                        <strong>{shown.ref}</strong>
                      )}
                      {shown.text && <small>{shown.text}</small>}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="ac-muted">None recorded for {name}</p>
            )}
            {kind && count > 3 && (
              <button type="button" className="ac-link" onClick={() => at({ view: "Records", list: kind })}>
                See all on Records
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Six tiles of connected records, the monthly chart and the data limitations (spec 3.3, Overview). */
function Overview({
  view,
  links,
  version,
  at,
}: {
  view: Row;
  links: Resource<Row>;
  version: string | null;
  at: (next: Partial<HubPlace>, how?: "push" | "replace") => void;
}) {
  const openRecord = useRecordOpener();
  const tiles: Row = links.data?.tiles ?? {};
  const changeMarkers = (view.changes ?? [])
    .filter((change: Row) => change.effective_timestamp ?? change.event_timestamp)
    .map((change: Row) => ({
      kind: "change",
      label: `${change.change_identifier} took effect`,
      at: change.effective_timestamp ?? change.event_timestamp,
    }));
  return (
    <>
      <Panel title={version ? `Linked to ${version}` : "Linked to the product"} source={links}>
        <ul className="uw-ph-tiles">
          {RECORD_KINDS.map(([kind, title]) => {
            const tile: Row = tiles[kind] ?? { count: 0, items: [] };
            return (
              <li key={kind} className="uw-ph-tile">
                <div className="uw-ph-tile-head">
                  <h3>{title}</h3>
                  <span className="uw-ph-tile-count">{tile.count}</span>
                </div>
                {tile.items.length ? (
                  <ul>
                    {tile.items.map((row: Row) => {
                      const line = recordLine(kind, row);
                      return (
                        <li key={row.id}>
                          <button type="button" className="ac-link" onClick={() => openRecord(kind, row)}>
                            {line.ref}
                          </button>
                          {line.text && <small>{line.text}</small>}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="ac-muted">
                    {kind === "complaints"
                      ? "No complaints recorded for this version"
                      : kind === "risks"
                        ? "No risks recorded in MDARIX for this product"
                        : `No ${title.toLowerCase()} recorded`}
                  </p>
                )}
                {tile.count > tile.items.length && (
                  <button type="button" className="ac-link" onClick={() => at({ view: "Records", list: kind })}>
                    See all {tile.count}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </Panel>
      <div className="uw-ph-section">
        <MonthlyChart monthly={links.data?.monthly} extra={changeMarkers} />
      </div>
      {!!view.limitations?.length && (
        <section className="uw-ph-section" aria-label="Data limitations">
          <h3>Data limitations</h3>
          <ul>
            {view.limitations.map((item: Row) => (
              <li key={item.code}>{item.description}</li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** The version's parts and their suppliers; with `compare`, the earlier version beside it (spec 3.3). */
function Configuration({ view, place, go }: { view: Row; place: HubPlace; go: Go }) {
  const product = encodeURIComponent(place.product ?? "");
  const earlier = useResource<Row>(
    place.compare
      ? `/api/v1/products/${product}/product-360?light=1&version_id=${encodeURIComponent(place.compare)}`
      : null,
  );
  const version = view.selected_version?.version_identifier;
  const config = view.configuration ?? { components: [], suppliers: [] };
  const supplierLink = (row: Row) => (
    <button
      key={`${row.id}-${row.component_identifier}`}
      type="button"
      className="ac-link"
      onClick={() => go(supplierTab(String(row.supplier_identifier ?? row.business_id ?? row.id)))}
    >
      {row.name}
    </button>
  );
  if (!version) return <p className="ac-muted">No versions recorded: a configuration belongs to a version.</p>;
  if (place.compare) {
    if (!earlier.data)
      return (
        <Panel title={`Compare with ${place.compare}`} source={earlier}>
          {null}
        </Panel>
      );
    const rows = compareConfigurations(
      earlier.data.configuration,
      config,
      view.changes ?? [],
      String(view.selected_version?.id ?? ""),
    );
    return (
      <section className="uw-ph-section" aria-label={`${place.compare} beside ${version}`}>
        <div className="ca-action-row">
          <button type="button" className="ac-link" onClick={() => go(hubTab({ ...place, compare: null }), "replace")}>
            Show {version} only
          </button>
        </div>
        <FlatTable caption={`${place.compare} beside ${version}`} head={["Part", place.compare, version, ""]}>
          {rows.map((row) => (
            <tr key={row.key} className={row.state === "same" ? undefined : "is-changed"}>
              <th scope="row">
                {row.name}
                <small>{row.key}</small>
              </th>
              <td>{row.before.length ? row.before.map(supplierLink) : <span className="ac-muted">Not in it</span>}</td>
              <td>{row.after.length ? row.after.map(supplierLink) : <span className="ac-muted">Not in it</span>}</td>
              <td>
                <span className="uw-ph-state">
                  {{ same: "Same", added: "Added", removed: "Removed", changed: "Different supplier" }[row.state]}
                </span>
                {row.changes.map((change) => (
                  <small key={change.change_identifier ?? ""}>
                    {change.change_identifier}
                    {change.description ? `: ${change.description}` : ""}, effective{" "}
                    {formatDay(change.effective_timestamp ?? change.event_timestamp)}
                  </small>
                ))}
              </td>
            </tr>
          ))}
        </FlatTable>
      </section>
    );
  }
  if (!config.components.length) return <p className="ac-muted">No parts are recorded for {version}.</p>;
  return (
    <FlatTable caption={`The parts of ${version}`} head={["Part", "Revision", "Supplier", "Supplied since", ""]}>
      {config.components.map((part: Row) => {
        const suppliers = config.suppliers.filter((row: Row) => row.component_id === part.id);
        return (
          <tr key={part.id}>
            <th scope="row">
              {part.name}
              <small>{part.component_identifier}</small>
            </th>
            <td>{part.revision ?? "—"}</td>
            <td>
              {suppliers.length ? suppliers.map(supplierLink) : <span className="ac-muted">None recorded</span>}
              {suppliers.length > 1 && <small>{suppliers.length} recorded suppliers</small>}
            </td>
            <td>{suppliers.map((row: Row) => formatDay(row.supplied_from)).join(", ") || "—"}</td>
            <td>
              <OriginChip origin={part.origin} />
            </td>
          </tr>
        );
      })}
    </FlatTable>
  );
}

/** The version's lots, complaints first, with the rate only where the units released are known (spec 3.3). */
function Lots({ view, version }: { view: Row; version: string | null }) {
  if (!version) return <p className="ac-muted">No versions recorded: lots belong to a version.</p>;
  const lots: Row[] = [...(view.manufacturing?.lots ?? [])].sort(
    (a, b) => (b.complaints ?? 0) - (a.complaints ?? 0) || String(a.lot_identifier).localeCompare(b.lot_identifier),
  );
  if (!lots.length) return <p className="ac-muted">No lots recorded for {version}.</p>;
  return (
    <FlatTable
      caption={`The lots of ${version}`}
      head={["Lot", "Made on", "Site", "Units released", "Complaints", "Per 1,000", "Genealogy", "Distribution"]}
    >
      {lots.map((lot) => (
        <tr key={lot.id}>
          <th scope="row">
            {lot.lot_identifier}
            <OriginChip origin={lot.origin} />
          </th>
          <td>{formatDay(lot.manufactured_timestamp)}</td>
          <td>{lot.site_name ?? "—"}</td>
          <td>{lot.quantity ?? "Not known"}</td>
          <td>{lot.complaints ?? 0}</td>
          <td>{rateText(lot.per_1000, lot.quantity != null)}</td>
          <td>{lot.genealogy?.length ? lot.genealogy.join("; ") : "Not imported"}</td>
          <td>{lot.distribution_imported ? "Imported" : "Not imported"}</td>
        </tr>
      ))}
    </FlatTable>
  );
}

/** The product's own changes, with the complaints before and after each took effect (spec 3.3, IV-14). */
export function Changes({ changes }: { changes: Row[] }) {
  return (
    <section className="uw-ph-section" aria-label="Changes">
      <p className="ac-muted">MDARIX lists what was recorded; it does not infer a cause.</p>
      {!changes.length ? (
        <p className="ac-muted">No change is recorded as affecting these parts.</p>
      ) : (
        <FlatTable
          caption="Recorded changes"
          head={["Change", "Effective", "Affects", "Complaints on affected versions"]}
        >
          {changes.map((change) => (
            <tr key={change.id}>
              <th scope="row">
                {change.change_identifier}
                <small>{[change.change_type, change.description].filter(Boolean).join(" · ")}</small>
                <OriginChip origin={change.origin} />
              </th>
              <td>{formatDay(change.effective_timestamp ?? change.event_timestamp)}</td>
              <td>
                {change.affects_product
                  ? "The whole product"
                  : (change.affects_names ?? change.affects ?? []).join(", ")}
              </td>
              <td>
                Before it took effect {change.complaints_before ?? 0} · after {change.complaints_after ?? 0}
              </td>
            </tr>
          ))}
        </FlatTable>
      )}
    </section>
  );
}

const PAGE = 20;

/** The full lists, 20 at a time (spec 3.3, Records); each row opens its record. */
function Records({
  product,
  version,
  tiles,
  list,
  choose,
}: {
  product: string;
  version: string | null;
  tiles: Row | undefined;
  list: RecordKind;
  choose: (kind: RecordKind) => void;
}) {
  const [offset, setOffset] = useState(0);
  const openRecord = useRecordOpener();
  const query = new URLSearchParams({ kind: list, offset: String(offset), limit: String(PAGE) });
  if (version) query.set("version", version);
  const rows = useResource<Row[]>(`/api/v1/products/${product}/links?${query}`);
  const total = tiles?.[list]?.count ?? null;
  const title = RECORD_KINDS.find(([kind]) => kind === list)?.[1] ?? list;
  return (
    <>
      <div className="uw-ph-kinds" role="group" aria-label="Lists">
        {RECORD_KINDS.map(([kind, name]) => (
          <button
            key={kind}
            type="button"
            className="uw-ph-version"
            aria-pressed={kind === list}
            onClick={() => {
              setOffset(0);
              choose(kind);
            }}
          >
            {name}
            {tiles?.[kind] && <small>{tiles[kind].count}</small>}
          </button>
        ))}
      </div>
      <Panel title={total === null ? title : `${title} · ${total}`} source={rows}>
        {!rows.data?.length ? (
          <p className="ac-muted">None recorded{version ? ` for ${version}` : ""}.</p>
        ) : (
          <FlatTable caption={title} head={["Record", "Details", "Origin"]}>
            {rows.data.map((row) => {
              const line = recordLine(list, row);
              return (
                <tr key={row.id}>
                  <th scope="row">
                    <button type="button" className="ac-link" onClick={() => openRecord(list, row)}>
                      {line.ref}
                    </button>
                  </th>
                  <td>{line.text || "—"}</td>
                  <td>
                    <OriginChip origin={row.origin} />
                  </td>
                </tr>
              );
            })}
          </FlatTable>
        )}
        {total !== null && total > PAGE && (
          <div className="uw-ph-pager">
            <button
              type="button"
              className="ac-secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}
            >
              Previous
            </button>
            <span>
              {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
            </span>
            <button
              type="button"
              className="ac-secondary"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              Next
            </button>
          </div>
        )}
      </Panel>
    </>
  );
}
