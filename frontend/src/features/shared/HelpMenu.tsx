import { useContext, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Bug,
  CircleHelp,
  LifeBuoy,
  ListChecks,
  NotebookText,
  PlayCircle,
  ShieldCheck,
  Signpost,
} from "lucide-react";
import { useSiteInfo } from "../../site/legal";
import { ReportProblemDialog } from "./ReportProblem";
import { TRIAL_GUIDE_PATH } from "../help/trialGuide";
import { NEXT_STEPS_HELP, NEXT_STEPS_LINK } from "../help/trialNextSteps";
import { WorkspaceContext } from "../workspace/workspaceContext";
import { USER_GUIDE_PATH } from "../help/userGuide";

/** The website's video series (frontend/src/site/videos.tsx), opened beside the product. */
export const VIDEOS_PATH = "/videos";

/**
 * Help in every signed-in screen: getting started (during a trial), the step-by-step user guide (every screen), the
 * free trial user guide (the trial's seven steps, during a trial), the website's short videos, "Talk to us about the
 * next step", which opens Next steps from trial to pilot (during a trial, UX-25), the pilot guide, the support
 * address, a "report a problem" form that reaches the MDARIX team (with an email fallback), and the security and
 * privacy pages. The support address comes from the server configuration (backend/app/site_info.py).
 */
export function HelpMenu({
  onGettingStarted,
  more = [],
}: {
  onGettingStarted?: () => void;
  /** Screens the new navigation reaches from Help (0.10.68): Look ahead and Share feedback. */
  more?: Array<{ label: string; detail: string; onSelect: () => void }>;
}) {
  const [open, setOpen] = useState(false);
  const [reporting, setReporting] = useState(false);
  const info = useSiteInfo();
  // In a trial workspace: Next steps, from trial to pilot (UserWorkspace says whether it is a trial).
  const workspace = useContext(WorkspaceContext);
  const onNextSteps = workspace?.isTrial ? () => workspace.open("Next steps") : undefined;
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
  return (
    <div className="help-menu" ref={root}>
      <button
        type="button"
        className="ac-secondary"
        aria-label={open ? "Close help menu" : "Open help menu"}
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
            <a
              href={workspace?.navigation === "new" ? `${USER_GUIDE_PATH}?navigation=new` : USER_GUIDE_PATH}
              target="_blank"
              rel="noopener"
            >
              <ListChecks size={15} aria-hidden="true" />
              <span className="help-menu-item">
                Step-by-step user guide
                <small>Every screen, task by task</small>
              </span>
            </a>
          </li>
          {onGettingStarted && (
            <li>
              <a href={TRIAL_GUIDE_PATH} target="_blank" rel="noopener">
                <NotebookText size={15} aria-hidden="true" />
                <span className="help-menu-item">
                  Free trial user guide
                  <small>The trial in 7 steps</small>
                </span>
              </a>
            </li>
          )}
          <li>
            <a href={VIDEOS_PATH} target="_blank" rel="noopener">
              <PlayCircle size={15} aria-hidden="true" />
              <span className="help-menu-item">
                Watch the videos
                <small>The free trial in short videos, step by step</small>
              </span>
            </a>
          </li>
          {more.map((item) => (
            <li key={item.label}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  item.onSelect();
                }}
              >
                <Signpost size={15} aria-hidden="true" />
                <span className="help-menu-item">
                  {item.label}
                  <small>{item.detail}</small>
                </span>
              </button>
            </li>
          ))}
          {onNextSteps && (
            <li>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onNextSteps();
                }}
              >
                <Signpost size={15} aria-hidden="true" />
                <span className="help-menu-item">
                  {NEXT_STEPS_HELP}
                  <small>{NEXT_STEPS_LINK}</small>
                </span>
              </button>
            </li>
          )}
          <li>
            <a href="/help/pilot-guide" target="_blank" rel="noopener">
              <NotebookText size={15} aria-hidden="true" /> Pilot guide
            </a>
          </li>
          <li>
            <a href={support ? `mailto:${support}` : "/contact"} target={support ? undefined : "_blank"} rel="noopener">
              <LifeBuoy size={15} aria-hidden="true" /> Contact support{support ? ` (${support})` : ""}
            </a>
          </li>
          <li>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setReporting(true);
              }}
            >
              <Bug size={15} aria-hidden="true" /> Report a problem
            </button>
          </li>
          <li>
            <a href="/security" target="_blank" rel="noopener">
              <ShieldCheck size={15} aria-hidden="true" /> Security and privacy
            </a>
          </li>
        </ul>
      )}
      {reporting && <ReportProblemDialog supportEmail={support ?? undefined} onClose={() => setReporting(false)} />}
    </div>
  );
}
