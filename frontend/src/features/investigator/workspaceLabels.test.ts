import { describe, expect, it } from "vitest";
import { pointInTimeText, searchStatusText, stateText, workspaceNote, workspaceNotes } from "./workspaceLabels";

describe("the case Workspace tab in plain words", () => {
  it("never shows a limitation's code", () => {
    const notes = workspaceNotes([
      { code: "NO_CAUSAL_CONCLUSION", description: "Product 360 shows lifecycle context only." },
      { code: "NO_DIRECT_EVIDENCE", description: "No direct evidence records are attached." },
      { code: "NO_RELEVANT_EVIDENCE", description: "Trusted retrieval did not return complete contextual evidence." },
      { code: "NO_INVESTIGATION_CONCLUSION", description: "Workspace presents context only." },
      { code: "NO_ROOT_CAUSE", description: "" },
    ]);
    expect(notes.map((note) => note.title)).toEqual([
      "MDARIX does not decide the root cause",
      "No evidence on this investigation yet",
      "No matching evidence found yet",
      "The conclusion stays with people",
    ]);
    for (const note of notes) expect(`${note.title} ${note.text}`).not.toMatch(/[A-Z]{2,}_[A-Z]/);
    expect(workspaceNote({ code: "SOME_NEW_CODE", description: "Said by the server." })).toEqual({
      title: "Some new code",
      text: "Said by the server.",
    });
  });

  it("says what the search found and which records are shown", () => {
    expect(searchStatusText("NO_RELEVANT_EVIDENCE")).toBe("No matching evidence yet");
    expect(searchStatusText(null)).toBe("Not searched yet");
    // A case with its own evidence is not told it has none when the search for more finds nothing.
    expect(searchStatusText("NO_RELEVANT_EVIDENCE", 3)).toBe("No further matching records");
    expect(workspaceNote({ code: "NO_RELEVANT_EVIDENCE" }, 3).title).toBe("No further matching records");
    expect(pointInTimeText("current")).toBe("Today's records");
    expect(pointInTimeText("event", "2026-10-01T00:00:00Z")).toBe("As it happened on 2026-10-01");
    expect(stateText("READY_FOR_REVIEW", "x")).toBe("Ready for review");
    expect(stateText(null, "Not run")).toBe("Not run");
  });
});
