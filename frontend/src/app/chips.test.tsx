import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeadlineChip, HarmChip, StateChip, deadlineUrgency } from "./chips";
import { StatusBadge } from "../features/workspace/sections/common";

const now = new Date("2026-11-02T06:00:00Z");
const html = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("the three kinds of label (V1-V4)", () => {
  it("a deadline says its time left in words with an icon; only overdue is red", () => {
    const overdue = html(<DeadlineChip item={{ due_at: "2026-10-30T18:29:00Z", state: "OVERDUE" }} now={now} />);
    expect(overdue).toContain("is-overdue");
    expect(overdue).toContain("2 days overdue");
    expect(overdue).toContain("<svg");
    const soon = html(<DeadlineChip item={{ due_at: "2026-11-02T12:00:00Z", state: "RUNNING" }} now={now} />);
    expect(soon).toContain("is-soon");
    expect(soon).toContain("6 h left");
    const later = html(<DeadlineChip item={{ due_date: "2026-11-20" }} prefix="Report" now={now} />);
    expect(later).toContain("is-later");
    expect(later).toMatch(/Report: 1[78] days left/);
    expect(html(<DeadlineChip item={{}} now={now} />)).toBe("");
  });

  it("reads urgency from the one time-left text", () => {
    expect(deadlineUrgency("3 days overdue")).toBe("overdue");
    expect(deadlineUrgency("Overdue")).toBe("overdue");
    expect(deadlineUrgency("Due today")).toBe("soon");
    expect(deadlineUrgency("5 h left")).toBe("soon");
    expect(deadlineUrgency("1 day left")).toBe("later");
  });

  it("a state is neutral, whatever the state", () => {
    expect(html(<StateChip label="Rejected" />)).toBe('<span class="ms-chip ms-chip-state">Rejected</span>');
    expect(html(<StatusBadge value="REJECTED" />)).toContain("ms-chip-state");
    expect(html(<StatusBadge value="closed" />)).toContain(">Closed<");
  });

  it("a harm is outlined with its shape, so it never relies on colour", () => {
    expect(html(<HarmChip harm="critical" label="Death recorded" />)).toContain("◆");
    expect(html(<HarmChip harm="serious" label="Serious injury recorded" />)).toContain("▲");
    expect(html(<HarmChip harm="none" label="Malfunction" />)).toContain("○");
    expect(html(<StatusBadge value="HIGH" />)).toContain("▲");
    expect(html(<StatusBadge value="CRITICAL" />)).toContain("◆");
  });
});
