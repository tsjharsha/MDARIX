import { describe, expect, it } from "vitest";
import {
  LINK_LEGEND,
  aiChainLayout,
  aiNoticeOf,
  aiStatusBanner,
  aiStatusText,
  addedByText,
  allowedHumanStatuses,
  canRequestForUnknown,
  chainLayout,
  contradictionView,
  epistemicOf,
  filterObservations,
  groupEvidence,
  historyEventText,
  historyEvents,
  humanStatusLabel,
  hypothesesPath,
  intelligencePath,
  intelligenceTab,
  linkBody,
  linkProblem,
  linkStateBody,
  linkStateOf,
  linkStateProblem,
  manualChainBody,
  manualChainProblem,
  newManualChain,
  observationBody,
  observationProblem,
  parseInvestigationsTab,
  statusProblem,
  textProblem,
  unknownBody,
  unknownProblem,
  unknownTransitions,
  unknownsPath,
  withNode,
  withoutNode,
  type ManualChainForm,
  type Observation,
} from "./intelligence";

const UUID = "3f2b8c1e-4d5a-4b6c-8d7e-9f0a1b2c3d4e";
const LONG = "Seal hardness is below specification for lot KS-5521.";

describe("the Intelligence tab of Investigations", () => {
  it("opens on a view through the tab name, and ignores an unknown view", () => {
    expect(intelligenceTab("Unknowns")).toBe("Intelligence?view=Unknowns");
    expect(intelligenceTab("Failure chain")).toBe("Intelligence?view=Failure+chain");
    expect(intelligenceTab()).toBe("Intelligence");
    expect(parseInvestigationsTab("Intelligence?view=Failure+chain")).toEqual({
      tab: "Intelligence",
      view: "Failure chain",
    });
    expect(parseInvestigationsTab("Intelligence?view=Nope")).toEqual({ tab: "Intelligence", view: null });
    expect(parseInvestigationsTab("Workspace")).toEqual({ tab: "Workspace", view: null });
    expect(parseInvestigationsTab(undefined)).toEqual({ tab: "", view: null });
  });

  it("builds the intelligence addresses", () => {
    expect(intelligencePath(UUID, "contradictions")).toBe(`/api/v1/investigations/${UUID}/intelligence/contradictions`);
    expect(hypothesesPath(UUID)).toBe(`/api/v1/investigations/${UUID}/intelligence/hypotheses`);
    expect(hypothesesPath(UUID, { includeRetired: true })).toBe(
      `/api/v1/investigations/${UUID}/intelligence/hypotheses?include_retired=true`,
    );
    expect(unknownsPath(UUID, true)).toBe(
      `/api/v1/investigations/${UUID}/intelligence/unknowns?include_superseded=true`,
    );
  });
});

describe("written text", () => {
  it("needs 10 to 2000 characters unless optional", () => {
    expect(textProblem("short", "the reason")).toMatch(/at least 10 characters \(5 more\)/);
    expect(textProblem("x".repeat(2001), "the reason")).toMatch(/2000 characters/);
    expect(textProblem("  ", "the rationale", { min: 0, required: false })).toBeNull();
    expect(textProblem(LONG, "the reason")).toBeNull();
  });
});

describe("hypotheses", () => {
  it("labels a person's judgement, and says when nobody judged it yet", () => {
    expect(humanStatusLabel("PARTIALLY_SUPPORTED")).toBe("Partially supported");
    expect(humanStatusLabel(null)).toBe("Not judged by a person yet");
    expect(humanStatusLabel("CONTRADICTED", "Contradicted by evidence")).toBe("Contradicted by evidence");
  });

  it("keeps the AI's status apart from the person's judgement", () => {
    expect(aiStatusText({ origin: "AI", ai_status: "MIXED_EVIDENCE", ai_status_label: null })).toBe("Mixed Evidence");
    expect(aiStatusText({ origin: "AI", ai_status: null, ai_status_label: "Evidence points both ways" })).toBe(
      "Evidence points both ways",
    );
    expect(aiStatusText({ origin: "HUMAN", ai_status: null, ai_status_label: null })).toBe("Not proposed by AI");
  });

  it("offers every judgement but Proposed and the current one; a retired one can only come back", () => {
    expect(allowedHumanStatuses(null)).toEqual([
      "HYPOTHESIZED",
      "PARTIALLY_SUPPORTED",
      "STRONGLY_SUPPORTED",
      "WEAKLY_SUPPORTED",
      "CONTRADICTED",
      "RETIRED",
    ]);
    expect(allowedHumanStatuses("CONTRADICTED")).not.toContain("CONTRADICTED");
    expect(allowedHumanStatuses("PROPOSED")).not.toContain("PROPOSED");
    expect(allowedHumanStatuses("RETIRED")).toEqual(["HYPOTHESIZED"]);
  });

  it("needs a judgement and a reason", () => {
    expect(statusProblem({ status: "", reason: LONG })).toBe("Choose your judgement.");
    expect(statusProblem({ status: "CONTRADICTED", reason: "no" })).toMatch(/reason/);
    expect(statusProblem({ status: "CONTRADICTED", reason: LONG })).toBeNull();
  });

  it("groups evidence Supporting, Contradicting, Contextual, Unresolved, with withdrawn links apart", () => {
    const groups = groupEvidence({
      supporting: [
        { id: "l1", evidence: { business_id: "EVD000003" }, added_by: "Dana Lee", created_by_type: "PERSON" },
        { id: "l2", retracted: true, retraction_reason: "Wrong lot" },
      ],
      contradicting: [{ id: "l3", created_by_type: "AI" }],
    });
    expect(groups.map((group) => group.relation)).toEqual(["SUPPORTING", "CONTRADICTING", "CONTEXTUAL", "UNRESOLVED"]);
    expect(groups[0].active.map((link) => link.id)).toEqual(["l1"]);
    expect(groups[0].withdrawn.map((link) => link.id)).toEqual(["l2"]);
    expect(groups[1].active).toHaveLength(1);
    expect(groups[2].active).toEqual([]);
  });

  it("groups a flat list of links by their relation too", () => {
    const groups = groupEvidence([
      { id: "a", relation: "unresolved" },
      { id: "b", relation: "CONTEXTUAL" },
      { id: "c", relation: "ODD" },
    ]);
    expect(groups[3].active.map((link) => link.id)).toEqual(["a"]);
    expect(groups[2].active.map((link) => link.id)).toEqual(["b"]);
    expect(groups.flatMap((group) => group.active)).toHaveLength(2);
  });

  it("says who added a link", () => {
    expect(addedByText({ added_by: "Dana Lee", created_by_type: "PERSON" })).toBe("Added by Dana Lee");
    expect(addedByText({ added_by: null, created_by_type: "AI" })).toBe("Added by AI");
    expect(addedByText({ added_by: null, created_by_type: "SYSTEM" })).toBe("Added by MDARIX rules");
    expect(addedByText({ added_by: UUID, created_by_type: "PERSON" })).toBe("Added by a person");
  });

  it("needs evidence, a relation and a rationale to link evidence", () => {
    const form = { evidenceId: "e1", relation: "SUPPORTING" as const, rationale: LONG };
    expect(linkProblem({ ...form, evidenceId: "" })).toMatch(/Choose the evidence/);
    expect(linkProblem({ ...form, relation: "" })).toMatch(/bears on/);
    expect(linkProblem({ ...form, rationale: "short" })).toMatch(/rationale/);
    expect(linkProblem(form)).toBeNull();
    expect(linkBody(form)).toEqual({ evidence_id: "e1", relation: "SUPPORTING", rationale: LONG });
  });
});

describe("contradictions", () => {
  it("reads a contradiction defensively, without UUIDs", () => {
    const view = contradictionView({
      id: "c1",
      hypothesis: { id: UUID, business_id: "HYP000012", statement: "Seal wear" },
      evidence: { id: UUID, business_id: "EVD000004", title: "Hardness test" },
      rationale: "Hardness within spec",
      origin: "HUMAN",
      judged_since: false,
    });
    expect(view).toMatchObject({
      key: "c1",
      hypothesis: "HYP000012",
      evidence: "EVD000004",
      rationale: "Hardness within spec",
      judgedSince: false,
      kind: "DERIVED_OBSERVATION",
    });
    expect(contradictionView(null, 3)).toMatchObject({ key: "3", hypothesis: null, judgedSince: null });
    expect(contradictionView({ hypothesis_business_id: UUID }).hypothesis).toBeNull();
  });
});

describe("unknowns", () => {
  it("offers the status changes of each status", () => {
    expect(unknownTransitions("open").map((item) => item.to)).toEqual([
      "in_progress",
      "resolved",
      "accepted_limitation",
      "superseded",
    ]);
    expect(unknownTransitions("in_progress").map((item) => item.to)).toContain("open");
    expect(unknownTransitions("resolved").map((item) => item.to)).toEqual(["open"]);
    expect(unknownTransitions("accepted_limitation").map((item) => item.to)).toEqual(["open"]);
    expect(unknownTransitions("superseded")).toEqual([]);
    expect(unknownTransitions("odd")).toEqual([]);
  });

  it("allows requesting evidence only while an unknown is open or worked on", () => {
    expect(canRequestForUnknown("open")).toBe(true);
    expect(canRequestForUnknown("IN_PROGRESS")).toBe(true);
    expect(canRequestForUnknown("resolved")).toBe(false);
  });

  it("validates and builds a new unknown, leaving empty optional fields out", () => {
    const form = { description: LONG, category: "", evidenceNeeded: " ", hypothesisId: "" };
    expect(unknownProblem({ ...form, description: "short" })).toMatch(/at least 10/);
    expect(unknownProblem(form)).toBeNull();
    expect(unknownBody(form)).toEqual({ description: LONG });
    expect(unknownBody({ ...form, category: "SUPPLIER", evidenceNeeded: "Test report", hypothesisId: "h1" })).toEqual({
      description: LONG,
      category: "SUPPLIER",
      evidence_needed: "Test report",
      hypothesis_id: "h1",
    });
  });
});

describe("failure chains", () => {
  it("has a legend entry with a distinct line style for each state", () => {
    expect(LINK_LEGEND.map((item) => item.state)).toEqual([
      "SUPPORTED",
      "PARTIALLY_SUPPORTED",
      "HYPOTHESIZED",
      "UNKNOWN",
      "CONTRADICTED",
    ]);
    expect(new Set(LINK_LEGEND.map((item) => item.line)).size).toBe(5);
  });

  it("maps the AI's epistemic statuses onto the five link states", () => {
    expect(linkStateOf("OBSERVED_SOURCE_SUPPORTED")).toBe("SUPPORTED");
    expect(linkStateOf("DETERMINISTICALLY_DERIVED")).toBe("SUPPORTED");
    expect(linkStateOf("HYPOTHESIZED")).toBe("HYPOTHESIZED");
    expect(linkStateOf("CONTRADICTED")).toBe("CONTRADICTED");
    expect(linkStateOf("UNKNOWN_GAP")).toBe("UNKNOWN");
    expect(linkStateOf("UNSUPPORTED")).toBe("UNKNOWN");
    expect(linkStateOf("CAUSALITY_NOT_ESTABLISHED")).toBe("UNKNOWN");
    expect(linkStateOf("partially supported")).toBe("PARTIALLY_SUPPORTED");
    expect(linkStateOf(null)).toBe("UNKNOWN");
  });

  it("lays a stored chain out left to right by sequence, with gaps and side links", () => {
    const layout = chainLayout({
      nodes: [
        { id: "n2", sequence: 2, label: "Seal softer" },
        { id: "n1", sequence: 1, label: "Supplier change" },
        { id: "n3", sequence: 3, label: "Occlusion alarm" },
      ],
      links: [
        {
          id: "l1",
          from_node_id: "n1",
          to_node_id: "n2",
          state: "SUPPORTED",
          evidence: { id: UUID, business_id: "EVD000004" },
        },
        { id: "l9", from_node_id: "n1", to_node_id: "n3", state: "HYPOTHESIZED" },
      ],
    });
    expect(layout.nodes.map((node) => node.label)).toEqual(["Supplier change", "Seal softer", "Occlusion alarm"]);
    expect(layout.segments).toHaveLength(2);
    expect(layout.segments[0]).toMatchObject({ linkId: "l1", state: "SUPPORTED", evidence: "EVD000004" });
    expect(layout.segments[1]).toMatchObject({ linkId: null, state: "UNKNOWN", stateLabel: "No link recorded" });
    expect(layout.other).toEqual([
      expect.objectContaining({ linkId: "l9", from: "Supplier change", to: "Occlusion alarm" }),
    ]);
  });

  it("lays out an AI chain from its links", () => {
    const layout = aiChainLayout({
      links: [
        {
          link_id: "a",
          from_entity_or_state: "Supplier change",
          relationship: "precedes",
          to_entity_or_state: "Seal softer",
          epistemic_status: "OBSERVED_SOURCE_SUPPORTED",
        },
        {
          link_id: "b",
          from_entity_or_state: "Seal softer",
          relationship: "may cause",
          to_entity_or_state: "Occlusion",
          epistemic_status: "HYPOTHESIZED",
        },
        {
          link_id: "c",
          from_entity_or_state: "Firmware",
          relationship: "may cause",
          to_entity_or_state: "Occlusion",
          epistemic_status: "UNKNOWN_GAP",
        },
      ],
    });
    expect(layout.nodes.map((node) => node.label)).toEqual(["Supplier change", "Seal softer", "Occlusion"]);
    expect(layout.segments.map((segment) => segment.state)).toEqual(["SUPPORTED", "HYPOTHESIZED"]);
    expect(layout.other).toEqual([expect.objectContaining({ from: "Firmware", to: "Occlusion", state: "UNKNOWN" })]);
  });

  it("validates a hand-built chain", () => {
    const named = (form: ManualChainForm) => ({
      ...form,
      name: "Seal wear chain",
      nodes: ["Supplier change", "Seal softer"],
    });
    expect(manualChainProblem(newManualChain())).toMatch(/Name the chain/);
    expect(manualChainProblem({ ...named(newManualChain()), nodes: ["Supplier change", " "] })).toBe(
      "Describe step 2.",
    );
    const ok = named(newManualChain());
    expect(manualChainProblem(ok)).toBeNull();
    expect(manualChainProblem({ ...ok, links: [] })).toMatch(/at least one link/);
    expect(manualChainProblem({ ...ok, links: [{ ...ok.links[0], toIndex: 0 }] })).toMatch(/two different steps/);
    expect(manualChainProblem({ ...ok, links: [{ ...ok.links[0], toIndex: 5 }] })).toMatch(/does not exist/);
    expect(manualChainProblem({ ...ok, links: [ok.links[0], ok.links[0]] })).toMatch(/repeats/);
    expect(manualChainProblem({ ...ok, links: [{ ...ok.links[0], state: "SUPPORTED" }] })).toMatch(/evidence/);
    expect(manualChainProblem({ ...ok, links: [{ ...ok.links[0], state: "SUPPORTED", evidenceId: "e1" }] })).toBeNull();
  });

  it("adds and removes steps, keeping the links consistent", () => {
    const three = withNode({ ...newManualChain(), nodes: ["A", "B"] });
    expect(three.nodes).toEqual(["A", "B", ""]);
    expect(three.links.map((link) => [link.fromIndex, link.toIndex])).toEqual([
      [0, 1],
      [1, 2],
    ]);
    const removed = withoutNode({ ...three, nodes: ["A", "B", "C"] }, 0);
    expect(removed.nodes).toEqual(["B", "C"]);
    expect(removed.links.map((link) => [link.fromIndex, link.toIndex])).toEqual([[0, 1]]);
    expect(withoutNode(newManualChain(), 0).nodes).toHaveLength(2);
  });

  it("sends the chain with indexes and only the optional fields that are set", () => {
    const form: ManualChainForm = {
      name: " Seal wear ",
      nodes: [" Supplier change ", "Seal softer"],
      links: [{ fromIndex: 0, toIndex: 1, state: "SUPPORTED", evidenceId: "e1", rationale: " " }],
    };
    expect(manualChainBody(form)).toEqual({
      name: "Seal wear",
      nodes: ["Supplier change", "Seal softer"],
      links: [{ from_index: 0, to_index: 1, state: "SUPPORTED", evidence_id: "e1" }],
    });
  });

  it("needs a new state, evidence for a supported link, and a reason to change a link", () => {
    expect(linkStateProblem({ state: "", reason: LONG, evidenceId: "" })).toMatch(/new state/);
    expect(linkStateProblem({ state: "HYPOTHESIZED", reason: LONG, evidenceId: "" }, "HYPOTHESIZED")).toMatch(
      /different state/,
    );
    expect(linkStateProblem({ state: "SUPPORTED", reason: LONG, evidenceId: "" })).toMatch(/evidence/);
    expect(linkStateProblem({ state: "CONTRADICTED", reason: "no", evidenceId: "" })).toMatch(/reason/);
    expect(linkStateProblem({ state: "CONTRADICTED", reason: LONG, evidenceId: "" }, "SUPPORTED")).toBeNull();
    expect(linkStateBody({ state: "UNKNOWN", reason: ` ${LONG} `, evidenceId: "" })).toEqual({
      state: "UNKNOWN",
      reason: LONG,
    });
  });
});

describe("observations", () => {
  const items: Observation[] = [
    { id: "1", epistemic_type: "FACT", origin: "HUMAN" },
    { id: "2", epistemic_type: "SOURCE_ASSERTION", origin: "SYSTEM" },
    { id: "3", epistemic_type: "AI_INTERPRETATION", origin: "AI" },
  ];

  it("filters by kind and by who made them", () => {
    expect(filterObservations(items, { kind: "", origin: "" })).toHaveLength(3);
    expect(filterObservations(items, { kind: "FACT", origin: "" }).map((item) => item.id)).toEqual(["1"]);
    expect(filterObservations(items, { kind: "", origin: "AI" }).map((item) => item.id)).toEqual(["3"]);
    expect(filterObservations(items, { kind: "AI_INTERPRETATION", origin: "" }).map((item) => item.id)).toEqual(["3"]);
    expect(filterObservations(null, { kind: "", origin: "" })).toEqual([]);
  });

  it("needs evidence, a kind and a statement of at least 5 characters", () => {
    const form = { evidenceId: "e1", statement: "Lot passed", kind: "FACT" as const, rationale: "" };
    expect(observationProblem({ ...form, evidenceId: "" })).toMatch(/evidence/);
    expect(observationProblem({ ...form, kind: "" })).toMatch(/kind/);
    expect(observationProblem({ ...form, statement: "ok" })).toMatch(/at least 5/);
    expect(observationProblem(form)).toBeNull();
    expect(observationBody(form)).toEqual({ evidence_id: "e1", statement: "Lot passed", epistemic_type: "FACT" });
  });
});

describe("history", () => {
  it("reads an event as one line, never with a UUID", () => {
    expect(
      historyEventText({
        object_type: "HYPOTHESIS",
        object_business_id: "HYP000012",
        event_type: "STATUS_CHANGED",
        from_value: "HYPOTHESIZED",
        to_value: "CONTRADICTED",
      }),
    ).toBe("Hypothesis HYP000012: Status Changed (Hypothesized → Contradicted)");
    expect(historyEventText({ object_type: "UNKNOWN", object_business_id: UUID, event_label: "Added" })).toBe(
      "Unknown: Added",
    );
  });

  it("accepts the paged envelope or a plain list", () => {
    expect(historyEvents({ items: [{ id: "1" }], total: 4 })).toHaveLength(1);
    expect(historyEvents({ events: [{ id: "1" }, { id: "2" }] })).toHaveLength(2);
    expect(historyEvents([{ id: "1" }])).toHaveLength(1);
    expect(historyEvents(null)).toEqual([]);
  });
});

describe("AI status", () => {
  it("shows nothing when AI can run or the status is unknown", () => {
    expect(aiStatusBanner(null)).toBeNull();
    expect(aiStatusBanner({ enabled: true, available: true, budget: { used: 1, limit: 10, remaining: 9 } })).toBeNull();
  });

  it("explains why AI cannot run and offers the manual way", () => {
    const off = aiStatusBanner({ enabled: false, available: false, reason_code: "AI_DISABLED", message: null })!;
    expect(off.reason).toBe("AI_DISABLED");
    expect(off.manual.map((item) => item.view)).toEqual(["Hypotheses", "Unknowns", "Failure chain", "Observations"]);
    const spent = aiStatusBanner({ enabled: true, available: true, budget: { used: 10, limit: 10, remaining: 0 } })!;
    expect(spent.reason).toBe("BUDGET_EXHAUSTED");
    const down = aiStatusBanner({
      enabled: true,
      available: false,
      reason_code: "PROVIDER_UNAVAILABLE",
      message: "The AI service is down for maintenance.",
    })!;
    expect(down.reason).toBe("PROVIDER_UNAVAILABLE");
    expect(down.message).toBe("The AI service is down for maintenance.");
    expect(down.disabledReason).toContain("down for maintenance");
  });

  it("offers only the manual paths the server names, when it names any", () => {
    const banner = aiStatusBanner({ enabled: false, manual_paths: ["unknowns", "failure_chain"] })!;
    expect(banner.manual.map((item) => item.view)).toEqual(["Unknowns", "Failure chain"]);
  });

  it("reads the epistemic label and the fallback notice of an AI response", () => {
    expect(epistemicOf({ epistemic: { origin: "AI", type: "AI_INTERPRETATION", note: "Review it" } })).toEqual({
      note: "Review it",
      humanReviewRequired: true,
    });
    expect(epistemicOf({ analysis: {} })).toBeNull();
    expect(aiNoticeOf({ ai_notice: { message: "Rules produced this.", manual_alternative: "Add by hand." } })).toEqual({
      message: "Rules produced this.",
      manual: "Add by hand.",
    });
    expect(aiNoticeOf({ ai_notice: null })).toBeNull();
  });
});
