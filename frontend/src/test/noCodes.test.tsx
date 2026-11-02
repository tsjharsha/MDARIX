import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "../features/workspace/workspaceContext";
import sample from "./sampleScreens.json";

/*
 * Names, not codes (stage 5, J18, V2): the main screens rendered with the sample trial's own API answers
 * (sampleScreens.json: recorded from a trial seeded with the sample, 0.10.66, the reworded RV-08 request as
 * refresh_trial_story.py leaves it) show no code (UPPER_SNAKE), no market question code (US2A) and no raw id.
 *
 * The one exception is the customer's own data: a complaint's problem code is shown as their system recorded it
 * (the sample's SPO2_DROPOUT_HARM), so the problem codes in the answers are allowed.
 */
const answers = sample as Record<string, unknown>;

vi.mock("../features/customer-admin/shared", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/customer-admin/shared")>();
  return {
    ...actual,
    useResource: (path: string | null) => ({
      data: path ? (answers[path] ?? null) : null,
      error: null,
      state: path && answers[path] ? "ready" : "loading",
      reload: vi.fn(),
    }),
  };
});

const { Triage } = await import("../features/workspace/sections/Triage");
const { OversightView } = await import("../features/workspace/sections/Oversight");
const { ReadinessSection } = await import("../features/workspace/sections/Readiness");
const { Communications, EntryDrawer } = await import("../features/workspace/sections/Communications");
const { DecisionGuides, GuideDrawer } = await import("../features/workspace/sections/DecisionGuides");
const { ReportabilityWatch } = await import("../features/workspace/sections/ReportabilityWatch");
const { RemindersPanel } = await import("../features/workspace/sections/Reminders");

const PERMISSIONS = [
  "records.read",
  "records.write",
  "regulatory.review",
  "quality.review",
  "data.export",
  "signals.triage",
  "complaints.triage",
];

function workspace(): WorkspaceApi {
  return {
    session: {
      allowed_menu: ["products", "investigations", "complaints", "signals", "records", "readiness"],
      business_permissions: PERMISSIONS,
      roles: ["QUALITY_MANAGER"],
    },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [], requestOpenInvestigation: vi.fn() },
  } as unknown as WorkspaceApi;
}

/** The text a person reads: the markup without its tags and attributes. */
const visibleText = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace()}>{node}</WorkspaceContext.Provider>)
    .replace(/<[^>]*>/g, " ")
    .replace(/&[a-z#0-9]+;/g, " ");

const problemCodes = new Set<string>();
JSON.stringify(sample, (key, value) => {
  if (key === "problem_code" && typeof value === "string") problemCodes.add(value);
  return value;
});

const CODE = /\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/g;
const QUESTION = /\b(?:US|GB|IN|EU_NI)\d+[A-Z]?\b/g;
const RAW_ID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b[0-9a-f]{32}\b/g;

const found = (text: string) => [
  ...new Set([
    ...(text.match(CODE) ?? []).filter((code) => !problemCodes.has(code)),
    ...(text.match(QUESTION) ?? []),
    ...(text.match(RAW_ID) ?? []),
  ]),
];

const SCREENS: Array<[string, ReactNode]> = [
  ["Complaints › Triage", <Triage onOpenTab={() => undefined} />],
  ["Complaints › Reportability", <ReportabilityWatch onOpenTab={() => undefined} />],
  ["Complaints › Communications", <Communications />],
  ["Complaints › Decision guides", <DecisionGuides />],
  ["Readiness › Inspection checks", <ReadinessSection tab="Inspection checks" />],
  ["Readiness › Oversight", <OversightView />],
  ["My Work › Reminders", <RemindersPanel />],
  ["Drawer: a decision guide version", <GuideDrawer market="US" version={3} onClose={() => undefined} />],
  ["Drawer: a communication", <EntryDrawer id="7acec452-a15d-42e3-a0f5-8cdbac11a795" onClose={() => undefined} />],
];

describe("names, not codes, on the main screens with the sample (J18)", () => {
  it("has the sample's answers to render", () => {
    expect(Object.keys(answers).length).toBeGreaterThan(10);
    expect(problemCodes.has("SPO2_DROPOUT_HARM")).toBe(true);
  });

  it.each(SCREENS)("%s shows no code or raw id", (_name, node) => {
    const text = visibleText(node);
    expect(text.trim().length).toBeGreaterThan(200); // the screen rendered its data, not a loading line
    expect(found(text)).toEqual([]);
  });

  it("would catch a code, a market question code and a raw id", () => {
    expect(found("Trigger NEW_FAILURE_MODE on EU_NI; US2A; 7acec452-a15d-42e3-a0f5-8cdbac11a795")).toEqual([
      "NEW_FAILURE_MODE",
      "EU_NI",
      "US2A",
      "7acec452-a15d-42e3-a0f5-8cdbac11a795",
    ]);
  });
});
