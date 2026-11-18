import { useEffect, useRef, useState } from "react";
import {
  Boxes,
  Building2,
  CalendarClock,
  Check,
  ChevronDown,
  Ellipsis,
  Eye,
  FileText,
  Gavel,
  House,
  Inbox,
  ListChecks,
  Lock,
  LogOut,
  MessageSquare,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  SearchCheck,
  Settings2,
  ShieldCheck,
  Signpost,
  TrendingUp,
  Upload,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { recordPlace } from "../../app/linkTable";
import { signOut } from "../shared/session";
import { SwitchOrganization } from "../shared/SwitchOrganization";
import { IMPORTED_SOURCE, SAMPLE_SOURCE, complaintListTab } from "./complaintList";
import { canImportOwnData, type SessionContext, type WorkspaceSection } from "./workspaceContext";
import { areaOf, areaSections } from "./areas";
import type { StoryRun } from "./oneStory";
import { ProgressArc } from "../shared/hero/HeroVisuals";

/*
 * The new navigation's shell (0.10.73, Release C part C1; since 0.10.90 the owner-approved hero design
 * `mdarix-hero-ui.html`): a slim top bar with the organization, one search, "Viewing as [persona]", the bell, help and
 * the avatar; a left icon rail with only the persona's destinations, a bottom bar on a phone. The persona changes what a person sees, never what they may sign: every action keeps
 * the server's own check, and the persona never reaches the server as a permission.
 */

/** A persona as the session context sends it (access_control/personas.py WORKSPACE_PERSONAS). */
export type PersonaOption = { code: string; label: string; sub: string; tabs: string[] };

/** Each tab of the rail: the five work areas (UX2, areas.ts), named as the area, opening its first screen. */
export const PERSONA_TABS: Record<string, { label: string; section: WorkspaceSection }> = {
  // A trial's guide, left of Today, for every persona (0.10.80; trialTabs). Never a persona's own tab.
  start: { label: "Getting started", section: "Getting started" },
  home: { label: "Today", section: "My Work" },
  complaints: { label: "Cases", section: "Complaints" },
  investigations: { label: "Investigations", section: "Investigations" },
  // Product 360, Supplier 360 and Trends (0.10.94, W1; UX2).
  products: { label: "Products", section: "Product 360" },
  // Approvals, decision trees and authority reports in one place (UX2); opens the first one the person may open.
  decisions: { label: "Decisions & Reports", section: "Approvals" },
};

/** The tab a screen belongs to: its area's (one complaint's page is Cases', Trends is Products'); Getting started its
 * own; Records, Settings, Team, Account and Administration none (they are in the avatar menu). */
export const tabOfSection = (section: string): string | null =>
  section === "Getting started" ? "start" : areaOf(section);

/** The persona's tabs the server lets this person open (any screen of the area), in the rail's order. */
export const visibleTabs = (tabs: readonly string[], allowed: readonly string[]): string[] =>
  Object.keys(PERSONA_TABS).filter(
    (key) =>
      tabs.includes(key) &&
      (key === "start" ? allowed.includes("Getting started") : areaSections(key, allowed).length > 0),
  );

/** A trial's tabs: Getting started first, whatever the persona (0.10.80); Look ahead and Next steps are in Today
 * (UX2). A pilot's are the persona's. */
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
  colleague = false,
}: {
  persona: string;
  options: readonly PersonaOption[];
  locked: boolean;
  onChoose: (code: string) => void;
  /** A colleague the owner gave several personas: the menu lists only theirs (0.10.82, D1.9). */
  colleague?: boolean;
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
        {/* One avatar on the top bar (0.10.82): the persona is named here, its circle only in the menu. */}
        <Eye size={14} aria-hidden="true" className="uw-persona-eye" />
        <small className="uw-persona-hint">Viewing as</small>
        <span>{label}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div className="uw-pop uw-persona-menu" id="uw-persona-menu" role="menu" aria-label="View MDARIX as">
          <p className="uw-pop-title">{colleague ? "Your personas · set by the trial owner" : "View MDARIX as"}</p>
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
            {colleague
              ? `You hold these ${options.length} personas, so you can switch between them. Only the trial owner can add or remove one. You may sign what each of your roles allows, but never approve something you prepared.`
              : "Changes what you see, not what you may sign. Signing follows your own role. MDARIX remembers your choice for your next sign-in."}
          </p>
        </div>
      )}
    </div>
  );
}

type Hit = {
  key: string;
  kind: "Complaint" | "Call" | "Product" | "Report" | "Investigation" | "Trend";
  title: string;
  detail: string;
  go: () => void;
};

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
        // Calls not yet a complaint (SAMPLE-URG-01) are found too, and open their triage card (0.10.82, U-20).
        requestJson<any>("/api/v1/triage").catch(() => null),
        // Trends to review by any part of their title or reference (0.10.85, D3.11).
        requestJson<any>(`/api/v1/triage/signals?q=${term}&page_size=5`).catch(() => null),
      ]).then(([complaints, records, reports, triage, trends]) => {
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
        found.push(...recordHits(records?.records ?? [], trends?.items ?? [], go));
        const needle = q.toLowerCase();
        for (const row of ((triage?.items ?? []) as any[])
          .filter(
            (item) =>
              item.kind === "INTAKE" &&
              String(item.ref ?? "")
                .toLowerCase()
                .includes(needle),
          )
          .slice(0, 3)) {
          found.push({
            key: `t-${row.id}`,
            kind: "Call",
            title: String(row.ref),
            detail: `A call to triage · ${String(row.words ?? "").slice(0, 70)}`,
            go: go({ section: "Complaints", tab: `To triage?${new URLSearchParams({ ref: String(row.ref) })}` }),
          });
        }
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
        // Only while the results exist: a reference to a missing id is invalid (0.10.84, accessibility).
        aria-controls={shown && hits ? "uw-search-results" : undefined}
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
    <button type="button" className="ac-secondary uw-top-import" title="Import your data" onClick={onOpen}>
      <Upload size={15} aria-hidden="true" /> <span className="uw-top-label">Import your data</span>
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
  canOpen = () => false,
  defaultOpen = false,
}: {
  session: SessionContext | null;
  current: string;
  open: (section: WorkspaceSection) => void;
  onAdminConsole?: () => void;
  showSettings: boolean;
  /** Which of the avatar menu's screens this person may open (UX2: Records & trust, Team, Administration, Import
   * data); none when not given. */
  canOpen?: (section: WorkspaceSection) => boolean;
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
          {/* The name only (0.10.87): the persona is on the top bar's "Viewing as" chip. */}
          <p className="uw-avatar-who">
            <b>{name}</b>
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
          {/* Records & trust and administration live here, not in the work areas (UX2): used weekly, not daily. */}
          {AVATAR_SCREENS.filter(({ section }) => canOpen(section) && (section !== "Import data" || !onImport)).map(
            ({ section, label, icon: Icon }) => (
              <button
                key={section}
                type="button"
                role="menuitem"
                className="uw-pop-option"
                aria-current={current === section ? "page" : undefined}
                onClick={() => go(section)}
              >
                <Icon size={16} aria-hidden="true" /> <span>{label}</span>
              </button>
            ),
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
          {onAdminConsole && !canOpen("Administration") && (
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

/** The avatar menu's screens (UX2), in order; each shows only to whoever may open it. */
const AVATAR_SCREENS: ReadonlyArray<{ section: WorkspaceSection; label: string; icon: LucideIcon }> = [
  { section: "Records", label: "Records & trust", icon: ShieldCheck },
  { section: "Team", label: "Team", icon: Users },
  { section: "Administration", label: "Administration", icon: Building2 },
  { section: "Import data", label: "Import data", icon: Upload },
];

/** What happens in each work area: the story the rail tells, under each name (visual direction 0.11.07). */
export const TAB_STORY: Record<string, string> = {
  home: "Your work today",
  complaints: "The signal",
  investigations: "Why it happened",
  products: "What changed",
  decisions: "Decide, report, prove",
};

/** Each destination's icon on the rail and the phone's bar (0.10.90, the hero design). */
const TAB_ICON: Record<string, LucideIcon> = {
  home: House,
  complaints: Inbox,
  investigations: SearchCheck,
  products: Boxes,
  decisions: Gavel,
};

/** Screens with an emblem of their own: the avatar menu's, and the second screens of an area (UX2). */
const SECTION_ICON: Record<string, LucideIcon> = {
  Settings: Settings2,
  "My Account": UserRound,
  "Import your data": Upload,
  "Import data": Upload,
  "Share feedback": MessageSquare,
  Records: ShieldCheck,
  Team: Users,
  Administration: Building2,
  Trends: TrendingUp,
  "Decision trees": Network,
  Reports: FileText,
  "Look ahead": CalendarClock,
  "Next steps": Signpost,
};

/** A page's emblem in its head: its destination's icon; Settings, Account, Import your data and feedback their own. */
export const sectionIcon = (section: string): LucideIcon =>
  SECTION_ICON[section] ?? TAB_ICON[tabOfSection(section) ?? ""] ?? House;

/** The rail's one group (UX2): the five work areas in the order the work runs; Getting started heads it. */
export const RAIL_GROUPS: ReadonlyArray<{ label: string; tabs: readonly string[] }> = [
  { label: "Work", tabs: ["home", "complaints", "investigations", "products", "decisions"] },
];

/** The phone's bottom bar: these four, where the persona has them; "More" opens the rest. */
export const PHONE_SLOTS: readonly string[] = ["start", "home", "complaints", "products"];

/** The tabs the rail and the phone's bar show: the persona's, and a screen they do not list (opened from the story or
 * a link) while it is open, marked so (0.10.85; the approved design): the person always sees where they are. */
export const shownTabs = (listed: readonly string[], current: string | null) => {
  const extra = current && current in PERSONA_TABS && !listed.includes(current) ? current : null;
  return { tabs: extra ? [...listed, extra] : [...listed], extra };
};

/** The phone's bar: the slots the persona has, and the rest behind "More". */
export const phoneBar = (tabs: readonly string[]) => ({
  slots: PHONE_SLOTS.filter((key) => tabs.includes(key)),
  more: tabs.filter((key) => !PHONE_SLOTS.includes(key)),
});

/** The destinations that have something new for the person (owner, 5 Nov 2026: a dot, never a count): Cases while a
 * complaint is overdue, Products (which holds Trends, UX2) while a product is rising against its history. */
export const railAlerts = (overdue: number | null | undefined, rising: number | null | undefined) =>
  new Set([...(overdue ? ["complaints"] : []), ...(rising ? ["products"] : [])]);

/** A destination's dot: a mark beside its name, and the words "New items" for screen readers and as its tooltip. */
function AlertDot() {
  return (
    <>
      <i className="uw-tab-dot" aria-hidden="true" title="New items" />
      <span className="sr-only"> · New items</span>
    </>
  );
}

/** The walkthrough's progress for the rail's ring: steps done or not needed, of ten, from the story's own read. */
export const storyProgress = (run: StoryRun | null | undefined) =>
  run ? run.steps.filter((step) => step.done || step.skipped).length : null;

function TabButton({
  tab,
  current,
  extra,
  personaLabel,
  open,
  className = "uw-tab",
  alert = false,
}: {
  tab: string;
  current: string | null;
  extra: string | null;
  personaLabel?: string;
  open: (section: WorkspaceSection) => void;
  className?: string;
  /** Something new there: the dot. */
  alert?: boolean;
}) {
  const Icon = TAB_ICON[tab] ?? House;
  const label = PERSONA_TABS[tab].label;
  return (
    <button
      type="button"
      className={tab === extra ? `${className} is-extra` : className}
      aria-current={current === tab ? "page" : undefined}
      title={
        tab === extra
          ? `Opened from Getting started or a link: not one of ${personaLabel ?? "this view"}'s tabs`
          : label
      }
      onClick={() => open(PERSONA_TABS[tab].section)}
    >
      <Icon size={20} aria-hidden="true" />
      <span className="uw-tab-label">{label}</span>
      {/* The story line is the rail's picture; the name alone is the button's name. */}
      {TAB_STORY[tab] && (
        <small className="uw-tab-sub" aria-hidden="true">
          {TAB_STORY[tab]}
        </small>
      )}
      {alert && <AlertDot />}
      {tab === extra && <span className="sr-only"> (opened from Getting started; not one of your tabs)</span>}
    </button>
  );
}

/** The MDARIX mark: a ring with the ECG trace, as the hero design draws it. */
function BrandMark() {
  return (
    <svg width="32" height="32" viewBox="0 0 30 30" aria-hidden="true">
      <rect width="30" height="30" rx="9" fill="#0f2240" />
      <circle cx="15" cy="15" r="8.5" fill="none" stroke="rgba(255,255,255,.16)" strokeWidth="3" />
      <circle
        cx="15"
        cy="15"
        r="8.5"
        fill="none"
        stroke="#3fe0d6"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray="40 53.4"
        transform="rotate(-90 15 15)"
      />
      <path
        d="M10.5 15.5h2.4l1.3-3 1.8 6 1.3-3h2.2"
        fill="none"
        stroke="#fff"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * The left icon rail (0.10.90, the owner-approved hero design), in place of the eleven tabs across the top: the brand,
 * Getting started with its progress ring, the persona's destinations in two groups, and Next steps pinned at the foot.
 * It folds to icons on request, and by itself below 1240 px; each icon keeps its name for screen readers and as a
 * tooltip. On a phone the bottom bar (PhoneBar) stands in for it.
 */
export function NavRail({
  tabs: listed,
  current,
  open,
  personaLabel,
  progress = null,
  progressTotal = 10,
  alerts = new Set<string>(),
}: {
  tabs: readonly string[];
  current: string | null;
  open: (section: WorkspaceSection) => void;
  personaLabel?: string;
  /** Getting started's steps done of ten, when the story is read. */
  progress?: number | null;
  /** Of how many: seven while the flagship investigation leads (W1). */
  progressTotal?: number;
  /** The destinations with something new (railAlerts). */
  alerts?: ReadonlySet<string>;
}) {
  const [folded, setFolded] = useState(false);
  const { tabs, extra } = shownTabs(listed, current);
  const button = (tab: string) => (
    <TabButton
      key={tab}
      tab={tab}
      current={current}
      extra={extra}
      personaLabel={personaLabel}
      open={open}
      alert={alerts.has(tab)}
    />
  );
  const groups = RAIL_GROUPS.map((group) => ({ ...group, tabs: group.tabs.filter((tab) => tabs.includes(tab)) }));
  return (
    <nav className={`uw-navrail${folded ? " is-folded" : ""}`} aria-label="Destinations">
      <div className="uw-navrail-brand">
        <BrandMark />
        <b className="uw-navrail-word">MDARIX</b>
        <button
          type="button"
          className="uw-navrail-fold"
          aria-label={folded ? "Expand the menu" : "Collapse the menu"}
          aria-expanded={!folded}
          onClick={() => setFolded((value) => !value)}
        >
          {folded ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
        </button>
      </div>
      {tabs.includes("start") && (
        <button
          type="button"
          className={extra === "start" ? "uw-navrail-story is-extra" : "uw-navrail-story"}
          aria-current={current === "start" ? "page" : undefined}
          title="Getting started"
          onClick={() => open(PERSONA_TABS.start.section)}
        >
          {/* Until the story is read, the step's icon, not an empty ring that reads as loading. */}
          {progress === null ? (
            <span className="uw-navrail-ring-wait" aria-hidden="true">
              <ListChecks size={22} />
            </span>
          ) : (
            <ProgressArc done={progress} total={progressTotal} size={44} decorative />
          )}
          <span className="uw-tab-label">
            <strong>Getting started</strong>
            {progress !== null && (
              <small>
                {progress} of {progressTotal} completed
              </small>
            )}
          </span>
        </button>
      )}
      {groups
        .filter((group) => group.tabs.length)
        .map((group) => (
          <div className="uw-navrail-group" key={group.label}>
            <p className="uw-navrail-grp" aria-hidden="true">
              {group.label}
            </p>
            {group.tabs.map(button)}
          </div>
        ))}
    </nav>
  );
}

/** A phone's bottom bar (0.10.90): Getting started, Home, Complaints and Trends where the persona has them, and
 * "More", which opens the persona's other destinations above the bar. */
export function PhoneBar({
  tabs: listed,
  current,
  open,
  personaLabel,
  progress = null,
  progressTotal = 10,
  alerts = new Set<string>(),
}: {
  tabs: readonly string[];
  current: string | null;
  open: (section: WorkspaceSection) => void;
  personaLabel?: string;
  progress?: number | null;
  progressTotal?: number;
  alerts?: ReadonlySet<string>;
}) {
  const [shown, setShown] = useState(false);
  const root = useRef<HTMLElement>(null);
  useDismiss(shown, () => setShown(false), root);
  const { tabs, extra } = shownTabs(listed, current);
  const { slots, more } = phoneBar(tabs);
  const go = (section: WorkspaceSection) => {
    setShown(false);
    open(section);
  };
  return (
    <nav className="uw-phonebar" aria-label="Destinations" ref={root}>
      {shown && (
        <div className="uw-phonebar-more" id="uw-phonebar-more">
          {more.map((tab) => (
            <TabButton
              key={tab}
              tab={tab}
              current={current}
              extra={extra}
              personaLabel={personaLabel}
              open={go}
              className="uw-tab uw-more-item"
              alert={alerts.has(tab)}
            />
          ))}
        </div>
      )}
      <div className="uw-phonebar-in">
        {slots.map((tab) =>
          tab === "start" ? (
            <button
              key={tab}
              type="button"
              className={extra === "start" ? "uw-tab is-extra" : "uw-tab"}
              aria-current={current === "start" ? "page" : undefined}
              onClick={() => go(PERSONA_TABS.start.section)}
            >
              {progress === null ? (
                <ListChecks size={20} aria-hidden="true" />
              ) : (
                <ProgressArc done={progress} total={progressTotal} size={22} tone="light" decorative />
              )}
              <span className="uw-tab-label">Getting started</span>
            </button>
          ) : (
            <TabButton
              key={tab}
              tab={tab}
              current={current}
              extra={extra}
              personaLabel={personaLabel}
              open={go}
              alert={alerts.has(tab)}
            />
          ),
        )}
        {more.length > 0 && (
          <button
            type="button"
            className={`uw-tab${current && more.includes(current) ? " is-within" : ""}`}
            aria-expanded={shown}
            aria-controls={shown ? "uw-phonebar-more" : undefined}
            onClick={() => setShown((value) => !value)}
          >
            <Ellipsis size={20} aria-hidden="true" />
            <span className="uw-tab-label">More</span>
            {more.some((tab) => alerts.has(tab)) && <AlertDot />}
          </button>
        )}
      </div>
    </nav>
  );
}

/**
 * The top bar's investigation and trend hits (0.10.85, D3.11): an investigation by any part of its reference or
 * question (from the record search), opening its page; a trend to review by its title or reference.
 */
export function recordHits(
  records: any[],
  trends: any[],
  go: (place: { section: string; tab?: string }) => () => void,
): Hit[] {
  const cases = records
    .filter((item) => item.record_type === "investigation")
    .slice(0, 3)
    .map((row) => {
      const ref = String(row.investigation_identifier ?? row.business_id ?? "");
      return {
        key: `i-${row.id}`,
        kind: "Investigation" as const,
        title: ref,
        detail: String(row.investigation_question ?? "").slice(0, 90),
        go: () => window.location.assign(`/app/investigations?${new URLSearchParams({ case: ref })}`),
      };
    });
  const raised = trends.slice(0, 5).map((row) => {
    const ref = String(row.business_id ?? row.id);
    return {
      key: `s-${row.id}`,
      kind: "Trend" as const,
      title: String(row.title ?? ref),
      detail: ref,
      go: go({ section: "Trends", tab: `Trends to review?${new URLSearchParams({ signal: ref })}` }),
    };
  });
  return [...cases, ...raised];
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

/*
 * The new navigation's shell, said once (0.10.87, the owner-approved duplication review): which page heads, lines and
 * banners show where, so the shell never repeats what a page says itself.
 */

/** Pages that show times or deadlines: only they carry the head's time-zone line. */
const ZONE_SECTIONS: readonly string[] = [
  "Complaints",
  "Decision trees",
  "Reports",
  "Investigations",
  "Trends",
  "Records",
  "Settings",
];

/** Whether the shell's page head (eyebrow, question, guide) shows: not where the page has its own head. */
export function pageHeadShown(section: string, fresh: boolean, isTrial: boolean, tab?: string): boolean {
  if (section === "Complaint") return false;
  if (!fresh) return true;
  if (section === "My Work" || section === "Next steps" || (section === "Getting started" && isTrial)) return false;
  // One report has its own head (its form, reference and chips); so have one product and one supplier (0.10.94).
  const carried = new URLSearchParams(tab?.split("?")[1] ?? "");
  if (section === "Product 360") return !carried.has("product") && !carried.has("supplier");
  return !(section === "Reports" && carried.has("report"));
}

/** Whether the head says the organization's time zone (the classic head always does). */
export const zoneLineShown = (section: string, fresh: boolean) => !fresh || ZONE_SECTIONS.includes(section);

/** Whether the product or investigation picker shows on the new navigation: only on Trends' tabs without a filter
 * of their own (the trend check has one; an investigation is chosen on its list). */
export const contextPickerShown = (section: string, tab?: string) =>
  section === "Trends" && !["", "Trend check"].includes((tab ?? "").split("?")[0]);

/** What a trial's shell shows around a page (0.10.87): the top bar's sample label, except on Getting started (its card
 * says it); Import your data, except on that page; the chapter banners on the classic navigation only (the new one
 * has the ten-step walkthrough); the story bar, except on Home (its own story banner says it). */
export function trialShellShows(section: string, fresh: boolean, dataBar: string) {
  return {
    sampleChip: dataBar === "sample" && section !== "Getting started",
    importButton: section !== "Import your data",
    chapterDone: !fresh,
    storyBar: fresh && section !== "My Work",
  };
}
