import { useState } from "react";
import { Eraser, RotateCcw } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { errorText, send, useResource } from "../../customer-admin/shared";
import { countOf } from "./common";

type Preview = {
  sample: Record<string, number>;
  work_on_sample: number;
  own_records_affected: number;
  has_sample: boolean;
  is_owner: boolean;
  own_records?: number;
  sample_dated_at?: string | null;
  clock_stopped?: boolean;
};

export const SAMPLE_REMOVAL_PATH = "/api/v1/trial/sample-data/removal";
export const SAMPLE_RESTART_PATH = "/api/v1/trial/sample-data/restart";

/** What each restart choice removes, in plain words (exported for tests). */
export function restartChoices(data: Pick<Preview, "sample" | "own_records">): {
  story: string;
  own: string;
} {
  return {
    story: `Removes the sample (${sampleSummary(data.sample)}) and everything done on it, then brings it back dated today. Your own uploads and what you did with them stay.`,
    own: data.own_records
      ? `Also removes your own ${countOf(data.own_records, "uploaded record")} and everything you did with them.`
      : "You have not uploaded records of your own, so nothing more goes.",
  };
}

/**
 * "Restart the sample story" for the person who started the trial: the sample is removed and seeded again dated now
 * (backend/app/trial/sample_clock.py). The page asks first, with what each choice removes; never a browser dialog.
 */
export function RestartSamplePanel({ onRestarted }: { onRestarted: (text: string) => void }) {
  const preview = useResource<Preview>(SAMPLE_REMOVAL_PATH);
  const [asking, setAsking] = useState(false);
  const [own, setOwn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = preview.data;
  if (!data?.has_sample || !data.is_owner) return null;
  const choices = restartChoices(data);
  const restart = async () => {
    setBusy(true);
    setError("");
    try {
      await send(SAMPLE_RESTART_PATH, "POST", { confirm: true, own });
      setAsking(false);
      onRestarted("The sample story starts again today: every date, alert and next step is as on day one.");
    } catch (failure) {
      setError(errorText(failure, "The sample story was not restarted. Nothing was changed; please try again."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel eyebrow="The sample's clock" title="Restart the sample story" source={preview}>
      <p className="uw-trial-note">
        {data.clock_stopped
          ? "You have worked on the sample, so its dates stay where you left them and its deadlines age. Restart the story to see it as on day one."
          : "The sample's dates move with your trial, so its deadlines stay ahead of you. Restart the story to undo your practice on it."}
      </p>
      {!asking ? (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={() => setAsking(true)}>
            <RotateCcw size={15} aria-hidden="true" /> Restart the sample story
          </button>
        </div>
      ) : (
        <div role="group" aria-label="Confirm the restart">
          <ul className="uw-remove-sample">
            <li>
              <b>Restart:</b> {choices.story}
            </li>
            <li>
              <b>Also remove my practice work:</b> {choices.own}
            </li>
          </ul>
          <label className="ca-check">
            <input type="checkbox" checked={own} onChange={(event) => setOwn(event.target.checked)} /> Also remove my
            practice work
          </label>
          {error && (
            <p className="uw-flag-critical" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={() => void restart()} disabled={busy}>
              <RotateCcw size={15} aria-hidden="true" /> {busy ? "Restarting…" : "Yes, restart the story"}
            </button>
            <button type="button" className="ac-link" onClick={() => setAsking(false)} disabled={busy}>
              Keep the story as it is
            </button>
          </div>
        </div>
      )}
    </Panel>
  );
}

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
