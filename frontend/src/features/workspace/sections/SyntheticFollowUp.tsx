/** W1d (D04): SAMPLE-CAPA-02's synthetic follow-up on its effectiveness check, flat (G-2) and labelled "Synthetic
 * follow-up (sample)" everywhere; never real history. The person reads it and signs the result below it. */
import { FlaskConical } from "lucide-react";
import { ToneBadge } from "../../admin/console/charts";
import type { FollowUpSide, SyntheticFollowUp } from "../effectiveness";
import { FlatTable } from "./ProductHub";

const rate = (value: number | null) => (value === null ? "–" : String(value));

/** "1 complaint in 750 unit-months (1.3 per 1,000)". */
export const sideLine = (side: FollowUpSide) =>
  `${side.complaints} complaint${side.complaints === 1 ? "" : "s"} in ${side.unit_months} unit-months ` +
  `(${rate(side.per_1000_unit_months)} per 1,000)`;

export function SyntheticFollowUpView({ followUp }: { followUp: SyntheticFollowUp }) {
  const { before, after } = followUp;
  const months = Math.max(before.months.length, after.months.length);
  return (
    <section className="ca-drawer-section uw-ef-synthetic" aria-label={followUp.label}>
      <h3>
        <FlaskConical size={16} aria-hidden="true" /> {followUp.label}
      </h3>
      <ToneBadge tone="warning" label="Synthetic, not real history" />
      <p className="ac-note">{followUp.notice}</p>
      <p className="uw-cr-meta">
        {followUp.action} · {followUp.follow_up_days} days after the fix · record {followUp.evidence_ref}
      </p>
      <FlatTable
        caption="Lots built after the fix (synthetic)"
        head={["Lot (synthetic)", "Built", "Units", "Inspection", "Complaints"]}
      >
        {after.lots.map((lot) => (
          <tr key={lot.lot}>
            <th scope="row">{lot.lot}</th>
            <td>Day {lot.built_day_after_fix} after the fix</td>
            <td>{lot.units}</td>
            <td>
              {lot.sensors_out_of_range} of {lot.sensors_inspected} sensors out of range
            </td>
            <td>{lot.complaints}</td>
          </tr>
        ))}
      </FlatTable>
      <FlatTable
        caption="Pressure-alarm complaints a month, before and after the fix"
        head={[
          "Month",
          `Before: ${before.lots.map((lot) => lot.replace(/^.*-LOT-/, "lot ")).join(", ")}`,
          "After (synthetic)",
        ]}
      >
        {Array.from({ length: months }, (_, index) => (
          <tr key={index}>
            <th scope="row">Month {index + 1}</th>
            <td>
              {before.months[index]
                ? `${before.months[index].complaints}${before.months[index].days < 30 ? ` (${before.months[index].days} days so far)` : ""}`
                : "–"}
            </td>
            <td>{after.months[index]?.complaints ?? "–"}</td>
          </tr>
        ))}
      </FlatTable>
      <dl className="uw-ef-compare">
        <div>
          <dt>Before: {before.source}</dt>
          <dd>{sideLine(before)}</dd>
        </div>
        <div>
          <dt>After: {after.source}</dt>
          <dd>{sideLine(after)}</dd>
        </div>
      </dl>
      <details className="uw-more">
        <summary>Limits of the synthetic follow-up</summary>
        <ul>
          {followUp.limits.map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </details>
      <p className="ac-muted">You judge it against the check&apos;s criteria and sign the result yourself.</p>
    </section>
  );
}
