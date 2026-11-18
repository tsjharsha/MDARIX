// UX3 (Persona Blueprint wave C): the investigation cockpit's summary strip and its 6-step rail.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Cockpit, cockpitFigures } from "./sections/Cockpit";
import { caseSteps } from "./caseWorkflow";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

beforeEach(() => {
  resources.data = {};
});

const link = (relation: string, ref: string) => ({ relation, evidence: { business_id: ref, title: ref } });
const HYPOTHESES = [
  {
    id: "h1",
    origin: "HUMAN",
    statement: "NovaSense sensor drift",
    human_status: "STRONGLY_SUPPORTED",
    evidence: [link("SUPPORTING", "EV-1"), link("SUPPORTING", "EV-2")],
  },
  {
    id: "h2",
    origin: "HUMAN",
    statement: "User error",
    human_status: "WEAKLY_SUPPORTED",
    evidence: [link("CONTRADICTING", "EV-3")],
  },
  { id: "h3", origin: "AI", statement: "Firmware", human_status: "PROPOSED", evidence: [] },
  { id: "h4", origin: "HUMAN", statement: "Shipping damage", human_status: "RETIRED", evidence: [] },
];
const UNKNOWNS = [
  { id: "u1", business_id: "UNK-1", description: "Sensor lot of the field units", status: "open" },
  { id: "u2", business_id: "UNK-2", description: "Done", status: "resolved" },
];
const READINESS = {
  steps: [
    { key: "evidence", status: "DONE" },
    { key: "gaps", status: "IN_PROGRESS" },
    { key: "brief", status: "NOT_STARTED" },
    { key: "human_review", status: "NOT_STARTED" },
  ],
  checks: [
    { key: "unknowns_resolved", label: "Open unknowns resolved or accepted", result: "BLOCKED" },
    { key: "brief_ready", label: "Brief accepted for decision", result: "PENDING" },
    { key: "decision", label: "Decision signed", result: "PENDING" },
    { key: "evidence", label: "Evidence reviewed", result: "PASS" },
  ],
};

describe("the cockpit's summary strip", () => {
  it("counts evidence for, against and missing, the causes still considered, and what blocks the decision", () => {
    const figures = cockpitFigures({
      hypotheses: HYPOTHESES as never,
      unknowns: UNKNOWNS as never,
      readiness: READINESS as never,
    });
    // For: records a person linked in support (AI links never count); against: explanations with a record against them.
    expect(figures.evidenceFor).toBe(2);
    expect(figures.evidenceAgainst).toBe(1);
    // Missing: open questions (resolved ones are not) and unshown chain links.
    expect(figures.evidenceMissing).toBe(1);
    // Retired explanations are no longer considered; leading = strongly supported by a person.
    expect(figures.causes).toBe(3);
    expect(figures.leading).toBe(1);
    // The decision's own check is not a blocker of itself.
    expect(figures.blocking).toEqual({ count: 2, first: "Open unknowns resolved or accepted" });
  });

  it("shows each figure with its definition, one primary next step and the 6-step rail with the shown step marked", () => {
    const base = "/api/v1/investigations/i1/intelligence";
    resources.data[`${base}/hypotheses`] = { items: HYPOTHESES };
    resources.data[`${base}/unknowns`] = { items: UNKNOWNS };
    const html = renderToStaticMarkup(
      <Cockpit
        investigationId="i1"
        steps={caseSteps(READINESS as never)}
        readiness={READINESS as never}
        active="Evidence"
        onSection={vi.fn()}
      />,
    );
    expect(html).toContain("2 for · 1 against · 1 missing");
    expect(html).toContain("3, 1 leading");
    expect(html).toContain("2 open checks");
    expect(html).toContain("First: Open unknowns resolved or accepted.");
    expect(html).toContain("Leading: judged strongly supported by a person; never a concluded root cause.");
    // One main button: the next step.
    expect(html.split('class="ac-primary"').length - 1).toBe(1);
    expect(html).toMatch(/class="ac-primary"[^>]*>Next: /);
    // The rail: six steps in order, the one shown marked, Product reality read (never "Done").
    const rail = html.slice(html.indexOf('aria-label="Investigation steps"'));
    const names = ["Signal", "Product reality", "Evidence", "Possible causes", "Brief", "Decision &amp; action"];
    const at = names.map((name) => rail.indexOf(name));
    expect(at.every((value, index) => value > 0 && (!index || value > at[index - 1]))).toBe(true);
    expect(rail).toMatch(/aria-current="step"[^>]*><strong><span class="uw-num">3<\/span> Evidence/);
    expect(rail).toContain("Versions, changes, lots");
    expect(html).not.toContain('role="tablist"');
  });

  it("once the decision is signed, the one button opens the decision and its follow-up", () => {
    const signed = { steps: [{ key: "human_review", status: "DONE" }], checks: [] };
    const html = renderToStaticMarkup(
      <Cockpit
        investigationId="i1"
        steps={caseSteps(signed as never)}
        readiness={signed as never}
        onSection={vi.fn()}
      />,
    );
    expect(html).toContain("See the decision and its follow-up");
    expect(html).toContain("Nothing");
  });
});
