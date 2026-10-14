// Sentence starters for the reasons people write on the second look and the reportability watch: one click starts the
// sentence, the person finishes it in their own words. A starter alone is never a reason: inspectors cite rationales
// that are boilerplate, so a reason must add at least STARTER_MIN_EXTRA characters of its own to the starter it began
// with. Decisions that are signed (the case decision) and review outcomes take no starters: they are written whole.

export const STARTER_MIN_EXTRA = 10;

export const SECOND_LOOK_STARTERS: Record<"CONFIRMED" | "DISMISSED", readonly string[]> = {
  CONFIRMED: [
    "Meets our complaint definition because ",
    "A complaint: the record reports harm when ",
    "A complaint: the device did not perform as intended when ",
  ],
  DISMISSED: [
    "Not a complaint because ",
    "A duplicate of complaint ",
    "A question about use, with no sign of a device problem: ",
  ],
};

export const REPORTABILITY_STARTERS: Record<"REPORTED" | "NOT_REPORTABLE", readonly string[]> = {
  REPORTED: [
    "Reportable: the device may have caused or contributed to ",
    "Reportable malfunction: if it recurred it would be likely to cause or contribute to a death or serious injury because ",
  ],
  NOT_REPORTABLE: [
    "Not reportable: no death or serious injury, and a recurrence would not be likely to cause or contribute to one because ",
    "Not reportable: the device did not cause or contribute to the event because ",
  ],
};

/** Why a reason that begins with a starter cannot be sent yet (too little of the person's own words), or null. */
export function starterProblem(text: string, starters: readonly string[]): string | null {
  const value = text.trim();
  for (const starter of starters) {
    const base = starter.trim();
    if (value.startsWith(base) && value.length - base.length < STARTER_MIN_EXTRA)
      return "Finish the sentence in your own words: what in this record shows it?";
  }
  return null;
}
