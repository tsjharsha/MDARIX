import { ArrowLeft, ChevronRight, ListChecks } from "lucide-react";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import {
  FLAGSHIP_STEPS,
  LOT_005_LINE,
  flagshipCount,
  flagshipNextLabel,
  flagshipStepOn,
  openFlagshipStep,
  useOneStory,
  type FlagshipRun,
} from "../oneStory";
import { useAiReady } from "../useAiStatus";
import { REGISTER_LINK, registerTab, type RegisterPart } from "./SampleRegister";

/** The bar's words (exported for its test): product · version · case · step, or the optional branch. ``on``: the step
 * the screen shows (UX1), else the step to do now. */
export function flagshipBarParts(run: FlagshipRun, branch = false, on: number | null = null): string[] {
  if (branch) return ["Optional branch", run.branch?.ref ?? "SAMPLE-RV-06"];
  const version =
    run.product.version_state === "UNVERIFIED" || !run.product.version ? "Version not verified" : run.product.version;
  return [
    run.product.label ?? run.product.name ?? run.product.ref ?? "Product",
    version,
    run.investigation.ref,
    on === null || run.finished ? flagshipCount(run) : `Step ${on + 1} of ${FLAGSHIP_STEPS}`,
  ];
}

/** W1e: the register section that answers the figures on each flagship screen (the trend, Rev B against Rev A, the
 * evidence, the effectiveness check). */
const SECTION_PART: Record<string, RegisterPart> = {
  Trends: "trend",
  "Product 360": "change",
  Investigations: "evidence",
  Records: "follow-up",
};

/**
 * The flagship story's bar (W1), in the legacy story bar's slot while the flagship is under way: "OrbitCare 300 · Rev B ·
 * SAMPLE-INV-001 · Step 1 of 7", a Next link to the next step's screen, and Back to Getting started. On the optional
 * branch: "Optional branch · SAMPLE-RV-06". Its step is the server's (the saved records), never this screen's.
 */
export function FlagshipBar({ section, branch = false }: { section: string; branch?: boolean }) {
  const { open, work, shownTab } = useWorkspace();
  const run = useOneStory(section !== "Getting started").data?.flagship ?? null;
  // Asked only while step 4 is next: its link says what happens with AI on or off.
  const aiReady = useAiReady(run?.current === 3);
  if (!run || section === "Getting started") return null;
  // The evidence page is where step 4's proposals are reviewed: on it, while step 4 is next, the bar says step 4.
  const at = flagshipStepOn(section, shownTab);
  const on = at === 2 && run.current === 3 ? 3 : at;
  return (
    <>
      <nav className="uw-story-bar uw-flagship-bar" aria-label="The sample investigation">
        <span className="uw-story-title">
          {flagshipBarParts(run, branch, on).map((part, index) => (
            <span key={part}>
              {index > 0 && " · "}
              {index === 0 ? <b>{part}</b> : part}
            </span>
          ))}
        </span>
        <span className="uw-story-actions">
          {!branch && !run.finished && (
            <button
              type="button"
              className="ac-link"
              onClick={() =>
                openFlagshipStep(run, run.current, (s, t) => open(s as WorkspaceSection, t), work.setInvestigationId)
              }
            >
              {flagshipNextLabel(run, aiReady)} <ChevronRight size={14} aria-hidden="true" />
            </button>
          )}
          {!branch && (
            <button
              type="button"
              className="ac-link"
              onClick={() => open("Getting started", registerTab(SECTION_PART[section]))}
            >
              <ListChecks size={14} aria-hidden="true" /> {REGISTER_LINK}
            </button>
          )}
          <button type="button" className="ac-link" onClick={() => open("Getting started")}>
            <ArrowLeft size={14} aria-hidden="true" /> Back to Getting started
          </button>
        </span>
      </nav>
      {/* The trend names lot 005 too: said where it shows (W1 open item 2). */}
      {section === "Trends" && !branch && <p className="ac-note">{LOT_005_LINE}</p>}
    </>
  );
}
