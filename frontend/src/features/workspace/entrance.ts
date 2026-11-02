import { tabParts, type Place } from "../../app/linkTable";

/**
 * The five-minute entrance (quality plan stage 8, 8.4): a trial on the new navigation starts with three stories on the
 * sample, and one on the person's own export. Each tile opens its story on the right record; a story bar then shows
 * the step and the way back. Steps are places of the new navigation (linkTable.json newPlaces); the bar shows the last
 * step whose place is on screen.
 */
export type StoryStep = {
  label: string;
  /** The main button that does this step, as the screen names it (the walk-through test checks it exists). */
  button: string;
  section: string;
  /** The tab, or the tabs, the step is on. */
  tab?: string | readonly string[];
  /** A parameter the place must carry (a report's panel), or must not. */
  has?: string;
  hasNot?: string;
};

export type Scenario = {
  key: "complaint" | "rising" | "reportable" | "own";
  title: string;
  minutes: number;
  lede: string;
  /** Where the story starts, as a classic place: the table moves it (routeFor). */
  start: Place;
  steps: StoryStep[];
  /**
   * The story's own records (0.10.70): its complaint, by its reference, and its investigation, by its identifier or
   * "escalated" (the one the complaint's disposition opens). A place showing another record is off the story's path.
   */
  record?: { complaint?: string; investigation?: string };
};

export const FLAGSHIP = "SAMPLE-RV-11";

export const SCENARIOS: readonly Scenario[] = [
  {
    key: "complaint",
    title: "A complaint just arrived: what now?",
    minutes: 5,
    lede: "An urgent call from a hospital: check whether it is a complaint, triage it and see its next step.",
    start: { section: "Complaints", tab: "Triage" },
    steps: [
      {
        label: "The triage list: what arrived, and its clock",
        button: "Open",
        section: "Complaints",
        tab: "To triage",
      },
      { label: "Check the call: is it a complaint?", button: "Sign the check", section: "My Work", tab: "Queues" },
      { label: "Its page: what needs attention next", button: "Next step", section: "Complaint" },
    ],
  },
  {
    key: "rising",
    title: "Is a problem rising?",
    minutes: 5,
    lede: "OrbitCare 300 Rev B: complaints per unit against the earlier average, its investigation and the lots it touches.",
    start: { section: "Signals", tab: "Trend check" },
    record: { investigation: "SAMPLE-INV-001" },
    steps: [
      { label: "See Rev B rise against the earlier average", button: "Open", section: "Trends", tab: "Trend check" },
      { label: "Open its trend", button: "Open an investigation", section: "Trends", tab: "Trends to review" },
      { label: "The investigation: question, evidence, decision", button: "Next", section: "Investigations" },
      {
        label: "Lot impact: which lots and countries share the suspect part",
        button: "Lot impact",
        section: "Investigations",
        tab: "Summary",
        has: "part",
      },
    ],
  },
  {
    key: "reportable",
    title: "Is this reportable, and by when, in the US and India?",
    minutes: 5,
    lede: "A PulseWatch 410 read SpO2 too high; nobody was harmed. Each market's questions, its clock and the report.",
    start: { section: "Complaint", tab: `Summary?ref=${FLAGSHIP}` },
    record: { complaint: FLAGSHIP, investigation: "escalated" },
    steps: [
      {
        label: "What happened, and each market's legal clock",
        button: "Complete the triage record",
        section: "Complaint",
        tab: "Summary",
      },
      { label: "Triage it", button: "Save the triage record", section: "Complaints", tab: "To triage" },
      {
        label: "Assess the US, then India",
        button: "Save and sign",
        section: "Complaints",
        tab: "Reporting",
        hasNot: "report",
      },
      {
        label: "Prepare the US 30-day report",
        button: "Ask for approval",
        section: "Complaints",
        tab: "Reporting",
        has: "report",
      },
      { label: "Sign the disposition", button: "Sign", section: "My Work", tab: "Queues" },
      { label: "The investigation's decision", button: "Sign decision", section: "Investigations" },
      // Once signed, its receipt is in History: still the story's last step.
      {
        label: "Ready to close",
        button: "Sign ready to close",
        section: "Complaint",
        tab: ["Decisions & actions", "History"],
      },
    ],
  },
  {
    key: "own",
    title: "Try it on your own export",
    minutes: 5,
    lede: "Upload your complaints export as it comes from your QMS (Excel or CSV). Optional: the sample stays until you remove it.",
    start: { section: "Import data" },
    steps: [{ label: "Upload your export and check it", button: "Check file", section: "Import data" }],
  },
];

/** The step of a story the place on screen is (the last that fits), or -1 when the place is off the story's path. */
export function storyStep(scenario: Scenario, place: { section: string; tab?: string }): number {
  const { name, query } = tabParts(place.tab);
  const carried = new URLSearchParams(query);
  for (let index = scenario.steps.length - 1; index >= 0; index--) {
    const step = scenario.steps[index];
    if (step.section !== place.section) continue;
    if (step.tab && ![step.tab].flat().includes(name || defaultTab(place.section))) continue;
    if (step.has && !carried.has(step.has)) continue;
    if (step.hasNot && carried.has(step.hasNot)) continue;
    return index;
  }
  return -1;
}

/** What a story's records are, once read: its complaint's id and its investigation's id (null until there is one). */
export type StoryIds = { complaintId?: string | null; caseId?: string | null };

/**
 * Whether the place shows the story's own record (0.10.70): a complaint page or a list's panel names a complaint by
 * its reference (ref=) or its id (complaint=); an investigation's screen shows the investigation in the context. A
 * record not yet read counts as the story's (no flicker); an "escalated" investigation that does not exist yet does
 * not: an investigation shown before the flagship's disposition is another one.
 */
export function onStoryRecord(
  scenario: Scenario,
  place: { section: string; tab?: string },
  ids: StoryIds,
  investigationId?: string | null,
): boolean {
  const record = scenario.record;
  if (!record) return true;
  const carried = new URLSearchParams(tabParts(place.tab).query);
  if (record.complaint) {
    const ref = carried.get("ref");
    const complaint = carried.get("complaint");
    if (ref && ref !== record.complaint) return false;
    if (complaint && ids.complaintId && complaint !== ids.complaintId) return false;
  }
  if (record.investigation && place.section === "Investigations") {
    if (record.investigation === "escalated" && ids.caseId === null) return false;
    if (ids.caseId && investigationId && investigationId !== ids.caseId) return false;
  }
  return true;
}

const defaultTab = (section: string) => (section === "Complaint" || section === "Investigations" ? "Summary" : "");

const STORY_KEY = "mdarix.story";
const SEEN_KEY = "mdarix.entrance.seen";

/** The story under way in this browser tab (sessionStorage: a convenience; the work itself is on the server). */
export function savedStory(): Scenario["key"] | null {
  try {
    const key = window.sessionStorage.getItem(STORY_KEY);
    return SCENARIOS.some((item) => item.key === key) ? (key as Scenario["key"]) : null;
  } catch {
    return null;
  }
}

export function saveStory(key: Scenario["key"] | null): void {
  try {
    if (key) window.sessionStorage.setItem(STORY_KEY, key);
    else window.sessionStorage.removeItem(STORY_KEY);
  } catch {
    // No storage: the story bar lasts until the page is reloaded.
  }
}

/**
 * Whether this person has seen the entrance in this browser: a returning person lands on My work, with the entrance
 * one click away. shortcut: per browser, not per person; a server-side "first visit" would follow them across devices.
 */
export function entranceSeen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

export function markEntranceSeen(): void {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // No storage: the entrance shows again next time.
  }
}
