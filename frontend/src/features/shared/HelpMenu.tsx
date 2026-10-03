import { useEffect, useRef, useState } from "react";
import { BookOpen, Bug, CircleHelp, LifeBuoy, ShieldCheck } from "lucide-react";
import { useSiteInfo } from "../../site/legal";

/**
 * Help in every signed-in screen: getting started (during a trial), the support address, a "report a problem" email
 * that carries the page and time (no personal data), and the security and privacy pages. The support address comes
 * from the server configuration (backend/app/site_info.py).
 */
export function HelpMenu({ onGettingStarted }: { onGettingStarted?: () => void }) {
  const [open, setOpen] = useState(false);
  const info = useSiteInfo();
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node))
        setOpen(false);
    };
    window.addEventListener("keydown", close);
    window.addEventListener("pointerdown", close);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("pointerdown", close);
    };
  }, [open]);
  const support = info?.support_email;
  const report = support
    ? `mailto:${support}?subject=${encodeURIComponent("MDARIX problem report")}&body=${encodeURIComponent(
        `What happened:\n\nWhat you expected:\n\nPage: ${window.location.pathname}\nTime: ${new Date().toISOString()}\n`,
      )}`
    : "/contact";
  return (
    <div className="help-menu" ref={root}>
      <button
        type="button"
        className="ac-secondary"
        aria-expanded={open}
        aria-controls="help-menu-list"
        onClick={() => setOpen((value) => !value)}
      >
        <CircleHelp size={16} aria-hidden="true" /> <span className="ac-hide-sm">Help</span>
      </button>
      {open && (
        <ul id="help-menu-list" className="help-menu-list" aria-label="Help">
          {onGettingStarted && (
            <li>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onGettingStarted();
                }}
              >
                <BookOpen size={15} aria-hidden="true" /> Getting started and import templates
              </button>
            </li>
          )}
          <li>
            <a href={support ? `mailto:${support}` : "/contact"} target={support ? undefined : "_blank"} rel="noopener">
              <LifeBuoy size={15} aria-hidden="true" /> Contact support{support ? ` (${support})` : ""}
            </a>
          </li>
          <li>
            <a href={report} target={support ? undefined : "_blank"} rel="noopener">
              <Bug size={15} aria-hidden="true" /> Report a problem
            </a>
          </li>
          <li>
            <a href="/security" target="_blank" rel="noopener">
              <ShieldCheck size={15} aria-hidden="true" /> Security and privacy
            </a>
          </li>
        </ul>
      )}
    </div>
  );
}
