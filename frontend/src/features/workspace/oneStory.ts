import { recordPlace } from "../../app/linkTable";
import { send, useResource } from "../customer-admin/shared";
import { reportPlace } from "./authorityReports";
import { treePlace } from "./sections/DecisionTrees";
import { IMPORTED_SOURCE } from "./complaintList";

/**
 * One story, from the first call to the signed report (0.10.82, D1): ten steps on one complaint, the sample's
 * SAMPLE-RV-11 first, then the trial's own most urgent imported complaint. The server reads each tick from the saved
 * record (backend/app/trial/one_story.py); each step opens the real screen with the record in place.
 */
export const ONE_STORY_PATH = "/api/v1/trial/one-story";

export type StoryRunKey = "sample" | "yours";
export type StoryNeed = { fact: "COUNTRY" | "AWARENESS_DATE"; label: string; message: string; rule: string };
export type StoryRun = {
  run: StoryRunKey;
  complaint: {
    id: string;
    ref: string;
    description: string | null;
    product_id: string | null;
    serious_injury: boolean;
    death: boolean;
  };
  market: string | null;
  market_label: string | null;
  conclusion: string | null;
  report_id: string | null;
  report_stage: string | null;
  needs: StoryNeed[];
  steps: Array<{ key: string; label: string; done: boolean; skipped: boolean }>;
  current: number;
  finished: boolean;
};
export type OneStory = { sample: StoryRun | null; yours: StoryRun | null };

export const STORY_STEPS = 10;
/** The steps whose tick is the person's own mark: it is saved when the step's screen is opened from the story. */
const MARKED: Record<number, string> = { 0: "call", 4: "form", 8: "records", 9: "trends" };

export const useOneStory = (on = true) => useResource<OneStory>(on ? ONE_STORY_PATH : null);

/** The run shown: the one the data switch chose, while it has a complaint; else whichever has one. */
export function shownRun(story: OneStory | null | undefined, dataSource?: string): StoryRun | null {
  if (!story) return null;
  if (dataSource === IMPORTED_SOURCE && story.yours) return story.yours;
  return story.sample ?? story.yours;
}

/** The run, if any, whose complaint is this one (the story's own record). */
export const runOf = (story: OneStory | null | undefined, ref: string | undefined) =>
  [story?.sample, story?.yours].find((run) => !!run && !!ref && run.complaint.ref === ref) ?? null;

/** The run, if any, whose report is this one. */
export const runOfReport = (story: OneStory | null | undefined, reportId: string | null | undefined) =>
  [story?.sample, story?.yours].find((run) => !!run && !!reportId && run.report_id === reportId) ?? null;

type Place = { section: string; tab?: string };

/** Why a step cannot open its own screen yet, if it cannot: a fact the import lacks, or a report not created yet. */
export function stepBlocker(run: StoryRun, index: number): string | null {
  const country = run.needs.find((need) => need.fact === "COUNTRY");
  const awareness = run.needs.find((need) => need.fact === "AWARENESS_DATE");
  if (index >= 1 && index <= 3 && awareness)
    return `Your file gives no awareness date for ${run.complaint.ref}. The complaint page asks for it: every clock counts from it, and nothing is signed without it.`;
  if (index >= 2 && index <= 7 && (country || !run.market))
    return `Your file gives no incident country for ${run.complaint.ref}. The complaint page asks for it: it decides which market's tree and form apply.`;
  if (index >= 4 && index <= 7 && !run.report_id && run.conclusion !== "NOT_REPORTABLE")
    return "The report is created when you sign a “reportable” conclusion: finish step 4 first.";
  return null;
}

/** The real screen a step opens, with the story's record in place. */
export function stepPlace(run: StoryRun, index: number): Place {
  const complaint = recordPlace("complaint", run.complaint.ref, {}, "new") as Place;
  const blocked = stepBlocker(run, index);
  if (index <= 1) return complaint;
  if (blocked && (run.needs.length || !run.market)) return complaint;
  if (index <= 3 || (index <= 7 && !run.report_id))
    return run.market ? treePlace(run.market, run.complaint.id) : complaint;
  if (index <= 7) return reportPlace(run.report_id!);
  if (index === 8) return { section: "Records" };
  return run.run === "sample"
    ? { section: "Trends", tab: "Trend check?product=SAMPLE-ORBIT-300" }
    : { section: "Trends" };
}

/** Open a step: its own mark saved first where the step is the person's (the call, the report, Records, Trends). */
export async function openStep(
  run: StoryRun,
  index: number,
  open: (section: any, tab?: string) => void,
): Promise<void> {
  const mark = MARKED[index];
  const place = stepPlace(run, index);
  // The report's mark only counts once there is a report to open (step 5 is otherwise blocked).
  if (mark && !(index === 4 && !run.report_id))
    await send(`${ONE_STORY_PATH}/marks`, "POST", { run: run.run, step: mark }).catch(() => null);
  open(place.section, place.tab);
}

/** "Step 4 of 10", or "All ten steps done". */
export const stepCount = (run: StoryRun) =>
  run.finished ? "All ten steps done" : `Step ${run.current + 1} of ${STORY_STEPS}`;
