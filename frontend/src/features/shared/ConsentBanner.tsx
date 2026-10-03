import { useEffect, useState } from "react";

export function ConsentBanner() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    setVisible(localStorage.getItem("mdarix-compliance-consent") !== "accepted");
  }, []);
  if (!visible) return null;
  const accept = () => {
    localStorage.setItem("mdarix-compliance-consent", "accepted");
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
        <button className="secondary-action" onClick={() => setVisible(false)}>
          Dismiss
        </button>
        <button className="primary-action" onClick={accept}>
          Acknowledge
        </button>
      </div>
    </section>
  );
}
