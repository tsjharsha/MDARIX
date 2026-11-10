import { useEffect, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { useConsole } from "../context";
import { formatDate, send, useResource } from "../shared";

// B7b (spec 4.3): the organisation's intake address, for the Customer Administrator. Flat panel (G-2).
export type IntakeSettings = {
  address: string | null;
  on: boolean;
  trial: boolean;
  old_addresses?: { address: string; until: string }[];
  allowed_domains: string[];
  daily_limit: number;
};

const SETTINGS = "/api/v1/email-intake/settings";

/** "a.example, b.example" (or one per line) as the list the API takes. */
export const domainList = (text: string) =>
  text
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);

export function EmailIntakePanel() {
  const { confirm, notify } = useConsole();
  const settings = useResource<IntakeSettings>(SETTINGS);
  const data = settings.data;
  const [domains, setDomains] = useState(() => data?.allowed_domains.join(", ") ?? "");
  const [limit, setLimit] = useState(() => data?.daily_limit ?? 200);
  useEffect(() => {
    if (!data) return;
    setDomains(data.allowed_domains.join(", "));
    setLimit(data.daily_limit);
  }, [data]);

  const save = (on: boolean) =>
    confirm({
      title: on === data?.on ? "Save the e-mail intake settings?" : on ? "Turn e-mail intake on?" : "Turn it off?",
      body: on
        ? "Messages sent to the address appear in Cases › E-mail to check for a person to decide. No reply is ever sent to the sender."
        : "Messages sent to the address are refused while it is off. Messages already received stay where they are.",
      confirmLabel: "Save",
      done: "E-mail intake settings saved.",
      run: async () => {
        await send(SETTINGS, "PUT", { on, allowed_domains: domainList(domains), daily_limit: limit });
        settings.reload();
      },
    });

  return (
    <Panel eyebrow="Organization" title="E-mail intake" source={settings}>
      {data?.trial ? (
        <p className="ac-muted">
          A free trial has no real intake address. The SAMPLE e-mail in Cases › First contact shows how a message
          becomes a case.
        </p>
      ) : data ? (
        <>
          <dl className="ca-facts">
            <div>
              <dt>Address</dt>
              <dd>
                <code>{data.address ?? "Made when you turn it on"}</code>{" "}
                {data.address && (
                  <button
                    type="button"
                    className="ac-secondary"
                    onClick={() =>
                      navigator.clipboard
                        ?.writeText(data.address ?? "")
                        .then(() => notify?.("Address copied.", "good"))
                        .catch(() => undefined)
                    }
                  >
                    <Copy size={14} aria-hidden="true" /> Copy
                  </button>
                )}
              </dd>
            </div>
            <div>
              <dt>State</dt>
              <dd>{data.on ? "On: messages are accepted" : "Off: messages are refused"}</dd>
            </div>
            {(data.old_addresses ?? []).map((old) => (
              <div key={old.address}>
                <dt>Old address</dt>
                <dd>
                  <code>{old.address}</code> still works until {formatDate(old.until)}
                </dd>
              </div>
            ))}
          </dl>
          <form
            className="ca-form"
            onSubmit={(event) => {
              event.preventDefault();
              save(data.on);
            }}
          >
            <div className="ca-form-grid">
              <label className="ca-field">
                Accept mail only from these sender domains (empty: from anyone)
                <input
                  value={domains}
                  placeholder="hospital.example, distributor.example"
                  onChange={(event) => setDomains(event.target.value)}
                />
              </label>
              <label className="ca-field">
                Messages a day, at most
                <input
                  type="number"
                  min={1}
                  max={5000}
                  required
                  value={limit}
                  onChange={(event) => setLimit(Number(event.target.value))}
                />
              </label>
            </div>
            <span className="ca-row-actions">
              <button type="submit" className="ac-secondary">
                Save
              </button>
              <button type="button" className="ac-primary" onClick={() => save(!data.on)}>
                {data.on ? "Turn off" : "Turn on"}
              </button>
              {data.address && (
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() =>
                    confirm({
                      title: "Rotate the address?",
                      body: "A new address is made. The old one keeps working for 30 days, then mail sent to it is refused. Update your forwarding rule to the new address.",
                      confirmLabel: "Rotate",
                      danger: true,
                      done: "A new address was made.",
                      run: async () => {
                        await send(`${SETTINGS}/rotate`, "POST");
                        settings.reload();
                      },
                    })
                  }
                >
                  <RefreshCw size={14} aria-hidden="true" /> Rotate
                </button>
              )}
            </span>
          </form>
          <p className="ac-muted">
            To send a complaints mailbox here, set it to forward to this address. Many mail systems block forwarding to
            outside addresses until an administrator allows it, and some first send a confirmation message: it appears
            in Cases › E-mail to check as a setup message. Rotate the address if it attracts spam.
          </p>
        </>
      ) : null}
    </Panel>
  );
}
