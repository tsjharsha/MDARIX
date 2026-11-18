import { describe, expect, it } from "vitest";
import {
  EMPTY_TIMELINE_FILTERS,
  actorOptions,
  aiModelText,
  aiRunCountsText,
  aiRunKindLabel,
  aiRunStatus,
  aiVersionText,
  auditChainView,
  briefHashRows,
  categoryChips,
  categoryClass,
  categoryLabel,
  chipCounts,
  dateRangeProblem,
  durationText,
  eventActor,
  eventMatches,
  eventObject,
  eventOrigin,
  eventTitle,
  guardrailItems,
  guardrailSummary,
  humanReviewView,
  initialTrustTab,
  integrityHeadline,
  isoFromLocalInput,
  knownSplit,
  localInputValue,
  objectTarget,
  originView,
  pageCount,
  parseTrustTab,
  replayDecisionOptions,
  replayIntegrity,
  replayItem,
  replayPath,
  sentence,
  signatureRows,
  signerText,
  timelinePath,
  timelineQuery,
  toggleCategory,
  trustExportName,
  trustExportPath,
  trustPath,
  trustTab,
  usageText,
  type TimelineEvent,
} from "./caseAudit";
import type { HistoryRow } from "./humanDecision";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";
const CASE = "1c6f8f9e-1111-4222-8333-444455556666";

const historyRow = (patch: Partial<HistoryRow>): HistoryRow => ({
  key: "k",
  id: UUID,
  businessId: "DEC000001",
  outcome: "Accept conclusion",
  outcomeTone: "good",
  status: "Current",
  statusTone: "good",
  current: true,
  decidedAt: "2026-10-01T10:00:00Z",
  signer: "Dana Lee",
  signerRole: "APPROVER",
  supersedes: null,
  supersededBy: null,
  ...patch,
});

describe("addresses", () => {
  it("builds the trust paths of a case, encoded", () => {
    expect(trustPath(CASE, "timeline")).toBe(`/api/v1/investigations/${CASE}/trust/timeline`);
    expect(trustPath("a/b", "integrity")).toBe("/api/v1/investigations/a%2Fb/trust/integrity");
    expect(trustExportPath(CASE, "csv")).toBe(`/api/v1/investigations/${CASE}/trust/export?format=csv`);
  });

  it("names an exported audit trail after the case, never after nothing", () => {
    expect(trustExportName("INV000147", "json")).toBe("INV000147-audit-trail.json");
    expect(trustExportName("Selected investigation", "csv")).toBe("Selected-investigation-audit-trail.csv");
    expect(trustExportName("", "csv")).toBe("investigation-audit-trail.csv");
    expect(trustExportName("../..", "csv")).toBe("investigation-audit-trail.csv");
  });
});

describe("the Trust & Audit tabs", () => {
  it("opens on the case timeline when a case is chosen and nothing else was asked for", () => {
    expect(initialTrustTab(null, true)).toBe("Investigation timeline");
    expect(initialTrustTab(null, false)).toBe("AI assurance");
    expect(initialTrustTab("Audit trail", true)).toBe("Audit trail");
  });

  it("links to a tab for one case and reads the link back", () => {
    const tab = trustTab({ caseId: CASE, caseLabel: "INV000147" });
    expect(tab).toBe(`Investigation timeline?case=${CASE}&label=INV000147`);
    expect(parseTrustTab(tab)).toEqual({ tab: "Investigation timeline", caseId: CASE, caseLabel: "INV000147" });
    // A link from before 0.10.93 still opens the timeline, with its case and label.
    expect(parseTrustTab(`Case timeline?case=${CASE}&label=INV000147`)).toEqual({
      tab: "Investigation timeline",
      caseId: CASE,
      caseLabel: "INV000147",
    });
    expect(trustTab()).toBe("Investigation timeline");
    expect(trustTab({ tab: "Replay" })).toBe("Replay");
  });

  it("ignores unknown tabs and unsafe references", () => {
    expect(parseTrustTab("AI assurance")).toEqual({ tab: "AI assurance", caseId: null, caseLabel: null });
    expect(parseTrustTab("Nope")).toEqual({ tab: null, caseId: null, caseLabel: null });
    expect(parseTrustTab(undefined).tab).toBeNull();
    expect(parseTrustTab("Replay?case=<script>&label=INV1")).toEqual({ tab: "Replay", caseId: null, caseLabel: null });
    expect(trustTab({ caseId: CASE, caseLabel: "Selected investigation" })).toBe(`Investigation timeline?case=${CASE}`);
  });
});

describe("timeline categories and origins", () => {
  it("labels known categories and reads unknown ones", () => {
    expect(categoryLabel("FOLLOW_UP")).toBe("Follow-up");
    expect(categoryLabel("request")).toBe("Evidence request");
    expect(categoryLabel("NEW_THING")).toBe("New Thing");
    expect(categoryLabel(null)).toBe("Other");
    expect(categoryClass("FOLLOW_UP")).toBe("ta-cat-follow-up");
    expect(categoryClass("whatever")).toBe("ta-cat-other");
  });

  it("never lets an AI event read as a person's act", () => {
    expect(eventOrigin({ origin: "AI" })).toBe("AI");
    expect(eventOrigin({ origin: null, category: "AI" })).toBe("AI");
    expect(eventOrigin({ origin: "HUMAN" })).toBe("HUMAN");
    expect(eventOrigin({ origin: "SYSTEM" })).toBe("SYSTEM");
    expect(eventOrigin({ origin: "", category: "CASE" })).toBeNull();
    expect(originView({ origin: "AI" }).label).toBe("AI");
    expect(originView({ origin: "AI" }).style).toBe("ai");
    expect(originView({ origin: "HUMAN" }).label).toBe("Person");
    expect(originView({ origin: "SYSTEM" }).label).toBe("System");
    expect(originView({}).label).toBe("Origin not recorded");
  });
});

describe("how an event reads", () => {
  it("uses the server's title, else the event code as words, else the category", () => {
    expect(eventTitle({ title: "Decision signed by Dana" })).toBe("Decision signed by Dana");
    expect(eventTitle({ title: UUID, event: "DECISION_SIGNED" })).toBe("Decision signed");
    expect(eventTitle({ category: "SCOPE" })).toBe("Scope event");
    expect(sentence("brief.approved")).toBe("Brief approved");
    expect(sentence("Already words")).toBe("Already words");
    expect(sentence("DECIDED")).toBe("Decided");
    expect(sentence("Signed")).toBe("Signed");
  });

  it("names the actor and role, or AI / MDARIX when no person is recorded", () => {
    expect(eventActor({ actor: { name: "Dana Lee", role_label: "APPROVER" } })).toEqual({
      name: "Dana Lee",
      role: "Decision Maker",
    });
    expect(eventActor({ actor: { name: "Dana Lee", role_label: "Quality lead" } }).role).toBe("Quality lead");
    expect(eventActor({ actor: null, origin: "AI" }).name).toBe("AI");
    expect(eventActor({ actor: null, origin: "SYSTEM" }).name).toBe("MDARIX");
    expect(eventActor({ actor: { name: UUID } }).name).toBe("Not recorded");
  });

  it("shows a linked record by its business ID, never its UUID, and knows where it opens", () => {
    expect(eventObject({ object: { type: "DECISION", id: UUID, business_id: "DEC000004" } })).toEqual({
      label: "DEC000004",
      typeLabel: "Decision",
      target: { kind: "decision", id: UUID },
    });
    expect(eventObject({ object: { type: "REVIEW", id: UUID, business_id: null } })?.label).toBe("Review");
    expect(eventObject({ object: null })).toBeNull();
    expect(eventObject({ object: { type: "SIGNAL" } })).toBeNull();
  });

  it("routes each kind of record to its screen", () => {
    expect(objectTarget({ type: "SIGNAL", id: UUID, business_id: "SIG000023" })).toEqual({
      kind: "section",
      section: "Signals",
      tab: "Signal inbox?signal=SIG000023",
    });
    expect(objectTarget({ type: "REVIEW", id: UUID })).toEqual({
      kind: "section",
      section: "Investigations",
      tab: `Reviews?review=${UUID}`,
    });
    expect(objectTarget({ type: "DECISION_BRIEF", business_id: "DB000002" })).toEqual({
      kind: "section",
      section: "Investigations",
      tab: "Decision Brief",
    });
    expect(objectTarget({ type: "TASK", id: UUID })).toEqual({ kind: "section", section: "My Work" });
    expect(objectTarget({ type: "FOLLOW_UP", id: UUID })).toEqual({
      kind: "section",
      section: "Investigations",
      tab: `Decision?follow_up=${UUID}`,
    });
    expect(objectTarget({ type: "IMPACT_ASSESSMENT", id: UUID })).toEqual({
      kind: "section",
      section: "Investigations",
      tab: `Decision?assessment=${UUID}`,
    });
    expect(objectTarget({ type: "EVIDENCE_REQUEST", id: UUID })).toEqual({
      kind: "section",
      section: "My Work",
      tab: `Evidence requests?request=${UUID}`,
    });
    expect(objectTarget({ type: "HYPOTHESIS", id: UUID })).toEqual({
      kind: "section",
      section: "Investigations",
      tab: "Intelligence?view=Hypotheses",
    });
    expect(objectTarget({ type: "DECISION", business_id: "DEC000001" })).toBeNull();
    expect(objectTarget({ type: "SIGNATURE", id: UUID })).toBeNull();
  });

  it("searches what is shown, never the UUIDs behind it", () => {
    const event: TimelineEvent = {
      title: "Evidence linked",
      category: "EVIDENCE",
      actor: { name: "Ana Ruiz", role_label: "Investigator" },
      object: { type: "EVIDENCE", id: UUID, business_id: "EVD000010" },
      reason: "Supplier report received",
      origin: "HUMAN",
    };
    expect(eventMatches(event, "")).toBe(true);
    expect(eventMatches(event, "evd000010")).toBe(true);
    expect(eventMatches(event, "ruiz")).toBe(true);
    expect(eventMatches(event, "supplier")).toBe(true);
    expect(eventMatches(event, "0b6f8f9e")).toBe(false);
  });
});

describe("timeline filters", () => {
  it("turns filters into the query, with whole UTC days", () => {
    const query = new URLSearchParams(
      timelineQuery(
        {
          categories: ["decision", "AI", "AI"],
          actor: " Dana Lee ",
          since: "2026-10-01",
          until: "2026-10-03",
          search: "x",
        },
        2,
      ),
    );
    expect(query.get("types")).toBe("DECISION,AI");
    expect(query.get("actor")).toBe("Dana Lee");
    expect(query.get("since")).toBe("2026-10-01T00:00:00Z");
    expect(query.get("until")).toBe("2026-10-03T23:59:59Z");
    expect(query.get("page")).toBe("2");
    expect(query.get("page_size")).toBe("50");
    expect(query.has("search")).toBe(false);
    expect(timelineQuery(EMPTY_TIMELINE_FILTERS)).toBe("page=1&page_size=50");
    expect(timelinePath(CASE, EMPTY_TIMELINE_FILTERS, 0)).toBe(
      `/api/v1/investigations/${CASE}/trust/timeline?page=1&page_size=50`,
    );
  });

  it("refuses a range that ends before it starts", () => {
    expect(dateRangeProblem({ since: "2026-10-05", until: "2026-10-01" })).toBe(
      "The start date is after the end date.",
    );
    expect(dateRangeProblem({ since: "2026-10-01", until: "2026-10-01" })).toBeNull();
    expect(dateRangeProblem({ since: "", until: "" })).toBeNull();
    expect(dateRangeProblem({ since: "01/10/2026", until: "" })).not.toBeNull();
  });

  it("toggles categories and offers chips with their counts", () => {
    expect(toggleCategory([], "ai")).toEqual(["AI"]);
    expect(toggleCategory(["AI", "CASE"], "AI")).toEqual(["CASE"]);
    const chips = categoryChips({ DECISION: 2, CASE: 5, AI: 0, CUSTOM: 1 }, ["SCOPE"]);
    expect(chips.map((chip) => chip.code)).toEqual(["CASE", "SCOPE", "DECISION", "CUSTOM"]);
    expect(chips.find((chip) => chip.code === "SCOPE")).toMatchObject({ count: 0, selected: true });
    expect(categoryChips(null, []).length).toBe(15);
    expect(categoryChips(null, [])[0].count).toBeNull();
  });

  it("keeps every category chip available once one is chosen", () => {
    const base = { CASE: 5, DECISION: 2 };
    expect(chipCounts(base, { DECISION: 2 }, ["DECISION"])).toEqual({ CASE: 5, DECISION: 2 });
    expect(chipCounts(base, {}, ["AI"])).toEqual({ CASE: 5, DECISION: 2, AI: 0 });
    expect(chipCounts(base, { CASE: 4 }, [])).toEqual({ CASE: 4 });
    expect(chipCounts(null, null, [])).toBeNull();
    expect(chipCounts(null, null, ["AI"])).toBeNull();
  });

  it("collects the people seen and counts pages", () => {
    expect(actorOptions(["Zed"], [{ actor: { name: "Ana" } }, { actor: { name: "Zed" } }, { actor: null }])).toEqual([
      "Ana",
      "Zed",
    ]);
    expect(pageCount(0)).toBe(1);
    expect(pageCount(101)).toBe(3);
    expect(pageCount("x")).toBe(1);
  });
});

describe("replay", () => {
  it("asks for a decision's moment, or a chosen moment", () => {
    expect(replayPath(CASE, { decisionId: UUID })).toBe(
      `/api/v1/investigations/${CASE}/trust/replay?decision_id=${UUID}`,
    );
    expect(replayPath(CASE, { asKnownAt: "2026-10-01T10:00:00.000Z" })).toBe(
      `/api/v1/investigations/${CASE}/trust/replay?as_known_at=2026-10-01T10%3A00%3A00.000Z`,
    );
    expect(replayPath(CASE, {})).toBeNull();
  });

  it("splits records into known then and arrived later", () => {
    expect(knownSplit({ known_then: [{ business_id: "CMP1" }], arrived_later: [{ business_id: "CMP2" }] })).toEqual({
      knownThen: [{ business_id: "CMP1" }],
      arrivedLater: [{ business_id: "CMP2" }],
    });
    expect(knownSplit([{ id: 1 }, { id: 2, arrived_later: true }, { id: 3, known_then: false }])).toEqual({
      knownThen: [{ id: 1 }],
      arrivedLater: [
        { id: 2, arrived_later: true },
        { id: 3, known_then: false },
      ],
    });
    expect(knownSplit(null)).toEqual({ knownThen: [], arrivedLater: [] });
  });

  it("reads a replayed record by its business ID, never a UUID", () => {
    expect(replayItem({ business_id: "CMP000001", title: "Pump alarm", received_at: "2026-09-01" })).toEqual({
      label: "CMP000001",
      detail: "Pump alarm",
      status: null,
      at: "2026-09-01",
    });
    expect(replayItem({ id: UUID, statement: "Seal wear" }).label).toBe("Seal wear");
    expect(replayItem({ id: UUID }).label).toBe("Recorded item");
    expect(replayItem("A limitation").label).toBe("A limitation");
    expect(
      replayItem({ business_id: "HYP000002", statement: "Seal wear", human_status_label: "Supported" }).status,
    ).toBe("Supported");
    expect(replayItem({ business_id: "CMP000003", severity: "HIGH" }).status).toBe("High");
  });

  it("says whether the evidence set changed since then", () => {
    expect(
      replayIntegrity({ evidence_set_hash_then: "a", evidence_set_hash_now: "b", changed_since: true }),
    ).toMatchObject({ state: "changed", tone: "warning", then: "a", now: "b" });
    expect(replayIntegrity({ evidence_set_hash_then: "a", evidence_set_hash_now: "a" }).state).toBe("unchanged");
    expect(replayIntegrity({ evidence_set_hash_then: "a", evidence_set_hash_now: "b" }).state).toBe("changed");
    expect(replayIntegrity(null).state).toBe("unknown");
  });

  it("offers every decision, superseded ones marked", () => {
    expect(
      replayDecisionOptions([
        historyRow({}),
        historyRow({ id: CASE, businessId: "DEC000000", current: false, status: "Superseded" }),
        historyRow({ id: null }),
      ]),
    ).toEqual([
      { id: UUID, label: "DEC000001 · Accept conclusion · current" },
      { id: CASE, label: "DEC000000 · Accept conclusion · superseded" },
    ]);
  });

  it("reads the signer and converts the moment field both ways", () => {
    expect(signerText({ name: "Dana Lee", role_label: "Approver" })).toBe("Dana Lee (Approver)");
    expect(signerText("Dana Lee")).toBe("Dana Lee");
    expect(signerText(null)).toBeNull();
    const local = localInputValue("2026-10-01T10:30:00Z");
    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(isoFromLocalInput(local)).toBe("2026-10-01T10:30:00.000Z");
    expect(localInputValue("not a date")).toBe("");
    expect(isoFromLocalInput("2026-10-01")).toBeNull();
  });
});

describe("AI runs", () => {
  it("labels the kind, status, model and versions", () => {
    expect(aiRunKindLabel({ kind: "HYPOTHESIS_GENERATION" })).toBe("Hypothesis generation");
    expect(aiRunKindLabel({})).toBe("AI run");
    expect(aiRunStatus("SUCCEEDED")).toEqual({ label: "Completed", tone: "good" });
    expect(aiRunStatus("BLOCKED").tone).toBe("serious");
    expect(aiRunStatus(null).label).toBe("Not recorded");
    expect(aiModelText({ model: "claude", model_version: "2026-01", provider: "anthropic" })).toBe(
      "claude · version 2026-01 (anthropic)",
    );
    expect(aiModelText({})).toBe("Not recorded");
    expect(aiVersionText({ prompt_template_version: "p3", orchestration_version: "o2" })).toBe(
      "Prompt p3 · Orchestration o2",
    );
    expect(aiVersionText({})).toBe("Not recorded");
  });

  it("reads guardrails from a list or an object and sums them up", () => {
    expect(guardrailItems({ citations_required: "PASS", no_causal_claims: false })).toEqual([
      { key: "citations_required", label: "Citations required", ok: true, detail: null },
      { key: "no_causal_claims", label: "No causal claims", ok: false, detail: null },
    ]);
    expect(guardrailItems([{ name: "GROUNDED", passed: true, detail: "All cited" }])[0]).toMatchObject({
      label: "Grounded",
      ok: true,
      detail: "All cited",
    });
    expect(guardrailSummary({ a: "PASS", b: "PASS" })).toEqual({ text: "All 2 passed", tone: "good" });
    expect(guardrailSummary({ grounded: "PASS", no_pii: "FAIL" })).toEqual({
      text: "1 of 2 failed: No pii",
      tone: "critical",
    });
    expect(guardrailSummary(null)).toEqual({ text: "Not reported", tone: "neutral" });
    expect(guardrailSummary({ a: "PASS", b: "SOMETHING" }).tone).toBe("warning");
  });

  it("reads the server's guardrail summary form", () => {
    const report = { checks: 4, passed: 3, failed: ["no_causal_claims"], rejected_items: 2, dropped_statements: 0 };
    expect(guardrailSummary(report)).toEqual({
      text: "1 of 4 failed: No causal claims · 2 items rejected",
      tone: "critical",
    });
    expect(guardrailSummary({ checks: 3, passed: 3, failed: [] })).toEqual({ text: "All 3 passed", tone: "good" });
    expect(guardrailSummary({ checks: 0, passed: 0, failed: [] })).toEqual({ text: "Not reported", tone: "neutral" });
    expect(guardrailSummary({ checks: 0, passed: 0, failed: [], error: "Refused" }).text).toBe("Error: Refused");
    expect(guardrailItems(report)).toEqual([
      { key: "failed-0", label: "No causal claims", ok: false, detail: null },
      { key: "passed", label: "3 checks passed", ok: true, detail: null },
      { key: "extra-0", label: "2 items rejected", ok: null, detail: null },
    ]);
  });

  it("shows duration, usage, human review and counts when reported", () => {
    expect(durationText(850)).toBe("850 ms");
    expect(durationText(2500)).toBe("2.5 s");
    expect(durationText(null)).toBeNull();
    expect(usageText({ tokens: 1234, cost: 0.01 })).toBe("1,234 tokens · cost 0.0100");
    expect(usageText({ tokens: { input: 10, output: 5 }, cost: { amount: 0.5, currency: "USD" } })).toBe(
      "15 tokens · 0.5000 USD",
    );
    expect(usageText({})).toBeNull();
    expect(usageText({ input_tokens: 100, output_tokens: 20, estimated_cost: 0.002 })).toBe("120 tokens · cost 0.0020");
    expect(aiRunKindLabel({ kind: "ask" })).toBe("Ask MDARIX question");
    expect(aiRunKindLabel({ kind: "evidence_extraction" })).toBe("Evidence extraction");
    expect(humanReviewView({ status: "ACCEPTED", by: "Ana" })).toMatchObject({
      label: "Reviewed by Ana",
      tone: "good",
    });
    expect(humanReviewView(null)).toMatchObject({ label: "Not reviewed by a person", tone: "warning" });
    expect(humanReviewView({ status: "REJECTED" }).label).toBe("Rejected by a person");
    expect(aiRunCountsText({ COMPLETED: 3, FAILED: 1 })).toBe("Completed 3 · Failed 1");
    expect(aiRunCountsText({ total: 3, by_kind: { ask: 1 }, used_in_signed_decision: 1 })).toBe(
      "Total 3 · Used in signed decision 1",
    );
    expect(aiRunCountsText(null)).toBeNull();
  });
});

describe("integrity", () => {
  it("lists signatures as Valid or Invalid with the failed checks, linked to their decision", () => {
    const rows = signatureRows(
      [
        { business_id: "SIG000001", decision_business_id: "DEC000001", status: "VALID", checks: [] },
        {
          business_id: "SIG000002",
          decision_business_id: "DEC000009",
          status: "INVALID",
          checks: [
            { key: "SIGNATURE_PRESENT", ok: true },
            { key: "BRIEF_HASH", ok: false, detail: "Brief changed" },
          ],
        },
        { business_id: "SIG000003", status: "INVALID", checks: { DECISION_HASH: false, SIGNATURE_PRESENT: true } },
      ],
      [historyRow({})],
    );
    expect(rows[0]).toMatchObject({ label: "Valid", tone: "good", decisionId: UUID, failed: [] });
    expect(rows[1]).toMatchObject({ label: "Invalid", tone: "critical", decisionId: null });
    expect(rows[1].failed.map((check) => check.label)).toEqual(["The brief still matches the content that was signed"]);
    expect(rows[2].failed.map((check) => check.label)).toEqual(["The decision is unchanged since it was signed"]);
    expect(signatureRows(null)).toEqual([]);
  });

  it("reads the audit chain as verified, broken or not checked", () => {
    expect(auditChainView({ status: "VERIFIED", checked_events: 12 })).toMatchObject({
      state: "verified",
      label: "Verified",
      detail: "12 events checked, none changed.",
    });
    expect(
      auditChainView({ status: "BROKEN", first_break: { business_id: "AUD000042", at: "2026-10-01T10:00:00Z" } }),
    ).toMatchObject({ state: "broken", label: "Break found at AUD000042 · 2026-10-01T10:00:00Z", tone: "critical" });
    expect(auditChainView({ status: "NOT_CHECKED", reason: "No audit events yet" })).toMatchObject({
      state: "unchecked",
      detail: "No audit events yet",
    });
    expect(auditChainView(null).state).toBe("unchecked");
    expect(auditChainView({ status: "VALID", checked_events: 1, first_break: null }).label).toBe("Verified");
    expect(auditChainView({ status: "BROKEN", first_break: { plane: "data", seq: 17 } }).label).toBe(
      "Break found at data records · event 17",
    );
  });

  it("checks brief fingerprints and sums up every check", () => {
    expect(briefHashRows([{ business_id: "DB1", version: 2, hash_verified: false }])[0]).toMatchObject({
      businessId: "DB1",
      version: "2",
      tone: "critical",
    });
    expect(
      integrityHeadline({
        signatures: [{ business_id: "S", status: "VALID" }],
        audit_chain: { status: "VERIFIED" },
        brief_hashes: [{ business_id: "B", hash_verified: true }],
      }),
    ).toEqual({ label: "Every check passed", tone: "good" });
    expect(integrityHeadline({ signatures: [{ status: "INVALID" }], audit_chain: { status: "BROKEN" } }).label).toBe(
      "2 integrity problems found",
    );
    expect(integrityHeadline({}).label).toBe("Nothing checked yet");
  });
});
