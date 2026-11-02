import { useState } from "react";
import { BellRing, CalendarOff, ChevronRight } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { placeOf } from "../../../app/linkTable";
import {
  ALERTS,
  OVERSIGHT,
  absenceProblem,
  alertTone,
  groupAlerts,
  hoursText,
  type Alert,
  type AlertList,
  type Opens,
} from "../oversight";
import { InlineError } from "./boardParts";

/** Opens where an alert's work is done (its own section and tab). */
function useOpen() {
  const { open } = useWorkspace();
  return (opens: Opens) => {
    if (!opens) return;
    const place = placeOf(opens);
    open(place.section as WorkspaceSection, place.tab);
  };
}

/**
 * Reminders and escalations at the top of My Work (T-G25): escalations and overdue items one by one, the items only
 * due soon grouped by category; each opens where it is done. Reading never resolves an alert: it resolves itself
 * when its item is done. The person's own absence, with the colleague who covers it, is recorded here too.
 */
export function RemindersPanel() {
  const data = useResource<AlertList>(ALERTS);
  const go = useOpen();
  const [error, setError] = useState("");
  const list = data.data;
  const groups = groupAlerts(list?.items ?? []);
  const markRead = async (body: { ids?: string[]; all?: boolean }) => {
    setError("");
    try {
      await send(`${ALERTS}/read`, "POST", body);
      data.reload();
    } catch (reason) {
      setError(errorText(reason, "That could not be marked read."));
    }
  };
  const count = list?.items.length ?? 0;
  return (
    <Panel
      eyebrow="Reminders and escalations"
      title={
        !list
          ? "Reading your reminders…"
          : count
            ? `${count} ${count === 1 ? "reminder" : "reminders"} for you${list.unread ? `, ${list.unread} unread` : ""}`
            : "Nothing due soon or overdue for you"
      }
      source={data}
      className="uw-rm-panel"
      action={
        list?.unread ? (
          <button type="button" className="ac-link" onClick={() => void markRead({ all: true })}>
            Mark all read
          </button>
        ) : undefined
      }
    >
      {groups.urgent.length > 0 && (
        <ul className="uw-rm-list" aria-label="Escalations and overdue items">
          {groups.urgent.map((item) => (
            <AlertRow
              key={item.id}
              item={item}
              onOpen={() => go(item.opens)}
              onRead={() => void markRead({ ids: item.ids })}
            />
          ))}
        </ul>
      )}
      {groups.soon.length > 0 && (
        <ul className="uw-rm-soon" aria-label="Due soon">
          {groups.soon.map((group) => (
            <li key={group.category}>
              <ToneBadge tone="warning" label={`${group.items.length} due soon`} />
              <span>
                <strong>{group.label}</strong>:{" "}
                {group.items
                  .slice(0, 4)
                  .map((item) => item.ref || item.title)
                  .join(", ")}
                {group.items.length > 4 ? ` and ${group.items.length - 4} more` : ""}; the first{" "}
                {hoursText(
                  group.items.reduce((soonest, item) => (item.hours_left < soonest.hours_left ? item : soonest)),
                )}
              </span>
              <button type="button" className="ac-secondary" onClick={() => go(group.items[0].opens)}>
                Open <ChevronRight size={14} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {list && <AwayControl list={list} onChanged={data.reload} />}
      <InlineError text={error} />
    </Panel>
  );
}

function AlertRow({ item, onOpen, onRead }: { item: Alert; onOpen: () => void; onRead: () => void }) {
  return (
    <li className={`uw-rm-item${item.read ? "" : " unread"}`}>
      <span className={`uw-cr-rail tone-${alertTone(item)}`} aria-hidden="true" />
      <div className="uw-rm-body">
        <div className="uw-cr-head">
          <ToneBadge
            tone={alertTone(item)}
            label={item.tier === "ESCALATION" ? "Escalated to you" : item.state_label}
          />
          <strong>{item.ref}</strong>
          <span className="ac-muted">{item.category_label}</span>
        </div>
        <p className="uw-cr-text">{item.title}</p>
        <p className="uw-cr-meta">
          Due {item.due_label ?? formatDate(item.due_at)} ({hoursText(item)}). {item.reason_label}.
          {item.owner && item.reason !== "OWNER" ? ` Owner: ${item.owner}.` : ""}
        </p>
      </div>
      <div className="uw-cr-actions">
        <button type="button" className="ac-secondary" onClick={onOpen}>
          Open <ChevronRight size={14} aria-hidden="true" />
        </button>
        {!item.read && (
          <button type="button" className="ac-link" onClick={onRead} aria-label={`Mark ${item.ref ?? "it"} read`}>
            Mark read
          </button>
        )}
      </div>
    </li>
  );
}

const isoDay = (value: Date) => value.toISOString().slice(0, 10);

/** The person's own absence: from, to and the colleague who covers it (who gains no signing right). */
export function AwayControl({ list, onChanged }: { list: AlertList; onChanged: () => void }) {
  const { session } = useWorkspace();
  const me = session?.user_id;
  const today = isoDay(new Date());
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ starts_on: today, ends_on: today, backup_id: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mine = list.absences.filter((item) => item.user_id === me);
  const covering = list.absences.filter((item) => item.backup_id === me);
  const problem = absenceProblem(form, today);
  const run = async (path: string, body?: unknown) => {
    setBusy(true);
    setError("");
    try {
      await send(path, "POST", body);
      setOpen(false);
      onChanged();
    } catch (reason) {
      setError(errorText(reason, "The absence was not recorded."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="uw-rm-away">
      {covering.map((item) => (
        <p key={item.id} className="uw-rm-cover">
          <CalendarOff size={15} aria-hidden="true" /> You cover for <strong>{item.user_name}</strong> until{" "}
          {formatDate(item.ends_on)}: their reminders and escalations come to you; their items stay theirs.
          {item.note ? ` ${item.note}` : ""}
        </p>
      ))}
      {mine.map((item) => (
        <p key={item.id} className="uw-rm-cover">
          <CalendarOff size={15} aria-hidden="true" /> You are away {formatDate(item.starts_on)} to{" "}
          {formatDate(item.ends_on)}; <strong>{item.backup_name}</strong> covers for you.{" "}
          <button
            type="button"
            className="ac-link"
            disabled={busy}
            onClick={() => void run(`${OVERSIGHT}/absences/${item.id}/cancel`)}
          >
            I am back
          </button>
        </p>
      ))}
      {!mine.length && !open && (
        <button type="button" className="ac-secondary" onClick={() => setOpen(true)}>
          <CalendarOff size={15} aria-hidden="true" /> I will be away
        </button>
      )}
      {open && (
        <form
          className="uw-rm-form"
          aria-label="Record an absence"
          onSubmit={(event) => {
            event.preventDefault();
            if (!problem) void run(`${OVERSIGHT}/absences`, form);
          }}
        >
          <div className="ca-form-grid">
            <label className="ca-field">
              First day
              <input
                type="date"
                value={form.starts_on}
                onChange={(e) => setForm({ ...form, starts_on: e.target.value })}
              />
            </label>
            <label className="ca-field">
              Last day
              <input type="date" value={form.ends_on} onChange={(e) => setForm({ ...form, ends_on: e.target.value })} />
            </label>
            <label className="ca-field">
              Who covers for you
              <select value={form.backup_id} onChange={(e) => setForm({ ...form, backup_id: e.target.value })}>
                <option value="">Choose a colleague</option>
                {list.people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Note (optional)
              <input value={form.note} maxLength={300} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </label>
          </div>
          {!list.people.length && (
            <p className="ac-muted">
              Nobody else can cover yet: invite a colleague first (Getting started, Your team).
            </p>
          )}
          <p className="ac-muted">
            Your backup receives your reminders and escalations while you are away. Your items stay yours, and your
            backup gains no right to sign for you.
          </p>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !!problem}>
              {busy ? "Recording…" : "Record my absence"}
            </button>
            <button type="button" className="ac-link" onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
          {problem && <p className="ac-muted">{problem}</p>}
        </form>
      )}
      <InlineError text={error} />
    </div>
  );
}

/** The header's bell: how many reminders and escalations are unread; opens My Work. */
export function AlertsBell({ onOpen }: { onOpen: () => void }) {
  const data = useResource<AlertList>(ALERTS);
  const unread = data.data?.unread ?? 0;
  const escalations = data.data?.escalations ?? 0;
  const label = unread
    ? `${unread} unread reminders${escalations ? `, ${escalations} escalated to you` : ""}: open My Work`
    : "Reminders and escalations: open My Work";
  return (
    <button type="button" className="ac-secondary uw-rm-bell" onClick={onOpen} aria-label={label} title={label}>
      <BellRing size={16} aria-hidden="true" />
      {unread > 0 && <span className={`uw-rm-count${escalations ? " tone-critical" : ""}`}>{unread}</span>}
    </button>
  );
}
