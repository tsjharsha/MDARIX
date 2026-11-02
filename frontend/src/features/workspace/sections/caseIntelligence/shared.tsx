/** Shared pieces of the case intelligence views: sending a change, the case's evidence for pickers, a reason field. (Part of CaseIntelligence.tsx.) */
import { useState } from "react";
import { errorText, formatDate, listOf, send, useResource } from "../../../customer-admin/shared";
import { safeText } from "../../../../app/displayId";
import { useWorkspace } from "../../workspaceContext";
import {
  inventoryPath,
  itemReview,
  reviewStatusLabel,
  type EvidenceInventory,
  type InventoryItem,
} from "../../evidenceWorkflow";
import { TEXT_MAX } from "../../intelligence";

/** Send one change; on success say so and call onDone, on failure keep the drawer open with the server's message. */
export function useSend(onDone: () => void) {
  const { notify } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path: string, body: unknown, done: string, failed: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await send(path, "POST", body);
      notify(done);
      onDone();
    } catch (failure) {
      setError(errorText(failure, failed));
      setBusy(false);
    }
  };
  return { busy, error, run };
}

export function DrawerError({ error }: { error: string }) {
  return error ? (
    <p className="ac-message tone-critical" role="alert">
      {error}
    </p>
  ) : null;
}

export function DrawerActions({
  onClose,
  busy,
  disabled,
  label,
}: {
  onClose: () => void;
  busy: boolean;
  disabled: boolean;
  label: string;
}) {
  return (
    <div className="ca-action-row">
      <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
        Cancel
      </button>
      <button type="submit" className="ac-primary" disabled={busy || disabled}>
        {busy ? "Saving…" : label}
      </button>
    </div>
  );
}

/** The case's evidence (Phase 3 inventory), for choosing the record a link or an observation is about. */
export function useCaseEvidence(investigationId: string) {
  const inventory = useResource<EvidenceInventory>(inventoryPath(investigationId));
  return { inventory, items: listOf(inventory.data?.items) as InventoryItem[] };
}

export const evidenceOption = (item: InventoryItem) =>
  `${safeText(item.evidence?.business_id) ?? safeText(item.evidence?.evidence_identifier) ?? "Evidence"} · ${
    safeText(item.evidence?.title) ?? "Untitled record"
  } (${reviewStatusLabel(itemReview(item), item.link?.review_status_label)})`;

export function EvidenceSelect({
  investigationId,
  value,
  onChange,
  label,
  optional = false,
}: {
  investigationId: string;
  value: string;
  onChange: (id: string) => void;
  label: string;
  optional?: boolean;
}) {
  const { inventory, items } = useCaseEvidence(investigationId);
  return (
    <label className="ca-field">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">
          {inventory.state === "loading" && !inventory.data
            ? "Loading the investigation's evidence…"
            : items.length
              ? optional
                ? "No evidence"
                : "Choose evidence from this investigation"
              : "No evidence in this investigation yet"}
        </option>
        {items
          .filter((item) => item.evidence?.id)
          .map((item) => (
            <option key={item.evidence.id} value={String(item.evidence.id)}>
              {evidenceOption(item)}
            </option>
          ))}
      </select>
      {inventory.state !== "loading" && inventory.state !== "ready" && (
        <small className="ca-inline-error">
          {inventory.error ?? "The investigation's evidence could not be read."}
        </small>
      )}
    </label>
  );
}

export function ReasonField({
  label,
  value,
  onChange,
  required = true,
  min = 10,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  min?: number;
}) {
  return (
    <label className="ca-field">
      {label}
      <textarea
        required={required}
        rows={3}
        maxLength={TEXT_MAX}
        value={value}
        placeholder={required ? `At least ${min} characters` : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export const Problem = ({ problem, touched }: { problem: string | null; touched: boolean }) =>
  problem && touched ? <p className="uw-hint">{problem}</p> : null;

export const byWhom = (name: unknown, when: unknown) => {
  const who = safeText(name);
  return [who ? `by ${who}` : null, when ? formatDate(when) : null].filter(Boolean).join(" · ");
};
