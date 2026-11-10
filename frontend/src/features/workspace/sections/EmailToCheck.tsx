import { useState } from "react";
import { Mail, Paperclip } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { useCan, useEmailIntake } from "../workspaceContext";

export const EMAIL_INTAKE = "/api/v1/email-intake";

export type EmailAttachment = { id: string; file_name: string; size: number; usable: boolean; reason: string | null };
export type EmailItem = {
  id: string;
  state: string;
  received_at: string;
  from_domain: string | null;
  sender_verified: boolean;
  subject: string | null;
  words: string;
  identifiers: Record<string, { text: string; id?: string }>;
  note: string | null;
  checked: boolean;
  harm_words: string[];
  fault_words: string[];
  may_not_be_english: boolean;
  add_to_case: { id: string; reference: string } | null;
  possible_duplicate: { id: string; received_at: string } | null;
  possibly_known_earlier: string[];
  attachments: EmailAttachment[];
  message_id: string;
  sample: boolean;
};
type EmailPage = { items: EmailItem[]; reasons: string[] };

export const REASON_LABELS: Record<string, string> = {
  SPAM: "Spam",
  AUTO_REPLY: "Auto-reply",
  SETUP_MESSAGE: "Setup message",
  INTERNAL: "Internal",
  DUPLICATE: "Duplicate",
  OTHER: "Other",
};

/** The first lines of the masked words, for the card. */
export function firstLines(words: string, limit = 280): string {
  const flat = words.replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit - 1)}…` : flat;
}

/**
 * Cases › E-mail to check (B7b, spec 4.4): each message received on the organization's intake address, one card at a
 * time. A person decides: make it a case (Log a case opens pre-filled), add it to the Case it answers, or say why it
 * is not a case. An e-mail is never a complaint by itself. Shown only while e-mail intake is switched on.
 */
export function EmailToCheck({
  reloadKey = 0,
  onMakeCase,
  onChanged,
}: {
  reloadKey?: number;
  onMakeCase: (item: EmailItem) => void;
  onChanged: () => void;
}) {
  const on = useEmailIntake();
  const list = useResource<EmailPage>(on ? `${EMAIL_INTAKE}/messages?r=${reloadKey}` : null);
  if (!on) return null;
  const items = list.data?.items ?? [];
  return (
    <Panel eyebrow="Cases" title="E-mail to check" source={list}>
      {items.length === 0 ? (
        <Empty
          title="No e-mail to check"
          detail="Messages sent to your intake address appear here for a person to decide."
        />
      ) : (
        <ul className="uw-email-list">
          {items.map((item) => (
            <EmailCard
              key={item.id}
              item={item}
              reasons={list.data?.reasons ?? []}
              onMakeCase={onMakeCase}
              onChanged={() => {
                list.reload();
                onChanged();
              }}
            />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function EmailCard({
  item,
  reasons,
  onMakeCase,
  onChanged,
}: {
  item: EmailItem;
  reasons: string[];
  onMakeCase: (item: EmailItem) => void;
  onChanged: () => void;
}) {
  const canLog = useCan("case.log");
  const [closing, setClosing] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const act = async (path: string, body: unknown) => {
    setBusy(true);
    setError("");
    try {
      await send(`${EMAIL_INTAKE}/messages/${item.id}/${path}`, "POST", body);
      onChanged();
    } catch (reason) {
      setError(errorText(reason, "Not saved"));
    } finally {
      setBusy(false);
    }
  };
  const flagged = item.harm_words.length > 0 || item.fault_words.length > 0;
  return (
    <li className="uw-email-card" aria-label={`E-mail received ${formatDate(item.received_at)}`}>
      <header>
        <Mail size={16} aria-hidden="true" />
        <strong>{item.subject || "(no subject)"}</strong>
        {item.sample && <ToneBadge tone="neutral" label="SAMPLE" />}
      </header>
      <p className="uw-email-meta">
        Received {formatDate(item.received_at)} · from {item.from_domain ?? "an unknown sender"}{" "}
        <span title="The sender's address is not checked">(unverified)</span>
      </p>
      <p className="uw-email-words">{item.note ?? (item.checked ? firstLines(item.words) : "Being checked…")}</p>
      <div className="uw-email-chips">
        {item.harm_words.length > 0 && (
          <ToneBadge tone="critical" label={`Harm words: ${item.harm_words.join(", ")}`} />
        )}
        {item.fault_words.length > 0 && (
          <ToneBadge tone="warning" label={`Fault words: ${item.fault_words.join(", ")}`} />
        )}
        {item.may_not_be_english && <ToneBadge tone="warning" label="May not be English: add a translation" />}
        {item.possible_duplicate && (
          <ToneBadge
            tone="neutral"
            label={`Possible duplicate of the e-mail of ${formatDate(item.possible_duplicate.received_at)}`}
          />
        )}
        {item.possibly_known_earlier.map((moment) => (
          <ToneBadge key={moment} tone="warning" label={`Possibly known earlier: ${formatDate(moment)}`} />
        ))}
        {Object.entries(item.identifiers).map(([code, value]) => (
          <ToneBadge key={code} tone="neutral" label={`${code}: ${value.text} (unconfirmed, source: E-mail)`} />
        ))}
      </div>
      {item.attachments.length > 0 && (
        <ul className="uw-email-files">
          {item.attachments.map((file) => (
            <li key={file.id}>
              <Paperclip size={13} aria-hidden="true" /> {file.file_name}
              {!file.usable && <span className="uw-email-refused"> · {file.reason}</span>}
            </li>
          ))}
        </ul>
      )}
      {canLog && !closing && (
        <div className="uw-entry-actions">
          <button
            type="button"
            className="ac-primary"
            disabled={busy || !item.checked}
            onClick={() => onMakeCase(item)}
          >
            Make it a case
          </button>
          {item.add_to_case && (
            <button
              type="button"
              className="ac-secondary"
              disabled={busy}
              onClick={() => act("add-to-case", { case_id: item.add_to_case?.id })}
            >
              Add to {item.add_to_case.reference}
            </button>
          )}
          <button type="button" className="ac-link" disabled={busy} onClick={() => setClosing(true)}>
            Not a case
          </button>
          <button
            type="button"
            className="ac-link"
            onClick={() =>
              void downloadFile(`${EMAIL_INTAKE}/messages/${item.id}/raw`, { fallbackName: "email.eml" }).catch(
                (reason) => setError(errorText(reason, "Not opened")),
              )
            }
          >
            Open the original
          </button>
        </div>
      )}
      {closing && (
        <div className="uw-email-close" role="group" aria-label="Why it is not a case">
          {flagged && <p role="note">It has harm or fault words: a quality reviewer decides.</p>}
          <label>
            Why
            <select value={reason} onChange={(event) => setReason(event.target.value)}>
              <option value="">Choose…</option>
              {reasons.map((code) => (
                <option key={code} value={code}>
                  {REASON_LABELS[code] ?? code}
                </option>
              ))}
            </select>
          </label>
          {reason === "OTHER" && (
            <label>
              Say why
              <input value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
          )}
          <button
            type="button"
            className="ac-primary"
            disabled={busy || !reason || (reason === "OTHER" && note.trim().length < 10)}
            onClick={() => act("not-a-case", { reason, note })}
          >
            Confirm: not a case
          </button>
          <button type="button" className="ac-link" onClick={() => setClosing(false)}>
            Cancel
          </button>
        </div>
      )}
      {error && <p role="alert">{error}</p>}
    </li>
  );
}
