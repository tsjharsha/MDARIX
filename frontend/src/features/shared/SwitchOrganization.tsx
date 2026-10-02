import { useEffect, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { requestJson } from "../../app/apiClient";

/**
 * Shown only to someone whose email also has an account in another organization. Each organization is a separate
 * account (own password, role and data), so switching signs out here and signs in there.
 */
export function SwitchOrganization() {
  const [session, setSession] = useState<{ email?: string; other_organizations?: number } | null>(null);
  useEffect(() => {
    requestJson<{ email?: string; other_organizations?: number }>("/api/v1/auth/session", { retries: 0 })
      .then(setSession)
      .catch(() => setSession(null));
  }, []);
  if (!session?.other_organizations) return null;
  const switchOrganization = async () => {
    await requestJson("/api/v1/auth/signout", { method: "POST", retries: 0 }).catch(() => undefined);
    try {
      sessionStorage.clear();
    } catch {
      // Storage may be unavailable; nothing tenant-scoped is kept there then.
    }
    window.location.replace(`/signin?email=${encodeURIComponent(session.email ?? "")}`);
  };
  return (
    <button type="button" className="ac-secondary" onClick={() => void switchOrganization()}>
      <ArrowLeftRight size={16} aria-hidden="true" /> <span className="ac-hide-sm">Switch organization</span>
    </button>
  );
}
