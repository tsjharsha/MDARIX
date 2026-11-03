import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Lock, LogOut, Search, Settings2, Upload, UserRound } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { recordPlace } from "../../app/linkTable";
import { shortRoles } from "../../app/roles";
import { signOut } from "../shared/session";
import { SwitchOrganization } from "../shared/SwitchOrganization";
import { IMPORTED_SOURCE, SAMPLE_SOURCE, complaintListTab } from "./complaintList";
import { canImportOwnData, type SessionContext, type WorkspaceSection } from "./workspaceContext";

/*
 * The new navigation's shell (0.10.73, Release C part C1; the approved design `mdarix-hybrid-mockup.html`): a top bar
 * with the organization, one search, "Viewing as [persona]", the bell, help and the avatar; then a tab bar with only
 * the persona's destinations. The persona changes what a person sees, never what they may sign: every action keeps
 * the server's own check, and the persona never reaches the server as a permission.
 */

/** A persona as the session context sends it (access_control/personas.py WORKSPACE_PERSONAS). */
export type PersonaOption = { code: string; label: string; sub: string; tabs: string[] };

/** Each tab of the bar: its name and the screen it opens (My work is Home). */
export const PERSONA_TABS: Record<string, { label: string; section: WorkspaceSection }> = {
  // A trial's guide, left of Home, for every persona (0.10.80; trialTabs). Never a persona's own tab.
  start: { label: "Getting started", section: "Getting started" },
  home: { label: "Home", section: "My Work" },
  complaints: { label: "Complaints", section: "Complaints" },
  trees: { label: "Decision trees", section: "Decision trees" },
  reports: { label: "Reports", section: "Reports" },
  investigations: { label: "Investigations", section: "Investigations" },
  trends: { label: "Trends", section: "Trends" },
  records: { label: "Records", section: "Records" },
  team: { label: "Team", section: "Team" },
};

/** The tab a screen belongs to: one complaint's page is the Complaints tab's; Settings or Account none. */
export const tabOfSection = (section: string): string | null =>
  section === "Complaint"
    ? "complaints"
    : (Object.entries(PERSONA_TABS).find(([, tab]) => tab.section === section)?.[0] ?? null);

/** The persona's tabs the server lets this person open, in the bar's order. */
export const visibleTabs = (tabs: readonly string[], allowed: readonly string[]): string[] =>
  Object.keys(PERSONA_TABS).filter((key) => tabs.includes(key) && allowed.includes(PERSONA_TABS[key].section));

/** A trial's tabs: Getting started first, whatever the persona (0.10.80); a pilot's are the persona's. */
export const trialTabs = (tabs: readonly string[], isTrial: boolean): readonly string[] =>
  isTrial ? ["start", ...tabs] : tabs;

/** Each persona's mark: two letters on its own colour (the design system's fills under white text). */
const PERSONA_COLOR: Record<string, string> = {
  admin: "var(--ms-teal)",
  quality: "var(--ms-info)",
  regulatory: "var(--ms-ai)",
  handler: "var(--ms-warn)",
  investigator: "var(--ms-good)",
  risk: "var(--ms-teal-dark)",
  decision: "var(--ms-navy)",
  executive: "var(--ms-muted)",
};

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

export function PersonaDot({ code, label, size = 22 }: { code: string; label: string; size?: number }) {
  return (
    <span
      className="uw-persona-dot"
      style={{ background: PERSONA_COLOR[code] ?? "var(--ms-muted)", width: size, height: size }}
      aria-hidden="true"
    >
      {initials(label)}
    </span>
  );
}

/** Close a pop-up on Escape or a click outside it. */
function useDismiss(open: boolean, close: () => void, root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const handler = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node))
        close();
    };
    window.addEventListener("keydown", handler);
    window.addEventListener("pointerdown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      window.removeEventListener("pointerdown", handler);
    };
  }, [open]);
}

/**
 * "Viewing as [persona ▾]". The trial owner chooses; the server keeps the choice for their next sign-in. Anyone else
 * sees their persona with a lock: it is their real role, set by the trial owner (or, in a pilot, by their role).
 */
export function PersonaSwitch({
  persona,
  options,
  locked,
  onChoose,
}: {
  persona: string;
  options: readonly PersonaOption[];
  locked: boolean;
  onChoose: (code: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useDismiss(open, () => setOpen(false), root);
  const current = options.find((item) => item.code === persona);
  const label = current?.label ?? persona;
  if (locked)
    return (
      <div className="uw-persona">
        <span className="uw-persona-btn is-locked" title="Your persona is your role, set by the trial owner">
          <PersonaDot code={persona} label={label} />
          <span>{label}</span>
          <small className="uw-persona-hint">· set by the trial owner</small>
          <Lock size={14} aria-label="Locked" />
        </span>
      </div>
    );
  return (
    <div className="uw-persona" ref={root}>
      <button
        type="button"
        className="uw-persona-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="uw-persona-menu"
        onClick={() => setOpen((value) => !value)}
      >
        <PersonaDot code={persona} label={label} />
        <small className="uw-persona-hint">Viewing as</small>
        <span>{label}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div className="uw-pop uw-persona-menu" id="uw-persona-menu" role="menu" aria-label="View MDARIX as">
          <p className="uw-pop-title">View MDARIX as</p>
          {options.map((item) => (
            <button
              key={item.code}
              type="button"
              role="menuitemradio"
              aria-checked={item.code === persona}
              className="uw-pop-option"
              onClick={() => {
                setOpen(false);
                if (item.code !== persona) onChoose(item.code);
              }}
            >
              <PersonaDot code={item.code} label={item.label} />
              <span>
                <b>{item.label}</b>
                <small>{item.sub}</small>
              </span>
              {item.code === persona && <Check size={15} aria-hidden="true" />}
            </button>
          ))}
          <p className="uw-pop-note">
            Changes what you see, not what you may sign. Signing follows your own role. MDARIX remembers your choice for
            your next sign-in.
          </p>
        </div>
      )}
    </div>
  );
}

type Hit = { key: string; kind: "Complaint" | "Product" | "Report"; title: string; detail: string; go: () => void };

/**
 * One search across complaints, products and reports (the server's own reads: the complaint list, the product search
 * and the report list). A complaint opens its page, a report its panel, a product the complaints about it.
 */
export function GlobalSearch({ open }: { open: (section: WorkspaceSection, tab?: string) => void }) {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [shown, setShown] = useState(false);
  // On a phone the search is an icon that opens the same search as a bar under the top bar (0.10.74, C2).
  const [phoneOpen, setPhoneOpen] = useState(false);
  const root = useRef<HTMLFormElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useDismiss(shown, () => setShown(false), root);
  useDismiss(phoneOpen, () => setPhoneOpen(false), root);
  useEffect(() => {
    if (phoneOpen) input.current?.focus();
  }, [phoneOpen]);
  useEffect(() => {
    const q = text.trim();
    if (q.length < 2) {
      setHits(null);
      return;
    }
    let live = true;
    const timer = window.setTimeout(() => {
      const term = encodeURIComponent(q);
      const go = (place: { section: string; tab?: string }) => () => {
        setShown(false);
        setPhoneOpen(false);
        setText("");
        open(place.section as WorkspaceSection, place.tab);
      };
      Promise.all([
        requestJson<any>(`/api/v1/complaints?q=${term}&page_size=5`).catch(() => null),
        requestJson<any>(`/api/v1/data-plane/search?q=${term}&limit=20`).catch(() => null),
        requestJson<any>("/api/v1/reports").catch(() => null),
      ]).then(([complaints, records, reports]) => {
        if (!live) return;
        const found: Hit[] = [];
        for (const row of (complaints?.items ?? complaints?.complaints ?? []) as any[]) {
          const ref = String(row.complaint_identifier ?? row.business_id ?? "");
          found.push({
            key: `c-${row.id}`,
            kind: "Complaint",
            title: ref,
            detail: String(row.description ?? "").slice(0, 90),
            go: go(recordPlace("complaint", ref, {}, "new")),
          });
        }
        for (const row of ((records?.records ?? []) as any[]).filter((item) => item.record_type === "product")) {
          found.push({
            key: `p-${row.id}`,
            kind: "Product",
            title: String(row.name ?? row.product_identifier),
            detail: String(row.product_identifier ?? ""),
            go: go({
              section: "Complaints",
              tab: complaintListTab({ productId: String(row.id) }).replace(/^[^?]*/, "All complaints"),
            }),
          });
        }
        const needle = q.toLowerCase();
        for (const row of reportHits(reports?.items ?? reports?.reports ?? [], needle)) {
          found.push({
            key: `r-${row.id}`,
            kind: "Report",
            title: String(row.form_title ?? row.title ?? "Authority report"),
            detail: String(row.complaint_ref ?? row.complaint ?? ""),
            go: go(recordPlace("report", String(row.id), {}, "new")),
          });
        }
        setHits(found.slice(0, 12));
        setShown(true);
      });
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [text]);
  return (
    <form
      className={`uw-search${phoneOpen ? " is-open" : ""}`}
      role="search"
      ref={root}
      onSubmit={(event) => {
        event.preventDefault();
        hits?.[0]?.go();
      }}
    >
      <button
        type="button"
        className="uw-search-toggle"
        aria-label="Open the search"
        aria-expanded={phoneOpen}
        onClick={() => setPhoneOpen((value) => !value)}
      >
        <Search size={18} aria-hidden="true" />
      </button>
      <Search size={16} aria-hidden="true" className="uw-search-icon" />
      <input
        ref={input}
        type="search"
        value={text}
        placeholder="Search complaints, products, reports"
        aria-label="Search complaints, products and reports"
        aria-controls="uw-search-results"
        onFocus={() => hits && setShown(true)}
        onChange={(event) => setText(event.target.value)}
      />
      {shown && hits && (
        <div className="uw-pop uw-search-results" id="uw-search-results" aria-live="polite">
          {hits.length ? (
            <ul>
              {hits.map((hit) => (
                <li key={hit.key}>
                  <button type="button" onClick={hit.go}>
                    <span className="uw-search-kind">{hit.kind}</span>
                    <span>
                      <b>{hit.title}</b>
                      {hit.detail && <small>{hit.detail}</small>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="uw-pop-note">Nothing found for “{text.trim()}”.</p>
          )}
        </div>
      )}
    </form>
  );
}

/** "Import your data" beside the trial's Sample data label (0.10.79): only in a trial whose organization imports, for a
 * person who may change records; it opens the trial's import page (0.10.80), as Help › Try your own data does. */
export const importOwnDataAction = (
  isTrial: boolean,
  session: SessionContext | null | undefined,
  open: (section: WorkspaceSection, tab?: string) => void,
) => (isTrial && canImportOwnData(session) ? () => open("Import your data") : undefined);

/** What the top bar says about a trial's data (0.10.80): the sample alone ("Sample data"), the sample and the imported
 * data side by side (a choice), or nothing once the sample is removed. Read from the server's trial status. */
export function trialDataBar(trial: { sample?: { complaints?: number }; own_data?: { complaints?: number } } | null) {
  const sample = (trial?.sample?.complaints ?? 0) > 0;
  const own = (trial?.own_data?.complaints ?? 0) > 0;
  return sample && own ? "choice" : sample ? "sample" : "none";
}

/** Where a person's data choice is kept: this browser, per organization and person (a view, never a record). */
const dataChoiceKey = (session: SessionContext | null | undefined) =>
  `mdarix.dataShown.${session?.current_tenant?.tenant_id ?? ""}.${session?.user_id ?? ""}`;

/** The data a person chose to see: the sample (the default) or their imported data. */
export function readDataChoice(session: SessionContext | null | undefined): string {
  try {
    return window.localStorage.getItem(dataChoiceKey(session)) === IMPORTED_SOURCE ? IMPORTED_SOURCE : SAMPLE_SOURCE;
  } catch {
    return SAMPLE_SOURCE; // No storage in this browser: the default.
  }
}

export function saveDataChoice(session: SessionContext | null | undefined, source: string) {
  try {
    window.localStorage.setItem(dataChoiceKey(session), source);
  } catch {
    // No storage in this browser: the choice holds until the page is reloaded.
  }
}

const DATA_CHOICES = [
  { source: SAMPLE_SOURCE, label: "Sample data" },
  { source: IMPORTED_SOURCE, label: "Your data" },
] as const;

/** "Sample data · Your data": which of the trial's data the lists and insights show, while both exist (0.10.80). */
export function DataChoice({ source, onChoose }: { source: string; onChoose: (source: string) => void }) {
  return (
    <div className="uw-data-choice uw-top-sample" role="group" aria-label="Data shown">
      {DATA_CHOICES.map((item) => (
        <button
          key={item.source}
          type="button"
          aria-pressed={source === item.source}
          className={source === item.source ? "is-on" : undefined}
          onClick={() => source !== item.source && onChoose(item.source)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function ImportOwnData({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" className="ac-secondary uw-top-import" onClick={onOpen}>
      <Upload size={15} aria-hidden="true" /> Import your data
    </button>
  );
}

/** The avatar: who is signed in, Account, Settings, the admin console, another organization and Sign out. */
export function AvatarMenu({
  session,
  current,
  open,
  onAdminConsole,
  showSettings,
  onImport,
  data,
  defaultOpen = false,
}: {
  session: SessionContext | null;
  current: string;
  open: (section: WorkspaceSection) => void;
  onAdminConsole?: () => void;
  showSettings: boolean;
  /** "Import your data", for the phone, where the top bar hides it (0.10.79). */
  onImport?: () => void;
  /** "Sample data · Your data", for the phone, where the top bar hides it (0.10.80). */
  data?: { source: string; onChoose: (source: string) => void };
  /** Tests only: render the menu open. */
  defaultOpen?: boolean;
}) {
  const [shown, setShown] = useState(defaultOpen);
  const root = useRef<HTMLDivElement>(null);
  useDismiss(shown, () => setShown(false), root);
  const name = session?.display_name ?? "User";
  const go = (section: WorkspaceSection) => {
    setShown(false);
    open(section);
  };
  return (
    <div className="uw-avatar-box" ref={root}>
      <button
        type="button"
        className="uw-avatar"
        aria-haspopup="menu"
        aria-expanded={shown}
        aria-label={`${name}: account menu`}
        title={name}
        onClick={() => setShown((value) => !value)}
      >
        {initials(name)}
      </button>
      {shown && (
        <div className="uw-pop uw-avatar-menu" role="menu" aria-label="Account">
          <p className="uw-avatar-who">
            <b>{name}</b>
            <small>{shortRoles(session)}</small>
          </p>
          <button
            type="button"
            role="menuitem"
            className="uw-pop-option"
            aria-current={current === "My Account" ? "page" : undefined}
            onClick={() => go("My Account")}
          >
            <UserRound size={16} aria-hidden="true" /> <span>Account</span>
          </button>
          {onImport && (
            <button
              type="button"
              role="menuitem"
              className="uw-pop-option uw-avatar-import"
              onClick={() => {
                setShown(false);
                onImport();
              }}
            >
              <Upload size={16} aria-hidden="true" /> <span>Import your data</span>
            </button>
          )}
          {data && (
            <div className="uw-avatar-data" role="group" aria-label="Data shown">
              <p className="uw-pop-title">Data shown</p>
              {DATA_CHOICES.map((item) => (
                <button
                  key={item.source}
                  type="button"
                  role="menuitemradio"
                  aria-checked={data.source === item.source}
                  className="uw-pop-option"
                  onClick={() => {
                    setShown(false);
                    if (data.source !== item.source) data.onChoose(item.source);
                  }}
                >
                  <span>{item.label}</span>
                  {data.source === item.source && <Check size={15} aria-hidden="true" />}
                </button>
              ))}
            </div>
          )}
          {showSettings && (
            <button
              type="button"
              role="menuitem"
              className="uw-pop-option"
              aria-current={current === "Settings" ? "page" : undefined}
              onClick={() => go("Settings")}
            >
              <Settings2 size={16} aria-hidden="true" /> <span>Settings</span>
            </button>
          )}
          {onAdminConsole && (
            <button
              type="button"
              role="menuitem"
              className="uw-pop-option"
              onClick={() => {
                setShown(false);
                onAdminConsole();
              }}
            >
              <Settings2 size={16} aria-hidden="true" /> <span>Admin console</span>
            </button>
          )}
          <SwitchOrganization />
          <button type="button" role="menuitem" className="uw-pop-option" onClick={() => void signOut()}>
            <LogOut size={16} aria-hidden="true" /> <span>Sign out</span>
          </button>
        </div>
      )}
    </div>
  );
}

/** The tab bar: only the persona's destinations, the current one marked. */
export function TabBar({
  tabs,
  current,
  open,
}: {
  tabs: readonly string[];
  current: string | null;
  open: (section: WorkspaceSection) => void;
}) {
  return (
    <nav className="uw-tabs" aria-label="Destinations">
      <div className="uw-tabs-in">
        {tabs.map((key) => (
          <button
            key={key}
            type="button"
            className="uw-tab"
            aria-current={current === key ? "page" : undefined}
            onClick={() => open(PERSONA_TABS[key].section)}
          >
            {PERSONA_TABS[key].label}
          </button>
        ))}
      </div>
    </nav>
  );
}

/** The top bar's report hits (0.10.81, navigation M2): only started reports, which have a page; a report not started
 * yet (no id) is found through its complaint. */
export function reportHits(items: any[], needle: string): any[] {
  return items
    .filter((item) => item.id)
    .filter((item) =>
      [item.complaint_ref, item.complaint, item.form_title, item.title, item.market_label]
        .filter(Boolean)
        .some((value: unknown) => String(value).toLowerCase().includes(needle)),
    )
    .slice(0, 5);
}
