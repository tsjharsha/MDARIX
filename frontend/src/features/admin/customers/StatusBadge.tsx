import { ToneBadge } from "../console/charts";
import { statusTone, titleCase } from "./model";

export function StatusBadge({ status }: { status: unknown }) {
  return (
    <span title={String(status ?? "")}>
      <ToneBadge tone={statusTone(status)} label={status ? titleCase(status) : "Unknown"} />
    </span>
  );
}
