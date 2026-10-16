import { useEffect, useRef, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import {
  BUILT_VERSION,
  CHECK_EVERY_MS,
  MIN_GAP_MS,
  checkDue,
  fetchServerVersion,
  isNewerVersion,
  versionCheckEnabled,
} from "./appVersion";

/** The newer version the server runs, once one is seen (appVersion.ts); null otherwise. */
function useNewerServerVersion(): string | null {
  const [newer, setNewer] = useState<string | null>(null);
  const lastCheck = useRef(Date.now());
  useEffect(() => {
    const automated = typeof navigator !== "undefined" && navigator.webdriver === true;
    if (!versionCheckEnabled(BUILT_VERSION, import.meta.env.MODE, automated)) return;
    let current = true;
    let busy = false;
    const check = async (gap: number) => {
      const visible = document.visibilityState !== "hidden";
      const online = navigator.onLine !== false;
      if (busy || !checkDue(Date.now(), lastCheck.current, gap, visible, online)) return;
      busy = true;
      lastCheck.current = Date.now();
      const server = await fetchServerVersion();
      busy = false;
      if (current && server && isNewerVersion(server, BUILT_VERSION)) setNewer(server);
    };
    // The interval allows a little slack, so a timer that fires a moment early still asks.
    const timer = window.setInterval(() => void check(CHECK_EVERY_MS - 1_000), CHECK_EVERY_MS);
    const onShown = () => {
      if (document.visibilityState === "visible") void check(MIN_GAP_MS);
    };
    document.addEventListener("visibilitychange", onShown);
    return () => {
      current = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onShown);
    };
  }, []);
  return newer;
}

/** The notice itself (exported so its test can render it). */
export function NewVersionNoticeView({ onReload, onDismiss }: { onReload: () => void; onDismiss: () => void }) {
  return (
    <div className="new-version-notice">
      <RefreshCw size={16} aria-hidden="true" />
      <span>A new version of MDARIX is available.</span>
      <button type="button" className="new-version-reload" onClick={onReload}>
        Reload
      </button>
      <button type="button" className="new-version-dismiss" aria-label="Dismiss for now" onClick={onDismiss}>
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  );
}

/**
 * Says, without interrupting, that a newer MDARIX is deployed than the one this tab runs, with a button to reload.
 * Never reloads by itself. Dismissed, it stays away until the server reports a newer version again.
 */
export function NewVersionNotice() {
  const newer = useNewerServerVersion();
  const [dismissed, setDismissed] = useState<string | null>(null);
  const shown = newer !== null && newer !== dismissed;
  return (
    <div className="new-version-region" role="status" aria-live="polite">
      {shown && (
        <NewVersionNoticeView onReload={() => window.location.reload()} onDismiss={() => setDismissed(newer)} />
      )}
    </div>
  );
}
