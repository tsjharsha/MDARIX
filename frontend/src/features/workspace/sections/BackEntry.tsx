import { useContext } from "react";
import { recordPlace } from "../../../app/linkTable";
import { INTAKE } from "../intake";
import { addressFor } from "../workspaceAddress";
import { WorkspaceContext } from "../workspaceContext";

/** B6a G18b/c: entering a Case after an outage (a back-entry). The server decides (entered more than 24 h after it was
 * received needs a reason, 422 LATE_ENTRY_REASON_NEEDED; owner, 11 Nov); the form asks early when Received is that old. */

/** Asked a little before the server's 24 h, since the form's times are wall-clock times in the Case's zone. */
const ASK_AFTER_HOURS = 12;

export type DuplicateHit = { kind: string; id: string; ref: string; source: string; reasons: string[] };

/** Whether any of the form's times (received, first knowledge, awareness) is old enough to ask for the reason. */
export function looksLate(times: string[], now: number = Date.now()): boolean {
  const parsed = times
    .filter(Boolean)
    .map((value) => Date.parse(value))
    .filter((value) => !Number.isNaN(value));
  return parsed.length > 0 && now - Math.min(...parsed) > ASK_AFTER_HOURS * 3600_000;
}

/** The duplicate check's address for the form's product, lot, serial, site, country and event day. */
export function duplicatesPath(form: {
  product: string;
  lot: string;
  serial: string;
  site: string;
  country: string;
  event: string;
}): string {
  // No product chosen: the server takes the lot's product (the lot alone is enough to check).
  const query = new URLSearchParams(form.product ? { product_id: form.product } : {});
  for (const [key, value] of [
    ["lot", form.lot],
    ["serial", form.serial],
    ["site", form.site],
    ["country", form.country],
  ])
    query.set(key, value);
  if (form.event) query.set("event_on", form.event.slice(0, 10));
  return `${INTAKE}/possible-duplicates?${query}`;
}

export function LateEntryField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="ca-field ca-wide">
      Why is this Case entered late? (needed when it was received more than 24 hours ago)
      <textarea
        rows={2}
        value={value}
        placeholder="For example: MDARIX was unavailable 10:00-14:00; entered from our paper log"
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="uw-hint">
        The reporting clock still counts from when you became aware, never from now: it may already be overdue.
      </span>
    </label>
  );
}

/** Where a possible duplicate opens: a complaint on its page (the new navigation) or its Oversight checklist (the
 * classic one); a Case on its check (Complaints › First contact; the new navigation's link table opens Calls to check). */
export function recordAddress(record: { kind: string; id: string; ref: string }, navigation?: string): string {
  if (record.kind !== "COMPLAINT")
    return addressFor({ section: "Complaints", tab: `First contact?${new URLSearchParams({ check: record.id })}` });
  return addressFor(
    navigation === "new" ? recordPlace("complaint", record.ref, {}, "new") : recordPlace("complaint", record.id),
  );
}

/** Navigation polish (B6a D4 #4, #5): a possible duplicate's reference opens its record in a new tab, so the form or
 * the reason being typed here is kept. */
export function RecordRef({ record }: { record: { kind: string; id: string; ref: string } }) {
  const navigation = useContext(WorkspaceContext)?.navigation;
  return (
    <a
      className="ac-link"
      href={recordAddress(record, navigation)}
      target="_blank"
      rel="noopener"
      aria-label={`${record.ref} (opens in a new tab)`}
    >
      <strong>{record.ref}</strong>
    </a>
  );
}

export function DuplicateHits({ hits }: { hits: DuplicateHit[] }) {
  return (
    <div className="uw-ma-starter" role="note">
      <p>
        <strong>This may be an event already in MDARIX.</strong> Open a record to compare (a new tab: this form stays).
        If it is the same event, close this form and add the call to that record. If not, save anyway; you can still
        link them later under Possible duplicates.
      </p>
      <ul>
        {hits.map((hit) => (
          <li key={`${hit.kind}:${hit.id}`}>
            <RecordRef record={hit} /> ({hit.source}): {hit.reasons.join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}
