import { useState } from "react";
import { Wrench } from "lucide-react";
import { errorText, formatDate, send } from "../../customer-admin/shared";
import { useCan } from "../workspaceContext";
import { SERVICE_STATUSES, eventPath, type EventView, type ServiceStatus } from "../oversight";
import { InlineError } from "./boardParts";

/**
 * A complaint's linked service work (0.10.71, A5): the reference in your service system, its owner and its status,
 * dated. Narrow on purpose (no scheduling, parts or technicians), and it never closes or advances the complaint.
 */
export function ServiceWork({
  view,
  onChanged,
  title = "Linked service work",
  headless = false,
}: {
  view: EventView;
  onChanged: (view: EventView) => void;
  title?: string;
  /** The heading and the state line are said by the fold that holds this (the complaint page's rail): not again. */
  headless?: boolean;
}) {
  const service = view.service ?? null;
  const canWrite = useCan("signal.triage") || useCan("investigation.work") || useCan("quality.review");
  const [reference, setReference] = useState(service?.reference ?? "");
  const [owner, setOwner] = useState(service?.owner_id ?? "");
  const [status, setStatus] = useState<ServiceStatus>(service?.status ?? "OPEN");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const unchanged =
    !!service && reference === service.reference && owner === (service.owner_id ?? "") && status === service.status;
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      onChanged(
        await send<EventView>(`${eventPath(view.event.complaint_id)}/service`, "PUT", {
          reference,
          status,
          owner_id: owner || null,
        }),
      );
    } catch (reason) {
      setError(errorText(reason, "The service work was not saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ca-drawer-section uw-service" aria-label={title}>
      {!headless && (
        <>
          <h3>
            <Wrench size={16} aria-hidden="true" /> {title}
          </h3>
          <p className="uw-service-state">{serviceText(view)}</p>
        </>
      )}
      {canWrite && (
        <div className="uw-service-form">
          <label className="ca-field">
            Service reference (your service system's ID)
            <input value={reference} maxLength={120} onChange={(event) => setReference(event.target.value)} />
          </label>
          <label className="ca-field">
            Service owner
            <select value={owner} onChange={(event) => setOwner(event.target.value)}>
              <option value="">Not named yet</option>
              {view.people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Status
            <select value={status} onChange={(event) => setStatus(event.target.value as ServiceStatus)}>
              {SERVICE_STATUSES.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="ac-secondary"
            disabled={busy || reference.trim().length < 2 || unchanged}
            onClick={() => void save()}
          >
            Save the service work
          </button>
        </div>
      )}
      <p className="ac-note">Service and quality are separate: completing the service never closes this complaint.</p>
      <InlineError text={error} />
    </section>
  );
}

/** "In progress since 1 Nov · SVC-24-1107 · owner Asha Rao", or that none is linked. */
export function serviceText(view: Pick<EventView, "service">): string {
  const service = view.service;
  if (!service) return "No service work linked.";
  return [
    `${service.status_label}${service.status_at ? ` since ${formatDate(service.status_at)}` : ""}`,
    service.reference,
    service.owner_name ? `owner ${service.owner_name}` : "owner not named yet",
  ].join(" · ");
}
