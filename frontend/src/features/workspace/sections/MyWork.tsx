import { useMemo, useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { Table, Tabs, errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { useWorkspace } from "../workspaceContext";
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
      <Tabs tabs={TABS} active={active} onChange={setActive} label="My work sections" />
      {(active === "Assigned to me" || active === "Needs an owner") && <Cases mine={active === "Assigned to me"} />}
      {active === "Evidence requests" && <EvidenceRequests />}
      {active === "My AI conversations" && <Conversations />}
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
      state={cases.state}
      error={cases.error}
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

function EvidenceRequests() {
  const requests = useResource<any>("/api/v1/stage3/supplier-evidence-requests");
  return (
    <>
      <NewEvidenceRequest onSent={requests.reload} />
      <Panel eyebrow="My work" title="Supplier evidence requests" state={requests.state} error={requests.error}>
        <Table
          caption="Evidence requests"
          rows={listOf(requests.data?.requests ?? requests.data)}
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
          ]}
        />
      </Panel>
    </>
  );
}

function Conversations() {
  const interactions = useResource<any>("/api/v1/stage3/interactions");
  const rows = listOf(interactions.data?.interactions ?? interactions.data);
  return (
    <Panel
      eyebrow="My work"
      title="Your Ask MDARIX conversations"
      state={interactions.state}
      error={interactions.error}
    >
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
