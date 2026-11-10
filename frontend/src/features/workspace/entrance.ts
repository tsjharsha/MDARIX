import { tabParts, type Place } from "../../app/linkTable";

/**
 * The entrance (quality plan stage 8, 8.4; 0.10.71, Release A, the first screens): a trial on the new navigation
 * leads with one event, the short story on SAMPLE-RV-11, and keeps the other stories under "More stories". Each story
 * opens on its own named record, never a queue. Steps are places of the new navigation (linkTable.json newPlaces);
 * the short story's progress comes from what was saved on its record (the server's /api/v1/trial/short-story), the
 * others' bar shows the last step whose place is on screen. No time claims: step counts only, until they are measured.
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
  key: "short" | "complaint" | "rising" | "reportable";
  title: string;
  lede: string;
  /** Where the story starts, as a classic place: the table moves it (routeFor). Always a named record. */
  start: Place;
  steps: StoryStep[];
  /**
   * The story's own records (0.10.70): its complaint, by its reference, and its investigation, by its identifier or
   * "escalated" (the one the complaint's disposition opens). A place showing another record is off the story's path.
   */
  record?: { complaint?: string; investigation?: string };
};

export const FLAGSHIP = "SAMPLE-RV-11";

/** The short story (0.10.71, A4): four steps on SAMPLE-RV-11, ending in the intake decision summary. */
export const SHORT: Scenario = {
  key: "short",
  title: "A hospital sent a monitor for service. Should Quality review this too?",
  lede: "Read the call, decide its route, name the open question and see the intake decision summary.",
  start: { section: "Complaint", tab: `Summary?ref=${FLAGSHIP}` },
  record: { complaint: FLAGSHIP },
  steps: [
    { label: "Read the call", button: "Decide the route", section: "Complaint", tab: "Summary" },
    { label: "Decide the route", button: "Confirm the route", section: "Complaint", tab: "Summary" },
    { label: "Name the open question", button: "Record the question", section: "Complaint", tab: "Summary" },
    {
      label: "The intake decision summary",
      button: "Continue the full evaluation",
      section: "Complaint",
      tab: "Summary",
    },
  ],
};

/** The other stories, under "More stories". The flagship's full evaluation follows the short story's summary. */
export const SCENARIOS: readonly Scenario[] = [
  SHORT,
  {
    key: "complaint",
    title: "A complaint just arrived: what now?",
    lede: "SAMPLE-URG-01, an urgent call from a hospital: check whether it is a complaint, triage it and see its next step.",
    start: { section: "Complaints", tab: "Triage?ref=SAMPLE-URG-01" },
    steps: [
      {
        label: "The urgent call on the triage list, and its clock",
        button: "Open",
        section: "Complaints",
        tab: "To triage",
      },
      { label: "Check the call: is it a complaint?", button: "Sign the case check", section: "My Work", tab: "Queues" },
      { label: "Its page: what needs attention next", button: "Next step", section: "Complaint" },
    ],
  },
  {
    key: "rising",
    title: "Is a problem rising?",
    lede: "OrbitCare 300 Rev B: complaints per unit against the earlier average, its investigation and the lots it touches.",
    start: { section: "Signals", tab: "Trend check?product=SAMPLE-ORBIT-300" },
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
    lede: "The full evaluation of SAMPLE-RV-11: each market's questions, its clock, the report, the decision and ready to close.",
    start: { section: "Complaint", tab: `Summary?ref=${FLAGSHIP}` },
    record: { complaint: FLAGSHIP, investigation: "escalated" },
    steps: [
      {
        label: "What happened, and each market's legal clock",
        button: "Complete the triage record",
        section: "Complaint",
        tab: "Summary",
      },
      { label: "Triage it", button: "Save the triage", section: "Complaints", tab: "To triage" },
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
];

/** The stories under "More stories" (every one but the short story the entrance leads with). */
export const MORE_STORIES = SCENARIOS.filter((item) => item.key !== "short");
/** A saved story that still runs: never the retired short story (0.10.87). */
export const liveStory = (key: string | null) => (key === "short" ? null : key);

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
