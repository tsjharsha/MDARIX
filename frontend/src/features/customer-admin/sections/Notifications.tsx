import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { useConsole } from "../context";
import { LifecycleBadge } from "./Access";
import { Table, listOf, send, useResource } from "../shared";

const RECIPIENT_TYPES = ["CUSTOMER_ADMIN", "BILLING_CONTACT", "BUSINESS_CONTACT", "ACCOUNT_OWNER"] as const;

export function NotificationsSection() {
  const { confirm } = useConsole();
  const preferences = useResource<any>("/api/v1/admin/notifications/preferences");
  const policy = listOf(preferences.data?.policies)[0];
  const [thresholds, setThresholds] = useState("60, 30, 7");
  const [timezone, setTimezone] = useState("UTC");
  const [types, setTypes] = useState<string[]>(["CUSTOMER_ADMIN"]);
  const [recipient, setRecipient] = useState({ recipient_type: "BILLING_CONTACT", name: "", email: "" });

  useEffect(() => {
    if (!policy) return;
    setThresholds(listOf(policy.thresholds).join(", ") || "60, 30, 7");
    setTimezone(policy.timezone ?? "UTC");
    setTypes(listOf(policy.recipient_types).length ? listOf(policy.recipient_types) : ["CUSTOMER_ADMIN"]);
  }, [policy?.id]);

  const parsedThresholds = thresholds
    .split(",")
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isInteger(value) && value >= 0);

  return (
    <>
      <Panel eyebrow="Notifications" title="Subscription reminders" state={preferences.state} error={preferences.error}>
        <form
          className="ca-form"
          onSubmit={(event) => {
            event.preventDefault();
            confirm({
              title: "Save reminder settings?",
              body: `Reminders are sent ${parsedThresholds.join(", ")} days before your subscription ends, to: ${types
                .map(titleCase)
                .join(", ")}.`,
              confirmLabel: "Save",
              reason: { label: "Reason for the change", min: 10 },
              done: "Reminder settings saved.",
              run: async (reason) => {
                await send("/api/v1/admin/notifications/preferences", "PUT", {
                  thresholds: [...new Set(parsedThresholds)].sort((a, b) => b - a),
                  timezone,
                  recipient_types: types,
                  reason,
                });
                preferences.reload();
              },
            });
          }}
        >
          <div className="ca-form-grid">
            <label className="ca-field">
              Days before expiry
              <input
                required
                value={thresholds}
                onChange={(event) => setThresholds(event.target.value)}
                placeholder="60, 30, 7"
              />
            </label>
            <label className="ca-field">
              Time zone
              <input required value={timezone} onChange={(event) => setTimezone(event.target.value)} />
            </label>
          </div>
          <fieldset className="ca-fieldset">
            <legend>Send reminders to</legend>
            {RECIPIENT_TYPES.map((type) => (
              <label className="ca-check" key={type}>
                <input
                  type="checkbox"
                  checked={types.includes(type)}
                  onChange={(event) =>
                    setTypes((current) =>
                      event.target.checked ? [...current, type] : current.filter((value) => value !== type),
                    )
                  }
                />
                {titleCase(type)}
              </label>
            ))}
          </fieldset>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={!types.length || !parsedThresholds.length}>
              Save reminder settings
            </button>
          </div>
        </form>
      </Panel>

      <Panel eyebrow="Notifications" title="Contacts" state={preferences.state} error={preferences.error}>
        <Table
          caption="Notification contacts"
          rows={listOf(preferences.data?.recipients)}
          rowKey={(row) => row.id}
          empty={{ title: "No contacts yet", detail: "Add billing or business contacts who should receive reminders." }}
          columns={[
            { key: "type", label: "Type", render: (row) => titleCase(row.recipient_type ?? "") },
            { key: "contact", label: "Contact", render: (row) => row.contact_id ?? "—" },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
          ]}
        />
        {policy ? (
          <form
            className="ca-form"
            onSubmit={(event) => {
              event.preventDefault();
              confirm({
                title: `Add ${recipient.name} as a contact?`,
                body: `${recipient.email} will receive subscription reminders as ${titleCase(recipient.recipient_type)}.`,
                confirmLabel: "Add contact",
                reason: { label: "Reason", min: 10 },
                done: "Contact added.",
                run: async (reason) => {
                  await send("/api/v1/admin/notifications/recipients", "POST", { ...recipient, reason });
                  setRecipient({ ...recipient, name: "", email: "" });
                  preferences.reload();
                },
              });
            }}
          >
            <div className="ca-form-grid">
              <label className="ca-field">
                Type
                <select
                  value={recipient.recipient_type}
                  onChange={(event) => setRecipient({ ...recipient, recipient_type: event.target.value })}
                >
                  {RECIPIENT_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {titleCase(type)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ca-field">
                Name
                <input
                  required
                  value={recipient.name}
                  onChange={(event) => setRecipient({ ...recipient, name: event.target.value })}
                />
              </label>
              <label className="ca-field">
                Email
                <input
                  required
                  type="email"
                  value={recipient.email}
                  onChange={(event) => setRecipient({ ...recipient, email: event.target.value })}
                />
              </label>
            </div>
            <div className="ca-action-row">
              <button type="submit" className="ac-secondary">
                <Plus size={16} /> Add contact
              </button>
            </div>
          </form>
        ) : (
          <p className="ac-muted">Save the reminder settings first; contacts are attached to them.</p>
        )}
      </Panel>
    </>
  );
}
