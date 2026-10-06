import { describe, expect, it } from "vitest";
import {
  EMPTY_INVENTORY_FILTER,
  EMPTY_NEW_REQUEST,
  attachmentPath,
  availableRequestActions,
  filesProblem,
  filterInventory,
  inventoryPath,
  linkBody,
  linkCandidates,
  newRequestBody,
  newRequestProblem,
  originLabel,
  parseRequestTab,
  relationshipChips,
  relationshipLabel,
  requestEventText,
  requestListPath,
  requestPath,
  requestReasonProblem,
  requestRecipientText,
  requestReviewBody,
  requestReviewFormFrom,
  requestReviewProblem,
  requestStatusLabel,
  requestStatusTone,
  respondProblem,
  reviewBody,
  reviewChips,
  reviewEventText,
  reviewFormFrom,
  reviewProblem,
  reviewStatusLabel,
  sourceText,
  tabWithRequest,
  type InventoryItem,
  type NewRequestForm,
} from "./evidenceWorkflow";

const UUID = "0b6f8f9e-1111-4222-8333-444455556666";

const item = (
  id: string,
  review: string | null,
  relationship: string | null,
  extra: Partial<InventoryItem["evidence"]> = {},
): InventoryItem => ({
  evidence: { id, business_id: `EVD0000${id}`, title: `Record ${id}`, evidence_type: "TEST_REPORT", ...extra },
  link: review || relationship ? { review_status: review, relationship } : null,
  origin: "LINKED",
});

const items = [
  item("31", "ACCEPTED", "SUPPORTING", { source_system: "SAP QM" }),
  item("32", "REJECTED", "CONTRADICTING"),
  item("33", null, null, { title: "Seal hardness report" }),
  item("34", "ACCEPTED_WITH_LIMITATION", "SUPPORTING"),
];

describe("how evidence is judged for a case", () => {
  it("labels review status and relationship separately", () => {
    expect(reviewStatusLabel("ACCEPTED_WITH_LIMITATION")).toBe("Accepted with limitation");
    expect(reviewStatusLabel("ACCEPTED", "Accepted (QA)")).toBe("Accepted (QA)");
    expect(reviewStatusLabel(null)).toBe("—");
    expect(relationshipLabel("UNREVIEWED")).toBe("Not judged");
    expect(relationshipLabel("CONTRADICTING")).toBe("Contradicting");
  });

  it("needs a reason to reject, quarantine or supersede, and a limitation to accept with one", () => {
    const base = reviewFormFrom(null);
    expect(base).toEqual({ reviewStatus: "UNREVIEWED", relationship: "UNREVIEWED", reason: "", limitation: "" });
    expect(reviewProblem({ ...base, reviewStatus: "ACCEPTED", relationship: "SUPPORTING" })).toBeNull();
    for (const status of ["REJECTED", "QUARANTINED", "SUPERSEDED"] as const) {
      expect(reviewProblem({ ...base, reviewStatus: status })).toMatch(/at least 10/);
      expect(reviewProblem({ ...base, reviewStatus: status, reason: "Lab not accredited for this test" })).toBeNull();
    }
    expect(reviewProblem({ ...base, reviewStatus: "ACCEPTED_WITH_LIMITATION" })).toMatch(/limitation/);
    expect(
      reviewProblem({ ...base, reviewStatus: "ACCEPTED_WITH_LIMITATION", limitation: "Sample size of three units" }),
    ).toBeNull();
    expect(reviewProblem({ ...base, reviewStatus: "ACCEPTED", reason: "x".repeat(2001) })).toMatch(/2000/);
  });

  it("sends the limitation only when it applies, and the reason when given", () => {
    expect(
      reviewBody({ reviewStatus: "ACCEPTED", relationship: "CONTEXTUAL", reason: "  ", limitation: "old text" }),
    ).toEqual({ review_status: "ACCEPTED", relationship: "CONTEXTUAL" });
    expect(
      reviewBody({
        reviewStatus: "ACCEPTED_WITH_LIMITATION",
        relationship: "SUPPORTING",
        reason: " Matches the field returns ",
        limitation: " Three units only ",
      }),
    ).toEqual({
      review_status: "ACCEPTED_WITH_LIMITATION",
      relationship: "SUPPORTING",
      reason: "Matches the field returns",
      limitation: "Three units only",
    });
  });

  it("starts the review form from the item's current judgement", () => {
    expect(reviewFormFrom(items[1])).toMatchObject({ reviewStatus: "REJECTED", relationship: "CONTRADICTING" });
    expect(reviewFormFrom(items[2])).toMatchObject({ reviewStatus: "UNREVIEWED", relationship: "UNREVIEWED" });
  });
});

describe("the case's evidence inventory", () => {
  it("counts chips from the server, else from the items", () => {
    const fromItems = reviewChips({ items });
    expect(fromItems.find((chip) => chip.key === "ACCEPTED")?.count).toBe(1);
    expect(fromItems.find((chip) => chip.key === "UNREVIEWED")?.count).toBe(1);
    const fromServer = reviewChips({ items, counts: { accepted: 9 } });
    expect(fromServer.find((chip) => chip.key === "ACCEPTED")?.count).toBe(9);
    const relationships = relationshipChips({ items, counts: { contradicting: 4 } });
    expect(relationships.map((chip) => chip.key)).toEqual([
      "SUPPORTING",
      "CONTRADICTING",
      "CONTEXTUAL",
      "UNRESOLVED",
      "UNRELATED",
    ]);
    expect(relationships.find((chip) => chip.key === "SUPPORTING")?.count).toBe(2);
    expect(relationships.find((chip) => chip.key === "CONTRADICTING")?.count).toBe(4);
  });

  it("filters by review status, relationship and text", () => {
    const ids = (filter: Partial<typeof EMPTY_INVENTORY_FILTER>) =>
      filterInventory(items, { ...EMPTY_INVENTORY_FILTER, ...filter }).map((row) => row.evidence.id);
    expect(ids({})).toEqual(["31", "32", "33", "34"]);
    expect(ids({ review: "UNREVIEWED" })).toEqual(["33"]);
    expect(ids({ relationship: "SUPPORTING" })).toEqual(["31", "34"]);
    expect(ids({ review: "ACCEPTED", relationship: "SUPPORTING" })).toEqual(["31"]);
    expect(ids({ query: "seal" })).toEqual(["33"]);
    expect(ids({ query: "evd000032" })).toEqual(["32"]);
    expect(ids({ query: "sap qm" })).toEqual(["31"]);
    expect(filterInventory(null, EMPTY_INVENTORY_FILTER)).toEqual([]);
  });

  it("names origins and sources without UUIDs", () => {
    expect(originLabel("REQUEST")).toBe("From a request");
    expect(originLabel("DIRECT")).toBe("Recorded on the case");
    expect(sourceText({ source_system: "SAP QM", source_identifier: "QN-1234" })).toBe("SAP QM · QN-1234");
    expect(sourceText({ source_system: null, source_identifier: UUID, source_reference: "REF-9" })).toBe("REF-9");
    expect(sourceText({})).toBe("—");
    expect(inventoryPath(UUID)).toBe(`/api/v1/investigations/${UUID}/evidence-inventory`);
  });

  it("offers library records not yet in the case, and links them with an optional relationship", () => {
    const library = [
      { id: "31", business_id: "EVD000031", title: "Hardness" },
      { id: "40", business_id: "EVD000040", title: "Torque test", source_system: "LIMS" },
      { id: "41", business_id: "EVD000041", title: "Visual inspection" },
    ];
    expect(linkCandidates(library, ["31"], "").map((row) => row.id)).toEqual(["40", "41"]);
    expect(linkCandidates(library, ["31"], "lims").map((row) => row.id)).toEqual(["40"]);
    expect(linkBody(["40"], "", "  ")).toEqual({ evidence_ids: ["40"] });
    expect(linkBody(["40", "41"], "CONTEXTUAL", " Same lot ")).toEqual({
      evidence_ids: ["40", "41"],
      relationship: "CONTEXTUAL",
      reason: "Same lot",
    });
  });

  it("describes review history events", () => {
    expect(
      reviewEventText({
        event_type: "REVIEWED",
        from_review_status: "UNREVIEWED",
        to_review_status: "ACCEPTED",
        from_relationship: "UNREVIEWED",
        to_relationship: "SUPPORTING",
      }),
    ).toBe("Reviewed: Unreviewed → Accepted; Not judged → Supporting");
    expect(reviewEventText({ event_type: "LINKED" })).toBe("Linked");
    expect(reviewEventText({ event_type: "REVIEWED", to_review_status: "REJECTED" })).toBe("Reviewed: Rejected");
  });
});

describe("evidence requests", () => {
  it("offers only the actions the server allows, in a fixed order", () => {
    expect(
      availableRequestActions({ actions: { can_cancel: true, can_respond: true, can_acknowledge: true } }),
    ).toEqual(["acknowledge", "respond", "cancel"]);
    expect(availableRequestActions({ actions: { can_review: true, can_cannot_provide: false } })).toEqual(["review"]);
    expect(availableRequestActions(null)).toEqual([]);
  });

  it("builds the request addresses", () => {
    expect(requestListPath({ investigationId: UUID, box: "sent" })).toBe(
      `/api/v1/evidence-requests?investigation_id=${UUID}&box=sent&page=1&page_size=50`,
    );
    expect(requestListPath({ box: "received", status: "OPEN", page: 2, pageSize: 20 })).toBe(
      "/api/v1/evidence-requests?box=received&status=OPEN&page=2&page_size=20",
    );
    expect(requestPath(UUID)).toBe(`/api/v1/evidence-requests/${UUID}`);
    expect(requestPath(UUID, "cannot-provide")).toBe(`/api/v1/evidence-requests/${UUID}/cannot-provide`);
    expect(attachmentPath(UUID, "a-1")).toBe(`/api/v1/evidence-requests/${UUID}/attachments/a-1`);
  });

  it("reads status and recipient as people read them", () => {
    expect(requestStatusLabel({ status: "CANNOT_PROVIDE", status_label: "Cannot be provided" })).toBe(
      "Cannot be provided",
    );
    expect(requestStatusLabel({ status: "ACKNOWLEDGED" })).toBe("Acknowledged");
    expect(requestStatusTone("CANNOT_PROVIDE")).toBe("serious");
    expect(requestStatusTone("whatever")).toBe("neutral");
    expect(requestRecipientText({ recipient: { user: { id: UUID, name: "Ana Silva" }, role: "INVESTIGATOR" } })).toBe(
      "Ana Silva",
    );
    expect(requestRecipientText({ recipient: { user: null, role: "RISK_REVIEWER" } })).toBe("Risk Reviewer");
    expect(
      requestRecipientText({ recipient: { supplier: { id: UUID, name: "Seals Ltd" }, email: "qa@seals.example" } }),
    ).toBe("Seals Ltd (qa@seals.example)");
    expect(requestRecipientText({ recipient: null })).toBe("—");
  });

  describe("a new request", () => {
    const today = "2026-10-06";
    const internal: NewRequestForm = {
      ...EMPTY_NEW_REQUEST,
      title: "Hardness results for lot KS-5521",
      items: "Test report\n\n  Raw data  \n",
      recipientUserId: UUID,
    };

    it("checks what is needed for each kind of recipient", () => {
      expect(newRequestProblem(internal, today)).toBeNull();
      expect(newRequestProblem({ ...internal, title: "ab" }, today)).toMatch(/at least 3/);
      expect(newRequestProblem({ ...internal, items: " \n " }, today)).toMatch(/at least one/);
      expect(newRequestProblem({ ...internal, recipientUserId: "" }, today)).toMatch(/person/);
      expect(newRequestProblem({ ...internal, recipientMode: "role" }, today)).toMatch(/role queue/);
      expect(newRequestProblem({ ...internal, recipientMode: "role", recipientRole: "REVIEWER" }, today)).toBeNull();
      const supplier = { ...internal, kind: "SUPPLIER" as const, supplierId: "s-1", email: "qa@seals.example" };
      expect(newRequestProblem(supplier, today)).toBeNull();
      expect(newRequestProblem({ ...supplier, email: "not an email" }, today)).toMatch(/email/);
      expect(newRequestProblem({ ...supplier, supplierId: "" }, today)).toMatch(/supplier/);
      expect(newRequestProblem({ ...internal, dueDay: "2026-10-01" }, today)).toMatch(/past/);
      expect(newRequestProblem({ ...internal, dueDay: "2026-10-06" }, today)).toBeNull();
    });

    it("sends only the chosen kind's recipient fields", () => {
      expect(newRequestBody({ ...internal, unknownId: "u-1", rationale: " For UNK000012 " })).toEqual({
        kind: "INTERNAL",
        title: "Hardness results for lot KS-5521",
        requested_items: ["Test report", "Raw data"],
        rationale: "For UNK000012",
        unknown_id: "u-1",
        priority: "MEDIUM",
        recipient_user_id: UUID,
      });
      expect(newRequestBody({ ...internal, recipientMode: "role", recipientRole: "REVIEWER" })).toMatchObject({
        recipient_role: "REVIEWER",
      });
      expect(newRequestBody({ ...internal, recipientMode: "role", recipientRole: "REVIEWER" })).not.toHaveProperty(
        "recipient_user_id",
      );
      const supplier = newRequestBody({
        ...internal,
        kind: "SUPPLIER",
        supplierId: "s-1",
        email: " qa@seals.example ",
        priority: "HIGH",
        dueDay: "2026-10-20",
      });
      expect(supplier).toMatchObject({ kind: "SUPPLIER", supplier_id: "s-1", recipient_email: "qa@seals.example" });
      expect(supplier).not.toHaveProperty("recipient_user_id");
      expect(supplier.priority).toBe("HIGH");
      expect(typeof supplier.due_at).toBe("string");
    });
  });

  it("checks responses, reasons and files", () => {
    expect(respondProblem("  ")).toMatch(/note/);
    expect(respondProblem("Report attached")).toBeNull();
    expect(requestReasonProblem("no")).toMatch(/at least 10/);
    expect(requestReasonProblem("The lot records were destroyed")).toBeNull();
    expect(filesProblem([{ name: "report.pdf", type: "application/pdf", size: 1000 }])).toBeNull();
    expect(filesProblem([{ name: "macro.xlsm", type: "application/vnd.ms-excel", size: 1000 }])).toMatch(/macro\.xlsm/);
    expect(filesProblem([{ name: "big.pdf", type: "application/pdf", size: 11 * 1024 * 1024 }])).toMatch(/10 MB/);
    expect(filesProblem([])).toBeNull();
  });

  it("reviews a response into evidence, or rejects it with a reason", () => {
    const form = requestReviewFormFrom({ title: "Hardness results" });
    expect(form).toMatchObject({ accept: true, title: "Hardness results", reviewStatus: "ACCEPTED" });
    expect(requestReviewProblem(form)).toBeNull();
    expect(requestReviewProblem({ ...form, title: "" })).toMatch(/title/);
    expect(requestReviewProblem({ ...form, reviewStatus: "ACCEPTED_WITH_LIMITATION" })).toMatch(/limitation/);
    expect(requestReviewBody(form)).toEqual({
      accept: true,
      title: "Hardness results",
      evidence_type: "DOCUMENT",
      review_status: "ACCEPTED",
      relationship: "UNRESOLVED",
    });
    const reject = { ...form, accept: false, reason: "Wrong lot was tested" };
    expect(requestReviewProblem({ ...reject, reason: "no" })).toMatch(/at least 10/);
    expect(requestReviewProblem(reject)).toBeNull();
    expect(requestReviewBody(reject)).toEqual({ accept: false, reason: "Wrong lot was tested" });
  });

  it("describes request history events", () => {
    expect(requestEventText({ event_type: "RESPONDED", from_status: "ACKNOWLEDGED", to_status: "RESPONDED" })).toBe(
      "Responded: Acknowledged → Responded",
    );
    expect(requestEventText({})).toBe("Updated");
  });

  it("carries a request to open in a tab name, and reads it back", () => {
    expect(tabWithRequest("Requests", UUID)).toBe(`Requests?request=${UUID}`);
    expect(tabWithRequest("Requests", "bad ref!")).toBe("Requests");
    expect(parseRequestTab(`Evidence requests?request=${UUID}`)).toEqual({ tab: "Evidence requests", request: UUID });
    expect(parseRequestTab("Requests?request=<script>")).toEqual({ tab: "Requests", request: null });
    expect(parseRequestTab("Case evidence")).toEqual({ tab: "Case evidence", request: null });
    expect(parseRequestTab(undefined)).toEqual({ tab: "", request: null });
  });
});
