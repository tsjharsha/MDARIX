import { useEffect, useState } from "react";

const ACKNOWLEDGED_KEY = "mdarix-compliance-consent";
// "Dismiss" hides the notice for this browser session only; "Acknowledge" hides it for good on this device.
const DISMISSED_KEY = "mdarix-compliance-notice-dismissed";

type Stores = { local: Pick<Storage, "getItem"> | null; session: Pick<Storage, "getItem"> | null };

/** Whether the notice is due: not acknowledged on this device and not dismissed in this browser session. Storage that
 * cannot be read shows the notice (it is better shown again than never). */
export function noticeDue(stores: Stores): boolean {
  const read = (store: Pick<Storage, "getItem"> | null, key: string) => {
    try {
      return store?.getItem(key) ?? null;
    } catch {
      return null;
    }
  };
  return read(stores.local, ACKNOWLEDGED_KEY) !== "accepted" && read(stores.session, DISMISSED_KEY) !== "1";
}

const store = (name: "localStorage" | "sessionStorage"): Storage | null => {
  try {
    return window[name];
  } catch {
    return null;
  }
};

const remember = (name: "localStorage" | "sessionStorage", key: string, value: string) => {
  try {
    store(name)?.setItem(key, value);
  } catch {
    // Without storage the notice returns on the next page load; nothing else depends on it.
  }
};

export function ConsentBanner() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    setVisible(noticeDue({ local: store("localStorage"), session: store("sessionStorage") }));
  }, []);
  if (!visible) return null;
  const accept = () => {
    remember("localStorage", ACKNOWLEDGED_KEY, "accepted");
    setVisible(false);
  };
  const dismiss = () => {
    remember("sessionStorage", DISMISSED_KEY, "1");
    setVisible(false);
  };
  return (
    <section className="consent-banner" role="dialog" aria-label="Privacy and data-use notice">
      <div>
        <strong>Privacy and data-use notice</strong>
        <p>
          MDARIX uses one essential sign-in cookie and keeps an audit record of actions in your organization&apos;s
          workspace. Please do not enter patient-identifiable information. MDARIX is not certified for GDPR, HIPAA or
          other regulations; review your organization&apos;s obligations before entering regulated data. Read the{" "}
          <a href="/privacy" target="_blank" rel="noopener">
            Privacy Policy
          </a>
          .
        </p>
      </div>
      <div className="consent-actions">
        <button className="secondary-action" onClick={dismiss}>
          Dismiss
        </button>
        <button className="primary-action" onClick={accept}>
          Acknowledge
        </button>
      </div>
    </section>
  );
}
