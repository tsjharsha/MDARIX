import { useState } from "react";
import { FilePlus2, Paperclip } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { Panel, ToneBadge } from "../../admin/console/charts";
import {
  Drawer,
  SearchBox,
  Table,
  errorText,
  formatDate,
  listOf,
  matches,
  send,
  useResource,
  type Column,
} from "../../customer-admin/shared";
import { displayId, safeText } from "../../../app/displayId";
import { WORKFLOW_ROLE_CODES, roleLabel } from "../../../app/roles";
import { useCan, useWorkspace } from "../workspaceContext";
import { localDay } from "../workspaceModel";
import { unknownSetFrom } from "../../investigator/savedResults";
import { CASE_PRIORITIES, casePriorityLabel } from "../caseWorkflow";
import { dueState, dueText, pageText, priorityRank, priorityTone } from "../tasks";
import {
  EMPTY_NEW_REQUEST,
  EVIDENCE_TYPES,
  NOTE_MAX,
  QUALITY_VS_RELATIONSHIP,
  RATIONALE_MAX,
  RELATIONSHIP,
  RELATIONSHIPS,
  REQUEST_ACTIONS,
  REQUEST_ATTACHMENT_TYPES,
  REQUEST_BOXES,
  REQUEST_REASON_MAX,
  REQUEST_TITLE_MAX,
  REVIEW_STATUS,
  REVIEW_STATUSES,
  attachmentPath,
  availableRequestActions,
  filesProblem,
  newRequestBody,
  newRequestPath,
  newRequestProblem,
  requestEventText,
  requestKindLabel,
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
  reviewNeedsLimitation,
  reviewNeedsReason,
  type EvidenceRequest,
  type EvidenceRequestDetail,
  type NewRequestForm,
  type Relationship,
  type RequestActionKey,
  type RequestBox,
  type RequestReviewForm,
  type ReviewStatus,
} from "../evidenceWorkflow";

const PAGE_SIZE = 50;

type RequestList = { items?: EvidenceRequest[]; total?: number; page?: number; page_size?: number };

/**
 * Evidence requests, received and sent: for one case (Evidence › Requests) or for the person across cases (My Work).
 * A request named by a task or a link (`initialRequest`) opens at once. New requests are made for a case.
 */
export function EvidenceRequestsPanel({
  investigationId,
  initialRequest = null,
  caseLabel,
}: {
  /** The case whose requests are listed; null lists the person's own requests. */
  investigationId: string | null;
  initialRequest?: string | null;
  /** The case new requests are made for (the context's case), when there is one. */
  caseLabel?: string;
}) {
  const { work } = useWorkspace();
  const canRequest = useCan("evidence.request");
  const [box, setBox] = useState<RequestBox>(investigationId ? "sent" : "received");
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<string | null>(initialRequest);
  const [creating, setCreating] = useState(false);
  const list = useResource<RequestList>(requestListPath({ investigationId, box, page, pageSize: PAGE_SIZE }));
  const rows = (listOf(list.data?.items) as EvidenceRequest[]).filter((row) => matches(row, query));
  const total = list.data?.total ?? rows.length;
  const pages = Math.max(1, Math.ceil(total / (list.data?.page_size || PAGE_SIZE)));
  const newFor = investigationId ?? (work.investigationId || null);
  return (
    <>
      <Panel
        eyebrow={investigationId ? "Case evidence" : "My work"}
        title={investigationId ? `Evidence requests for ${caseLabel ?? "this case"}` : "Evidence requests"}
        source={list}
        action={
          canRequest && newFor ? (
            <button type="button" className="ac-primary" onClick={() => setCreating(true)}>
              <FilePlus2 size={15} aria-hidden="true" /> New request
            </button>
          ) : undefined
        }
      >
        <div className="ca-toolbar">
          <div className="ca-chips" role="radiogroup" aria-label="Which requests">
            {REQUEST_BOXES.map((item) => (
              <button
                type="button"
                role="radio"
                key={item.box}
                aria-checked={box === item.box}
                className={box === item.box ? "selected" : ""}
                onClick={() => {
                  setBox(item.box);
                  setPage(1);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
          <SearchBox value={query} onChange={setQuery} label="Search request ID, title or recipient" />
        </div>
        <p className="ac-note">
          A response is never evidence by itself: the person who asked reviews it into the case's evidence.
        </p>
        <Table
          caption={box === "sent" ? "Evidence requests sent" : "Evidence requests received"}
          rows={rows}
          rowKey={(row) => String(row.id)}
          empty={
            box === "sent"
              ? { title: "No requests sent", detail: "Requests for evidence you or this case sent appear here." }
              : {
                  title: "No requests received",
                  detail: "Requests asking you (or your role) for evidence appear here.",
                }
          }
          columns={requestColumns(box, !investigationId, (row) => setDetail(String(row.id)))}
        />
        {pages > 1 && (
          <div className="ca-action-row uw-pager">
            <span className="ac-muted">
              {pageText({ total, page, page_size: list.data?.page_size || PAGE_SIZE }, rows.length)}
            </span>
            <button
              type="button"
              className="ac-secondary"
              disabled={page <= 1 || list.state === "loading"}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="ac-secondary"
              disabled={page >= pages || list.state === "loading"}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </button>
          </div>
        )}
      </Panel>
      {creating && newFor && (
        <NewRequestDrawer
          investigationId={newFor}
          onClose={() => setCreating(false)}
          onCreated={(made) => {
            setCreating(false);
            setBox("sent");
            list.reload();
            if (made?.id) setDetail(String(made.id));
          }}
        />
      )}
      {detail && (
        <RequestDetailDrawer requestId={detail} onClose={() => setDetail(null)} onChanged={() => list.reload()} />
      )}
    </>
  );
}

function RequestDue({ request }: { request: Pick<EvidenceRequest, "due_at" | "overdue" | "status"> }) {
  const finished = /^(CANCELLED|CLOSED|ACCEPTED|REJECTED|REVIEWED|RESOLVED|COMPLETED)$/i.test(
    String(request.status ?? ""),
  );
  const task = { due_at: request.due_at ?? null, overdue: request.overdue ?? null, status: finished ? "CLOSED" : null };
  const state = dueState(task);
  const text = dueText(task, formatDate);
  if (state === "overdue") return <span className="uw-flag-critical">{text}</span>;
  if (state === "due_soon") return <span className="uw-flag-warning">{text}</span>;
  return <>{text}</>;
}

function requestColumns(
  box: RequestBox,
  showCase: boolean,
  onDetails: (row: EvidenceRequest) => void,
): Column<EvidenceRequest>[] {
  return [
    {
      key: "business_id",
      label: "Request ID",
      fields: ["business_id"],
      render: (row) => safeText(row.business_id) ?? "—",
      sortValue: (row) => safeText(row.business_id),
    },
    {
      key: "title",
      label: "Request",
      fields: ["title", "kind"],
      sortValue: (row) => row.title ?? "",
      render: (row) => (
        <span className="ca-person">
          <strong>{safeText(row.title) ?? "Evidence request"}</strong>
          <small>{requestKindLabel(row.kind)}</small>
        </span>
      ),
    },
    ...(showCase
      ? [
          {
            key: "investigation",
            label: "Case",
            fields: ["investigation"],
            sortValue: (row: EvidenceRequest) => safeText(row.investigation?.business_id),
            render: (row: EvidenceRequest) => safeText(row.investigation?.business_id) ?? "—",
          },
        ]
      : []),
    {
      key: "party",
      label: box === "sent" ? "To" : "From",
      fields: ["recipient", "requester"],
      sortValue: (row) => (box === "sent" ? requestRecipientText(row) : (safeText(row.requester?.name) ?? "")),
      render: (row) => (box === "sent" ? requestRecipientText(row) : (safeText(row.requester?.name) ?? "—")),
    },
    {
      key: "status",
      label: "Status",
      fields: ["status", "status_label"],
      sortValue: (row) => requestStatusLabel(row),
      render: (row) => <ToneBadge tone={requestStatusTone(row.status)} label={requestStatusLabel(row)} />,
    },
    {
      key: "priority",
      label: "Priority",
      sortValue: (row) => priorityRank(row.priority),
      render: (row) =>
        row.priority ? <ToneBadge tone={priorityTone(row.priority)} label={casePriorityLabel(row.priority)} /> : "—",
    },
    {
      key: "due_at",
      label: "Due",
      fields: ["due_at", "overdue"],
      sortValue: (row) => row.due_at ?? "",
      render: (row) => <RequestDue request={row} />,
    },
    {
      key: "attachments_count",
      label: "Files",
      numeric: true,
      render: (row) => (typeof row.attachments_count === "number" ? row.attachments_count : "—"),
    },
    {
      key: "actions",
      label: "",
      render: (row) => (
        <button type="button" className="ac-link" onClick={() => onDetails(row)}>
          {availableRequestActions(row).length ? "Open" : "Details"}
        </button>
      ),
    },
  ];
}

type Person = { id: string; business_id?: string | null; display_name?: string | null };

/** Ask a colleague, a role queue or a supplier for evidence for a case, optionally tied to one of its unknowns. */
export function NewRequestDrawer({
  investigationId,
  unknownId,
  onClose,
  onCreated,
}: {
  investigationId: string;
  unknownId?: string;
  onClose: () => void;
  onCreated: (made: EvidenceRequest | null) => void;
}) {
  const { notify } = useWorkspace();
  const [form, setForm] = useState<NewRequestForm>(() => ({ ...EMPTY_NEW_REQUEST, unknownId: unknownId ?? "" }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const people = useResource<Person[]>(form.kind === "INTERNAL" ? "/api/v1/investigation-assignees" : null);
  const suppliers = useResource<any>(form.kind === "SUPPLIER" ? "/api/v1/data-plane/suppliers" : null);
  const unknowns = useResource<unknown>(`/api/v1/investigations/${encodeURIComponent(investigationId)}/unknowns`);
  const unknownRows = unknownSetFrom(unknowns.data)?.unknowns ?? [];
  const problem = newRequestProblem(form, localDay());
  const set = (change: Partial<NewRequestForm>) => setForm((value) => ({ ...value, ...change }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      const made = await send<EvidenceRequest>(newRequestPath(investigationId), "POST", newRequestBody(form));
      const id = safeText(made?.business_id);
      notify(id ? `Evidence request ${id} sent.` : "Evidence request sent.");
      onCreated(made ?? null);
    } catch (failure) {
      setError(errorText(failure, "The request was not sent."));
      setBusy(false);
    }
  };
  return (
    <Drawer title="New evidence request" onClose={onClose}>
      <form className="ca-form ca-drawer-section" onSubmit={submit}>
        <div className="ca-chips" role="radiogroup" aria-label="Who to ask">
          {(["INTERNAL", "SUPPLIER"] as const).map((kind) => (
            <button
              type="button"
              role="radio"
              key={kind}
              aria-checked={form.kind === kind}
              className={form.kind === kind ? "selected" : ""}
              onClick={() => set({ kind })}
            >
              {kind === "INTERNAL" ? "A colleague or role" : "A supplier"}
            </button>
          ))}
        </div>
        {form.kind === "INTERNAL" ? (
          <>
            <div className="ca-chips" role="radiogroup" aria-label="Ask">
              {(["person", "role"] as const).map((mode) => (
                <button
                  type="button"
                  role="radio"
                  key={mode}
                  aria-checked={form.recipientMode === mode}
                  className={form.recipientMode === mode ? "selected" : ""}
                  onClick={() => set({ recipientMode: mode })}
                >
                  {mode === "person" ? "A person" : "A role queue"}
                </button>
              ))}
            </div>
            {form.recipientMode === "person" ? (
              <label className="ca-field">
                Person
                <select value={form.recipientUserId} onChange={(event) => set({ recipientUserId: event.target.value })}>
                  <option value="">{people.state === "loading" ? "Loading…" : "Choose a person"}</option>
                  {listOf(people.data).map((person: Person) => (
                    <option key={person.id} value={person.id}>
                      {safeText(person.display_name) ?? "Person"}
                      {safeText(person.business_id) ? ` (${person.business_id})` : ""}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="ca-field">
                Role queue
                <select value={form.recipientRole} onChange={(event) => set({ recipientRole: event.target.value })}>
                  <option value="">Choose a role</option>
                  {WORKFLOW_ROLE_CODES.map((code) => (
                    <option key={code} value={code}>
                      {roleLabel(code)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </>
        ) : (
          <div className="ca-form-grid">
            <label className="ca-field">
              Supplier
              <select value={form.supplierId} onChange={(event) => set({ supplierId: event.target.value })}>
                <option value="">{suppliers.state === "loading" ? "Loading…" : "Choose a supplier"}</option>
                {listOf(suppliers.data?.records).map((row: any) => (
                  <option key={row.id} value={row.id}>
                    {row.name} ({displayId(row, "supplier_identifier")})
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Supplier contact email
              <input
                type="email"
                value={form.email}
                placeholder="quality@supplier.com"
                onChange={(event) => set({ email: event.target.value })}
              />
            </label>
          </div>
        )}
        <label className="ca-field">
          What you need
          <input
            required
            maxLength={REQUEST_TITLE_MAX}
            value={form.title}
            placeholder="e.g. Seal hardness test results for lot KS-5521"
            onChange={(event) => set({ title: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Documents or data requested (one per line)
          <textarea required rows={3} value={form.items} onChange={(event) => set({ items: event.target.value })} />
        </label>
        <label className="ca-field">
          Why it is needed (optional)
          <textarea
            rows={2}
            maxLength={RATIONALE_MAX}
            value={form.rationale}
            onChange={(event) => set({ rationale: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Unknown it would resolve (optional)
          <select value={form.unknownId} onChange={(event) => set({ unknownId: event.target.value })}>
            <option value="">
              {unknowns.state === "loading"
                ? "Loading…"
                : unknownRows.length
                  ? "Not tied to an unknown"
                  : "No unknowns recorded for this case"}
            </option>
            {unknownRows.map((row) => (
              <option key={row.unknown_id} value={row.unknown_id}>
                {safeText(row.business_id) ?? "Unknown"} · {row.statement}
              </option>
            ))}
          </select>
        </label>
        <div className="ca-form-grid">
          <label className="ca-field">
            Due (optional)
            <input
              type="date"
              value={form.dueDay}
              min={localDay()}
              onChange={(event) => set({ dueDay: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Priority
            <select value={form.priority} onChange={(event) => set({ priority: event.target.value })}>
              {CASE_PRIORITIES.map((priority) => (
                <option key={priority} value={priority}>
                  {casePriorityLabel(priority)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {form.kind === "SUPPLIER" && (
          <p className="ac-muted">
            The supplier receives this text by email, without links, and answers through MDARIX.
          </p>
        )}
        {(form.title || form.items) && problem && <p className="uw-hint">{problem}</p>}
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
            {busy ? "Sending…" : "Send request"}
          </button>
        </div>
      </form>
    </Drawer>
  );
}

type Mode = "details" | Exclude<RequestActionKey, "acknowledge">;

/** One request: what was asked and answered, its files and history, and the actions the server allows now. */
export function RequestDetailDrawer({
  requestId,
  onClose,
  onChanged,
}: {
  requestId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { work, open, notify } = useWorkspace();
  const detail = useResource<EvidenceRequestDetail>(requestPath(requestId));
  const [mode, setMode] = useState<Mode>("details");
  const [busy, setBusy] = useState(false);
  const request = detail.data;
  const name = safeText(request?.business_id) ?? "Evidence request";
  const actions = availableRequestActions(request);
  const changed = () => {
    setMode("details");
    detail.reload();
    onChanged();
  };
  const acknowledge = async () => {
    setBusy(true);
    try {
      await send(requestPath(requestId, "acknowledge"), "POST");
      notify(`${name}: acknowledged.`);
      changed();
    } catch (failure) {
      notify(errorText(failure, "The request could not be acknowledged."), "critical");
    } finally {
      setBusy(false);
    }
  };
  const openEvidence = () => {
    const kase = request?.investigation;
    if (kase?.id) work.setInvestigationId(String(kase.id), (kase as { product_id?: string | null }).product_id ?? null);
    open("Evidence", "Case evidence");
  };
  const items = request?.requested_items ?? [];
  const attachments = listOf(request?.attachments) as NonNullable<EvidenceRequestDetail["attachments"]>;
  const history = listOf(request?.history) as NonNullable<EvidenceRequestDetail["history"]>;
  return (
    <Drawer title={`${name}: ${safeText(request?.title) ?? "Evidence request"}`} onClose={onClose}>
      {detail.state === "loading" && !request && <p className="ac-muted">Loading…</p>}
      {detail.state !== "loading" && detail.state !== "ready" && (
        <p className="ca-inline-error" role="alert">
          {detail.error ?? "The request could not be read."}
        </p>
      )}
      {request && (
        <>
          <dl className="ca-facts">
            <div>
              <dt>Request ID</dt>
              <dd>{name}</dd>
            </div>
            <div>
              <dt>Kind</dt>
              <dd>{requestKindLabel(request.kind)}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <ToneBadge tone={requestStatusTone(request.status)} label={requestStatusLabel(request)} />
              </dd>
            </div>
            <div>
              <dt>Priority</dt>
              <dd>{casePriorityLabel(request.priority)}</dd>
            </div>
            <div>
              <dt>Due</dt>
              <dd>
                <RequestDue request={request} />
              </dd>
            </div>
            <div>
              <dt>Case</dt>
              <dd>{safeText(request.investigation?.business_id) ?? "—"}</dd>
            </div>
            <div>
              <dt>Asked by</dt>
              <dd>{safeText(request.requester?.name) ?? "—"}</dd>
            </div>
            <div>
              <dt>Asked of</dt>
              <dd>{requestRecipientText(request)}</dd>
            </div>
            {request.unknown && (
              <div className="uw-wide">
                <dt>Unknown it would resolve</dt>
                <dd>
                  {safeText(request.unknown.business_id) ?? "Unknown"}
                  {safeText(request.unknown.description) ? ` · ${request.unknown.description}` : ""}
                </dd>
              </div>
            )}
          </dl>
          <section className="ca-drawer-section">
            <h3>Requested</h3>
            {items.length ? (
              <ul>
                {items.map((item, index) => (
                  <li key={`${index}:${item}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="ac-muted">No items listed.</p>
            )}
            {safeText(request.rationale) && <p>{request.rationale}</p>}
          </section>
          {(request.response_note || request.cannot_provide_reason || attachments.length > 0) && (
            <section className="ca-drawer-section">
              <h3>Response</h3>
              {safeText(request.response_note) && <p className="uw-signal-text">{request.response_note}</p>}
              {safeText(request.cannot_provide_reason) && (
                <p>
                  <strong>Cannot provide:</strong> {request.cannot_provide_reason}
                </p>
              )}
              {request.responded_at && <p className="ac-muted">Answered {formatDate(request.responded_at)}</p>}
              {attachments.length > 0 && (
                <ul>
                  {attachments.map((file) => (
                    <li key={file.id}>
                      <a className="ac-link" href={attachmentPath(requestId, file.id)} download>
                        <Paperclip size={12} aria-hidden="true" /> {safeText(file.filename) ?? "Attached file"}
                      </a>
                      {typeof file.size === "number" && <small className="ac-muted"> · {formatBytes(file.size)}</small>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
          {request.resolved_evidence && (
            <section className="ca-drawer-section">
              <h3>Evidence</h3>
              <p>
                Reviewed into the case's evidence as{" "}
                <strong>{safeText(request.resolved_evidence.business_id) ?? "a new record"}</strong>.
              </p>
              <button type="button" className="ac-secondary" onClick={openEvidence}>
                Open in Case evidence
              </button>
            </section>
          )}
          {mode === "details" ? (
            <section className="ca-drawer-section">
              <h3>Actions</h3>
              <div className="ca-action-row">
                {actions.map((key) => {
                  const item = REQUEST_ACTIONS.find((entry) => entry.key === key);
                  return (
                    <button
                      type="button"
                      key={key}
                      className={key === "review" || key === "respond" ? "ac-primary" : "ac-secondary"}
                      disabled={busy}
                      onClick={() => (key === "acknowledge" ? void acknowledge() : setMode(key))}
                    >
                      {item?.label}
                    </button>
                  );
                })}
                {!actions.length && <p className="ac-muted">Nothing for you to do on this request right now.</p>}
              </div>
            </section>
          ) : mode === "respond" ? (
            <RespondForm requestId={requestId} onCancel={() => setMode("details")} onDone={changed} />
          ) : mode === "cannot-provide" || mode === "cancel" ? (
            <ReasonForm requestId={requestId} action={mode} onCancel={() => setMode("details")} onDone={changed} />
          ) : (
            <ReviewIntoEvidence request={request} onCancel={() => setMode("details")} onDone={changed} />
          )}
          <section className="ca-drawer-section">
            <h3>History</h3>
            {history.length ? (
              <ol className="ca-timeline uw-task-history">
                {history.map((event, index) => (
                  <li key={`${event.created_at ?? ""}:${index}`}>
                    <strong>{requestEventText(event)}</strong>
                    <small className="ac-muted">
                      {safeText(event.actor_name) ?? "MDARIX"}
                      {event.actor_role ? ` (${roleLabel(event.actor_role)})` : ""} · {formatDate(event.created_at)}
                    </small>
                    {(safeText(event.reason) || safeText(event.note)) && <p>{event.reason ?? event.note}</p>}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="ac-muted">No history recorded yet.</p>
            )}
          </section>
        </>
      )}
    </Drawer>
  );
}

const formatBytes = (size: number) =>
  size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;

/** Answer a request: a note, and any files; the files are stored first, then the response is recorded. */
function RespondForm({ requestId, onCancel, onDone }: { requestId: string; onCancel: () => void; onDone: () => void }) {
  const { notify } = useWorkspace();
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = respondProblem(note) ?? filesProblem(files);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      for (const file of files) {
        const body = new FormData();
        body.append("file", file);
        await requestJson(requestPath(requestId, "attachments"), { method: "POST", body, timeoutMs: 120_000 });
      }
      await send(requestPath(requestId, "respond"), "POST", { note: note.trim() });
      notify("Response recorded. The person who asked reviews it into the case's evidence.");
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The response was not recorded."));
      setBusy(false);
    }
  };
  return (
    <form className="ca-form ca-drawer-section" onSubmit={submit}>
      <h3>Respond</h3>
      <label className="ca-field">
        Your response
        <textarea
          required
          rows={4}
          maxLength={NOTE_MAX}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="What you provide, and anything the reviewer should know about it"
        />
      </label>
      <label className="ca-field">
        Files (optional: PDF, text, CSV, PNG or JPEG, up to 10 MB each)
        <input
          type="file"
          multiple
          accept={REQUEST_ATTACHMENT_TYPES.join(",")}
          onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
        />
      </label>
      {files.length > 0 && (
        <p className="ac-muted">{files.length === 1 ? "1 file" : `${files.length} files`} attached.</p>
      )}
      {(note.trim() || files.length > 0) && problem && <p className="uw-hint">{problem}</p>}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onCancel} disabled={busy}>
          Back
        </button>
        <button type="submit" className="ac-primary" disabled={busy || !!problem}>
          {busy ? "Sending…" : "Send response"}
        </button>
      </div>
    </form>
  );
}

/** "Cannot provide" (by the recipient) or "Cancel request" (by the requester): both need a reason. */
function ReasonForm({
  requestId,
  action,
  onCancel,
  onDone,
}: {
  requestId: string;
  action: "cannot-provide" | "cancel";
  onCancel: () => void;
  onDone: () => void;
}) {
  const { notify } = useWorkspace();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = requestReasonProblem(reason);
  const copy =
    action === "cancel"
      ? {
          title: "Cancel this request",
          label: "Why is it cancelled?",
          submit: "Cancel request",
          done: "Request cancelled.",
        }
      : {
          title: "Cannot provide",
          label: "Why can the evidence not be provided?",
          submit: "Record cannot provide",
          done: "Recorded that the evidence cannot be provided.",
        };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      await send(requestPath(requestId, action), "POST", { reason: reason.trim() });
      notify(copy.done);
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The change was not recorded."));
      setBusy(false);
    }
  };
  return (
    <form className="ca-form ca-drawer-section" onSubmit={submit}>
      <h3>{copy.title}</h3>
      <label className="ca-field">
        {copy.label}
        <textarea
          required
          rows={3}
          maxLength={REQUEST_REASON_MAX}
          value={reason}
          placeholder="At least 10 characters"
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      {reason.trim() && problem && <p className="ac-muted">{problem}</p>}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onCancel} disabled={busy}>
          Back
        </button>
        <button type="submit" className={action === "cancel" ? "ca-danger" : "ac-primary"} disabled={busy || !!problem}>
          {busy ? "Saving…" : copy.submit}
        </button>
      </div>
    </form>
  );
}

/** Accept the response as evidence for the case (with its review) or reject it with a reason. */
function ReviewIntoEvidence({
  request,
  onCancel,
  onDone,
}: {
  request: EvidenceRequest;
  onCancel: () => void;
  onDone: () => void;
}) {
  const { notify } = useWorkspace();
  const [form, setForm] = useState<RequestReviewForm>(() => requestReviewFormFrom(request));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = requestReviewProblem(form);
  const set = (change: Partial<RequestReviewForm>) => setForm((value) => ({ ...value, ...change }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await send<any>(requestPath(String(request.id), "review"), "POST", requestReviewBody(form));
      const evidence = safeText(result?.resolved_evidence?.business_id) ?? safeText(result?.evidence?.business_id);
      notify(
        form.accept
          ? `Response accepted as evidence${evidence ? ` ${evidence}` : ""}. Find it in Case evidence.`
          : "Response rejected; the reason is recorded.",
      );
      onDone();
    } catch (failure) {
      setError(errorText(failure, "The review was not recorded."));
      setBusy(false);
    }
  };
  const statuses = REVIEW_STATUSES.filter((status) => status !== "UNREVIEWED");
  return (
    <form className="ca-form ca-drawer-section" onSubmit={submit}>
      <h3>Review into evidence</h3>
      <div className="ca-chips" role="radiogroup" aria-label="Review outcome">
        {[true, false].map((accept) => (
          <button
            type="button"
            role="radio"
            key={String(accept)}
            aria-checked={form.accept === accept}
            className={form.accept === accept ? "selected" : ""}
            onClick={() => set({ accept })}
          >
            {accept ? "Accept as evidence" : "Reject the response"}
          </button>
        ))}
      </div>
      {form.accept ? (
        <>
          <label className="ca-field">
            Evidence title
            <input
              required
              maxLength={REQUEST_TITLE_MAX}
              value={form.title}
              onChange={(event) => set({ title: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Evidence type
            <select value={form.evidenceType} onChange={(event) => set({ evidenceType: event.target.value })}>
              {EVIDENCE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type.charAt(0) + type.slice(1).toLowerCase().replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
          <p className="ac-note">{QUALITY_VS_RELATIONSHIP}</p>
          <div className="ca-form-grid">
            <label className="ca-field">
              Review status (quality)
              <select
                value={form.reviewStatus}
                onChange={(event) => set({ reviewStatus: event.target.value as ReviewStatus })}
              >
                {statuses.map((status) => (
                  <option key={status} value={status}>
                    {REVIEW_STATUS[status].label}
                  </option>
                ))}
              </select>
              <small className="ac-muted">{REVIEW_STATUS[form.reviewStatus].help}</small>
            </label>
            <label className="ca-field">
              Relationship to the question
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
          </div>
          {reviewNeedsLimitation(form.reviewStatus) && (
            <label className="ca-field">
              The limitation
              <textarea
                required
                rows={2}
                maxLength={2000}
                value={form.limitation}
                onChange={(event) => set({ limitation: event.target.value })}
              />
            </label>
          )}
          <label className="ca-field">
            {reviewNeedsReason(form.reviewStatus) ? "Reason (required)" : "Reason (optional)"}
            <textarea
              rows={2}
              maxLength={2000}
              value={form.reason}
              onChange={(event) => set({ reason: event.target.value })}
            />
          </label>
        </>
      ) : (
        <label className="ca-field">
          Why is the response rejected?
          <textarea
            required
            rows={3}
            maxLength={REQUEST_REASON_MAX}
            value={form.reason}
            placeholder="At least 10 characters"
            onChange={(event) => set({ reason: event.target.value })}
          />
        </label>
      )}
      {problem && (form.reason.trim() || form.limitation.trim() || !form.accept) && (
        <p className="uw-hint">{problem}</p>
      )}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" onClick={onCancel} disabled={busy}>
          Back
        </button>
        <button type="submit" className="ac-primary" disabled={busy || !!problem}>
          {busy ? "Saving…" : form.accept ? "Accept into evidence" : "Reject response"}
        </button>
      </div>
    </form>
  );
}
