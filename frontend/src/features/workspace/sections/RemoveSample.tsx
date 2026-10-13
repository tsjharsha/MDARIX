import { useState } from "react";
import { Eraser } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { countOf } from "./common";

type Preview = {
  sample: Record<string, number>;
  work_on_sample: number;
  own_records_affected: number;
  has_sample: boolean;
  is_owner: boolean;
};

export const SAMPLE_REMOVAL_PATH = "/api/v1/trial/sample-data/removal";

/** "3 products, 37 complaints and 1 investigation": the sample's records as people name them (exported for tests). */
export function sampleSummary(sample: Record<string, number>): string {
  const parts = Object.entries(sample)
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => `${count} ${count === 1 ? kind.replace(/ies$/, "y").replace(/s$/, "") : kind}`);
  if (!parts.length) return "";
  return parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * Removing the sample data, for the person who started the trial: what goes (the sample's records and the work done
 * on them), what stays (the organization's own uploads, what it did with them, its reporting windows, the chapters
 * already tried), then a confirmed removal (backend/app/trial/sample_removal.py).
 */
export function RemoveSamplePanel({ onRemoved }: { onRemoved: (text: string) => void }) {
  const preview = useResource<Preview>(SAMPLE_REMOVAL_PATH);
  const [sure, setSure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = preview.data;
  if (!data?.has_sample || !data.is_owner) return null;
  const remove = async () => {
    setBusy(true);
    setError("");
    try {
      await send(SAMPLE_REMOVAL_PATH, "POST", { confirm: true });
      onRemoved("The sample data is removed: every screen now shows your own data.");
    } catch (failure) {
      setError(errorText(failure, "The sample data was not removed. Nothing was changed; please try again."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel eyebrow="Only your own data" title="Remove the sample data" source={preview}>
      <p className="uw-trial-note">
        Once your own export is in, remove the sample so every screen, check and count shows only your records.
      </p>
      <ul className="uw-remove-sample">
        <li>
          <b>Removed:</b> {sampleSummary(data.sample)}
          {data.work_on_sample ? `, and ${countOf(data.work_on_sample, "record")} of work done on them` : ""}.
        </li>
        <li>
          <b>Kept:</b> everything you uploaded and what you did with it, your reporting windows, and the chapters you
          already tried.
        </li>
        {data.own_records_affected > 0 && (
          <li className="uw-flag-critical">
            {data.own_records_affected} of your own{" "}
            {data.own_records_affected === 1 ? "records refers" : "records refer"} to sample records and would go too.
          </li>
        )}
      </ul>
      <label className="ca-check">
        <input type="checkbox" checked={sure} onChange={(event) => setSure(event.target.checked)} /> I understand the
        sample data cannot be brought back.
      </label>
      {error && (
        <p className="uw-flag-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={() => void remove()} disabled={!sure || busy}>
          <Eraser size={15} aria-hidden="true" /> {busy ? "Removing…" : "Remove the sample data"}
        </button>
      </div>
    </Panel>
  );
}
