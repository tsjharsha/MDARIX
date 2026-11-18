import { useState } from "react";
import { AlertTriangle, ArrowRight, Boxes, Download, Factory, PackageCheck, PlugZap, Truck } from "lucide-react";
import { Panel, StatTile } from "../../admin/console/charts";
import { errorText, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { formatDay } from "../../../app/dates";
import { chooseCase, useCan, useWorkspace } from "../workspaceContext";
import { documentLink } from "../documents";
import type { HubPlace } from "../productHub";
import {
  NOT_IMPORTED,
  PREVIEW_BANNER,
  SIMULATED_LABEL,
  SOURCES_PATH,
  chainNodes,
  impactPath,
  previewParam,
  runSteps,
  scopeGroups,
  scopeOf,
  scopePath,
  shippedText,
  traceText,
  twinPath,
  twinSummary,
  type ChainNode,
} from "../productTwin";
import type { ImpactList } from "../lotImpact";
import { InlineError } from "./boardParts";
import { countOf } from "./common";
import { ImportRunReport, RecordOrigin, type ImportRun } from "./ImportReports";
import { LotImpactCharts } from "./LotImpact";
import { FlatTable } from "./ProductHub";
import { REGISTER_LINK, registerTab } from "./SampleRegister";

// The server's rows (backend/app/product360/twin.py): plain records.
type Row = Record<string, any>;
type At = (next: Partial<HubPlace>, how?: "push" | "replace") => void;

/** A record's basis: why it is listed (every row of the impact and the scope says it). */
const Basis = ({ text }: { text?: string | null }) => (text ? <small className="uw-tw-basis">{text}</small> : null);

// ------------------------------------------------------------------------------------------- the connected view (U1)

/**
 * Connected (W5, U1): the version's records as one chain, each node a link to its own screen with where its records
 * came from, then the component lots its lots were built with. One main button: trace the component lot most lots with
 * complaints share. It only opens the field-action scope.
 */
export function ConnectedView({ product, version, at }: { product: string; version: string | null; at: At }) {
  const { open } = useWorkspace();
  const twin = useResource<Row>(twinPath(product, version));
  const data = twin.data;
  if (!data)
    return (
      <Panel title="Everything connected" source={twin}>
        {null}
      </Panel>
    );
  const trace: Row | null = data.trace;
  const go = (node: ChainNode) =>
    node.target === "risk-file"
      ? open("Records", "Risk file input")
      : node.target === "suppliers"
        ? at({ view: "Configuration" })
        : at({ change: null, preview: null, scope: null, list: null, ...node.target });
  return (
    <section className="uw-ph-section uw-tw" aria-label="Everything connected">
      <div className="uw-tw-lead">
        <div>
          <h2>{version ? `Everything connected to ${version}` : "Everything connected to the product"}</h2>
          <p className="ac-muted">
            MDARIX lists what was recorded and why each record is linked; it infers no cause and decides nothing.
          </p>
        </div>
        {trace && (
          <button type="button" className="ac-primary" onClick={() => at({ view: "Lots", scope: trace.scope })}>
            {traceText(trace)} <ArrowRight size={15} aria-hidden="true" />
          </button>
        )}
      </div>
      {data.sources?.simulated && <SimulatedBanner />}
      <TwinSummaryStrip data={data} at={at} />
      <h3>The connected records</h3>
      <ol className="uw-tw-chain" aria-label="The connected records, in order">
        {chainNodes(data).map((node) => (
          <li key={node.key}>
            <button type="button" className="uw-tw-node" onClick={() => go(node)}>
              <span className="uw-tw-node-label">{node.label}</span>
              <strong>{node.value}</strong>
              {node.caption && <small>{node.caption}</small>}
            </button>
          </li>
        ))}
      </ol>
      {!version ? (
        <p className="ac-muted">{data.limits?.[0]}</p>
      ) : (
        <details className="uw-more uw-tw-genealogy">
          <summary>Lot genealogy: the component lots in {version}'s lots</summary>
          {data.component_lots?.length ? (
            <FlatTable
              caption={`Component lots in ${version}'s lots`}
              head={["Component lot", "Lots built with it", "Lots with complaints", "Complaints", ""]}
            >
              {data.component_lots.map((row: Row) => (
                <tr key={row.scope} className={row.scope === trace?.scope ? "is-changed" : undefined}>
                  <th scope="row">
                    {row.lot}
                    <small>{row.component_name}</small>
                  </th>
                  <td>
                    {row.lots.length}
                    <small>{row.lots.join(", ")}</small>
                  </td>
                  <td>{row.lots_with_complaints}</td>
                  <td>{row.complaints}</td>
                  <td>
                    <button type="button" className="ac-link" onClick={() => at({ view: "Lots", scope: row.scope })}>
                      Field-action scope
                    </button>
                  </td>
                </tr>
              ))}
            </FlatTable>
          ) : (
            <p className="ac-muted">No lot genealogy is imported for {version}'s lots.</p>
          )}
        </details>
      )}
      <ul className="uw-tw-limits">
        {(data.limits ?? []).map((line: string) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}

/**
 * W1e: the twin at a glance for a quality lead, at the top of the connected view: what changed → which versions →
 * which lots → complaints → the investigations and CAPAs that need attention, each with a link to its record. Counts
 * and names from the connected view's own read; the genealogy, sources and change impact stay below.
 */
export function TwinSummaryStrip({ data, at }: { data: Row; at: At }) {
  const { open, work, notify } = useWorkspace();
  const summary = twinSummary(data);
  const { change, lots, complaints, investigations, capas } = summary;
  const openCase = (row: Row) =>
    void chooseCase(work, String(row.business_id ?? row.investigation_identifier)).then((found) =>
      found
        ? open("Investigations", "Summary")
        : notify(`${row.investigation_identifier ?? "The investigation"} could not be opened right now.`, "critical"),
    );
  const openCapa = (row: Row) => open("Records", `Effectiveness checks?${new URLSearchParams({ capa: row.id })}`);
  const link = (label: string, onClick: () => void) => (
    <button type="button" className="ac-link uw-tw-glance-link" onClick={onClick}>
      {label} <ArrowRight size={13} aria-hidden="true" />
    </button>
  );
  const attention = investigations.length + capas.length;
  return (
    <section className="uw-tw-glance" aria-labelledby="uw-tw-glance-title">
      <div className="uw-tw-glance-head">
        <h3 id="uw-tw-glance-title">At a glance</h3>
        {link(REGISTER_LINK, () => open("Getting started", registerTab("change")))}
      </div>
      <ol className="uw-tw-glance-steps">
        <li>
          <span className="uw-tw-glance-label">What changed</span>
          <strong>{change ? change.change_identifier : "No change recorded"}</strong>
          <small>
            {change
              ? [change.change_type, formatDay(change.effective_timestamp ?? change.event_timestamp, "")]
                  .filter(Boolean)
                  .join(" · ") + (summary.changes > 1 ? ` · ${countOf(summary.changes, "change")} in all` : "")
              : "On this product's parts"}
          </small>
          {change &&
            link("See its impact", () => at({ view: "Changes", change: change.id, preview: null, scope: null }))}
        </li>
        <li>
          <span className="uw-tw-glance-label">Product versions</span>
          <strong>{summary.versions.length ? summary.versions.join(", ") : "None named"}</strong>
          <small>{change ? `Recorded in ${change.change_identifier}` : "No change to trace"}</small>
          {link("Compare the versions", () => at({ view: "Version story", change: null, scope: null }))}
        </li>
        <li className={lots.withComplaints.length ? "is-flag" : undefined}>
          <span className="uw-tw-glance-label">Lots</span>
          <strong>
            {lots.total ? `${lots.withComplaints.length} of ${countOf(lots.total, "lot")} with complaints` : "No lots"}
          </strong>
          <small>
            {lots.withComplaints.join(", ") || (data.version ? "None with complaints" : "Choose a version")}
          </small>
          {lots.total > 0 &&
            link(data.trace ? `Trace ${data.trace.lot}` : "Open the lots", () =>
              at(data.trace ? { view: "Lots", scope: data.trace.scope } : { view: "Lots" }),
            )}
        </li>
        <li className={complaints.open ? "is-flag" : undefined}>
          <span className="uw-tw-glance-label">Complaints</span>
          <strong>
            {complaints.open} open of {complaints.total}
          </strong>
          <small>{data.version ? `On ${data.version.version_identifier}` : "On the product"}</small>
          {link("Open the complaints", () => at({ view: "Records", list: "complaints" }))}
        </li>
        <li className={attention ? "is-flag" : undefined}>
          <span className="uw-tw-glance-label">Needs attention</span>
          <strong>
            {attention
              ? [
                  investigations.length && countOf(investigations.length, "open investigation"),
                  capas.length && countOf(capas.length, "CAPA"),
                ]
                  .filter(Boolean)
                  .join(" · ")
              : "Nothing open"}
          </strong>
          {capas[0]?.check?.label && (
            <small>
              {capas[0].capa_identifier}: {capas[0].check.label}
            </small>
          )}
          {investigations.slice(0, 2).map((row) => (
            <span key={row.id}>
              {link(`Open ${row.investigation_identifier ?? row.business_id}`, () => openCase(row))}
            </span>
          ))}
          {capas.slice(0, 2).map((row) => (
            <span key={row.id}>{link(`Open ${row.capa_identifier ?? row.business_id}`, () => openCapa(row))}</span>
          ))}
        </li>
      </ol>
    </section>
  );
}

function SimulatedBanner() {
  return (
    <p className="uw-tw-banner" role="note">
      <PlugZap size={15} aria-hidden="true" /> {SIMULATED_LABEL}: the sample's PLM, ERP and eQMS records are recorded
      exports, read through the same checks as your own imports.
    </p>
  );
}

// ------------------------------------------------------------------------------------------------ change impact (U2)

/** The preview picker: a component of this version (and, optionally, one of its suppliers). Nothing is saved. */
export function PreviewPicker({ configuration, at }: { configuration: Row; at: At }) {
  const parts: Row[] = configuration?.components ?? [];
  const [component, setComponent] = useState("");
  const [supplier, setSupplier] = useState("");
  const suppliers: Row[] = (configuration?.suppliers ?? []).filter((row: Row) => row.component_id === component);
  return (
    <form
      className="uw-tw-picker"
      aria-label="Preview a change"
      onSubmit={(event) => {
        event.preventDefault();
        if (component) at({ change: null, scope: null, preview: previewParam(component, supplier || null) });
      }}
    >
      <label>
        Component
        <select value={component} onChange={(event) => (setComponent(event.target.value), setSupplier(""))}>
          <option value="">Choose a component</option>
          {parts.map((part) => (
            <option key={part.id} value={part.id}>
              {part.name} ({part.component_identifier})
            </option>
          ))}
        </select>
      </label>
      <label>
        Supplier (optional)
        <select value={supplier} disabled={!suppliers.length} onChange={(event) => setSupplier(event.target.value)}>
          <option value="">Any supplier</option>
          {suppliers.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="ac-secondary" disabled={!component}>
        Preview the impact
      </button>
    </form>
  );
}

const Section = ({ title, empty, children }: { title: string; empty: boolean; children: React.ReactNode }) => (
  <section className="uw-tw-part" aria-label={title}>
    <h3>{title}</h3>
    {empty ? <p className="ac-muted">None recorded.</p> : children}
  </section>
);

/**
 * "If <change> holds: what to re-check" (W5, U2): versions, lots (complaints first), markets, open complaints, before
 * and after, investigations, risk rows and CAPAs with their check state, each with why it is listed. A preview (no
 * change record) says so and saves nothing. One main button: open the risk file.
 */
export function ChangeImpactPanel({ product, place, at }: { product: string; place: HubPlace; at: At }) {
  const { open } = useWorkspace();
  const impact = useResource<Row>(impactPath(product, place));
  const data = impact.data;
  if (!data)
    return (
      <Panel title="What to re-check" source={impact}>
        {null}
      </Panel>
    );
  const name = data.change
    ? data.change.change_identifier
    : [data.previewed?.component?.name, data.previewed?.supplier?.name].filter(Boolean).join(" from ") || "this change";
  const lots: Row[] = data.lots ?? [];
  const markets: Row = data.markets ?? {};
  const scope: Row | null = data.scope;
  return (
    <section className="uw-ph-section uw-tw" aria-label={`If ${name} holds: what to re-check`}>
      {data.preview && (
        <p className="uw-tw-banner is-preview" role="note">
          {PREVIEW_BANNER}
        </p>
      )}
      <div className="uw-tw-lead">
        <div>
          <h2>{data.preview ? `If ${name} changed` : `If ${name} holds`}: what to re-check</h2>
          <p className="ac-muted">
            {data.change?.description ?? "Listed from the bill of materials: every version that uses it."} MDARIX lists;
            you decide what to re-check.
          </p>
        </div>
        <button type="button" className="ac-primary" onClick={() => open("Records", "Risk file input")}>
          Open the risk file <ArrowRight size={15} aria-hidden="true" />
        </button>
      </div>
      <div className="ca-action-row">
        {scope && (
          <button
            type="button"
            className="ac-link"
            onClick={() => at({ view: "Lots", scope: scope.scope, change: null, preview: null })}
          >
            Field-action scope from {scope.lot}
          </button>
        )}
        {data.change && (
          <button
            type="button"
            className="ac-link"
            onClick={() => open("Records", documentLink("CHANGE_IMPACT", data.change.id))}
          >
            The change impact document
          </button>
        )}
        <button type="button" className="ac-link" onClick={() => at({ change: null, preview: null }, "replace")}>
          Back to the changes
        </button>
      </div>
      <Section title="Versions" empty={!data.versions?.length}>
        <ul className="uw-tw-rows">
          {(data.versions ?? []).map((row: Row) => (
            <li key={row.id}>
              <strong>{row.version_identifier}</strong>
              <Basis text={row.basis} />
            </li>
          ))}
        </ul>
      </Section>
      <Section title={`Lots · ${countOf(lots.length, "lot")}, complaints first`} empty={!lots.length}>
        <FlatTable caption="Lots to re-check" head={["Lot", "Complaints", "Open", "Units released", "Shipped", "Why"]}>
          {lots.map((lot) => (
            <tr key={lot.id} className={lot.complaints ? "is-changed" : undefined}>
              <th scope="row">{lot.lot_identifier}</th>
              <td>{lot.complaints}</td>
              <td>{lot.open_complaints}</td>
              <td>{lot.quantity ?? "Not known"}</td>
              <td>{shippedText(lot)}</td>
              <td>
                <Basis text={lot.basis} />
              </td>
            </tr>
          ))}
        </FlatTable>
      </Section>
      <Section title="Markets" empty={!markets.by_country?.length && !markets.not_imported}>
        <p>
          {(markets.by_country ?? [])
            .map((row: Row) => `${row.country} ${row.units.toLocaleString("en-US")}`)
            .join(" · ") || "No shipments imported"}
          {markets.not_imported ? ` · ${countOf(markets.not_imported, "lot")}: ${NOT_IMPORTED.toLowerCase()}` : ""}
        </p>
        <Basis text="Units shipped by country, from the imported distribution of these lots" />
      </Section>
      <Section title={`Open complaints · ${data.open_complaints?.count ?? 0}`} empty={!data.open_complaints?.count}>
        <ul className="uw-tw-rows">
          {(data.open_complaints?.items ?? []).slice(0, 8).map((row: Row) => (
            <li key={row.id}>
              <button
                type="button"
                className="ac-link"
                onClick={() => open("Complaint", `Summary?ref=${encodeURIComponent(row.complaint_identifier)}`)}
              >
                {row.complaint_identifier}
              </button>
              <small>{[row.lot_identifier, formatDay(row.event_timestamp)].filter(Boolean).join(" · ")}</small>
              <Basis text={row.basis} />
            </li>
          ))}
        </ul>
      </Section>
      {data.before_after && (
        <Section title="Before and after" empty={false}>
          <p>
            Before it took effect <strong>{data.before_after.before}</strong> · after{" "}
            <strong>{data.before_after.after}</strong>
            {data.before_after.since ? ` (from ${formatDay(data.before_after.since)})` : ""}
          </p>
          <Basis text={data.before_after.basis} />
        </Section>
      )}
      <Section title="Investigations" empty={!data.investigations?.length}>
        <ul className="uw-tw-rows">
          {(data.investigations ?? []).map((row: Row) => (
            <li key={row.id}>
              <strong>{row.investigation_identifier ?? row.business_id}</strong>
              <small>{row.investigation_question}</small>
              <Basis text={row.basis} />
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Risk rows to re-check" empty={!data.risks?.length}>
        <ul className="uw-tw-rows">
          {(data.risks ?? []).map((row: Row) => (
            <li key={row.id}>
              <strong>{row.risk_identifier}</strong>
              <small>{row.description}</small>
              <Basis text={row.basis} />
            </li>
          ))}
        </ul>
      </Section>
      <Section title="CAPAs to re-check" empty={!data.capas?.length}>
        <ul className="uw-tw-rows">
          {(data.capas ?? []).map((row: Row) => (
            <li key={row.id}>
              <strong>{row.capa_identifier}</strong>
              <small>{row.title}</small>
              <small>{row.check?.label}</small>
              <Basis text={row.basis} />
            </li>
          ))}
        </ul>
      </Section>
    </section>
  );
}

// -------------------------------------------------------------------------------------------- field-action scope (U3)

/**
 * The field-action scope (W5, U3): every lot of the organization built with the component lot, its totals, the lot
 * impact charts, units by market and by site, the lots in three groups, and what the list cannot tell. One main button:
 * the CSV. It is signed on an investigation's Lot impact, never here (D5). MDARIX recommends no recall.
 */
export function FieldScopePanel({ scope, at }: { scope: string; at: At }) {
  const { open, work, notify } = useWorkspace();
  const canExport = useCan("data.export");
  const [error, setError] = useState("");
  const parsed = scopeOf(scope);
  const read = useResource<Row>(parsed ? scopePath(parsed) : null);
  const data = read.data;
  if (!parsed) return <p className="ac-muted">This field-action scope is not a component lot.</p>;
  if (!data)
    return (
      <Panel title="Field-action scope" source={read}>
        {null}
      </Panel>
    );
  const totals: Row = data.totals;
  const groups = scopeGroups<Row & { complaints: number; distribution_imported: boolean }>(data.lots ?? []);
  const download = async () => {
    setError("");
    try {
      await downloadFile(scopePath(parsed, true), { fallbackName: `mdarix-field-scope-${parsed.lot}.csv` });
    } catch (reason) {
      setError(errorText(reason, "The list could not be downloaded."));
    }
  };
  const caseRow: Row | undefined = data.investigations?.[0];
  const change: Row | undefined = data.changes?.[0];
  const signOnCase = () =>
    void chooseCase(work, String(caseRow?.business_id ?? caseRow?.investigation_identifier)).then((found) =>
      found
        ? open("Investigations", "Summary?part=lot-impact")
        : notify(`${caseRow?.investigation_identifier} could not be opened right now.`, "critical"),
    );
  const group = (title: string, lots: Row[]) =>
    lots.length > 0 && (
      <section className="uw-tw-part" aria-label={title}>
        <h3>
          {title} · {lots.length}
        </h3>
        <FlatTable
          caption={title}
          head={["Lot", "Product", "Units released", "Complaints", "Shipped", "In stock", "Markets"]}
        >
          {lots.map((lot) => (
            <tr key={lot.id}>
              <th scope="row">
                {lot.lot_identifier}
                <small>{lot.evidence?.[0]}</small>
              </th>
              <td>{[lot.product, lot.version].filter(Boolean).join(" ")}</td>
              <td>{lot.released ?? "Not known"}</td>
              <td>{lot.complaints}</td>
              <td>{shippedText(lot)}</td>
              <td>{lot.in_stock ?? "—"}</td>
              <td>{lot.by_country?.map((row: Row) => row.country).join(", ") || "—"}</td>
            </tr>
          ))}
        </FlatTable>
      </section>
    );
  return (
    <section className="uw-ph-section uw-tw" aria-label="Field-action scope">
      <div className="uw-tw-lead">
        <div>
          <h2>Field-action scope: lots built with {data.factor.label}</h2>
          <p className="ac-muted">
            Every lot of your organization built with it, across products and versions, from the imported lot genealogy.{" "}
            {data.never_decides}
          </p>
        </div>
        {canExport && (
          <button type="button" className="ac-primary" onClick={() => void download()}>
            <Download size={15} aria-hidden="true" /> Download the scope list (CSV)
          </button>
        )}
      </div>
      <InlineError text={error} />
      <div className="ca-action-row">
        {caseRow && (
          <button type="button" className="ac-link" onClick={signOnCase}>
            Sign it on the investigation ({caseRow.investigation_identifier} Lot impact)
          </button>
        )}
        {change && (
          <button
            type="button"
            className="ac-link"
            onClick={() => at({ view: "Changes", change: change.id, scope: null })}
          >
            What changed this part?
          </button>
        )}
        <button type="button" className="ac-link" onClick={() => at({ scope: null }, "replace")}>
          Back to the lots
        </button>
      </div>
      <div className="uw-trial-stats">
        <StatTile
          label="Lots built with it"
          value={totals.lots}
          detail="Across the organization"
          icon={<Boxes size={18} />}
        />
        <StatTile
          label="With complaints"
          value={totals.with_complaints}
          detail={countOf(totals.complaints, "complaint")}
          icon={<AlertTriangle size={18} />}
          tone={totals.with_complaints ? "warning" : "good"}
        />
        <StatTile
          label="Units released"
          value={totals.released.toLocaleString("en-US")}
          detail={`${totals.shipped.toLocaleString("en-US")} shipped`}
          icon={<Truck size={18} />}
        />
        <StatTile
          label="Still in stock"
          value={totals.in_stock.toLocaleString("en-US")}
          detail={
            totals.not_imported
              ? `${countOf(totals.not_imported, "lot")}: ${NOT_IMPORTED.toLowerCase()}`
              : "Released minus shipped"
          }
          icon={<PackageCheck size={18} />}
          tone={totals.not_imported ? "warning" : undefined}
        />
        <StatTile
          label="Markets and sites"
          value={data.by_market.length}
          detail={countOf(data.by_site.length, "site")}
          icon={<Factory size={18} />}
        />
      </div>
      <LotImpactCharts list={data as unknown as ImpactList} />
      <div className="uw-tw-pair">
        <section className="uw-tw-part" aria-label="By market">
          <h3>By market</h3>
          <FlatTable caption="Units shipped by market" head={["Country", "Units", "Sites", "Lots"]}>
            {data.by_market.map((row: Row) => (
              <tr key={row.country}>
                <th scope="row">{row.country}</th>
                <td>{row.units.toLocaleString("en-US")}</td>
                <td>{row.sites}</td>
                <td>{row.lots.join(", ")}</td>
              </tr>
            ))}
          </FlatTable>
        </section>
        <section className="uw-tw-part" aria-label="By site">
          <h3>By site</h3>
          <FlatTable caption="Units shipped by site" head={["Consignee", "Type", "Country", "Units", "Lots"]}>
            {data.by_site.map((row: Row) => (
              <tr key={`${row.consignee}-${row.country}`}>
                <th scope="row">{row.consignee}</th>
                <td>{row.consignee_type ?? "—"}</td>
                <td>{row.country}</td>
                <td>{row.units.toLocaleString("en-US")}</td>
                <td>{row.lots.join(", ")}</td>
              </tr>
            ))}
          </FlatTable>
        </section>
      </div>
      {group("With complaints", groups.withComplaints)}
      {group("Without complaints yet", groups.withoutComplaints)}
      {group(NOT_IMPORTED, groups.notImported)}
      {data.truncated && <p className="ac-note">Only the first 2,000 lots are listed.</p>}
      <details className="uw-more uw-tw-cannot" open>
        <summary>What this list cannot tell you</summary>
        <ol>
          {(data.cannot_tell ?? []).map((line: string) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
      </details>
    </section>
  );
}

// ----------------------------------------------------------------------------------------------- sources (section 1)

type SourceRun = ImportRun & {
  simulated: boolean;
  columns: { header: string; column: string; help: string | null }[];
  not_used: string[];
  lineage_rows: number;
  reconciled: boolean;
};
type Sources = {
  label: string;
  added_after_start: boolean | null;
  systems: { key: string; name: string; objects: string[]; runs: SourceRun[] }[];
};

/**
 * Sources (simulated) (W5, section 1): where the product's records came from, by system (PLM, ERP, eQMS; generic
 * names). Every card says "Simulated, not a live connection". Each run is a five-step strip, then its data-quality
 * report folded. One main button: open the connected view.
 */
export function SourcesView({ productId, version, at }: { productId: string; version: string | null; at: At }) {
  const sources = useResource<Sources>(SOURCES_PATH);
  const data = sources.data;
  if (!data)
    return (
      <Panel title="Where this product's records came from" source={sources}>
        {null}
      </Panel>
    );
  return (
    <section className="uw-ph-section uw-tw" aria-label="Where this product's records came from">
      <div className="uw-tw-lead">
        <div>
          <h2>Where this product's records came from</h2>
          <p className="ac-muted">
            Three systems, as recorded exports read through the same import checks as your own files: headers mapped,
            values checked, rows set aside with their reasons, every written row with its lineage.
          </p>
        </div>
        <button
          type="button"
          className="ac-primary"
          onClick={() => at({ view: "Connected", version, change: null, preview: null, scope: null })}
        >
          Open the connected product view <ArrowRight size={15} aria-hidden="true" />
        </button>
      </div>
      {data.added_after_start === null && (
        <p className="ac-note">
          The PLM, ERP and eQMS runs are added when your trial's sample is refreshed. Until then, the two sample runs
          below are shown.
        </p>
      )}
      <ul className="uw-tw-systems">
        {data.systems.map((system) => (
          <li key={system.key} className="uw-tw-system">
            <div className="uw-tw-system-head">
              <h3>{system.name}</h3>
              <span className="uw-tw-label">
                <PlugZap size={13} aria-hidden="true" /> {data.label}
              </span>
            </div>
            <p className="ac-muted">{system.objects.join(" · ")}</p>
            {system.runs.length ? (
              system.runs.map((run) => <SourceRunCard key={run.import_ref} run={run} />)
            ) : (
              <p className="ac-muted">No run recorded yet.</p>
            )}
          </li>
        ))}
      </ul>
      <RecordOrigin entity="products" recordId={productId} />
    </section>
  );
}

function SourceRunCard({ run }: { run: SourceRun }) {
  // The report reads the run's set-aside rows: only once someone opens it.
  const [opened, setOpened] = useState(false);
  return (
    <article className="uw-tw-run" aria-label={run.file_name ?? run.entity}>
      <p className="uw-tw-run-head">
        <strong>{run.file_name}</strong>
        <small>{run.mapping_version}</small>
      </p>
      <ol className="uw-tw-steps" aria-label="From the file to the records">
        {runSteps(run).map((step) => (
          <li key={step.label} className={step.ok ? "is-ok" : "is-flag"}>
            <span>{step.label}</span>
            <small>{step.detail}</small>
          </li>
        ))}
      </ol>
      <details className="uw-more" onToggle={(event) => setOpened(event.currentTarget.open)}>
        <summary>Columns and the data-quality report</summary>
        <ul className="uw-tw-columns">
          {run.columns.map((item) => (
            <li key={item.header}>
              <strong>{item.header}</strong> → {item.column}
              {item.help && <small>{item.help}</small>}
            </li>
          ))}
          {run.not_used.map((header) => (
            <li key={header} className="is-unused">
              <strong>{header}</strong> → not used
            </li>
          ))}
        </ul>
        {opened && <ImportRunReport run={run} />}
      </details>
    </article>
  );
}
