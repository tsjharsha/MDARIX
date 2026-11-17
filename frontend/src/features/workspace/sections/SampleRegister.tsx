/**
 * W1d (D08): the sample evidence register. One page that answers "where did this number come from?" for the flagship
 * story, from GET /api/v1/trial/sample-register (backend/app/trial/sample_register.py): the product and versions, the
 * supplier change, the lots, the complaint counts and monthly rates from the trend check (the same computation as
 * Trends and Home), the inspection changes, the evidence for, against and missing with dates and sources, the
 * synthetic follow-up (labelled) and the sample's limits. Plain English, flat (G-2), readable on a projector.
 */
import type { RefObject } from "react";
import { ChevronRight } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { FlatTable } from "./ProductHub";

/** Getting started's tab name that opens the register (from the flagship bar and Getting started). */
export const SAMPLE_REGISTER = "Sample evidence register";
export const REGISTER_LINK = "Where do the numbers come from?";
export const SAMPLE_REGISTER_PATH = "/api/v1/trial/sample-register";

type Link = { evidence: string; hypothesis: string; why: string | null };
export type SampleRegisterData = {
  title: string;
  product: {
    id: string;
    ref: string;
    name: string;
    versions: { version: string; released: string | null; description: string | null }[];
  };
  change: { ref: string; description: string; on: string | null } | null;
  component: { ref: string; suppliers: { revision: string | null; supplier: string; from: string | null }[] };
  lots: {
    ref: string;
    version: string | null;
    built: string | null;
    units: number | null;
    complaints: number;
    pressure_alarm: number;
    in_case: boolean;
  }[];
  complaints: {
    on_product: number;
    pressure_alarm: number;
    in_case: number;
    trend: {
      version: string | null;
      recent: number;
      recent_days: number;
      expected: number;
      ratio: number | null;
      label: string;
      monthly: { before: number; after: number } | null;
    }[];
    trend_source: string;
  };
  inspection: { when: string; units_per_lot: number; source: string }[];
  case: { id: string; ref: string; question: string } | null;
  evidence: {
    records: { ref: string; title: string; recorded: string | null; source: string | null; content: string | null }[];
    for: Link[];
    against: Link[];
    missing: { what: string; needed: string | null; status: string }[];
  };
  follow_up: {
    label: string;
    notice: string;
    record: { ref: string; title: string; recorded: string | null } | null;
    capa: { id: string; ref: string; title: string } | null;
    check: string | null;
    after: { complaints: number; unit_months: number; per_1000_unit_months: number | null };
  };
  limits: string[];
};

const day = (value: string | null) => (value ? formatDay(value, "–") : "–");

function LinkList({ items, empty }: { items: Link[]; empty: string }) {
  if (!items.length) return <p className="ac-muted">{empty}</p>;
  return (
    <ul className="uw-reg-list">
      {items.map((item) => (
        <li key={`${item.evidence}-${item.hypothesis}`}>
          <b>{item.evidence}</b> · {item.why ?? "No reason recorded"} <small>(about: {item.hypothesis})</small>
        </li>
      ))}
    </ul>
  );
}

export function SampleRegisterPage({ heading }: { heading?: RefObject<HTMLHeadingElement | null> }) {
  const { open, work } = useWorkspace();
  const resource = useResource<SampleRegisterData>(SAMPLE_REGISTER_PATH);
  const data = resource.data;
  const go = (section: string, tab?: string) => open(section as WorkspaceSection, tab);
  const openCase = (tab: string) => {
    if (!data?.case) return;
    work.setInvestigationId(data.case.id, data.product.id);
    go("Investigations", tab);
  };
  return (
    <div className="uw-gs uw-reg">
      <div className="uw-gs-more-head">
        <button type="button" className="ac-link" onClick={() => go("Getting started")}>
          <ChevronRight size={14} aria-hidden="true" className="uw-flip" /> Back to Getting started
        </button>
        <p className="ac-eyebrow">Sample data · OrbitCare 300 · SAMPLE-INV-001</p>
        <h1 ref={heading} tabIndex={-1}>
          {SAMPLE_REGISTER}
        </h1>
        <p>Where each number in the sample investigation comes from, read from the sample&apos;s own records.</p>
      </div>
      <Panel title="The product and its versions" source={resource}>
        {data && (
          <>
            <p>
              <b>{data.product.name}</b> ({data.product.ref})
            </p>
            <FlatTable caption="Versions" head={["Version", "Released", "Description"]}>
              {data.product.versions.map((row) => (
                <tr key={row.version}>
                  <th scope="row">{row.version}</th>
                  <td>{day(row.released)}</td>
                  <td>{row.description ?? "–"}</td>
                </tr>
              ))}
            </FlatTable>
          </>
        )}
      </Panel>
      {data && (
        <>
          <Panel title="Supplier and component change">
            {data.change ? (
              <p>
                <b>{data.change.ref}</b> ({day(data.change.on)}): {data.change.description}
              </p>
            ) : (
              <p className="ac-muted">No change record in the sample.</p>
            )}
            <FlatTable caption={`Suppliers of ${data.component.ref}`} head={["Component revision", "Supplier", "From"]}>
              {data.component.suppliers.map((row) => (
                <tr key={`${row.revision}-${row.supplier}`}>
                  <th scope="row">{row.revision ?? "–"}</th>
                  <td>{row.supplier}</td>
                  <td>{day(row.from)}</td>
                </tr>
              ))}
            </FlatTable>
          </Panel>
          <Panel title="Lots">
            <FlatTable
              caption="Lots"
              head={["Lot", "Version", "Built", "Units", "Complaints", "Pressure alarm", "In the investigation"]}
            >
              {data.lots.map((lot) => (
                <tr key={lot.ref}>
                  <th scope="row">{lot.ref}</th>
                  <td>{lot.version ?? "–"}</td>
                  <td>{day(lot.built)}</td>
                  <td>{lot.units ?? "Units unknown"}</td>
                  <td>{lot.complaints}</td>
                  <td>{lot.pressure_alarm}</td>
                  <td>{lot.in_case ? "Yes" : "No"}</td>
                </tr>
              ))}
            </FlatTable>
          </Panel>
          <Panel title="Complaint counts and monthly rates">
            <p>
              {data.complaints.on_product} complaints on the product, {data.complaints.pressure_alarm} of them pressure
              alarms; {data.complaints.in_case} are in the investigation.
            </p>
            <FlatTable
              caption="The trend check"
              head={["Version", "Last 30 days", "Expected", "Complaints a month, before → after", "Ratio", "Result"]}
            >
              {data.complaints.trend.map((row) => (
                <tr key={row.version ?? "none"}>
                  <th scope="row">{row.version ?? "Version not recorded"}</th>
                  <td>{row.recent}</td>
                  <td>{row.expected}</td>
                  <td>{row.monthly ? `${row.monthly.before.toFixed(1)} → ${row.monthly.after.toFixed(1)}` : "–"}</td>
                  <td>{row.ratio === null ? "–" : `${row.ratio}×`}</td>
                  <td>{row.label}</td>
                </tr>
              ))}
            </FlatTable>
            <p className="ac-muted">
              Source: {data.complaints.trend_source}.{" "}
              <button
                type="button"
                className="ac-link"
                onClick={() => go("Trends", `Trend check?product=${data.product.ref}`)}
              >
                Open the trend check
              </button>
            </p>
          </Panel>
          <Panel title="Incoming inspection of the pressure sensor">
            <FlatTable caption="Inspection" head={["When", "Sensors inspected per lot", "Source"]}>
              {data.inspection.map((row) => (
                <tr key={row.when}>
                  <th scope="row">{row.when}</th>
                  <td>{row.units_per_lot}</td>
                  <td>{row.source}</td>
                </tr>
              ))}
            </FlatTable>
          </Panel>
          <Panel title="Evidence for, against and missing">
            <FlatTable caption="Evidence records" head={["Record", "Title", "Recorded", "Source"]}>
              {data.evidence.records.map((row) => (
                <tr key={row.ref}>
                  <th scope="row">{row.ref}</th>
                  <td>{row.title}</td>
                  <td>{day(row.recorded)}</td>
                  <td>{row.source ?? "–"}</td>
                </tr>
              ))}
            </FlatTable>
            <h3>For</h3>
            <LinkList items={data.evidence.for} empty="No supporting evidence linked." />
            <h3>Against</h3>
            <LinkList items={data.evidence.against} empty="No contradicting evidence linked." />
            <h3>Missing</h3>
            <ul className="uw-reg-list">
              {data.evidence.missing.map((row) => (
                <li key={row.what}>
                  {row.what}{" "}
                  <small>
                    Needed: {row.needed ?? "not stated"} · {row.status}
                  </small>
                </li>
              ))}
            </ul>
            {data.case && (
              <p>
                <button
                  type="button"
                  className="ac-link"
                  onClick={() => openCase("Evidence?view=Overview&part=intelligence")}
                >
                  Open the evidence of {data.case.ref}
                </button>
              </p>
            )}
          </Panel>
          <Panel title={data.follow_up.label}>
            <p className="ac-note">{data.follow_up.notice}</p>
            <p>
              {data.follow_up.after.complaints} pressure-alarm complaint in {data.follow_up.after.unit_months}{" "}
              unit-months ({data.follow_up.after.per_1000_unit_months ?? "–"} per 1,000) on the synthetic lots
              {data.follow_up.record
                ? `; record ${data.follow_up.record.ref}, ${day(data.follow_up.record.recorded)}`
                : ""}
              .
            </p>
            <p>
              {data.follow_up.check
                ? `Effectiveness check of ${data.follow_up.capa?.ref}: ${data.follow_up.check.replace(/_/g, " ").toLowerCase()}.`
                : `The follow-up shows on ${data.follow_up.capa?.ref ?? "the CAPA"}'s effectiveness check once it is planned.`}{" "}
              {data.follow_up.capa && (
                <button
                  type="button"
                  className="ac-link"
                  onClick={() =>
                    go("Records", `Effectiveness checks?${new URLSearchParams({ capa: data.follow_up.capa!.id })}`)
                  }
                >
                  Open the effectiveness check
                </button>
              )}
            </p>
          </Panel>
          <Panel title="Limits of the sample dataset">
            <ul className="uw-reg-list">
              {data.limits.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}
