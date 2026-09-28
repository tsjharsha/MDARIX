import React, { useEffect, useState } from "react";

export function ConsentBanner() {
  const [visible, setVisible] = useState(false);
  useEffect(() => { setVisible(localStorage.getItem("mdarix-compliance-consent") !== "accepted"); }, []);
  if (!visible) return null;
  const accept = () => { localStorage.setItem("mdarix-compliance-consent", "accepted"); setVisible(false); };
  return <section className="consent-banner" role="dialog" aria-label="Privacy and data-use notice"><div><strong>Privacy and data-use notice</strong><p>MDARIX uses essential session storage and tenant-scoped audit records to operate this workspace. This notice does not represent a GDPR, HIPAA, or other compliance certification; review your organization&apos;s obligations before entering regulated data.</p></div><div className="consent-actions"><button className="secondary-action" onClick={() => setVisible(false)}>Dismiss</button><button className="primary-action" onClick={accept}>Acknowledge</button></div></section>;
}
