import type { RefObject } from "react";
import { FileSearch } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { Tabs, useResource } from "../../customer-admin/shared";
import { MonitorBand, StatusPill } from "../../shared/hero/HeroVisuals";
import { formatDay } from "../../../app/dates";
import {
  chooseCase,
  useIsTrial,
  useOpenInvestigation,
  useWorkspace,
  type OpenInvestigationRequest,
  type RequestedComplaint,
} from "../workspaceContext";
import { countOf } from "./common";
import {
  Changes,
  CorrectionNote,
  FlatTable,
  MonthlyChart,
  OriginChip,
  recordLine,
  useRecordOpener,
} from "./ProductHub";
import {
  SUPPLIER_VIEWS,
  chosenView,
  inDataShown,
  productTab,
  rateText,
  supplierTab,
  type HubPlace,
  type Origin,
  type SupplierView,
} from "../productHub";

type Row = Record<string, any>;
type Go = (tab: string, how?: "push" | "replace") => void;

/** The sections a supplier's page offers: Lots only in a free trial, like a case's Lot impact (owner, 10 Nov 2026;
 * the server answers 404 elsewhere, supplier_router.LOTS_TRIAL_ONLY). */
export const supplierViews = (isTrial: boolean): readonly SupplierView[] =>
  isTrial ? SUPPLIER_VIEWS : SUPPLIER_VIEWS.filter((view) => view !== "Lots");

/** The suppliers (spec 4.1): parts, products and versions using them, recent complaints, open investigations. */
export function SupplierList({ go }: { go: Go }) {
  const { dataSource } = useWorkspace();
  const suppliers = useResource<Row[]>("/api/v1/suppliers?limit=100");
  const shown = (suppliers.data ?? []).filter((row) => inDataShown(row.origin as Origin, dataSource));
  const ref = (row: Row) => String(row.supplier_identifier ?? row.business_id ?? row.id);
  return (
    <Panel title={countOf(shown.length, "supplier")} source={suppliers}>
      {!shown.length ? (
        <Empty
          title="No suppliers yet"
          detail="Suppliers come with your components and parts in an import; each part's supplier links it here."
        />
      ) : (
        <FlatTable
          caption="Suppliers"
          head={["Supplier", "Origin", "Parts", "Products · versions", "Complaints, 90 days", "Open investigations"]}
        >
          {shown.map((row) => (
            <tr key={row.id}>
              <th scope="row">
                <button type="button" className="ac-link" onClick={() => go(supplierTab(ref(row)))}>
                  {row.name}
                </button>
              </th>
              <td>
                <OriginChip origin={row.origin} />
              </td>
              <td>{row.parts}</td>
              <td>
                {row.products} · {row.versions}
              </td>
              <td>{row.complaints_90d}</td>
              <td>{row.open_investigations}</td>
            </tr>
          ))}
        </FlatTable>
      )}
    </Panel>
  );
}

/**
 * "Open an investigation" from a found pattern: every complaint of the pattern on the top version's product ticked (a
 * case links its own product's complaints only), and where it came from, kept with the new case (its opening's audit
 * reason). Null when the pattern names none of that product's complaints.
 */
export function patternRequest(box: Row, version: Row | undefined): OpenInvestigationRequest | null {
  const ticked: RequestedComplaint[] = (box.complaints ?? [])
    .filter((row: Row) => version && String(row.product_id) === String(version.product_id))
    .map((row: Row) => ({
      id: String(row.id),
      business_id: row.business_id ?? null,
      complaint_identifier: row.complaint_identifier ?? null,
      description: row.description ?? null,
    }));
  if (!version || !ticked.length) return null;
  const [complaint, ...also] = ticked;
  return {
    productId: String(version.product_id),
    version: version.version_identifier,
    complaint,
    also,
    openedFrom: `Opened from Supplier 360: pattern ${box.rule} v${box.rule_version}`,
  };
}

/** The pattern box (spec 4.3, rule P-1 v1): the server's own words, the rule printed, never a confirmed signal. */
export function PatternBox({ page, go }: { page: Row; go: Go }) {
  const box: Row = page.pattern;
  const { work, open, notify } = useWorkspace();
  const openInvestigation = useOpenInvestigation();
  const covering: Row | undefined = box.investigations?.[0];
  const top: Row | undefined = box.found ? box.versions?.[0] : undefined;
  const version: Row | undefined = top && page.versions.find((item: Row) => item.version_id === top.version_id);
  const request = patternRequest(box, version);
  return (
    <section className={`uw-ph-pattern${box.found ? "" : " is-quiet"}`} aria-label="Pattern to review">
      <h2>{box.found ? "Pattern to review" : "Patterns across versions"}</h2>
      <p>{box.text}</p>
      <p className="uw-ph-rule">
        Rule {box.rule} version {box.rule_version}: the same problem code with {box.thresholds?.complaints_per_version}{" "}
        or more complaints on each of {box.thresholds?.versions} or more versions that contain these parts, in the last{" "}
        {box.window_days} days. A pattern to review is never a confirmed signal.
      </p>
      {box.found && (
        <div className="ca-action-row">
          {covering ? (
            <button
              type="button"
              className="ac-secondary"
              onClick={() =>
                void chooseCase(work, String(covering.ref)).then((found) =>
                  found
                    ? open("Investigations", "Summary")
                    : notify(`${covering.ref} could not be opened.`, "critical"),
                )
              }
            >
              <FileSearch size={15} aria-hidden="true" /> Open {covering.ref} (covers {covering.held} of these
              complaints)
            </button>
          ) : openInvestigation && request ? (
            // A person confirms on the investigation form; nothing is opened from here by itself.
            <button type="button" className="ac-primary" onClick={() => openInvestigation(request)}>
              <FileSearch size={15} aria-hidden="true" /> Open an investigation
            </button>
          ) : (
            version && (
              <button
                type="button"
                className="ac-secondary"
                onClick={() => go(productTab(String(version.product_identifier), version.version_identifier))}
              >
                Open {version.product_name} {version.version_identifier}
              </button>
            )
          )}
        </div>
      )}
    </section>
  );
}

/** One supplier's page (spec 4.2): the hero head, the pattern box first, then its sections. */
export function SupplierPage({
  place,
  go,
  heading,
}: {
  place: HubPlace;
  go: Go;
  heading?: RefObject<HTMLHeadingElement | null>;
}) {
  const isTrial = useIsTrial();
  const ref = encodeURIComponent(place.supplier ?? "");
  const resource = useResource<Row>(`/api/v1/suppliers/${ref}`);
  const page = resource.data;
  const views = supplierViews(isTrial);
  const active = chosenView(views, place.view);
  if (!page)
    return (
      <Panel title="The supplier" source={resource}>
        {null}
      </Panel>
    );
  const supplier: Row = page.supplier;
  const counts: Row = page.counts;
  const show = (view: SupplierView) => go(supplierTab(String(place.supplier), view), "replace");
  const tile = (label: string, value: number, view: SupplierView) => (
    <li className="uw-ph-tile" key={label}>
      <div className="uw-ph-tile-head">
        <h3>{label}</h3>
        <span className="uw-ph-tile-count">{value}</span>
      </div>
      {views.includes(view) && view !== "Overview" && (
        <button type="button" className="ac-link" onClick={() => show(view)}>
          See {view.toLowerCase()}
        </button>
      )}
    </li>
  );
  return (
    <>
      <div className="uw-ph-head">
        <MonitorBand label={`${supplier.name} at a glance`}>
          <div className="uw-ph-headmain">
            <p className="ac-eyebrow">
              <button type="button" className="ac-link" onClick={() => go("Supplier 360")}>
                Supplier 360
              </button>{" "}
              · {supplier.supplier_identifier}
            </p>
            <h1 ref={heading} tabIndex={-1}>
              {supplier.name}
            </h1>
            <div className="uw-ph-chips">
              <OriginChip origin={supplier.origin} />
              {supplier.status && <StatusPill tone="none">{supplier.status}</StatusPill>}
              <span className="uw-ph-note">
                {supplier.since ? `Recorded supplier since ${formatDay(supplier.since)}` : "No part link recorded"}
              </span>
            </div>
            <CorrectionNote origin={supplier.origin} />
          </div>
        </MonitorBand>
      </div>
      <Tabs tabs={views} active={active} onChange={show} label={`${supplier.name} sections`}>
        {active === "Overview" && (
          <>
            <PatternBox page={page} go={go} />
            <ul className="uw-ph-tiles uw-ph-section">
              {tile("Parts", counts.parts, "Parts and products")}
              {tile("Products and versions", counts.versions, "Parts and products")}
              {tile("Lots on those versions", counts.lots_on_versions, "Lots")}
              {tile("Complaints, 90 days", counts.complaints_90d, "Complaints and investigations")}
              {tile("Investigations", counts.investigations, "Complaints and investigations")}
              {tile("Changes", counts.changes, "Changes and evidence")}
              {tile("Evidence", counts.evidence, "Changes and evidence")}
              {tile("CAPAs", counts.capas, "CAPAs")}
            </ul>
            <div className="uw-ph-section">
              <MonthlyChart monthly={page.trend} />
            </div>
          </>
        )}
        {active === "Parts and products" && <Parts page={page} go={go} />}
        {active === "Lots" && <SupplierLots supplier={ref} />}
        {active === "Complaints and investigations" && <ComplaintsAndInvestigations page={page} supplier={ref} />}
        {active === "Changes and evidence" && <ChangesAndEvidence page={page} />}
        {active === "CAPAs" && <Capas page={page} />}
      </Tabs>
      <p className="ac-muted uw-ph-note">{page.never_decides}</p>
    </>
  );
}

function Parts({ page, go }: { page: Row; go: Go }) {
  if (!page.parts.length) return <p className="ac-muted">{page.pattern.text}</p>;
  return (
    <FlatTable
      caption="Parts and the products using them"
      head={["Part", "Supplied since", "Other suppliers", "Used in"]}
    >
      {page.parts.map((part: Row) => (
        <tr key={part.id}>
          <th scope="row">
            {part.name}
            <small>
              {part.component_identifier}
              {part.revision ? ` · ${part.revision}` : ""}
            </small>
          </th>
          <td>{formatDay(part.supplied_from)}</td>
          <td>{part.other_suppliers?.length ? part.other_suppliers.join(", ") : "None recorded"}</td>
          <td>
            {part.used_in.length
              ? part.used_in.map((use: Row) => (
                  <button
                    key={use.version_id}
                    type="button"
                    className="ac-link"
                    onClick={() => go(productTab(String(use.product_identifier), use.version_identifier))}
                  >
                    {use.product_name} {use.version_identifier}
                  </button>
                ))
              : "No product version recorded"}
          </td>
        </tr>
      ))}
    </FlatTable>
  );
}

/** Lots whose genealogy names its parts (lot_impact.build), else the versions' lots, said plainly (spec 4.2). */
function SupplierLots({ supplier }: { supplier: string }) {
  const lots = useResource<Row>(`/api/v1/suppliers/${supplier}/lots`);
  const data = lots.data;
  return (
    <Panel title="Lots" source={lots}>
      {data && (
        <>
          {data.note && <p className="ac-muted">{data.note}</p>}
          {!data.lots.length ? (
            <p className="ac-muted">No lots are recorded for the versions that contain these parts.</p>
          ) : (
            <FlatTable
              caption="Lots"
              head={["Lot", "Product · version", "Units released", "Complaints", "Per 1,000", "Why it is listed"]}
            >
              {data.lots.map((lot: Row) => {
                const released = lot.released ?? lot.units_released ?? lot.quantity ?? null;
                return (
                  <tr key={lot.id ?? lot.lot_identifier}>
                    <th scope="row">{lot.lot_identifier}</th>
                    <td>
                      {[lot.product ?? lot.product_name, lot.version ?? lot.version_identifier]
                        .filter(Boolean)
                        .join(" ")}
                    </td>
                    <td>{released ?? "Not known"}</td>
                    <td>{lot.complaints}</td>
                    <td>{rateText(lot.per_1000, released != null)}</td>
                    <td>{(lot.evidence ?? []).join(" ")}</td>
                  </tr>
                );
              })}
            </FlatTable>
          )}
        </>
      )}
    </Panel>
  );
}

const PAGE = 20;

function ComplaintsAndInvestigations({ page, supplier }: { page: Row; supplier: string }) {
  const openRecord = useRecordOpener();
  const complaints = useResource<Row[]>(`/api/v1/suppliers/${supplier}/complaints?limit=${PAGE}`);
  const total = page.counts.complaints;
  return (
    <>
      <Panel title={`Complaints on versions with its parts · ${total}`} source={complaints}>
        {!complaints.data?.length ? (
          <p className="ac-muted">No complaints are recorded on versions that contain these parts.</p>
        ) : (
          <FlatTable caption="Complaints" head={["Complaint", "Product · version", "Problem", "Why it is linked"]}>
            {complaints.data.map((row) => (
              <tr key={row.id}>
                <th scope="row">
                  <button type="button" className="ac-link" onClick={() => openRecord("complaints", row)}>
                    {row.complaint_identifier ?? row.business_id}
                  </button>
                  <small>{formatDay(row.event_timestamp)}</small>
                </th>
                <td>
                  {row.product_name} {row.version_identifier}
                </td>
                <td>{row.problem_code ?? "—"}</td>
                <td>{row.basis}</td>
              </tr>
            ))}
          </FlatTable>
        )}
        {total > PAGE && (
          <p className="ac-muted uw-ph-note">
            The newest {PAGE} of {total}.
          </p>
        )}
      </Panel>
      <div className="uw-ph-section">
        <h3>Investigations holding these complaints</h3>
        {!page.investigations.length ? (
          <p className="ac-muted">No investigation holds any of these complaints.</p>
        ) : (
          <FlatTable caption="Investigations" head={["Investigation", "Status", "Complaints it holds"]}>
            {page.investigations.map((row: Row) => (
              <tr key={row.id}>
                <th scope="row">
                  <button type="button" className="ac-link" onClick={() => openRecord("investigations", row)}>
                    {row.investigation_identifier ?? row.business_id}
                  </button>
                </th>
                <td>{row.status ?? "—"}</td>
                <td>{row.held ?? "—"}</td>
              </tr>
            ))}
          </FlatTable>
        )}
      </div>
    </>
  );
}

function ChangesAndEvidence({ page }: { page: Row }) {
  return (
    <>
      <Changes changes={page.changes} />
      <section className="uw-ph-section" aria-label="Evidence">
        <h3>Incoming inspection and other evidence</h3>
        {!page.evidence.length ? (
          <p className="ac-muted">No evidence is linked to this supplier or its parts.</p>
        ) : (
          <FlatTable caption="Evidence" head={["Evidence", "Source", "Reliability", "Investigation", "Linked to"]}>
            {page.evidence.map((row: Row) => (
              <tr key={row.id}>
                <th scope="row">
                  {row.title}
                  <small>{row.evidence_identifier}</small>
                </th>
                <td>{row.source_reference ?? "—"}</td>
                <td>{row.reliability_status ?? "—"}</td>
                <td>{row.investigation_identifier ?? "—"}</td>
                <td>{row.basis ?? "—"}</td>
              </tr>
            ))}
          </FlatTable>
        )}
      </section>
      <section className="uw-ph-section" aria-label="Evidence requests">
        <h3>Evidence requests sent to the supplier</h3>
        {!page.evidence_requests.length ? (
          <p className="ac-muted">No evidence request has been sent to this supplier.</p>
        ) : (
          <FlatTable caption="Evidence requests" head={["Request", "Sent on", "Due", "Status", "Answer"]}>
            {page.evidence_requests.map((row: Row) => (
              <tr key={row.business_id ?? row.title}>
                <th scope="row">{row.title}</th>
                <td>{formatDay(row.created_at)}</td>
                <td>{formatDay(row.due_at)}</td>
                <td>{row.status ?? "—"}</td>
                <td>{row.responded_at ? `Received ${formatDay(row.responded_at)}` : "Not yet"}</td>
              </tr>
            ))}
          </FlatTable>
        )}
      </section>
    </>
  );
}

function Capas({ page }: { page: Row }) {
  const openRecord = useRecordOpener();
  return (
    <section className="uw-ph-section" aria-label="CAPAs">
      {!page.capas.length ? (
        <p className="ac-muted">No CAPA comes from these investigations or is on these products.</p>
      ) : (
        <FlatTable caption="CAPAs" head={["CAPA", "Details", "Origin"]}>
          {page.capas.map((row: Row) => {
            const line = recordLine("capas", row);
            return (
              <tr key={row.id}>
                <th scope="row">
                  <button type="button" className="ac-link" onClick={() => openRecord("capas", row)}>
                    {line.ref}
                  </button>
                </th>
                <td>{line.text}</td>
                <td>
                  <OriginChip origin={row.origin} />
                </td>
              </tr>
            );
          })}
        </FlatTable>
      )}
      <p className="ac-muted uw-ph-note">{page.scar_note}</p>
    </section>
  );
}

/** The Suppliers tab: the list, or one supplier's page. */
export function SuppliersTab({
  place,
  go,
  heading,
}: {
  place: HubPlace;
  go: Go;
  heading?: RefObject<HTMLHeadingElement | null>;
}) {
  return place.supplier ? <SupplierPage place={place} go={go} heading={heading} /> : <SupplierList go={go} />;
}
