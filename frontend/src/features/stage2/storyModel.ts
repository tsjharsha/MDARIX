import { titleCase, type Tone } from "../admin/console/dashboardModel";

/*
 * One stage of an investigation's story (GET /api/v1/story/{id}): AVAILABLE when the case has records for it,
 * COMPLETE only for a decision with a valid signature, PENDING when nothing is recorded yet. A stage is never
 * "reviewed" by the story itself: review happens in the decision, so no other state is shown.
 */
export type StoryStage = { key: string; label: string; status: string; count?: number };

const STATUS: Record<string, { label: string; tone: Tone }> = {
  COMPLETE: { label: "Complete", tone: "good" },
  AVAILABLE: { label: "Records available", tone: "neutral" },
  PENDING: { label: "Pending", tone: "warning" },
};

/** The stage's state in words with its tone, and how many records it has. */
export function storyStage(stage: StoryStage): { label: string; tone: Tone; records: string } {
  const known = STATUS[String(stage.status ?? "").toUpperCase()];
  const count = typeof stage.count === "number" && stage.count >= 0 ? stage.count : 0;
  return {
    // A state this screen does not know is shown as the server named it, never as one of the three above.
    label: known?.label ?? (stage.status ? titleCase(String(stage.status)) : "Unknown"),
    tone: known?.tone ?? "neutral",
    records: count === 1 ? "1 record" : `${count} records`,
  };
}

/** "5 of 13 stages have records; the decision is signed" for the story's summary line. */
export function storySummary(stages: StoryStage[]): string {
  const withRecords = stages.filter((stage) => ["AVAILABLE", "COMPLETE"].includes(String(stage.status).toUpperCase()));
  const signed = stages.some((stage) => stage.key === "decision" && String(stage.status).toUpperCase() === "COMPLETE");
  return `${withRecords.length} of ${stages.length} stages have records; ${
    signed ? "the decision is signed" : "no signed decision yet"
  }.`;
}
