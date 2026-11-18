import { recordPlace } from "../../app/linkTable";
import { useEffect } from "react";
import { errorText, onSaved, send, useResource } from "../customer-admin/shared";
import { reportPlace } from "./authorityReports";
import { treePlace } from "./sections/DecisionTrees";
import { IMPORTED_SOURCE } from "./complaintList";
import { monthlyRates, monthlyText } from "./signalAi";
import { cockpitStep } from "./caseWorkflow";

/**
 * One story, from the first contact to the submission (0.10.82, D1; Part 1 in 0.10.93, B2 spec 4.8): ten steps on one
 * complaint, the sample's SAMPLE-RV-11 and its call SAMPLE-CASE-11 first, then the trial's own most urgent imported
 * complaint. The server reads each tick from the saved
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
    /** The product's name, for the step's complaint summary (0.10.87). */
    product_name?: string | null;
    serious_injury: boolean;
    death: boolean;
    /** The harm the record states (0.10.87); null when it does not say, shown as not recorded. */
    harm?: "DEATH" | "SERIOUS_INJURY" | "NONE" | null;
    /** The linked service work's status (OPEN, IN_PROGRESS, COMPLETE), if any. */
    service_status?: string | null;
  };
  market: string | null;
  market_label: string | null;
  conclusion: string | null;
  report_id: string | null;
  report_stage: string | null;
  needs: StoryNeed[];
  /** The story's Case (steps 1 and 2 open its Case check); null: classified in your QMS (0.10.93). */
  case?: { id: string; ref: string; classification: string | null; state: string | null } | null;
  /** The QA review of a Case signed service only, inquiry or not a complaint (spec 4.8's branch card). */
  branch?: { key: string; label: string; who: string; evidence: string; why: string; done: boolean } | null;
  /** ``earlier`` (0.10.85): done by the team out of order; ticked once the steps before it are done. ``note``
   * (0.10.93): why a step is not needed, or what an open step waits for. */
  steps: Array<{
    key: string;
    label: string;
    done: boolean;
    skipped: boolean;
    earlier?: boolean;
    note?: string | null;
  }>;
  current: number;
  finished: boolean;
};
/** A sample Case offered under "More cases to try" (0.10.93), with its outcome as its record says; `complaint` marks
 * the routine sample complaint (B7a), which opens its Resolve and close drawer. */
export type MoreCase = { id: string; ref: string; label: string; signed: boolean; complaint?: boolean };
/**
 * The flagship story (W1): one investigation (SAMPLE-INV-001), one product and one version (OrbitCare 300 Rev B), seven
 * steps from the signal to the action (backend/app/trial/flagship.py). Steps 1 to 3 tick when their screen loads from
 * the story; the others from the saved records (a review, the brief accepted, the signed decision, a planned check).
 */
export type FlagshipRun = {
  run: "flagship";
  product: {
    id: string;
    ref: string | null;
    name: string | null;
    /** The short name the bar reads ("OrbitCare 300"). */
    label?: string | null;
    version: string | null;
    /** KNOWN: every complaint of the case on one version; MIXED: several, or some unverified; UNVERIFIED: none known. */
    version_state: "KNOWN" | "MIXED" | "UNVERIFIED";
    unverified: number;
  };
  investigation: { id: string; ref: string; question: string };
  change: { ref: string; description: string } | null;
  capa: {
    id: string;
    ref: string;
    title: string;
    check_planned: boolean;
    check_status: string | null;
    /** W1d: the synthetic follow-up is ready on the planned check. */
    follow_up?: boolean;
  } | null;
  branch: { complaint_id: string; ref: string } | null;
  ai_proposals: number;
  mfa_verified: boolean | null;
  steps: StoryRun["steps"];
  current: number;
  finished: boolean;
};
export type OneStory = {
  sample: StoryRun | null;
  yours: StoryRun | null;
  flagship?: FlagshipRun | null;
  more_cases?: MoreCase[];
};

export const STORY_STEPS = 10;
export const FLAGSHIP_STEPS = 7;
/** Why the trend's lot 005 is not in the case (W1 open item 2): it was built with the next sensor lot. */
export const LOT_005_LINE =
  "The trend also shows lot 005: a no-fault-found return and a free-flow report. Lot 005 was built with the next " +
  "sensor lot (NS-SL-2533), so the investigation keeps to lots 003 and 004, which share sensor lot NS-SL-2417.";
/** The steps ticked when someone opens the step's screen from the story: it counts for the whole team (0.10.84, M6);
 * per run (W1: the flagship's first three). */
const TEN_STEP_MARKS: Record<number, string> = { 5: "form", 8: "records", 9: "trends" };
const MARKED: Record<string, Record<number, string>> = {
  sample: TEN_STEP_MARKS,
  yours: TEN_STEP_MARKS,
  // UX1: step 5 too, the brief the sample reviewer accepted for decision, read before it is signed.
  flagship: { 0: "signal", 1: "product", 2: "evidence", 4: "brief" },
};
/** The screen whose load counts each mark (the flagship's signal is the trend check's load). */
const VISIT_OF: Record<string, string> = { signal: "trends" };

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
  if (index >= 2 && index <= 4 && awareness)
    return `Your file gives no awareness date for ${run.complaint.ref}. The complaint page asks for it: every clock counts from it, and nothing is signed without it.`;
  if (index >= 3 && index <= 7 && (country || !run.market))
    return `Your file gives no incident country for ${run.complaint.ref}. The complaint page asks for it: it decides which market's tree and form apply.`;
  if (index >= 5 && index <= 7 && !run.report_id && run.conclusion !== "NOT_REPORTABLE")
    return "The report is created when you sign a “reportable” conclusion: finish step 5 first.";
  return null;
}

/** A Case's own check drawer on the Cases view (First contact?check=<id>, the address CasesList opens). */
export const casePlace = (id: string): Place => ({ section: "Complaints", tab: `First contact?check=${id}` });

/** Where a "More cases to try" item opens: a Case's check, or the routine complaint's Dispositions drawer (B7a). */
export const moreCasePlace = (item: MoreCase): Place =>
  item.complaint
    ? { section: "Complaints", tab: `Dispositions?complaint=${encodeURIComponent(item.id)}` }
    : casePlace(item.id);

/** The real screen a step opens, with the story's record in place: steps 1 and 2 open the story's Case check. */
export function stepPlace(run: StoryRun, index: number): Place {
  const complaint = recordPlace("complaint", run.complaint.ref, {}, "new") as Place;
  const blocked = stepBlocker(run, index);
  if (index <= 1) return run.case ? casePlace(run.case.id) : complaint;
  if (index === 2) return complaint;
  if (blocked && (run.needs.length || !run.market)) return complaint;
  if (index <= 4 || (index <= 7 && !run.report_id))
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

/** A step opened from the story whose screen has not loaded yet (0.10.88, P0 of the review of 0.10.87): it counts
 * only once its own screen has read the right record successfully. */
type PendingVisit = {
  run: string;
  step: string;
  complaintId: string;
  reportId: string | null;
  product: string | null;
  version?: string | null;
};
let pendingVisit: PendingVisit | null = null;

/** What a destination loaded: the report (step 6), the finished record (step 9) or the trend check of a product
 * (step 10); for the flagship (W1), a product's version page and an investigation's evidence. */
export type Visit =
  | { step: "form"; reportId: string | undefined }
  | { step: "records"; complaintId: string | undefined }
  | { step: "trends"; product: string | undefined }
  | { step: "product"; product: string | undefined; version: string | null | undefined }
  | { step: "evidence"; investigationId: string | undefined }
  | { step: "brief"; investigationId: string | undefined };

/** Open a step's screen at once (0.10.85: waiting read as a dead click). A step ticked by the visit itself (the
 * report, Records, Trends) is remembered, and its mark is saved by the screen once it has loaded (``visited``):
 * a screen that failed to load ticks nothing. */
export async function openStep(
  run: StoryRun,
  index: number,
  open: (section: any, tab?: string) => void,
): Promise<void> {
  const mark = MARKED[run.run][index];
  const place = stepPlace(run, index);
  pendingVisit =
    mark && !(index === 5 && !run.report_id)
      ? {
          run: run.run,
          step: mark,
          complaintId: run.complaint.id,
          reportId: run.report_id,
          product: new URLSearchParams(place.tab?.split("?")[1] ?? "").get("product"),
        }
      : null;
  open(place.section, place.tab);
}

/** Called by a destination when its data has loaded: saves the pending step's mark when the screen shows the record
 * the step opened, once; a refusal (STEP_NOT_YET, STORY_MOVED) is kept and shown on Getting started. */
export async function visited(visit: Visit): Promise<void> {
  const pending = pendingVisit;
  if (!pending || (VISIT_OF[pending.step] ?? pending.step) !== visit.step) return;
  const matches =
    visit.step === "form"
      ? !!visit.reportId && visit.reportId === pending.reportId
      : visit.step === "trends"
        ? !pending.product || visit.product === pending.product
        : visit.step === "product"
          ? visit.product === pending.product && visit.version === pending.version
          : visit.step === "evidence" || visit.step === "brief"
            ? visit.investigationId === pending.complaintId
            : !!visit.complaintId && visit.complaintId === pending.complaintId;
  if (!matches) return;
  pendingVisit = null;
  try {
    await send(`${ONE_STORY_PATH}/marks`, "POST", {
      run: pending.run,
      step: pending.step,
      complaint_id: pending.complaintId,
    });
  } catch (reason) {
    const marks = MARKED[pending.run] ?? {};
    const index = Number(Object.keys(marks).find((key) => marks[Number(key)] === pending.step) ?? 0);
    markProblem = errorText(reason, `Step ${index + 1} was not saved. Open it again from Getting started.`);
  }
}

/** For a destination: once ``loaded`` (its data read successfully), count the pending step it is. */
export function useVisited(visit: Visit, loaded: boolean) {
  const key = JSON.stringify(visit);
  useEffect(() => {
    if (loaded) void visited(visit);
  }, [loaded, key]);
}

/** A flagship step's place: its screen, and the case to open first (steps 3 to 6) (W1). */
export type FlagshipPlace = Place & { caseId?: string; productId?: string };

/** The real screen each flagship step opens, with the record in place (W1, spec section 1). */
export function flagshipPlace(run: FlagshipRun, index: number): FlagshipPlace {
  const product = run.product.ref ?? "SAMPLE-ORBIT-300";
  const inCase = (tab: string): FlagshipPlace => ({
    section: "Investigations",
    tab,
    caseId: run.investigation.id,
    productId: run.product.id,
  });
  if (index === 0) return { section: "Trends", tab: `Trend check?${new URLSearchParams({ product })}` };
  if (index === 1) {
    const place: Record<string, string> = { product, view: "Configuration", compare: "Rev A" };
    if (run.product.version) place.version = run.product.version;
    return { section: "Product 360", tab: `Product 360?${new URLSearchParams(place)}` };
  }
  if (index === 2) return inCase("Evidence?part=glance");
  // The proposals waiting for a person, scrolled to (UX1): "Evidence" alone reloaded the evidence page in place.
  if (index === 3) return inCase(`Possible causes?part=${AI_PROPOSALS_PART}`);
  if (index === 4) return inCase("Brief?part=brief");
  if (index === 5) return inCase("Decision & action?part=decision");
  return run.capa
    ? { section: "Records", tab: `Effectiveness checks?${new URLSearchParams({ capa: run.capa.id })}` }
    : { section: "Records", tab: "Effectiveness checks" };
}

/** G-06: the flagship signal in the trend check's own numbers (the figures Home shows), as complaints a month before
 * and after (owner, 17 Nov 2026), from the product's strongest rising row; without a trend row, no number. */
export function signalWhy(
  items:
    ReadonlyArray<{ product: { id: string }; ratio: number | null } & Parameters<typeof monthlyRates>[0]> | undefined,
  productId: string | null | undefined,
): string {
  const rows = (items ?? []).filter((row) => row.product.id === productId && typeof row.ratio === "number");
  const top = rows.reduce<(typeof rows)[number] | null>(
    (best, row) => (!best || (row.ratio as number) > (best.ratio as number) ? row : best),
    null,
  );
  const rates = top ? monthlyRates(top) : null;
  const lead = rates
    ? `Pressure-alarm complaints on one pump went from ${monthlyText(rates).replace(" → ", " to ")} a month after Rev B.`
    : "Pressure-alarm complaints on one pump are rising after Rev B.";
  return `${lead} A rise like this starts an investigation.`;
}

/** E3 + W6: the signed decision's summary and record, leading the cockpit's Decision & action step. */
export const summaryPlace = (run: FlagshipRun): FlagshipPlace => ({
  section: "Investigations",
  tab: "Decision & action?part=summary",
  caseId: run.investigation.id,
  productId: run.product.id,
});

/** The optional branch (W1): is SAMPLE-RV-06 reportable in each market? Its US decision tree. */
export const branchPlace = (run: FlagshipRun): Place | null =>
  run.branch ? treePlace("US", run.branch.complaint_id) : null;

/** Open a flagship step's screen at once; steps 1 to 3 are remembered and their mark saved once the screen loads. */
export function openFlagshipStep(
  run: FlagshipRun,
  index: number,
  open: (section: any, tab?: string) => void,
  setCase?: (id: string, productId?: string | null) => void,
): void {
  const mark = MARKED.flagship[index];
  const place = flagshipPlace(run, index);
  pendingVisit = mark
    ? {
        run: "flagship",
        step: mark,
        complaintId: run.investigation.id,
        reportId: null,
        product: run.product.ref,
        version: run.product.version,
      }
    : null;
  if (place.caseId) setCase?.(place.caseId, place.productId);
  open(place.section, place.tab);
}

const RESULT_WORDS: Record<string, string> = {
  EFFECTIVE: "effective",
  NOT_EFFECTIVE: "not effective",
  INCONCLUSIVE: "inconclusive",
};

/** "Did it work?" from the records: the signed result, else too early (a person signs it, never MDARIX). */
export function didItWorkLine(capa: FlagshipRun["capa"]): string {
  const word = RESULT_WORDS[capa?.check_status ?? ""];
  return word
    ? `Did it work? Signed: ${word}`
    : "Did it work? Too early: only a signed effectiveness check says an action worked";
}

/** W1d (D04): step 7's effectiveness journey, planned -> synthetic follow-up -> signed, each read from the records. */
export function effectivenessStages(capa: FlagshipRun["capa"]): { label: string; done: boolean }[] {
  const signed = RESULT_WORDS[capa?.check_status ?? ""];
  return [
    { label: "Check planned", done: !!capa?.check_planned },
    { label: "Synthetic follow-up (sample) to review", done: !!capa?.follow_up || !!signed },
    { label: signed ? `Signed by a person: ${signed}` : "Result signed by a person", done: !!signed },
  ];
}

/** The part of the cockpit's Possible causes step that holds the AI proposals waiting for a person (UX1, UX3). */
export const AI_PROPOSALS_PART = "ai-proposals";

/** The flagship step a screen shows (UX1): the bar says the step you are on, not the steps done plus one. Null for a
 * screen that is no step's own. ``tab`` is the screen's tab with its parameters ("Brief?part=brief"); a former
 * section's address reads as the cockpit step it opens (cockpitStep, UX3). */
export function flagshipStepOn(section: string, tab: string | null | undefined): number | null {
  const [name, query = ""] = (tab ?? "").split("?");
  const params = new URLSearchParams(query);
  if (section === "Trends") return 0;
  if (section === "Product 360") return 1;
  if (section === "Records") return 6;
  if (section !== "Investigations") return null;
  const place = cockpitStep(name, params.get("part"), params.get("view"));
  if (place?.section === "Evidence") return 2;
  if (place?.section === "Possible causes") return 3;
  if (place?.section === "Brief") return place.part === "brief" ? 4 : null;
  if (place?.section === "Decision & action") return place.part === "decision" ? 5 : null;
  return null;
}

/** The bar's link to the step to do now (UX1): with AI off, step 4 reviews the proposals recorded with the sample. */
export const flagshipNextLabel = (run: FlagshipRun, aiReady: boolean | null) =>
  run.current === 3 && aiReady !== true ? "Review the recorded proposals" : `Next: ${run.steps[run.current].label}`;

/** "Step 4 of 7", or "All seven steps done" (W1). */
export const flagshipCount = (run: FlagshipRun) =>
  run.finished ? "All seven steps done" : `Step ${run.current + 1} of ${FLAGSHIP_STEPS}`;

/** "Step 4 of 10", or "All ten steps done". */
export const stepCount = (run: StoryRun) =>
  run.finished ? "All ten steps done" : `Step ${run.current + 1} of ${STORY_STEPS}`;
