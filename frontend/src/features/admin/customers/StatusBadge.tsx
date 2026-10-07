import { ToneBadge } from "../console/charts";
import { statusTone, titleCase } from "./model";

/** A status with its tone; `label` replaces the default wording (the raw code stays in the title). */
export function StatusBadge({ status, label }: { status: unknown; label?: string }) {
  return (
    <span title={String(status ?? "")}>
      <ToneBadge tone={statusTone(status)} label={label ?? (status ? titleCase(status) : "Unknown")} />
    </span>
  );
}
