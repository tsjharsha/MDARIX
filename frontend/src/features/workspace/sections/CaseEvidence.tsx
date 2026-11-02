import { useState } from "react";
import { FilePlus2, Link2 } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import {
  Drawer,
  SearchBox,
  Table,
  errorText,
  formatDate,
  listOf,
  send,
  useResource,
  type Column,
} from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { roleLabel } from "../../../app/roles";
import { usePanelFlag, usePanelState, useWorkspace } from "../workspaceContext";
import {
  EMPTY_INVENTORY_FILTER,
  QUALITY_VS_RELATIONSHIP,
  RELATIONSHIP,
  RELATIONSHIPS,
  REVIEW_REASON_MAX,
  REVIEW_STATUS,
  REVIEW_STATUSES,
  filterInventory,
  inventoryPath,
  itemRelationship,
  itemReview,
  linkBody,
  linkCandidates,
  linkPath,
  originLabel,
  provenancePath,
  relationshipChips,
  relationshipLabel,
  relationshipTone,
  requestKindLabel,
  reviewBody,
  reviewChips,
  reviewEventText,
  reviewFormFrom,
  reviewNeedsLimitation,
  reviewNeedsReason,
  reviewPath,
  reviewProblem,
  reviewStatusLabel,
  reviewStatusTone,
  sourceText,
  type EvidenceInventory,
  type InventoryFilter,
  type InventoryItem,
  type Relationship,
  type ReviewForm,
  type ReviewHistoryEvent,
  type ReviewStatus,
} from "../evidenceWorkflow";
import { NewRequestDrawer, RequestDetailDrawer } from "./EvidenceRequests";
import { readableSize } from "./ImportData";

/**
 * The evidence of one case: every record linked to it, recorded on it or received through a request, with how the
 * case judges it (review status) and how it bears on the question (relationship). Review, linking and requests follow
 * the server's `actions` for the person.
 */
export function CaseEvidencePanel({ investigationId, caseLabel }: { investigationId: string; caseLabel: string }) {
  const inventory = useResource<EvidenceInventory>(inventoryPath(investigationId));
  const [filter, setFilter] = useState<InventoryFilter>(EMPTY_INVENTORY_FILTER);
  const items = listOf(inventory.data?.items) as InventoryItem[];
  // Each drawer has its own address (panel=<kind>:<id>), so Back closes it and a refresh reopens it.
  const byId = (id: string) => items.find((item) => String(item.evidence?.id) === id) ?? null;
  const evidenceKey = (item: InventoryItem) => String(item.evidence?.id);
  const [reviewing, setReviewing] = usePanelState<InventoryItem>("review-evidence", evidenceKey, byId);
  const [provenance, setProvenance] = usePanelState<InventoryItem>("provenance", evidenceKey, byId);
  const [linking, setLinking] = usePanelFlag("link-evidence-records");
  const [requesting, setRequesting] = usePanelFlag("new-request");
  const [request, setRequest] = usePanelState<string>(
    "request",
    (id) => id,
    (id) => id,
  );
  const shown = filterInventory(items, filter);
  const actions = inventory.data?.actions ?? {};
  const total = inventory.data?.counts?.total ?? items.length;
  return (
    <>
      <Panel
        eyebrow={caseLabel}
        title="Investigation evidence"
        source={inventory}
        action={
          actions.can_link || actions.can_request ? (
            <span className="uw-task-actions">
              {actions.can_link && (
                <button type="button" className="ac-primary" onClick={() => setLinking(true)}>
                  <Link2 size={15} aria-hidden="true" /> Link evidence
                </button>
              )}
              {actions.can_request && (
                <button type="button" className="ac-secondary" onClick={() => setRequesting(true)}>
                  <FilePlus2 size={15} aria-hidden="true" /> Request evidence
                </button>
              )}
            </span>
          ) : undefined
        }
      >
        <p className="ac-note">
          {total} {total === 1 ? "record" : "records"} in this case. {QUALITY_VS_RELATIONSHIP}
        </p>
        <div className="uw-evidence-chips">
          <div className="ca-chips" role="group" aria-label="Filter by review status">
            <span className="ac-muted">Review status</span>
            {reviewChips(inventory.data).map((chip) => (
              <button
                type="button"
                key={chip.key}
                aria-pressed={filter.review === chip.key}
                className={filter.review === chip.key ? "selected" : ""}
                onClick={() => setFilter((value) => ({ ...value, review: value.review === chip.key ? "" : chip.key }))}
              >
                {chip.label} <span className="ac-tab-count">{chip.count}</span>
              </button>
            ))}
          </div>
          <div className="ca-chips" role="group" aria-label="Filter by relationship">
            <span className="ac-muted">Relationship</span>
            {relationshipChips(inventory.data).map((chip) => (
              <button
                type="button"
                key={chip.key}
                aria-pressed={filter.relationship === chip.key}
                className={filter.relationship === chip.key ? "selected" : ""}
                onClick={() =>
                  setFilter((value) => ({
                    ...value,
                    relationship: value.relationship === chip.key ? "" : chip.key,
                  }))
                }
              >
                {chip.label} <span className="ac-tab-count">{chip.count}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="ca-toolbar">
          <SearchBox
            value={filter.query}
            onChange={(query) => setFilter((value) => ({ ...value, query }))}
            label="Search evidence ID, title, type or source"
          />
          {(filter.review || filter.relationship || filter.query) && (
            <button type="button" className="ac-link" onClick={() => setFilter(EMPTY_INVENTORY_FILTER)}>
              Clear filters
            </button>
          )}
        </div>
        <Table
          caption="Investigation evidence"
          rows={shown}
          rowKey={(row) => String(row.evidence?.id)}
          empty={
            items.length
              ? { title: "No matching evidence", detail: "Change the filters to see more." }
              : {
                  title: "No evidence in this investigation yet",
                  detail: "Link records from the evidence library, or request evidence from colleagues or suppliers.",
                }
          }
          columns={inventoryColumns({
            canReview: !!actions.can_review,
            onReview: setReviewing,
            onProvenance: setProvenance,
            onRequest: (id) => setRequest(id),
          })}
        />
      </Panel>
      {reviewing && (
        <ReviewDrawer
          investigationId={investigationId}
          item={reviewing}
          onClose={() => setReviewing(null)}
          onDone={() => {
            setReviewing(null);
            inventory.reload();
          }}
        />
      )}
      {provenance && (
        <ProvenanceDrawer investigationId={investigationId} item={provenance} onClose={() => setProvenance(null)} />
      )}
      {linking && (
        <LinkDrawer
          investigationId={investigationId}
          linkedIds={items.map((item) => String(item.evidence?.id))}
          onClose={() => setLinking(false)}
          onDone={() => {
            setLinking(false);
            inventory.reload();
          }}
        />
      )}
      {requesting && (
        <NewRequestDrawer
          investigationId={investigationId}
          onClose={() => setRequesting(false)}
          onCreated={(made) => {
            setRequesting(false);
            if (made?.id) setRequest(String(made.id));
          }}
        />
      )}
      {request && (
        <RequestDetailDrawer
          requestId={request}
          onClose={() => setRequest(null)}
          onChanged={() => inventory.reload()}
        />
      )}
    </>
  );
}

function inventoryColumns(handlers: {
  canReview: boolean;
  onReview: (item: InventoryItem) => void;
  onProvenance: (item: InventoryItem) => void;
  onRequest: (id: string) => void;
}): Column<InventoryItem>[] {
  return [
    {
      key: "business_id",
      label: "Evidence ID",
      fields: ["evidence"],
      sortValue: (row) => safeText(row.evidence?.business_id) ?? safeText(row.evidence?.evidence_identifier),
      render: (row) => (
        <span className="ca-person">
          <strong>{safeText(row.evidence?.business_id) ?? safeText(row.evidence?.evidence_identifier) ?? "—"}</strong>
          {safeText(row.evidence?.business_id) && safeText(row.evidence?.evidence_identifier) && (
            <small>Source ID {row.evidence.evidence_identifier}</small>
          )}
        </span>
      ),
    },
    {
      key: "title",
      label: "Title",
      sortValue: (row) => row.evidence?.title ?? "",
      render: (row) => safeText(row.evidence?.title) ?? "—",
    },
    {
      key: "type",
      label: "Type",
      sortValue: (row) => row.evidence?.evidence_type ?? "",
      render: (row) => (row.evidence?.evidence_type ? titleCase(String(row.evidence.evidence_type)) : "—"),
    },
    {
      key: "source",
      label: "Source",
      sortValue: (row) => sourceText(row.evidence ?? {}),
      render: (row) => sourceText(row.evidence ?? {}),
    },
    {
      key: "origin",
      label: "Origin",
      fields: ["origin", "request"],
      sortValue: (row) => originLabel(row.origin),
      render: (row) => (
        <span className="ca-person">
          <span>{originLabel(row.origin)}</span>
          {row.request?.id && (
            <button type="button" className="ac-link" onClick={() => handlers.onRequest(String(row.request?.id))}>
              {safeText(row.request.business_id) ?? "Open request"}
            </button>
          )}
        </span>
      ),
    },
    {
      key: "review_status",
      label: "Review status",
      fields: ["link"],
      sortValue: (row) => REVIEW_STATUSES.indexOf(itemReview(row)),
      render: (row) => (
        <span className="ca-person">
          <ToneBadge
            tone={reviewStatusTone(itemReview(row))}
            label={reviewStatusLabel(itemReview(row), row.link?.review_status_label)}
          />
          {safeText(row.link?.limitation) && <small>Limitation: {row.link?.limitation}</small>}
        </span>
      ),
    },
    {
      key: "relationship",
      label: "Relationship",
      sortValue: (row) => RELATIONSHIPS.indexOf(itemRelationship(row)),
      render: (row) => (
        <ToneBadge
          tone={relationshipTone(itemRelationship(row))}
          label={relationshipLabel(itemRelationship(row), row.link?.relationship_label)}
        />
      ),
    },
    {
      key: "reviewed",
      label: "Reviewed",
      sortValue: (row) => row.link?.reviewed_at ?? "",
      render: (row) =>
        row.link?.reviewed_at || row.link?.reviewed_by_name ? (
          <span className="ca-person">
            <span>{safeText(row.link?.reviewed_by_name) ?? "—"}</span>
            <small>{formatDate(row.link?.reviewed_at)}</small>
          </span>
        ) : (
          <span className="ac-muted">Not yet</span>
        ),
    },
    {
      key: "actions",
      label: "",
      render: (row) => (
        <span className="uw-task-actions">
          {handlers.canReview && (
            <button type="button" className="ac-link" onClick={() => handlers.onReview(row)}>
              Review
            </button>
          )}
          <button type="button" className="ac-link" onClick={() => handlers.onProvenance(row)}>
            Provenance
          </button>
        </span>
      ),
    },
  ];
}

const evidenceName = (item: InventoryItem) =>
  safeText(item.evidence?.business_id) ?? safeText(item.evidence?.evidence_identifier) ?? "Evidence";

/** Judge one record for this case: its review status (quality) and, separately, its relationship to the question. */
function ReviewDrawer({
  investigationId,
  item,
  onClose,
  onDone,
}: {
  investigationId: string;
  item: InventoryItem;
  onClose: () => void;
  onDone: () => void;
}) {
  const { notify } = useWorkspace();
  const [form, setForm] = useState<ReviewForm>(() => reviewFormFrom(item));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = reviewProblem(form);
  const name = evidenceName(item);
  const set = (change: Partial<ReviewForm>) => setForm((value) => ({ ...value, ...change }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(reviewPath(investigationId, String(item.evidence.id)), "POST", reviewBody(form));
      notify(`${name}: review recorded.`);
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The review was not recorded."));
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Review ${name}`} onClose={onClose}>
      <p className="ac-muted">{safeText(item.evidence?.title) ?? "Untitled record"}</p>
      <p className="ac-note">{QUALITY_VS_RELATIONSHIP}</p>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <label className="ca-field">
          Review status: can it be relied on?
          <select
            value={form.reviewStatus}
            onChange={(event) => set({ reviewStatus: event.target.value as ReviewStatus })}
          >
            {REVIEW_STATUSES.map((status) => (
              <option key={status} value={status}>
                {REVIEW_STATUS[status].label}
              </option>
            ))}
          </select>
          <small className="ac-muted">{REVIEW_STATUS[form.reviewStatus].help}</small>
        </label>
        <label className="ca-field">
          Relationship: how does it bear on the question?
          <select
            value={form.relationship}
            onChange={(event) => set({ relationship: event.target.value as Relationship })}
          >
            {RELATIONSHIPS.map((relationship) => (
              <option key={relationship} value={relationship}>
                {RELATIONSHIP[relationship].label}
              </option>
            ))}
          </select>
          <small className="ac-muted">{RELATIONSHIP[form.relationship].help}</small>
        </label>
        {reviewNeedsLimitation(form.reviewStatus) && (
          <label className="ca-field">
            The limitation (shown wherever this evidence is used)
            <textarea
              required
              rows={2}
              maxLength={REVIEW_REASON_MAX}
              value={form.limitation}
              placeholder="At least 10 characters"
              onChange={(event) => set({ limitation: event.target.value })}
            />
          </label>
        )}
        <label className="ca-field">
          {reviewNeedsReason(form.reviewStatus) ? "Reason (required)" : "Reason (optional)"}
          <textarea
            required={reviewNeedsReason(form.reviewStatus)}
            rows={3}
            maxLength={REVIEW_REASON_MAX}
            value={form.reason}
            placeholder={reviewNeedsReason(form.reviewStatus) ? "At least 10 characters" : undefined}
            onChange={(event) => set({ reason: event.target.value })}
          />
        </label>
        {problem && (form.reason.trim() || form.limitation.trim()) && <p className="uw-hint">{problem}</p>}
        <p className="ac-muted">Every review is kept in the evidence's history and the audit trail.</p>
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Saving…" : "Record review"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

type LibraryRecord = { id: string } & Record<string, unknown>;

/** Link records from the organization's evidence library to this case, optionally with their relationship. */
function LinkDrawer({
  investigationId,
  linkedIds,
  onClose,
  onDone,
}: {
  investigationId: string;
  linkedIds: string[];
  onClose: () => void;
  onDone: () => void;
}) {
  const { notify } = useWorkspace();
  const library = useResource<LibraryRecord[]>("/api/v1/evidence?limit=200");
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [relationship, setRelationship] = useState<Relationship | "">("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const all = listOf(library.data) as LibraryRecord[];
  const candidates = linkCandidates(all, linkedIds, query);
  const shown = [
    ...all.filter((row) => chosen.includes(String(row.id)) && !candidates.includes(row)),
    ...candidates.slice(0, 50),
  ];
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!chosen.length || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(linkPath(investigationId), "POST", linkBody(chosen, relationship, reason));
      notify(
        chosen.length === 1
          ? "1 record linked to the investigation."
          : `${chosen.length} records linked to the investigation.`,
      );
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The evidence was not linked."));
      setBusy(false);
    }
  };
  return (
    <Drawer title="Link evidence to the investigation" onClose={onClose}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <SearchBox value={query} onChange={setQuery} label="Search the evidence library" />
        <p className="ac-note" role="status">
          {chosen.length} selected · {candidates.length} not yet in this case
          {candidates.length > 50 ? " (search to narrow the list)" : ""}
        </p>
        {library.state === "loading" && !library.data ? (
          <p className="ac-muted">Loading the evidence library…</p>
        ) : library.state !== "ready" ? (
          <p className="ca-inline-error">{library.error ?? "The evidence library could not be read."}</p>
        ) : shown.length ? (
          <ul className="uw-pick-list">
            {shown.map((row) => {
              const id = String(row.id);
              return (
                <li key={id}>
                  <label className="ca-check">
                    <input
                      type="checkbox"
                      checked={chosen.includes(id)}
                      onChange={(event) =>
                        setChosen((value) =>
                          event.target.checked ? [...value, id] : value.filter((item) => item !== id),
                        )
                      }
                    />
                    <span>
                      <strong>{safeText(row.business_id) ?? safeText(row.evidence_identifier) ?? "Evidence"}</strong>{" "}
                      {safeText(row.title) ?? ""}
                      <small className="ac-muted">
                        {" "}
                        · {row.evidence_type ? titleCase(String(row.evidence_type)) : "Type not recorded"} ·{" "}
                        {safeText(row.source_system) ?? "source not recorded"}
                      </small>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="ac-muted">No other records match.</p>
        )}
        <label className="ca-field">
          Relationship (optional: you can review it later)
          <select value={relationship} onChange={(event) => setRelationship(event.target.value as Relationship | "")}>
            <option value="">Not judged yet</option>
            {RELATIONSHIPS.filter((item) => item !== "UNREVIEWED").map((item) => (
              <option key={item} value={item}>
                {RELATIONSHIP[item].label}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Why they belong to this case (optional)
          <textarea
            rows={2}
            maxLength={REVIEW_REASON_MAX}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <p className="ac-muted">Linked records start unreviewed: linking is not accepting.</p>
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || !chosen.length}>
            {busy ? "Linking…" : chosen.length > 1 ? `Link ${chosen.length} records` : "Link record"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

type Provenance = {
  evidence?: Record<string, unknown> | null;
  source?: Record<string, unknown> | null;
  document?: {
    available?: boolean | null;
    filename?: string | null;
    content_type?: string | null;
    checksum?: string | null;
    size?: number | null;
  } | null;
  request?: {
    id: string;
    business_id?: string | null;
    kind?: string | null;
    title?: string | null;
    requested_by_name?: string | null;
    responded_at?: string | null;
  } | null;
  review_history?: ReviewHistoryEvent[] | null;
  used_by?: { observations?: unknown; hypotheses?: unknown } | null;
};

const TIME_KEY = /(_at|_time|timestamp)$/;

/** "PDF", "PNG image", "Word document": a file's type as people name it, else its media type as recorded. */
function fileTypeText(contentType: unknown): string {
  const type = safeText(contentType)?.toLowerCase();
  if (!type) return "—";
  if (type === "application/pdf") return "PDF";
  if (type.startsWith("image/")) return `${type.slice(6).toUpperCase()} image`;
  if (type === "text/csv") return "CSV file";
  if (type === "text/plain") return "Text file";
  if (type.includes("wordprocessingml") || type === "application/msword") return "Word document";
  if (type.includes("spreadsheetml") || type === "application/vnd.ms-excel") return "Excel workbook";
  return type;
}

/** Plain headings for the source fields a record's provenance carries; any other field is shown by its own name. */
const SOURCE_LABELS: Record<string, string> = {
  system: "Source system",
  record_identifier: "ID in the source system",
  record_version: "Version in the source system",
  reference: "Reference",
  source_timestamp: "Dated in the source",
  effective_timestamp: "Effective",
  recorded_timestamp: "Recorded in the source",
  ingestion_timestamp: "Received by MDARIX",
  checksum: "File fingerprint",
  data_quality_status: "Data quality",
  ingestion_run: "Import run",
  connector_run: "Connector run",
  mapping_version: "Mapping version",
};

/** A provenance value as text: dates in the person's time zone, records by their ID or name, never a UUID. */
function provenanceValue(key: string, value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return (
      safeText(record.business_id) ??
      safeText(record.name) ??
      safeText(record.version) ??
      safeText(record.label) ??
      safeText(record.identifier) ??
      null
    );
  }
  if (TIME_KEY.test(key)) return formatDate(value);
  return safeText(value);
}

const usedByText = (value: unknown, noun: string, nouns: string) => {
  if (typeof value === "number") return `${value} ${value === 1 ? noun : nouns}`;
  if (Array.isArray(value)) {
    const names = value
      .map((item) =>
        typeof item === "object" && item
          ? (safeText((item as Record<string, unknown>).business_id) ??
            safeText((item as Record<string, unknown>).statement))
          : safeText(item),
      )
      .filter(Boolean);
    return `${value.length} ${value.length === 1 ? noun : nouns}${names.length ? `: ${names.slice(0, 5).join(", ")}` : ""}`;
  }
  return `0 ${nouns}`;
};

/** Where a record came from (system, record, times, ingestion), its document, the request it answered, its review
 * history in this case, and what in the case uses it. */
function ProvenanceDrawer({
  investigationId,
  item,
  onClose,
}: {
  investigationId: string;
  item: InventoryItem;
  onClose: () => void;
}) {
  const provenance = useResource<Provenance>(provenancePath(investigationId, String(item.evidence.id)));
  const data = provenance.data;
  const source = Object.entries(data?.source ?? {})
    .map(([key, value]) => ({ key, value: provenanceValue(key, value) }))
    .filter((entry): entry is { key: string; value: string } => !!entry.value);
  const history = listOf(data?.review_history) as ReviewHistoryEvent[];
  return (
    <Drawer title={`Provenance of ${evidenceName(item)}`} onClose={onClose}>
      <p className="ac-muted">{safeText(item.evidence?.title) ?? "Untitled record"}</p>
      {provenance.state === "loading" && !data && <p className="ac-muted">Loading…</p>}
      {provenance.state !== "loading" && provenance.state !== "ready" && (
        <p className="ca-inline-error" role="alert">
          {provenance.error ?? "The provenance could not be read."}
        </p>
      )}
      {data && (
        <>
          <section className="ca-drawer-section">
            <h3>Source</h3>
            {source.length ? (
              <dl className="ca-facts">
                {source.map((entry) => (
                  <div key={entry.key}>
                    <dt>{SOURCE_LABELS[entry.key] ?? titleCase(entry.key)}</dt>
                    <dd>{entry.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="ac-muted">No source details recorded.</p>
            )}
          </section>
          <section className="ca-drawer-section">
            <h3>Document</h3>
            {data.document?.available ? (
              <dl className="ca-facts">
                <div>
                  <dt>File</dt>
                  <dd>{safeText(data.document.filename) ?? "—"}</dd>
                </div>
                <div>
                  <dt>Type</dt>
                  <dd>{fileTypeText(data.document.content_type)}</dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{typeof data.document.size === "number" ? readableSize(data.document.size) : "—"}</dd>
                </div>
                <div className="uw-wide">
                  <dt>File fingerprint</dt>
                  <dd>
                    <code>{safeText(data.document.checksum) ?? "—"}</code>
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="ac-muted">No document is stored with this record.</p>
            )}
          </section>
          {data.request && (
            <section className="ca-drawer-section">
              <h3>Request it answered</h3>
              <p>
                <strong>{safeText(data.request.business_id) ?? "Request"}</strong>
                {safeText(data.request.title) ? ` · ${data.request.title}` : ""}
              </p>
              <p className="ac-muted">
                {data.request.kind ? `${requestKindLabel(data.request.kind)} request` : "Request"}
                {safeText(data.request.requested_by_name) ? ` by ${data.request.requested_by_name}` : ""}
                {data.request.responded_at ? ` · answered ${formatDate(data.request.responded_at)}` : ""}
              </p>
            </section>
          )}
          <section className="ca-drawer-section">
            <h3>Review history in this investigation</h3>
            {history.length ? (
              <ol className="ca-timeline uw-task-history">
                {history.map((event, index) => (
                  <li key={`${event.created_at ?? ""}:${index}`}>
                    <strong>{reviewEventText(event)}</strong>
                    <small className="ac-muted">
                      {safeText(event.actor_name) ?? "MDARIX"}
                      {event.actor_role ? ` (${roleLabel(event.actor_role)})` : ""} · {formatDate(event.created_at)}
                    </small>
                    {safeText(event.reason) && <p>{event.reason}</p>}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="ac-muted">Not reviewed in this investigation yet.</p>
            )}
          </section>
          <section className="ca-drawer-section">
            <h3>Used by</h3>
            <ul className="ca-pill-list">
              <li>{usedByText(data.used_by?.observations, "observation", "observations")}</li>
              <li>{usedByText(data.used_by?.hypotheses, "hypothesis", "hypotheses")}</li>
            </ul>
          </section>
        </>
      )}
    </Drawer>
  );
}
