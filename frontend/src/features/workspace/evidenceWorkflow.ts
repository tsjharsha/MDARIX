// Pure rules for a case's evidence (Phase 3): how evidence is judged for one case (its review status and its
// relationship to the question, two separate things), the case's evidence inventory and its filters, and evidence
// requests to colleagues and suppliers. The server decides every review and every request action.
import { titleCase, type Tone } from "../admin/console/dashboardModel";
import { safeText } from "../../app/displayId";
import { sortParams, type SortState } from "../../app/tableSort";
import { roleLabel } from "../../app/roles";
import { dueAtFromDay } from "./caseWorkflow";

export const REVIEW_STATUSES = [
  "UNREVIEWED",
  "ACCEPTED",
  "ACCEPTED_WITH_LIMITATION",
  "REJECTED",
  "QUARANTINED",
  "SUPERSEDED",
] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

export const RELATIONSHIPS = [
  "SUPPORTING",
  "CONTRADICTING",
  "CONTEXTUAL",
  "UNRESOLVED",
  "UNRELATED",
  "UNREVIEWED",
] as const;
export type Relationship = (typeof RELATIONSHIPS)[number];

export const REVIEW_STATUS: Record<ReviewStatus, { label: string; tone: Tone; help: string }> = {
  UNREVIEWED: {
    label: "Unreviewed",
    tone: "neutral",
    help: "Nobody has judged this evidence for this investigation yet.",
  },
  ACCEPTED: { label: "Accepted", tone: "good", help: "Reliable enough to use in this investigation." },
  ACCEPTED_WITH_LIMITATION: {
    label: "Accepted with limitation",
    tone: "warning",
    help: "Usable, with a limitation every reader must see.",
  },
  REJECTED: { label: "Rejected", tone: "critical", help: "Not usable in this investigation. Say why." },
  QUARANTINED: { label: "Quarantined", tone: "serious", help: "Held back until a question about it is settled." },
  SUPERSEDED: { label: "Superseded", tone: "neutral", help: "Replaced by a newer record. Say which, and why." },
};

export const RELATIONSHIP: Record<Relationship, { label: string; tone: Tone; help: string }> = {
  SUPPORTING: { label: "Supporting", tone: "good", help: "Consistent with an explanation under consideration." },
  CONTRADICTING: { label: "Contradicting", tone: "critical", help: "Speaks against an explanation." },
  CONTEXTUAL: { label: "Contextual", tone: "neutral", help: "Background that frames the investigation." },
  UNRESOLVED: { label: "Unresolved", tone: "warning", help: "Its bearing on the question is not settled yet." },
  UNRELATED: { label: "Unrelated", tone: "neutral", help: "Does not bear on this investigation's question." },
  UNREVIEWED: { label: "Not judged", tone: "neutral", help: "Its relationship has not been judged yet." },
};

/** Why the review form explains the two choices separately. */
export const QUALITY_VS_RELATIONSHIP =
  "Quality and relationship are separate judgements. The review status says whether the record can be relied on; the relationship says how it bears on this investigation's question. Reliable evidence can contradict an explanation, and weak evidence can seem to support one.";

const code = (value: unknown) =>
  String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

export const reviewStatusLabel = (status: unknown, label?: unknown) =>
  safeText(label) ?? REVIEW_STATUS[code(status) as ReviewStatus]?.label ?? (status ? titleCase(String(status)) : "—");
export const reviewStatusTone = (status: unknown): Tone =>
  REVIEW_STATUS[code(status) as ReviewStatus]?.tone ?? "neutral";
export const relationshipLabel = (relationship: unknown, label?: unknown) =>
  safeText(label) ??
  RELATIONSHIP[code(relationship) as Relationship]?.label ??
  (relationship ? titleCase(String(relationship)) : "—");
export const relationshipTone = (relationship: unknown): Tone =>
  RELATIONSHIP[code(relationship) as Relationship]?.tone ?? "neutral";

// ---------------------------------------------------------------------------------------------------------------
// The case's evidence inventory (GET /api/v1/investigations/{id}/evidence-inventory)

export type InventoryEvidence = {
  id: string;
  business_id?: string | null;
  evidence_identifier?: string | null;
  title?: string | null;
  evidence_type?: string | null;
  source_system?: string | null;
  source_identifier?: string | null;
  source_reference?: string | null;
  source_timestamp?: string | null;
  recorded_timestamp?: string | null;
  ingestion_timestamp?: string | null;
  reliability_status?: string | null;
  fact_type?: string | null;
  has_document?: boolean | null;
};

export type InventoryLink = {
  linked?: boolean | null;
  review_status?: string | null;
  review_status_label?: string | null;
  relationship?: string | null;
  relationship_label?: string | null;
  review_reason?: string | null;
  limitation?: string | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  linked_by_name?: string | null;
  created_at?: string | null;
};

export type InventoryItem = {
  evidence: InventoryEvidence;
  link?: InventoryLink | null;
  origin?: "LINKED" | "DIRECT" | "REQUEST" | string | null;
  request?: { id: string; business_id?: string | null } | null;
};

export type InventoryCounts = Partial<
  Record<
    | "total"
    | "unreviewed"
    | "accepted"
    | "accepted_with_limitation"
    | "rejected"
    | "quarantined"
    | "superseded"
    | "supporting"
    | "contradicting"
    | "contextual"
    | "unresolved"
    | "unrelated",
    number
  >
>;

export type EvidenceInventory = {
  items?: InventoryItem[] | null;
  counts?: InventoryCounts | null;
  actions?: { can_link?: boolean; can_review?: boolean; can_request?: boolean } | null;
};

export const inventoryPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/evidence-inventory`;

const ORIGIN_LABELS: Record<string, string> = {
  LINKED: "Linked",
  DIRECT: "Recorded on the investigation",
  REQUEST: "From a request",
};
export const originLabel = (origin: unknown) =>
  ORIGIN_LABELS[code(origin)] ?? (origin ? titleCase(String(origin)) : "—");

/** An item's review status and relationship (unreviewed when the case has not judged it yet). */
export const itemReview = (item: InventoryItem): ReviewStatus => {
  const value = code(item.link?.review_status);
  return (REVIEW_STATUSES as readonly string[]).includes(value) ? (value as ReviewStatus) : "UNREVIEWED";
};
export const itemRelationship = (item: InventoryItem): Relationship => {
  const value = code(item.link?.relationship);
  return (RELATIONSHIPS as readonly string[]).includes(value) ? (value as Relationship) : "UNREVIEWED";
};

export type InventoryFilter = { review: ReviewStatus | ""; relationship: Relationship | ""; query: string };
export const EMPTY_INVENTORY_FILTER: InventoryFilter = { review: "", relationship: "", query: "" };

export type CountChip<K extends string> = { key: K; label: string; count: number; tone: Tone };

/** The review-status chips over the inventory, with the server's counts (or counted from the items). */
export function reviewChips(inventory: EvidenceInventory | null | undefined): CountChip<ReviewStatus>[] {
  const counts = inventory?.counts ?? {};
  const items = inventory?.items ?? [];
  return REVIEW_STATUSES.map((status) => {
    const fromServer = counts[status.toLowerCase() as keyof InventoryCounts];
    return {
      key: status,
      label: REVIEW_STATUS[status].label,
      count: typeof fromServer === "number" ? fromServer : items.filter((item) => itemReview(item) === status).length,
      tone: REVIEW_STATUS[status].tone,
    };
  });
}

/** The relationship chips (supporting, contradicting, contextual, unresolved, unrelated). */
export function relationshipChips(inventory: EvidenceInventory | null | undefined): CountChip<Relationship>[] {
  const counts = inventory?.counts ?? {};
  const items = inventory?.items ?? [];
  return RELATIONSHIPS.filter((relationship) => relationship !== "UNREVIEWED").map((relationship) => {
    const fromServer = counts[relationship.toLowerCase() as keyof InventoryCounts];
    return {
      key: relationship,
      label: RELATIONSHIP[relationship].label,
      count:
        typeof fromServer === "number"
          ? fromServer
          : items.filter((item) => itemRelationship(item) === relationship).length,
      tone: RELATIONSHIP[relationship].tone,
    };
  });
}

/** The items a filter keeps: by review status, relationship, and text (Evidence ID, title, type, source). */
export function filterInventory(items: InventoryItem[] | null | undefined, filter: InventoryFilter): InventoryItem[] {
  const query = filter.query.trim().toLowerCase();
  return (items ?? []).filter((item) => {
    if (filter.review && itemReview(item) !== filter.review) return false;
    if (filter.relationship && itemRelationship(item) !== filter.relationship) return false;
    if (!query) return true;
    const evidence = item.evidence ?? ({} as InventoryEvidence);
    return [
      evidence.business_id,
      evidence.evidence_identifier,
      evidence.title,
      evidence.evidence_type,
      evidence.source_system,
      evidence.source_identifier,
      item.request?.business_id,
    ].some((value) => (safeText(value) ?? "").toLowerCase().includes(query));
  });
}

/** "SAP QM · QN-1234": where a record came from, never a UUID. */
export function sourceText(
  evidence: Pick<InventoryEvidence, "source_system" | "source_identifier" | "source_reference">,
) {
  const system = safeText(evidence.source_system);
  const record = safeText(evidence.source_identifier) ?? safeText(evidence.source_reference);
  return [system, record].filter(Boolean).join(" · ") || "—";
}

// ---------------------------------------------------------------------------------------------------------------
// Reviewing evidence for a case

export type ReviewForm = { reviewStatus: ReviewStatus; relationship: Relationship; reason: string; limitation: string };

export const REVIEW_REASON_MIN = 10;
export const REVIEW_REASON_MAX = 2000;
const NEEDS_REASON: readonly ReviewStatus[] = ["REJECTED", "QUARANTINED", "SUPERSEDED"];

export const reviewNeedsReason = (status: ReviewStatus) => NEEDS_REASON.includes(status);
export const reviewNeedsLimitation = (status: ReviewStatus) => status === "ACCEPTED_WITH_LIMITATION";

export function reviewFormFrom(item: InventoryItem | null | undefined): ReviewForm {
  return {
    reviewStatus: item ? itemReview(item) : "UNREVIEWED",
    relationship: item ? itemRelationship(item) : "UNREVIEWED",
    reason: "",
    limitation: String(item?.link?.limitation ?? ""),
  };
}

/** Why a review cannot be recorded yet, or null when it can (the server checks the same rules). */
export function reviewProblem(form: ReviewForm): string | null {
  if (!(REVIEW_STATUSES as readonly string[]).includes(form.reviewStatus)) return "Choose a review status.";
  if (!(RELATIONSHIPS as readonly string[]).includes(form.relationship)) return "Choose a relationship.";
  const reason = form.reason.trim();
  if (reviewNeedsReason(form.reviewStatus) && reason.length < REVIEW_REASON_MIN)
    return `Say why it is ${REVIEW_STATUS[form.reviewStatus].label.toLowerCase()}, in at least ${REVIEW_REASON_MIN} characters.`;
  if (reason.length > REVIEW_REASON_MAX) return `Keep the reason to ${REVIEW_REASON_MAX} characters.`;
  const limitation = form.limitation.trim();
  if (reviewNeedsLimitation(form.reviewStatus) && limitation.length < REVIEW_REASON_MIN)
    return `Describe the limitation in at least ${REVIEW_REASON_MIN} characters.`;
  if (limitation.length > REVIEW_REASON_MAX) return `Keep the limitation to ${REVIEW_REASON_MAX} characters.`;
  return null;
}

/** The body of POST .../evidence/{evidence_id}/review: the reason when given, the limitation only when it applies. */
export function reviewBody(form: ReviewForm) {
  const reason = form.reason.trim();
  const limitation = form.limitation.trim();
  return {
    review_status: form.reviewStatus,
    relationship: form.relationship,
    ...(reason ? { reason } : {}),
    ...(reviewNeedsLimitation(form.reviewStatus) && limitation ? { limitation } : {}),
  };
}

export const reviewPath = (investigationId: string, evidenceId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/evidence/${encodeURIComponent(evidenceId)}/review`;
export const provenancePath = (investigationId: string, evidenceId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/evidence/${encodeURIComponent(evidenceId)}/provenance`;
export const linkPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/evidence-links`;

/** The body of POST .../evidence-links: the chosen records, and the relationship and reason when given. */
export function linkBody(evidenceIds: string[], relationship: Relationship | "", reason: string) {
  const why = reason.trim();
  return {
    evidence_ids: [...evidenceIds],
    ...(relationship ? { relationship } : {}),
    ...(why ? { reason: why } : {}),
  };
}

/** Library records offered for linking: matching the search, without those the case already holds. */
export function linkCandidates<T extends { id: string } & Record<string, unknown>>(
  library: T[] | null | undefined,
  linkedIds: string[],
  query: string,
): T[] {
  const search = query.trim().toLowerCase();
  return (library ?? []).filter((row) => {
    if (linkedIds.includes(String(row.id))) return false;
    if (!search) return true;
    return ["business_id", "evidence_identifier", "title", "evidence_type", "source_system"].some((key) =>
      (safeText(row[key]) ?? "").toLowerCase().includes(search),
    );
  });
}

export type ReviewHistoryEvent = {
  event_type?: string | null;
  from_review_status?: string | null;
  to_review_status?: string | null;
  from_relationship?: string | null;
  to_relationship?: string | null;
  reason?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  created_at?: string | null;
};

/** One line of an evidence's review history: what changed, from what to what. */
export function reviewEventText(event: ReviewHistoryEvent): string {
  const what = event.event_type ? titleCase(String(event.event_type)) : "Reviewed";
  const changes: string[] = [];
  if (event.to_review_status && code(event.to_review_status) !== code(event.from_review_status))
    changes.push(
      event.from_review_status
        ? `${reviewStatusLabel(event.from_review_status)} → ${reviewStatusLabel(event.to_review_status)}`
        : reviewStatusLabel(event.to_review_status),
    );
  if (event.to_relationship && code(event.to_relationship) !== code(event.from_relationship))
    changes.push(
      event.from_relationship
        ? `${relationshipLabel(event.from_relationship)} → ${relationshipLabel(event.to_relationship)}`
        : relationshipLabel(event.to_relationship),
    );
  return changes.length ? `${what}: ${changes.join("; ")}` : what;
}

// ---------------------------------------------------------------------------------------------------------------
// Evidence requests (internal and supplier)

export type RequestActions = {
  can_acknowledge?: boolean;
  can_respond?: boolean;
  can_cannot_provide?: boolean;
  can_cancel?: boolean;
  can_review?: boolean;
};

export type EvidenceRequest = {
  id: string;
  business_id?: string | null;
  kind?: "INTERNAL" | "SUPPLIER" | string | null;
  title?: string | null;
  requested_items?: string[] | null;
  rationale?: string | null;
  status?: string | null;
  status_label?: string | null;
  priority?: string | null;
  due_at?: string | null;
  overdue?: boolean | null;
  investigation?: { id: string; business_id?: string | null } | null;
  unknown?: { id: string; business_id?: string | null; description?: string | null } | null;
  requester?: { id?: string | null; name?: string | null } | null;
  recipient?: {
    user?: { id?: string | null; name?: string | null } | null;
    role?: string | null;
    role_label?: string | null;
    supplier?: { id?: string | null; business_id?: string | null; name?: string | null } | null;
    email?: string | null;
  } | null;
  response_note?: string | null;
  responded_at?: string | null;
  cannot_provide_reason?: string | null;
  resolved_evidence?: { id: string; business_id?: string | null } | null;
  attachments_count?: number | null;
  actions?: RequestActions | null;
  created_at?: string | null;
};

export type RequestAttachment = {
  id: string;
  filename?: string | null;
  content_type?: string | null;
  size?: number | null;
  uploaded_at?: string | null;
  created_at?: string | null;
};

export type RequestHistoryEvent = {
  event_type?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  note?: string | null;
  reason?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  created_at?: string | null;
};

export type EvidenceRequestDetail = EvidenceRequest & {
  attachments?: RequestAttachment[] | null;
  history?: RequestHistoryEvent[] | null;
};

export type RequestBox = "sent" | "received" | "all";
export const REQUEST_BOXES: ReadonlyArray<{ box: RequestBox; label: string }> = [
  { box: "received", label: "Received" },
  { box: "sent", label: "Sent" },
];

/** One page of evidence requests (GET /api/v1/evidence-requests), for a case or for the person. */
export function requestListPath(input: {
  investigationId?: string | null;
  box: RequestBox;
  status?: string | null;
  page?: number;
  pageSize?: number;
  /** Searches every page on the server (request ID, title, case, recipient, requester, supplier). */
  q?: string;
  /** A column heading's sort, applied by the server across every page. */
  sort?: SortState;
}): string {
  const params = new URLSearchParams();
  if (input.investigationId) params.set("investigation_id", input.investigationId);
  params.set("box", input.box);
  if (input.status) params.set("status", input.status);
  if (input.q?.trim()) params.set("q", input.q.trim());
  for (const [key, value] of Object.entries(sortParams(input.sort ?? null))) params.set(key, value);
  params.set("page", String(Math.max(1, input.page ?? 1)));
  params.set("page_size", String(input.pageSize ?? 50));
  return `/api/v1/evidence-requests?${params}`;
}

/** The request list's columns the server sorts across every page (GET /api/v1/evidence-requests sort/order). */
export const REQUEST_SORTS = [
  "business_id",
  "title",
  "investigation",
  "party",
  "status",
  "priority",
  "due_at",
  "attachments_count",
] as const;

export type RequestActionKey = "acknowledge" | "respond" | "cannot-provide" | "review" | "cancel";

/** The actions a request offers, in the order shown, each named as the endpoint it calls. */
export const REQUEST_ACTIONS: ReadonlyArray<{
  key: RequestActionKey;
  flag: keyof RequestActions;
  label: string;
  needsInput: boolean;
}> = [
  { key: "acknowledge", flag: "can_acknowledge", label: "Acknowledge", needsInput: false },
  { key: "respond", flag: "can_respond", label: "Respond", needsInput: true },
  { key: "cannot-provide", flag: "can_cannot_provide", label: "Cannot provide", needsInput: true },
  { key: "review", flag: "can_review", label: "Review into evidence", needsInput: true },
  { key: "cancel", flag: "can_cancel", label: "Cancel request", needsInput: true },
];

/** The actions the server allows on this request right now (its `actions` flags). */
export function availableRequestActions(
  request: Pick<EvidenceRequest, "actions"> | null | undefined,
): RequestActionKey[] {
  return REQUEST_ACTIONS.filter((action) => request?.actions?.[action.flag] === true).map((action) => action.key);
}

export const requestPath = (id: string, action?: RequestActionKey | "attachments") =>
  `/api/v1/evidence-requests/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
export const attachmentPath = (requestId: string, attachmentId: string) =>
  `${requestPath(requestId, "attachments")}/${encodeURIComponent(attachmentId)}`;
export const newRequestPath = (investigationId: string) =>
  `/api/v1/investigations/${encodeURIComponent(investigationId)}/evidence-requests`;

const REQUEST_TONES: Record<string, Tone> = {
  DRAFT: "neutral",
  OPEN: "warning",
  SENT: "warning",
  REQUESTED: "warning",
  ACKNOWLEDGED: "warning",
  IN_PROGRESS: "warning",
  RESPONDED: "good",
  REPLIED: "good",
  ACCEPTED: "good",
  REVIEWED: "good",
  RESOLVED: "good",
  CLOSED: "good",
  COMPLETED: "good",
  REJECTED: "critical",
  CANNOT_PROVIDE: "serious",
  CANCELLED: "neutral",
};

export const requestStatusLabel = (request: Pick<EvidenceRequest, "status" | "status_label">) =>
  safeText(request.status_label) ?? (request.status ? titleCase(String(request.status)) : "—");
export const requestStatusTone = (status: unknown): Tone => REQUEST_TONES[code(status)] ?? "neutral";

/** Who a request went to: the person, else the role queue, else the supplier (with the contact email). */
export function requestRecipientText(request: Pick<EvidenceRequest, "recipient">): string {
  const recipient = request.recipient;
  const person = safeText(recipient?.user?.name);
  if (person) return person;
  if (recipient?.role || recipient?.role_label) return roleLabel(recipient.role, recipient.role_label);
  const supplier = safeText(recipient?.supplier?.name) ?? safeText(recipient?.supplier?.business_id);
  const email = safeText(recipient?.email);
  if (supplier) return email ? `${supplier} (${email})` : supplier;
  return email ?? "—";
}

export const requestKindLabel = (kind: unknown) =>
  code(kind) === "SUPPLIER"
    ? "Supplier"
    : code(kind) === "INTERNAL"
      ? "Internal"
      : kind
        ? titleCase(String(kind))
        : "—";

export type NewRequestForm = {
  kind: "INTERNAL" | "SUPPLIER";
  title: string;
  items: string;
  rationale: string;
  unknownId: string;
  dueDay: string;
  priority: string;
  recipientMode: "person" | "role";
  recipientUserId: string;
  recipientRole: string;
  supplierId: string;
  email: string;
};

export const EMPTY_NEW_REQUEST: NewRequestForm = {
  kind: "INTERNAL",
  title: "",
  items: "",
  rationale: "",
  unknownId: "",
  dueDay: "",
  priority: "MEDIUM",
  recipientMode: "person",
  recipientUserId: "",
  recipientRole: "",
  supplierId: "",
  email: "",
};

export const REQUEST_TITLE_MIN = 3;
export const REQUEST_TITLE_MAX = 240;
export const RATIONALE_MAX = 2000;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** The requested items, one per line, trimmed and without empty lines. */
export const requestedItems = (text: string) =>
  text
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

/** Why a new request cannot be sent yet, or null when it can. `today` is the local day (YYYY-MM-DD). */
export function newRequestProblem(form: NewRequestForm, today: string): string | null {
  const title = form.title.trim();
  if (title.length < REQUEST_TITLE_MIN) return `Say what you need in at least ${REQUEST_TITLE_MIN} characters.`;
  if (title.length > REQUEST_TITLE_MAX) return `Keep the title to ${REQUEST_TITLE_MAX} characters.`;
  if (!requestedItems(form.items).length) return "List at least one document or piece of data you need.";
  if (form.rationale.trim().length > RATIONALE_MAX) return `Keep the rationale to ${RATIONALE_MAX} characters.`;
  if (form.kind === "INTERNAL") {
    if (form.recipientMode === "person" && !form.recipientUserId) return "Choose the person to ask.";
    if (form.recipientMode === "role" && !form.recipientRole) return "Choose the role queue to ask.";
  } else {
    if (!form.supplierId) return "Choose the supplier.";
    if (!EMAIL.test(form.email.trim())) return "Enter the supplier contact's email address.";
  }
  if (form.dueDay) {
    if (!DAY.test(form.dueDay)) return "Enter the due date as a date.";
    if (form.dueDay < today) return "The due date cannot be in the past.";
  }
  return null;
}

/** The body of POST /api/v1/investigations/{id}/evidence-requests: only the recipient fields of the chosen kind. */
export function newRequestBody(form: NewRequestForm) {
  const rationale = form.rationale.trim();
  const due = form.dueDay ? dueAtFromDay(form.dueDay) : null;
  return {
    kind: form.kind,
    title: form.title.trim(),
    requested_items: requestedItems(form.items),
    ...(rationale ? { rationale } : {}),
    ...(form.unknownId ? { unknown_id: form.unknownId } : {}),
    ...(due ? { due_at: due } : {}),
    priority: form.priority || "MEDIUM",
    ...(form.kind === "INTERNAL"
      ? form.recipientMode === "person"
        ? { recipient_user_id: form.recipientUserId }
        : { recipient_role: form.recipientRole }
      : { supplier_id: form.supplierId, recipient_email: form.email.trim() }),
  };
}

export const NOTE_MAX = 4000;
export const REQUEST_REASON_MIN = 10;
export const REQUEST_REASON_MAX = 2000;

/** Why a response cannot be sent yet: it needs a note (files are optional). */
export function respondProblem(note: string): string | null {
  const text = note.trim();
  if (!text) return "Write a note with your response.";
  if (text.length > NOTE_MAX) return `Keep the note to ${NOTE_MAX} characters.`;
  return null;
}

/** Why "cannot provide" or a cancellation cannot be sent yet: both need a reason. */
export function requestReasonProblem(reason: string): string | null {
  const text = reason.trim();
  if (text.length < REQUEST_REASON_MIN) return `Give a reason of at least ${REQUEST_REASON_MIN} characters.`;
  if (text.length > REQUEST_REASON_MAX) return `Keep the reason to ${REQUEST_REASON_MAX} characters.`;
  return null;
}

/** Files a response can carry (assumed to match the supplier reply limits: PDF, text, CSV, PNG, JPEG; 10 MB each). */
export const REQUEST_ATTACHMENT_TYPES = ["application/pdf", "text/plain", "text/csv", "image/png", "image/jpeg"];
export const MAX_REQUEST_ATTACHMENT_BYTES = 10 * 1024 * 1024;

export function filesProblem(files: Array<{ name?: string; type: string; size: number }>): string | null {
  for (const file of files) {
    const name = file.name ? `${file.name}: ` : "";
    if (!REQUEST_ATTACHMENT_TYPES.includes(file.type.toLowerCase()))
      return `${name}attach a PDF, a text or CSV file, or a PNG or JPEG image.`;
    if (file.size > MAX_REQUEST_ATTACHMENT_BYTES) return `${name}the file is larger than 10 MB.`;
  }
  return null;
}

export type RequestReviewForm = {
  accept: boolean;
  title: string;
  evidenceType: string;
  reviewStatus: ReviewStatus;
  relationship: Relationship;
  reason: string;
  limitation: string;
};

export function requestReviewFormFrom(request: Pick<EvidenceRequest, "title"> | null | undefined): RequestReviewForm {
  return {
    accept: true,
    title: String(request?.title ?? ""),
    evidenceType: "DOCUMENT",
    reviewStatus: "ACCEPTED",
    relationship: "UNRESOLVED",
    reason: "",
    limitation: "",
  };
}

/** Accepting turns the response into evidence (it needs a title and a review); rejecting needs a reason. */
export function requestReviewProblem(form: RequestReviewForm): string | null {
  if (!form.accept) return requestReasonProblem(form.reason);
  const title = form.title.trim();
  if (title.length < REQUEST_TITLE_MIN) return `Give the evidence a title of at least ${REQUEST_TITLE_MIN} characters.`;
  if (title.length > REQUEST_TITLE_MAX) return `Keep the title to ${REQUEST_TITLE_MAX} characters.`;
  return reviewProblem({
    reviewStatus: form.reviewStatus,
    relationship: form.relationship,
    reason: form.reason,
    limitation: form.limitation,
  });
}

/** The body of POST /api/v1/evidence-requests/{id}/review. */
export function requestReviewBody(form: RequestReviewForm) {
  const reason = form.reason.trim();
  if (!form.accept) return { accept: false, reason };
  const evidenceType = form.evidenceType.trim();
  return {
    accept: true,
    title: form.title.trim(),
    ...(evidenceType ? { evidence_type: evidenceType } : {}),
    ...reviewBody({
      reviewStatus: form.reviewStatus,
      relationship: form.relationship,
      reason,
      limitation: form.limitation,
    }),
  };
}

/** Evidence types offered when a response becomes evidence. */
export const EVIDENCE_TYPES = [
  "DOCUMENT",
  "TEST_REPORT",
  "CERTIFICATE",
  "INSPECTION",
  "DATA_EXTRACT",
  "OTHER",
] as const;

/** One line of a request's history. */
export function requestEventText(event: RequestHistoryEvent): string {
  const what = event.event_type ? titleCase(String(event.event_type)) : "Updated";
  const from = event.from_status ? titleCase(String(event.from_status)) : "";
  const to = event.to_status ? titleCase(String(event.to_status)) : "";
  if (from && to && from !== to) return `${what}: ${from} → ${to}`;
  return to && to !== what ? `${what}: ${to}` : what;
}

// ---------------------------------------------------------------------------------------------------------------
// Where the Evidence section and My Work open a request: "Requests?request=EVR000004"

const REQUEST_REF = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

/** A tab name that carries a request to open: `${tab}?request=<ref>`; the plain tab name without one. */
export function tabWithRequest(tab: string, request?: string | null): string {
  const ref = typeof request === "string" ? request.trim() : "";
  return REQUEST_REF.test(ref) ? `${tab}?${new URLSearchParams({ request: ref })}` : tab;
}

/** The tab name and the request a tab name passed to a section asks for (see tabWithRequest). */
export function parseRequestTab(value: string | null | undefined): { tab: string; request: string | null } {
  const text = String(value ?? "");
  const mark = text.indexOf("?");
  if (mark < 0) return { tab: text, request: null };
  const ref = (new URLSearchParams(text.slice(mark + 1)).get("request") ?? "").trim();
  return { tab: text.slice(0, mark), request: REQUEST_REF.test(ref) ? ref : null };
}
