import { recordPlace } from "../../app/linkTable";
import { useEffect } from "react";
import { errorText, onSaved, send, useResource } from "../customer-admin/shared";
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
    /** The product's own identifier, which the trend check opens on (0.10.84). */
    product_ref?: string | null;
    serious_injury: boolean;
    death: boolean;
  };
  market: string | null;
  market_label: string | null;
  conclusion: string | null;
  report_id: string | null;
  report_stage: string | null;
  needs: StoryNeed[];
  /** ``earlier`` (0.10.85): done by the team out of order; ticked once the steps before it are done. */
  steps: Array<{ key: string; label: string; done: boolean; skipped: boolean; earlier?: boolean }>;
  current: number;
  finished: boolean;
};
export type OneStory = { sample: StoryRun | null; yours: StoryRun | null };

export const STORY_STEPS = 10;
/** The steps ticked when someone opens the step's screen from the story: it counts for the whole team (0.10.84, M6). */
const MARKED: Record<number, string> = { 0: "call", 4: "form", 8: "records", 9: "trends" };

/** The story, read again after every saved change (0.10.84, M1): saving the triage moves the pill and Next step on. */
export function useOneStory(on = true) {
  const story = useResource<OneStory>(on ? ONE_STORY_PATH : null);
  const { reload } = story;
  useEffect(() => (on ? onSaved(reload) : undefined), [on, reload]);
  return story;
}

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
  // Records opens on the record just finished, and Trends on the story's own product: the sample's real rise, or your
  // data's product, never the sample's on your data (0.10.84, M4).
  if (index === 8) return { section: "Records", tab: recordsTab(run.complaint.ref) };
  const product = run.run === "sample" ? "SAMPLE-ORBIT-300" : run.complaint.product_ref;
  return product
    ? { section: "Trends", tab: `Trend check?${new URLSearchParams({ product })}` }
    : { section: "Trends", tab: "Trend check" };
}

/** Records on the record one story finished: its decision record leads (Records reads ``complaint``). */
export const recordsTab = (ref: string) => `Decision records?${new URLSearchParams({ complaint: ref })}`;

/** Why the last step the person opened was not saved (shown once on Getting started), or null. */
let markProblem: string | null = null;
export const takeMarkProblem = () => {
  const found = markProblem;
  markProblem = null;
  return found;
};

/** Open a step: its own mark saved where the step is the person's (the call, the report, Records, Trends). */
export async function openStep(
  run: StoryRun,
  index: number,
  open: (section: any, tab?: string) => void,
): Promise<void> {
  const mark = MARKED[index];
  const place = stepPlace(run, index);
  // The screen opens at once (0.10.85: waiting for the mark read as a dead click). The mark names the complaint the
  // person opened, so it never lands on another one; a refusal is kept and shown on Getting started, never dropped.
  open(place.section, place.tab);
  if (!mark || (index === 4 && !run.report_id)) return;
  try {
    await send(`${ONE_STORY_PATH}/marks`, "POST", { run: run.run, step: mark, complaint_id: run.complaint.id });
  } catch (reason) {
    markProblem = errorText(reason, `Step ${index + 1} was not saved. Open it again from Getting started.`);
  }
}

/** "Step 4 of 10", or "All ten steps done". */
export const stepCount = (run: StoryRun) =>
  run.finished ? "All ten steps done" : `Step ${run.current + 1} of ${STORY_STEPS}`;
