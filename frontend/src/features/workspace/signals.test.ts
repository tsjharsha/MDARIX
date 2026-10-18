import { describe, expect, it } from "vitest";
import {
  DEFAULT_SIGNAL_FILTERS,
  EMPTY_DISPOSITION,
  EMPTY_NEW_SIGNAL,
  addComplaintsProblem,
  addedHowLabel,
  ageText,
  defaultInvestigationQuestion,
  dispositionBody,
  dispositionProblem,
  harmFlags,
  investigationBody,
  investigationProblem,
  isSignalId,
  isSignalRef,
  mergeProblem,
  newSignalBody,
  nextSignalSort,
  newSignalProblem,
  parseSignalsTab,
  priorityBody,
  priorityNeedsReason,
  priorityProblem,
  priorityText,
  rankSignals,
  relatedItem,
  ruleBody,
  ruleChanged,
  ruleForm,
  ruleParametersText,
  ruleProblem,
  ruleSentence,
  runIds,
  runSummary,
  searchWithoutSignal,
  signalDueState,
  signalDueText,
  signalFromSearch,
  signalLinkStart,
  signalListPath,
  signalOriginLabel,
  signalPath,
  signalPriority,
  signalProductText,
  signalStatusLabel,
  signalStatusTone,
  signalTableSort,
  signalsTab,
  statusChips,
  statusesFor,
  triageCountTiles,
  versionSplit,
  type DetectionRule,
} from "./signals";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";
const PRODUCT = "9d1c2b3a-1111-4222-8333-444455556666";

const query = (path: string) => Object.fromEntries(new URLSearchParams(path.split("?")[1]));

describe("signal inbox filters", () => {
  it("reads the open signals by priority by default", () => {
    expect(query(signalListPath({}))).toEqual({
      status: "NEW,TRIAGE,MONITOR,INVESTIGATION_REQUIRED,ESCALATED,INVESTIGATION_OPEN",
      sort: "priority",
      page: "1",
      page_size: "50",
    });
    expect(signalListPath({}).startsWith("/api/v1/triage/signals?")).toBe(true);
  });

  it("sends every chosen filter and leaves out empty ones", () => {
    expect(
      query(
        signalListPath(
          {
            status: "ALL",
            priorities: ["HIGH", "CRITICAL"],
            productId: PRODUCT,
            origin: "THRESHOLD_RULE",
            owner: "me",
            q: "  SIG000023 ",
            sort: "due_at",
            overdue: true,
          },
          3,
          25,
        ),
      ),
    ).toEqual({
      priority: "HIGH,CRITICAL",
      product_id: PRODUCT,
      origin: "THRESHOLD_RULE",
      owner: "me",
      q: "SIG000023",
      overdue: "true",
      sort: "due_at",
      page: "3",
      page_size: "25",
    });
    expect(query(signalListPath({ status: "MONITOR", reviewDue: true }, 0))).toMatchObject({
      status: "MONITOR",
      review_due: "true",
      page: "1",
    });
  });

  it("sends a column heading's sort with its direction, and none for the Sort by choice", () => {
    expect(query(signalListPath({ sort: "owner", order: "desc" }, 2))).toMatchObject({
      sort: "owner",
      order: "desc",
      page: "2",
    });
    expect(query(signalListPath({ sort: "due_at" }))).not.toHaveProperty("order");
  });

  it("keeps the Sort by choice and the column headings in step", () => {
    // "Sort by" shows as the sorted heading in its natural direction.
    expect(signalTableSort({ sort: "priority", order: "" })).toEqual({ key: "priority", direction: "descending" });
    expect(signalTableSort({ sort: "created_at", order: "" })).toEqual({ key: "age_days", direction: "ascending" });
    expect(signalTableSort({ sort: "last_event_at", order: "" })).toBeNull();
    expect(signalTableSort({ sort: "title", order: "asc" })).toEqual({ key: "title", direction: "ascending" });
    // A click on that heading turns it round; another heading starts ascending; a third click restores the usual order.
    expect(nextSignalSort({ sort: "priority", order: "" }, "priority")).toEqual({ sort: "priority", order: "asc" });
    expect(nextSignalSort({ sort: "priority", order: "asc" }, "priority")).toEqual({ sort: "priority", order: "desc" });
    expect(nextSignalSort({ sort: "priority", order: "desc" }, "priority")).toEqual(
      expect.objectContaining({ sort: DEFAULT_SIGNAL_FILTERS.sort, order: "" }),
    );
    expect(nextSignalSort({ sort: "due_at", order: "" }, "owner")).toEqual({ sort: "owner", order: "asc" });
    expect(nextSignalSort({ sort: "due_at", order: "" }, "due_at")).toEqual({ sort: "due_at", order: "desc" });
  });

  it("names the statuses each status filter stands for", () => {
    expect(statusesFor("ALL")).toEqual([]);
    expect(statusesFor("NEW")).toEqual(["NEW"]);
    expect(statusesFor("OPEN")).toContain("INVESTIGATION_OPEN");
    expect(statusesFor("OPEN")).not.toContain("CLOSED");
  });

  it("shows the status chips with their counts, the open group summed", () => {
    const chips = statusChips({ NEW: 3, TRIAGE: 2, CLOSED: 5 }, "OPEN");
    expect(chips.map((chip) => [chip.label, chip.count])).toEqual([
      ["Open", 5],
      ["New", 3],
      ["In triage", 2],
      ["Closed", 5],
      ["All", 10],
    ]);
    // A selected status stays even without signals; without counts no number is shown.
    expect(statusChips(null, "ESCALATED").map((chip) => [chip.value, chip.count])).toEqual([
      ["OPEN", null],
      ["ESCALATED", null],
      ["ALL", null],
    ]);
  });
});

describe("where Signals opens", () => {
  it("carries the inbox's filters and a signal in the tab name, and reads them back", () => {
    const tab = signalsTab({ filters: { priorities: ["HIGH", "CRITICAL"] } });
    expect(tab).toBe("Signal inbox?priority=HIGH%2CCRITICAL");
    expect(parseSignalsTab(tab)).toEqual({
      tab: "Signal inbox",
      filters: { ...DEFAULT_SIGNAL_FILTERS, priorities: ["HIGH", "CRITICAL"] },
      signal: null,
    });
    expect(signalsTab({ signal: "SIG000023" })).toBe("Signal inbox?signal=SIG000023");
    expect(parseSignalsTab("Signal inbox?signal=SIG000023").signal).toBe("SIG000023");
    const overdue = parseSignalsTab(signalsTab({ filters: { status: "OPEN", overdue: true, sort: "due_at" } }));
    expect(overdue.filters).toMatchObject({ status: "OPEN", overdue: true, sort: "due_at" });
    expect(parseSignalsTab(signalsTab({ filters: { status: "NEW" } })).filters.status).toBe("NEW");
  });

  it("opens plain tab names, a former tab's replacement, else the Signal inbox", () => {
    expect(signalsTab({ tab: "Trends" })).toBe("Trends");
    expect(parseSignalsTab("Trends").tab).toBe("Trends");
    expect(parseSignalsTab("Complaint list").tab).toBe("Complaint list");
    expect(parseSignalsTab("All signals").tab).toBe("Recent complaints");
    expect(parseSignalsTab("Something else").tab).toBe("Signal inbox");
    expect(parseSignalsTab(undefined)).toEqual({ tab: "Signal inbox", filters: DEFAULT_SIGNAL_FILTERS, signal: null });
  });

  it("ignores values it does not know", () => {
    const parsed = parseSignalsTab("Signal inbox?status=BOGUS&priority=HIGH,URGENT&owner=boss&sort=x&signal=<b>");
    expect(parsed.filters.status).toBe("OPEN");
    expect(parsed.filters.priorities).toEqual(["HIGH"]);
    expect(parsed.filters.owner).toBe("");
    expect(parsed.filters.sort).toBe("priority");
    expect(parsed.signal).toBeNull();
  });

  it("reads a signal link from the address and removes it again", () => {
    expect(signalFromSearch("?signal=SIG000023")).toBe("SIG000023");
    expect(signalFromSearch("?signal=%3Cscript%3E")).toBeNull();
    expect(signalFromSearch("")).toBeNull();
    expect(searchWithoutSignal("?signal=SIG000023&x=1")).toBe("?x=1");
    expect(searchWithoutSignal("?signal=SIG000023")).toBe("");
    expect(signalLinkStart("signals", ["Signals"], "SIG000023")).toEqual(["Signals", "Signal inbox?signal=SIG000023"]);
    expect(signalLinkStart("home", ["Dashboard"], "SIG000023")).toEqual(["Dashboard"]);
    expect(signalLinkStart("signals", ["Signals"], null)).toEqual(["Signals"]);
  });

  it("finds the signal a link names by business ID or id", () => {
    expect(isSignalRef({ id: UUID, business_id: "SIG000023" }, "sig000023")).toBe(true);
    expect(isSignalRef({ id: UUID, business_id: "SIG000023" }, UUID)).toBe(true);
    expect(isSignalRef({ id: UUID, business_id: "SIG000023" }, "SIG000002")).toBe(false);
    expect(isSignalId(UUID)).toBe(true);
    expect(isSignalId("SIG000023")).toBe(false);
    expect(signalPath(UUID, "create-investigation")).toBe(`/api/v1/triage/signals/${UUID}/create-investigation`);
  });
});

describe("how a signal reads", () => {
  it("labels statuses, origins and products, never with raw codes", () => {
    expect(signalStatusLabel("TRIAGE")).toBe("In triage");
    expect(signalStatusLabel("INVESTIGATION_REQUIRED")).toBe("Investigation required");
    expect(signalStatusLabel("NEW", "Waiting")).toBe("Waiting");
    expect(signalStatusLabel(null)).toBe("—");
    expect(signalStatusTone("ESCALATED")).toBe("critical");
    expect(signalStatusTone("unknown")).toBe("neutral");
    expect(signalOriginLabel("THRESHOLD_RULE")).toBe("Complaint threshold rule");
    expect(signalOriginLabel("MANUAL", "Created by Ana")).toBe("Created by Ana");
    expect(
      signalProductText({
        product: { id: PRODUCT, name: "Infusion pump" },
        product_version: { id: UUID, version_identifier: "B" },
      }),
    ).toBe("Infusion pump · version B");
    expect(signalProductText({ product: { id: PRODUCT, name: UUID }, product_version: null })).toBe("—");
  });

  it("shows suggested and confirmed priority clearly", () => {
    expect(signalPriority({ suggested_priority: "HIGH", confirmed_priority: "CRITICAL" })).toEqual({
      current: "CRITICAL",
      suggested: "HIGH",
      confirmed: "CRITICAL",
      isConfirmed: true,
      changed: true,
    });
    expect(signalPriority({ suggested_priority: "HIGH", priority: "HIGH" }).isConfirmed).toBe(false);
    expect(priorityText({ suggested_priority: "HIGH", confirmed_priority: "CRITICAL" })).toBe(
      "Suggested High → confirmed Critical",
    );
    expect(priorityText({ suggested_priority: "HIGH", confirmed_priority: "HIGH" })).toBe("Confirmed High");
    expect(priorityText({ suggested_priority: "LOW" })).toBe("Suggested Low (not confirmed)");
    expect(priorityText({})).toBe("Not set");
  });

  it("reads the due date: overdue highlighted, closed signals never overdue", () => {
    const now = new Date("2026-10-06T12:00:00Z");
    expect(signalDueState({ due_at: "2026-10-05T12:00:00Z", status: "TRIAGE" }, now)).toBe("overdue");
    expect(signalDueState({ due_at: "2026-10-20T12:00:00Z", overdue: true }, now)).toBe("overdue");
    expect(signalDueState({ due_at: "2026-10-07T12:00:00Z" }, now)).toBe("due_soon");
    expect(signalDueState({ due_at: "2026-10-20T12:00:00Z" }, now)).toBe("due");
    expect(signalDueState({ due_at: "2026-10-01T12:00:00Z", status: "CLOSED" }, now)).toBe("done");
    expect(signalDueState({ due_at: null }, now)).toBe("none");
    expect(signalDueText({ due_at: "2026-10-05T12:00:00Z" }, String, now)).toBe("2026-10-05T12:00:00Z · overdue");
    expect(signalDueText({ due_at: "2026-10-07T12:00:00Z" }, String, now)).toBe("2026-10-07T12:00:00Z · due soon");
    expect(signalDueText({ due_at: null }, String, now)).toBe("—");
    expect(signalDueText({ due_at: null, overdue: true }, String, now)).toBe("Overdue");
  });

  it("reads age, harm flags and how a complaint was added", () => {
    expect(ageText(0)).toBe("Today");
    expect(ageText(1)).toBe("1 day");
    expect(ageText(12.7)).toBe("12 days");
    expect(ageText(null)).toBe("—");
    expect(harmFlags({ death: true, serious_injury: true, malfunction: true })).toEqual([
      "Death",
      "Serious injury",
      "Malfunction",
    ]);
    expect(harmFlags({})).toEqual([]);
    expect(addedHowLabel("RULE")).toBe("By the rule");
    expect(addedHowLabel("MERGE")).toBe("From a merge");
    expect(addedHowLabel(null)).toBe("—");
  });

  it("splits complaints across versions in whole percentages that add up to 100", () => {
    const split = versionSplit([
      { version_identifier: "A", product_version_business_id: "PV000001", count: 1 },
      { version_identifier: "B", product_version_business_id: "PV000002", count: 1 },
      { version_identifier: "C", product_version_business_id: "PV000003", count: 1 },
    ]);
    expect(split.reduce((sum, item) => sum + item.percent, 0)).toBe(100);
    expect(split.map((item) => item.percent)).toEqual([34, 33, 33]);
    const uneven = versionSplit([
      { version_identifier: "A", count: 1 },
      { version_identifier: "B", count: 3 },
    ]);
    expect(uneven.map((item) => [item.label, item.count, item.percent])).toEqual([
      ["Version B", 3, 75],
      ["Version A", 1, 25],
    ]);
    expect(versionSplit([{ product_version_business_id: "PV000009", count: 0 }])[0]).toMatchObject({
      label: "PV000009",
      percent: 0,
    });
    expect(versionSplit(null)).toEqual([]);
  });

  it("orders the dashboard's open signals by priority, then due date", () => {
    const rows = [
      { id: "a", priority: "MEDIUM", due_at: "2026-10-07T00:00:00Z" },
      { id: "b", priority: "CRITICAL", due_at: "2026-10-09T00:00:00Z" },
      { id: "c", priority: "CRITICAL", due_at: "2026-10-08T00:00:00Z" },
      { id: "d", suggested_priority: "HIGH", due_at: null },
    ];
    expect(rankSignals(rows).map((row) => row.id)).toEqual(["c", "b", "d", "a"]);
  });

  it("gives the dashboard's counts with the inbox filter each opens", () => {
    const tiles = triageCountTiles({ counts: { new: 4, triage: 1, overdue: 2 } });
    expect(tiles.map((tile) => [tile.label, tile.value])).toEqual([
      ["New", 4],
      ["In triage", 1],
      ["Escalated", 0],
      ["Investigation required", 0],
      ["Monitor review due", 0],
      ["Overdue", 2],
    ]);
    expect(tiles.find((tile) => tile.key === "overdue")?.filters).toEqual({
      status: "OPEN",
      overdue: true,
      sort: "due_at",
    });
    expect(tiles.find((tile) => tile.key === "new")?.filters).toEqual({ status: "NEW" });
    expect(triageCountTiles(null)[0].value).toBeNull();
  });

  it("describes a rule's parameters and related records without UUIDs", () => {
    expect(ruleParametersText({ min_complaints: 3, window_days: 30, rule_id: UUID, nested: { a: 1 } })).toBe(
      "Min complaints 3 · Window days 30",
    );
    expect(ruleParametersText(null)).toBe("");
    expect(
      relatedItem({ id: UUID, business_id: "CHG000004", title: "Battery supplier change", status: "RELEASED" }),
    ).toEqual({
      id: "CHG000004",
      text: "Battery supplier change",
      status: "RELEASED",
    });
    expect(relatedItem({ id: UUID, capa_identifier: "CAPA-12", description: "Retrain line 2" })).toEqual({
      id: "CAPA-12",
      text: "Retrain line 2",
      status: null,
    });
    expect(relatedItem({ id: UUID }).id).toBe("—");
  });
});

describe("triage actions", () => {
  it("asks for a reason only when the priority differs from the suggestion", () => {
    expect(priorityNeedsReason("HIGH", "HIGH")).toBe(false);
    expect(priorityNeedsReason("HIGH", "CRITICAL")).toBe(true);
    expect(priorityNeedsReason(null, "LOW")).toBe(false);
    expect(priorityProblem({ priority: "HIGH", reason: "", suggested: "HIGH" })).toBeNull();
    expect(priorityProblem({ priority: "CRITICAL", reason: "", suggested: "HIGH" })).toMatch(/at least 10/);
    expect(priorityProblem({ priority: "CRITICAL", reason: "Two deaths reported", suggested: "HIGH" })).toBeNull();
    expect(priorityProblem({ priority: "", reason: "", suggested: "HIGH" })).toBe("Choose a priority.");
    expect(priorityBody({ priority: "high", reason: "  " })).toEqual({ priority: "HIGH" });
    expect(priorityBody({ priority: "CRITICAL", reason: " Two deaths reported " })).toEqual({
      priority: "CRITICAL",
      reason: "Two deaths reported",
    });
  });

  it("checks a disposition the way the form adapts to it", () => {
    const today = "2026-10-06";
    const reason = "Reviewed with the clinical team";
    expect(dispositionProblem(EMPTY_DISPOSITION, today)).toBe("Choose a disposition.");
    expect(dispositionProblem({ ...EMPTY_DISPOSITION, disposition: "NO_ACTION", reason: "short" }, today)).toMatch(
      /at least 10/,
    );
    expect(dispositionProblem({ ...EMPTY_DISPOSITION, disposition: "NO_ACTION", reason }, today)).toBeNull();
    expect(dispositionProblem({ ...EMPTY_DISPOSITION, disposition: "DUPLICATE", reason }, today)).toMatch(/duplicates/);
    expect(
      dispositionProblem({ ...EMPTY_DISPOSITION, disposition: "DUPLICATE", reason, canonicalSignalId: UUID }, today),
    ).toBeNull();
    expect(dispositionProblem({ ...EMPTY_DISPOSITION, disposition: "MONITOR", reason }, today)).toMatch(/review/);
    expect(
      dispositionProblem({ ...EMPTY_DISPOSITION, disposition: "MONITOR", reason, monitorReviewDate: today }, today),
    ).toMatch(/future/);
    expect(
      dispositionProblem(
        { ...EMPTY_DISPOSITION, disposition: "MONITOR", reason, monitorReviewDate: "2026-11-01" },
        today,
      ),
    ).toBeNull();
    expect(
      dispositionProblem({ ...EMPTY_DISPOSITION, disposition: "ESCALATED", reason: "x".repeat(2001) }, today),
    ).toMatch(/2000/);
  });

  it("sends only the fields the chosen disposition takes", () => {
    const base = {
      ...EMPTY_DISPOSITION,
      reason: " Watch it ",
      canonicalSignalId: UUID,
      monitorReviewDate: "2026-11-01",
    };
    expect(dispositionBody({ ...base, disposition: "ESCALATED" })).toEqual({
      disposition: "ESCALATED",
      reason: "Watch it",
    });
    expect(dispositionBody({ ...base, disposition: "DUPLICATE" })).toEqual({
      disposition: "DUPLICATE",
      reason: "Watch it",
      canonical_signal_id: UUID,
    });
    expect(dispositionBody({ ...base, disposition: "MONITOR", monitorTrigger: " 2 more in 30 days " })).toEqual({
      disposition: "MONITOR",
      reason: "Watch it",
      monitor_review_date: "2026-11-01",
      monitor_trigger: "2 more in 30 days",
    });
    expect(dispositionBody({ ...base, disposition: "MONITOR" })).not.toHaveProperty("monitor_trigger");
  });

  it("checks merges and added complaints", () => {
    expect(mergeProblem([], "Same root cause found")).toMatch(/at least one signal/);
    expect(mergeProblem([UUID], "short")).toMatch(/at least 10/);
    expect(mergeProblem([UUID], "Same battery problem")).toBeNull();
    expect(addComplaintsProblem([], "Same battery problem")).toMatch(/at least one complaint/);
    expect(addComplaintsProblem([UUID], "Same battery problem")).toBeNull();
  });

  it("prefills and checks the investigation to create", () => {
    expect(defaultInvestigationQuestion({ title: "Battery drains early." })).toBe(
      "What is the root cause of battery drains early?",
    );
    expect(defaultInvestigationQuestion({ title: "USB port overheating" })).toBe(
      "What is the root cause of USB port overheating?",
    );
    expect(defaultInvestigationQuestion({ title: null })).toBe("");
    // A threshold rule's title reads as the question a quality lead asks.
    expect(
      defaultInvestigationQuestion({
        title: "5 complaints: pressure alarm on OrbitCare 300 Infusion Pump (Sample) Rev B in 30 days",
      }),
    ).toBe("Why did pressure-alarm complaints rise on OrbitCare 300 Infusion Pump (Sample) Rev B?");
    expect(defaultInvestigationQuestion({ title: "4 complaints: leak on Aster Pump Rev C in 7 days" })).toBe(
      "Why did leak complaints rise on Aster Pump Rev C?",
    );
    expect(
      defaultInvestigationQuestion({ title: "3 complaints: under infusion no alarm on Aster Pump Rev C in 30 days" }),
    ).toBe("Why did complaints about under infusion no alarm rise on Aster Pump Rev C?");
    expect(defaultInvestigationQuestion({ title: "3 complaints: unspecified problem on Aster Pump in 30 days" })).toBe(
      "Why did complaints without a problem code rise on Aster Pump?",
    );
    const form = {
      question: "Why do batteries drain early?",
      complaintIds: [UUID],
      assigneeUserId: "",
      alsoSignalIds: [],
      identifier: "",
    };
    expect(investigationProblem(form)).toBeNull();
    expect(investigationProblem({ ...form, complaintIds: [] })).toMatch(/at least one complaint/);
    expect(investigationProblem({ ...form, question: "Why?" })).toMatch(/investigation question/);
    expect(investigationBody(form)).toEqual({
      investigation_question: "Why do batteries drain early?",
      complaint_ids: [UUID],
    });
    expect(
      investigationBody({ ...form, assigneeUserId: "user-1", alsoSignalIds: ["sig-2"], identifier: " QMS-1 " }),
    ).toEqual({
      investigation_question: "Why do batteries drain early?",
      complaint_ids: [UUID],
      assignee_user_id: "user-1",
      also_signal_ids: ["sig-2"],
      investigation_identifier: "QMS-1",
    });
  });

  it("checks and sends a new signal", () => {
    const form = { ...EMPTY_NEW_SIGNAL, title: "Battery drains early", productId: PRODUCT, complaintIds: [UUID] };
    expect(newSignalProblem(EMPTY_NEW_SIGNAL)).toMatch(/title/);
    expect(newSignalProblem({ ...form, productId: "" })).toMatch(/product/);
    expect(newSignalProblem({ ...form, complaintIds: [] })).toMatch(/complaint/);
    expect(newSignalProblem(form)).toBeNull();
    expect(newSignalProblem({ ...form, priority: "HIGH" })).toMatch(/at least 10/);
    expect(newSignalProblem({ ...form, priority: "HIGH", reason: "Patient harm reported" })).toBeNull();
    expect(newSignalBody(form)).toEqual({ title: "Battery drains early", product_id: PRODUCT, complaint_ids: [UUID] });
    expect(
      newSignalBody({
        ...form,
        productVersionId: "pv-1",
        priority: "high",
        reason: " Patient harm reported ",
        description: " d ",
      }),
    ).toEqual({
      title: "Battery drains early",
      product_id: PRODUCT,
      complaint_ids: [UUID],
      description: "d",
      product_version_id: "pv-1",
      priority: "HIGH",
      reason: "Patient harm reported",
    });
  });
});

describe("detection rules", () => {
  const rule: DetectionRule = { rule_code: "COMPLAINT_THRESHOLD", enabled: true, min_complaints: 3, window_days: 30 };

  it("says what the rule does", () => {
    expect(ruleSentence(rule)).toBe(
      "Opens a signal when 3 or more complaints about the same product problem arrive within 30 days.",
    );
    expect(ruleSentence({ min_complaints: 2, window_days: 1 })).toMatch(/within 1 day\./);
  });

  it("checks the server's limits and asks for a reason", () => {
    const form = { ...ruleForm(rule), reason: "Fewer complaints should be enough" };
    expect(ruleChanged(rule, form)).toBe(false);
    expect(ruleChanged(rule, { ...form, minComplaints: "4" })).toBe(true);
    expect(ruleChanged(rule, { ...form, enabled: false })).toBe(true);
    expect(ruleProblem(form)).toBeNull();
    expect(ruleProblem({ ...form, minComplaints: "1" })).toMatch(/2 to 1000/);
    expect(ruleProblem({ ...form, minComplaints: "2.5" })).toMatch(/whole number/);
    expect(ruleProblem({ ...form, windowDays: "366" })).toMatch(/1 to 365/);
    expect(ruleProblem({ ...form, reason: "short" })).toMatch(/at least 10/);
    expect(ruleBody({ ...form, minComplaints: " 4 ", enabled: false })).toEqual({
      enabled: false,
      min_complaints: 4,
      window_days: 30,
      reason: "Fewer complaints should be enough",
    });
  });

  it("summarizes a detection run with the signal IDs", () => {
    const result = {
      created: [
        { id: UUID, business_id: "SIG000031" },
        { id: "x", business_id: "SIG000032" },
      ],
      updated: ["SIG000007"],
      monitor_reopened: [],
    };
    expect(runSummary(result)).toBe("Detection ran: 2 signals created, 1 updated, none reopened from monitoring.");
    expect(runIds(result.created)).toEqual({ count: 2, ids: ["SIG000031", "SIG000032"] });
    expect(runIds(3)).toEqual({ count: 3, ids: [] });
    expect(runIds([UUID])).toEqual({ count: 1, ids: [] });
    expect(runSummary({ created: [], updated: [], monitor_reopened: [] })).toBe(
      "Detection ran: no new or changed signals.",
    );
    expect(runSummary(null)).toBe("");
  });
});
