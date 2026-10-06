import { useMemo, useState } from "react";
import { MessageSquareReply, Paperclip } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { Empty, Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { Drawer, Table, Tabs, errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { useCan, useWorkspace } from "../workspaceContext";
import { isOpenInvestigation } from "../workspaceModel";
import { StatusBadge } from "./common";

const TABS = ["Assigned to me", "Needs an owner", "Evidence requests", "My AI conversations"] as const;
type Tab = (typeof TABS)[number];

export function MyWorkSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Assigned to me",
  );
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="My work sections">
        {(active === "Assigned to me" || active === "Needs an owner") && <Cases mine={active === "Assigned to me"} />}
        {active === "Evidence requests" && <EvidenceRequests />}
        {active === "My AI conversations" && <Conversations />}
      </Tabs>
    </>
  );
}

function Cases({ mine }: { mine: boolean }) {
  const { session, work, open } = useWorkspace();
  const cases = useResource<any>("/api/v1/data-plane/investigations?limit=500");
  const me = [session?.user_id, session?.email].filter(Boolean).map((value) => String(value).toLowerCase());
  const rows = useMemo(
    () =>
      listOf(cases.data?.records).filter((row) => {
        const owner = String(row.owner_ref ?? "").toLowerCase();
        return mine ? owner && me.includes(owner) : !owner && isOpenInvestigation(row.status);
      }),
    [cases.data, mine, me.join()],
  );
  const openCase = (row: any) => {
    if (row.product_id && row.product_id !== work.productId) work.setProductId(String(row.product_id));
    work.setInvestigationId(String(row.id));
    open("Investigations", "Workspace");
  };
  return (
    <Panel
      eyebrow="My work"
      title={mine ? "Investigations assigned to you" : "Open investigations without an owner"}
      source={cases}
    >
      <Table
        caption={mine ? "Assigned investigations" : "Unassigned investigations"}
        rows={rows}
        rowKey={(row) => String(row.id)}
        empty={
          mine
            ? { title: "Nothing is assigned to you", detail: "Investigations you own will appear here." }
            : { title: "Every open investigation has an owner", detail: "Unowned open cases would appear here." }
        }
        columns={[
          {
            key: "case",
            label: "Investigation",
            render: (row) => (
              <span className="ca-person">
                <strong>{row.investigation_identifier}</strong>
                <small>{row.investigation_question ?? "No question recorded"}</small>
              </span>
            ),
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
          { key: "opened", label: "Opened", render: (row) => formatDate(row.opened_at ?? row.created_at) },
          {
            key: "open",
            label: "",
            render: (row) => (
              <button type="button" className="ac-link" onClick={() => openCase(row)}>
                Open workspace
              </button>
            ),
          },
        ]}
      />
    </Panel>
  );
}

const EMPTY_REQUEST = { supplier_id: "", recipient: "", title: "", items: "" };

/** Ask one of your suppliers for evidence by email: plain text, no links; the supplier answers through MDARIX. */
function NewEvidenceRequest({ onSent }: { onSent: () => void }) {
  const { work } = useWorkspace();
  const suppliers = useResource<any>("/api/v1/data-plane/suppliers");
  const [form, setForm] = useState({ ...EMPTY_REQUEST });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const items = form.items
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const result = await send<any>("/api/v1/stage3/supplier-evidence-requests", "POST", {
        supplier_id: form.supplier_id,
        recipient: form.recipient.trim(),
        title: form.title.trim(),
        requested_items: items,
        investigation_id: work.investigationId || undefined,
      });
      setMessage({
        tone: "ok",
        text:
          result.status === "SENT"
            ? "Request sent to the supplier."
            : "Request saved; the email will be sent when delivery is available.",
      });
      setForm({ ...EMPTY_REQUEST });
      onSent();
    } catch (reason) {
      setMessage({ tone: "error", text: errorText(reason, "The request was not sent.") });
    } finally {
      setBusy(false);
    }
  };
  const options = listOf(suppliers.data?.records);
  return (
    <Panel eyebrow="Suppliers" title="Request evidence from a supplier">
      <form className="ca-form" onSubmit={submit}>
        <div className="ca-form-grid">
          <label className="ca-field">
            Supplier
            <select
              required
              value={form.supplier_id}
              onChange={(event) => setForm({ ...form, supplier_id: event.target.value })}
            >
              <option value="">{suppliers.state === "loading" ? "Loading…" : "Choose a supplier"}</option>
              {options.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} ({row.supplier_identifier})
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Supplier contact email
            <input
              type="email"
              required
              value={form.recipient}
              placeholder="quality@supplier.com"
              onChange={(event) => setForm({ ...form, recipient: event.target.value })}
            />
          </label>
        </div>
        <label className="ca-field">
          What you need
          <input
            required
            minLength={3}
            maxLength={240}
            value={form.title}
            placeholder="e.g. Certificate of conformance for lot KS-5521"
            onChange={(event) => setForm({ ...form, title: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Documents or data requested (one per line)
          <textarea
            required
            rows={3}
            value={form.items}
            onChange={(event) => setForm({ ...form, items: event.target.value })}
          />
        </label>
        <p className="ac-muted">
          {work.investigationId ? "Linked to the investigation open in your workspace. " : ""}
          The email carries this text only, without links. Requests are limited per person and per day.
        </p>
        {!options.length && suppliers.state === "ready" && (
          <p className="ac-muted">No suppliers yet: load them from your ERP or supplier system first.</p>
        )}
        {message && (
          <p className={message.tone === "ok" ? "ca-inline-ok" : "ca-inline-error"} role="status">
            {message.text}
          </p>
        )}
        <div className="ca-action-row">
          <button
            type="submit"
            className="ac-primary"
            disabled={busy || !form.supplier_id || !items.length || form.title.trim().length < 3}
          >
            {busy ? "Sending…" : "Send request"}
          </button>
        </div>
      </form>
    </Panel>
  );
}

/** Supplier attachments the server accepts (stage3_workflow_router.ALLOWED_ATTACHMENT_TYPES, MAX_ATTACHMENT_BYTES). */
export const ATTACHMENT_TYPES = ["application/pdf", "text/plain", "text/csv", "image/png", "image/jpeg"];
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

/** Why a file cannot be attached to a supplier reply, or null when it can (the server checks it again). */
export function attachmentProblem(file: { type: string; size: number } | null): string | null {
  if (!file) return null;
  if (!ATTACHMENT_TYPES.includes(file.type.toLowerCase()))
    return "Attach a PDF, a text or CSV file, or a PNG or JPEG image.";
  if (file.size > MAX_ATTACHMENT_BYTES) return "The file is larger than 10 MB.";
  return null;
}

/** The body of POST /api/v1/stage3/supplier-requests/{id}/reply: the note, and the uploaded file when there is one. */
export function replyBody(note: string, attachmentId?: string | null) {
  return { note: note.trim(), ...(attachmentId ? { attachment_id: attachmentId } : {}) };
}

export type SupplierReply = {
  id: string;
  note: string;
  attachment_id?: string | null;
  recorded_by?: string;
  recorded_at?: string;
};

/** "2 replies, latest 3 Oct 2026" for the request list (or "No reply yet"). */
export function repliesSummary(replies: SupplierReply[] | undefined, format: (value: unknown) => string): string {
  const list = replies ?? [];
  if (!list.length) return "No reply yet";
  const latest = list[list.length - 1];
  return `${list.length === 1 ? "1 reply" : `${list.length} replies`}, latest ${format(latest.recorded_at)}`;
}

export const REVIEW_NOTICE =
  "Replies are recorded for review. Supplier material is never accepted as evidence automatically: review it and add it to the investigation's evidence yourself.";

function EvidenceRequests() {
  const requests = useResource<any>("/api/v1/stage3/supplier-evidence-requests");
  const canWrite = useCan("records.write");
  const [replying, setReplying] = useState<any | null>(null);
  const rows = listOf(requests.data?.requests ?? requests.data);
  return (
    <>
      {canWrite && <NewEvidenceRequest onSent={requests.reload} />}
      <Panel eyebrow="My work" title="Supplier evidence requests" source={requests}>
        <p className="ac-note">{REVIEW_NOTICE}</p>
        <Table
          caption="Evidence requests"
          rows={rows}
          rowKey={(row, index) => String(row.id ?? index)}
          empty={{ title: "No evidence requests", detail: "Requests sent to suppliers for evidence appear here." }}
          columns={[
            {
              key: "title",
              label: "Request",
              render: (row) => <strong>{row.title ?? row.request_identifier ?? "Request"}</strong>,
            },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "recipient", label: "To", render: (row) => row.recipient ?? "—" },
            { key: "created", label: "Sent", render: (row) => formatDate(row.created_at) },
            { key: "replies", label: "Replies", render: (row) => repliesSummary(row.replies, formatDate) },
            {
              key: "reply",
              label: "",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => setReplying(row)}>
                  <MessageSquareReply size={14} aria-hidden="true" /> {canWrite ? "Record reply" : "View replies"}
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {replying && (
        <SupplierReplies
          request={replying}
          canWrite={canWrite}
          onClose={() => setReplying(null)}
          onSaved={(updated) => {
            setReplying({ ...replying, ...updated });
            requests.reload();
          }}
        />
      )}
    </>
  );
}

/** The exchange with the supplier on one request, and the form to record what they answered. */
function SupplierReplies({
  request,
  canWrite,
  onClose,
  onSaved,
}: {
  request: any;
  canWrite: boolean;
  onClose: () => void;
  onSaved: (updated: { status: string; replies: SupplierReply[] }) => void;
}) {
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const base = `/api/v1/stage3/supplier-evidence-requests/${encodeURIComponent(String(request.id))}`;
  const replies: SupplierReply[] = listOf(request.replies);
  const fileProblem = attachmentProblem(file);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (fileProblem) return;
    setBusy(true);
    setMessage(null);
    try {
      let attachmentId: string | null = null;
      if (file) {
        // The file is stored (and scanned) first; the reply then names it.
        const form = new FormData();
        form.append("file", file);
        const stored = await requestJson<{ id: string }>(`${base}/attachments`, {
          method: "POST",
          body: form,
          timeoutMs: 120_000,
        });
        attachmentId = stored.id;
      }
      const result = await send<{ status: string; replies: SupplierReply[] }>(
        `/api/v1/stage3/supplier-requests/${encodeURIComponent(String(request.id))}/reply`,
        "POST",
        replyBody(note, attachmentId),
      );
      setNote("");
      setFile(null);
      setMessage({ tone: "ok", text: "Reply recorded for review." });
      onSaved({ status: result.status, replies: result.replies });
    } catch (reason) {
      setMessage({ tone: "error", text: errorText(reason, "The reply was not recorded.") });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title={`Replies: ${request.title ?? "Evidence request"}`} onClose={onClose}>
      <p className="ac-note">{REVIEW_NOTICE}</p>
      <section className="ca-drawer-section">
        <h3>Recorded replies</h3>
        {replies.length ? (
          <ul>
            {replies.map((reply) => (
              <li key={reply.id}>
                <p>{reply.note}</p>
                <small className="ac-muted">
                  Recorded {formatDate(reply.recorded_at)}
                  {reply.attachment_id && (
                    <>
                      {" · "}
                      <a
                        className="ac-link"
                        href={`${base}/attachments/${encodeURIComponent(reply.attachment_id)}`}
                        download
                      >
                        <Paperclip size={12} aria-hidden="true" /> Attached file
                      </a>
                    </>
                  )}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No reply recorded yet.</p>
        )}
      </section>
      {canWrite && (
        <form className="ca-form ca-drawer-section" onSubmit={submit}>
          <h3>Record a reply</h3>
          <label className="ca-field">
            What the supplier answered
            <textarea
              required
              rows={4}
              maxLength={4000}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="e.g. Certificate of conformance for lot KS-5521 received by email on 3 Oct"
            />
          </label>
          <label className="ca-field">
            File they sent (optional: PDF, text, CSV, PNG or JPEG, up to 10 MB)
            <input
              type="file"
              accept={ATTACHMENT_TYPES.join(",")}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {fileProblem && (
            <p className="ca-inline-error" role="alert">
              {fileProblem}
            </p>
          )}
          {message && (
            <p className={message.tone === "ok" ? "ca-inline-ok" : "ca-inline-error"} role="status">
              {message.text}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || !note.trim() || !!fileProblem}>
              {busy ? "Recording…" : "Record reply"}
            </button>
          </div>
        </form>
      )}
    </Drawer>
  );
}

function Conversations() {
  const interactions = useResource<any>("/api/v1/stage3/interactions");
  const rows = listOf(interactions.data?.interactions ?? interactions.data);
  return (
    <Panel eyebrow="My work" title="Your Ask MDARIX conversations" source={interactions}>
      {rows.length ? (
        <Table
          caption="AI conversations"
          rows={rows.slice(0, 50)}
          rowKey={(row, index) => String(row.interaction_id ?? row.id ?? index)}
          empty={{ title: "", detail: "" }}
          columns={[
            {
              key: "prompt",
              label: "Question",
              render: (row) => <span className="uw-clamp">{row.prompt ?? row.question ?? "—"}</span>,
            },
            { key: "page", label: "Asked from", render: (row) => titleCase(String(row.page_context ?? "—")) },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
            { key: "when", label: "When", render: (row) => formatDate(row.created_at) },
          ]}
        />
      ) : (
        <Empty title="No conversations yet" detail="Questions you ask Ask MDARIX are listed here, only for you." />
      )}
    </Panel>
  );
}
