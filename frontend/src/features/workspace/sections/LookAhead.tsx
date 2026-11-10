import { Eye, Send } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Tabs, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { useReportedTab } from "../workspaceContext";
import { ProblemCodeOf } from "./ProblemCode";
import {
  LOOK_AHEAD_TABS,
  PREVIEW_PATHS,
  lookAheadTab,
  statusTone,
  type DistributorPreview,
  type IntakePreview,
  type LookAheadTab,
  type RepresentativePreview,
} from "../partyPreview";

/**
 * Look ahead (free trials only, T-G37P): read-only previews, with the sample parties, of how a distributor reports a
 * complaint and sees its status, and of what an EU authorised representative sees. Each page opening is audited; there
 * is nothing to send or change. Not a chapter: it counts for nothing in the story.
 */
export function LookAheadSection({ focus }: { focus?: string }) {
  const [tab, setTab] = useReportedTab<LookAheadTab>(lookAheadTab(focus));
  return (
    <Tabs tabs={LOOK_AHEAD_TABS} active={tab} onChange={setTab} label="Look ahead">
      {tab === "How a distributor reports" && <IntakePage />}
      {tab === "As your distributor sees it" && <DistributorPage />}
      {tab === "As your authorised representative sees it" && <RepresentativePage />}
    </Tabs>
  );
}

function Banner({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <p className="uw-preview-banner" role="note">
      <Eye size={16} aria-hidden="true" /> {text}
    </p>
  );
}

function IntakePage() {
  const page = useResource<IntakePreview>(PREVIEW_PATHS["How a distributor reports"]);
  return (
    // The tab names the page (0.10.87): the panel names the party.
    <Panel title={page.data?.party ?? "Sample distributor"} source={page}>
      {page.data && <IntakeBody data={page.data} />}
    </Panel>
  );
}

/** The intake form, filled and read-only: its Send button is disabled (exported for its test). */
export function IntakeBody({ data }: { data: IntakePreview }) {
  const item = data.submission;
  return (
    <>
      <Banner text={data.banner} />
      {!item ? (
        <Empty title="Nothing to preview" detail={data.empty ?? ""} />
      ) : (
        <form
          className="uw-preview-form"
          aria-label="Distributor intake form (preview)"
          onSubmit={(e) => e.preventDefault()}
        >
          <p className="ac-muted">
            The distributor sends a complaint straight to you, with its own reference. The form asks for no patient or
            reporter names. This one became {item.becomes} in your Complaints.
          </p>
          <fieldset disabled className="ca-fieldset">
            <label className="ca-field">
              Distributor
              <input readOnly value={data.party} />
            </label>
            <label className="ca-field">
              Your reference
              <input readOnly value={item.reference} />
            </label>
            <label className="ca-field">
              Product
              <input readOnly value={item.product} />
            </label>
            <label className="ca-field">
              Lot
              <input readOnly value={item.lot ?? ""} />
            </label>
            <label className="ca-field">
              Date you first knew of it
              <input readOnly value={formatDay(item.first_knowledge)} />
            </label>
            <label className="ca-field">
              What the reporter said
              <textarea readOnly rows={3} value={item.words} />
            </label>
          </fieldset>
          <div className="uw-preview-send">
            <button type="submit" className="ac-primary" disabled>
              <Send size={15} aria-hidden="true" /> Send to the manufacturer
            </button>
            <small className="ac-muted">Preview: nothing is sent.</small>
          </div>
        </form>
      )}
    </>
  );
}

function DistributorPage() {
  const page = useResource<DistributorPreview>(PREVIEW_PATHS["As your distributor sees it"]);
  return (
    <Panel title={page.data?.party ?? "Sample distributor"} source={page}>
      {page.data && <DistributorBody data={page.data} />}
    </Panel>
  );
}

/** The sample distributor's own complaints and their status (exported for its test). */
export function DistributorBody({ data }: { data: DistributorPreview }) {
  return (
    <>
      <Banner text={data.banner} />
      <p className="ac-muted">
        Only the complaints this distributor filed, each with its reference and status. It sees no patient data, no
        conclusion, no root cause and no report; a closing note only once you release one.
      </p>
      {!data.items.length ? (
        <Empty title="Nothing to preview" detail={data.empty ?? "This distributor has filed nothing."} />
      ) : (
        <ul className="uw-preview-items">
          {data.items.map((item) => (
            <li key={item.complaint}>
              <p>
                <strong>{item.reference}</strong> · {item.complaint}{" "}
                <ToneBadge tone={statusTone(item.status)} label={item.status_label} />
              </p>
              <p className="ac-muted">
                Received {formatDay(item.received)} · last change {formatDay(item.last_change)}
              </p>
              <p>
                <b>Closing note:</b> {item.closing_note ?? "none released yet"}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="ac-note">
        Received: with you, not yet assessed. Under assessment: a disposition, a market assessment or an investigation
        holds it. Closed: closed at service level or in your quality system.
      </p>
    </>
  );
}

function RepresentativePage() {
  const page = useResource<RepresentativePreview>(PREVIEW_PATHS["As your authorised representative sees it"]);
  return (
    <Panel title={page.data?.party ?? "Sample authorised representative"} source={page}>
      {page.data && <RepresentativeBody data={page.data} />}
    </Panel>
  );
}

/** The authorised representative's products, both panels, the PRRC note and every complaint (exported for its test). */
export function RepresentativeBody({ data }: { data: RepresentativePreview }) {
  const recurring = data.recurring;
  return (
    <>
      <Banner text={data.banner} />
      {!data.products.length ? (
        <Empty title="Nothing to preview" detail={data.empty ?? "No represented products."} />
      ) : (
        <>
          <p className="ac-muted">
            The products it represents in the EU: {data.products.join(" and ")}. It logs and monitors their complaints;
            it sees no patient or reporter data.
          </p>
          {data.prrc_note && (
            <p className="uw-preview-prrc" role="note">
              {data.prrc_note}
            </p>
          )}
          <div className="uw-preview-panels">
            <section aria-labelledby="ar-high-risk">
              <h3 id="ar-high-risk">High risk ({data.high_risk.length})</h3>
              <p className="ac-note">
                A safety or injury trigger, a harm level at or above the EU threshold, or a reportable conclusion.
              </p>
              <ul className="uw-preview-list">
                {data.high_risk.map((item) => (
                  <li key={item.id}>
                    <p>
                      <strong>{item.identifier}</strong> · {item.product} · {item.country ?? "—"}
                    </p>
                    <span>{item.reasons.join("; ")}</span>
                  </li>
                ))}
              </ul>
            </section>
            <section aria-labelledby="ar-recurring">
              <h3 id="ar-recurring">Recurring issues ({recurring.signals.length + recurring.service_level.length})</h3>
              <p className="ac-note">Open signals, and recurring service-level matters: {recurring.rule}.</p>
              <ul className="uw-preview-list">
                {recurring.signals.map((item) => (
                  <li key={item.id}>
                    <p>
                      <strong>{item.ref}</strong> · {item.product}
                    </p>
                    <span>
                      {item.title} · last event {formatDay(item.last_event)}
                    </span>
                  </li>
                ))}
                {recurring.service_level.map((item) => (
                  <li key={`${item.product_id}-${item.problem_code}`}>
                    <p>
                      <strong>{item.product_name}</strong> · <ProblemCodeOf code={item.problem_code} />
                    </p>
                    <span>
                      {item.count} service-level resolutions: {item.complaints.join(", ")}
                    </span>
                  </li>
                ))}
                {!recurring.signals.length && !recurring.service_level.length && <li>None open.</li>}
              </ul>
            </section>
          </div>
          <h3 className="uw-preview-heading">Every complaint on these products ({data.complaints.length})</h3>
          <div className="uw-table-scroll">
            <table className="ac-table ms-cards">
              <thead>
                <tr>
                  <th scope="col">Complaint</th>
                  <th scope="col">Product</th>
                  <th scope="col">Country</th>
                  <th scope="col">State</th>
                  <th scope="col">Received</th>
                  <th scope="col">Last change</th>
                  <th scope="col">EU/NI assessment</th>
                </tr>
              </thead>
              <tbody>
                {data.complaints.map((item) => (
                  <tr key={item.id}>
                    <td>{item.identifier}</td>
                    <td data-label="Product">{item.product}</td>
                    <td data-label="Country">{item.country ?? "—"}</td>
                    <td data-label="State">
                      <ToneBadge tone={statusTone(item.status)} label={item.state} />
                    </td>
                    <td data-label="Received">{formatDay(item.received)}</td>
                    <td data-label="Last change">{formatDay(item.last_change)}</td>
                    <td data-label="EU/NI assessment">
                      {item.eu_assessment.label}
                      {item.eu_assessment.date ? `, ${formatDay(item.eu_assessment.date)}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}
