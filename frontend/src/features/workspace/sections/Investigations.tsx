import { useState } from "react";
import { FilePlus2 } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { Drawer, Table, Tabs, errorText, formatDate, listOf, send, useResource } from "../../customer-admin/shared";
import { InvestigationWorkspacePanel } from "../../investigator/InvestigationWorkspacePanel";
import { Stage2Experience } from "../../stage2/Stage2Experience";
import { useCan, useWorkspace } from "../workspaceContext";
import { Embedded, StatusBadge } from "./common";

const TABS = ["All investigations", "Workspace", "Story", "CAPAs"] as const;
type Tab = (typeof TABS)[number];

export function InvestigationsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "All investigations",
  );
  const { work, open } = useWorkspace();
  const canOpen = useCan("records.write");
  const [starting, setStarting] = useState(false);
  const [managing, setManaging] = useState<any | null>(null);
  const all = useResource<any>("/api/v1/analytics/investigations");
  const selected = work.investigations.find((item) => String(item.id) === work.investigationId);
  const openCase = (id: string) => {
    if (work.investigations.some((item) => String(item.id) === id)) {
      work.setInvestigationId(id);
      setActive("Workspace");
    }
  };
  return (
    <>
      <p className="ca-lede">
        MDARIX organizes evidence and possible explanations. It never concludes a root cause for you.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Investigation sections" />
      {active === "All investigations" && canOpen && (
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={() => setStarting((value) => !value)}>
            <FilePlus2 size={16} /> {starting ? "Close" : "Open an investigation"}
          </button>
        </div>
      )}
      {active === "All investigations" && starting && (
        <OpenInvestigation
          onOpened={(id) => {
            setStarting(false);
            all.reload();
            work.refreshInvestigations(id);
            setActive("Workspace");
          }}
        />
      )}
      {active === "All investigations" && (
        <Panel eyebrow="Investigations" title="Investigations in your organization" state={all.state} error={all.error}>
          <Table
            caption="Investigations"
            rows={listOf(all.data?.investigations)}
            rowKey={(row) => String(row.id)}
            empty={{
              title: "No investigations yet",
              detail: "Investigations opened in your organization appear here.",
            }}
            columns={[
              { key: "id", label: "Investigation", render: (row) => <strong>{row.investigation_identifier}</strong> },
              { key: "question", label: "Question", render: (row) => row.investigation_question ?? "—" },
              { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
              ...(canOpen
                ? [
                    {
                      key: "manage",
                      label: "",
                      render: (row: any) => (
                        <button type="button" className="ac-link" onClick={() => setManaging(row)}>
                          Manage
                        </button>
                      ),
                    },
                  ]
                : []),
              {
                key: "open",
                label: "",
                render: (row) =>
                  work.investigations.some((item) => String(item.id) === String(row.id)) ? (
                    <button type="button" className="ac-link" onClick={() => openCase(String(row.id))}>
                      Open workspace
                    </button>
                  ) : (
                    <span className="ac-muted" title="Choose its product in the context bar to open it">
                      Other product
                    </span>
                  ),
              },
            ]}
          />
        </Panel>
      )}
      {managing && (
        <ManageInvestigation
          row={managing}
          onClose={() => setManaging(null)}
          onSaved={() => {
            setManaging(null);
            all.reload();
            work.refreshInvestigations();
          }}
        />
      )}
      {active === "Workspace" &&
        (work.investigationId ? (
          <Embedded>
            <InvestigationWorkspacePanel
              investigationId={work.investigationId}
              temporalMode={work.mode}
              asOf={work.asOf}
              onOpenDecision={() => open("Decisions")}
            />
          </Embedded>
        ) : (
          <Panel title="No investigation selected">
            <Empty
              title="Choose an investigation"
              detail="Pick one in the context bar above, or open one from the list."
            />
          </Panel>
        ))}
      {active === "Story" &&
        (work.investigationId ? (
          <Embedded>
            <Stage2Experience mode="story" investigationId={work.investigationId} />
          </Embedded>
        ) : (
          <Panel title="No investigation selected">
            <Empty
              title="Choose an investigation"
              detail="The story follows one investigation from signal to decision."
            />
          </Panel>
        ))}
      {active === "CAPAs" && <Capas />}
      {selected && active !== "All investigations" && active !== "CAPAs" && (
        <p className="ac-note">
          Showing {selected.investigation_identifier} · {selected.status}
        </p>
      )}
    </>
  );
}

/** Corrective and preventive actions from the quality system, with the case they came from. */
function Capas() {
  const capas = useResource<any>("/api/v1/data-plane/capas");
  const cases = useResource<any>("/api/v1/data-plane/investigations?limit=500");
  const caseName = new Map(
    listOf(cases.data?.records).map((row) => [String(row.id), String(row.investigation_identifier)] as const),
  );
  const today = new Date().toISOString().slice(0, 10);
  return (
    <Panel eyebrow="Quality system" title="CAPAs" state={capas.state} error={capas.error}>
      <Table
        caption="CAPAs"
        rows={listOf(capas.data?.records)}
        rowKey={(row) => String(row.id)}
        empty={{ title: "No CAPAs yet", detail: "CAPAs arrive from your quality system through its connection." }}
        columns={[
          {
            key: "capa",
            label: "CAPA",
            fields: ["capa_identifier", "title"],
            render: (row) => (
              <span className="ca-person">
                <strong>{row.capa_identifier}</strong>
                <small>{row.title}</small>
              </span>
            ),
          },
          { key: "type", label: "Type", fields: ["action_type"], render: (row) => row.action_type ?? "—" },
          {
            key: "case",
            label: "From",
            fields: ["investigation_id", "source_reference"],
            render: (row) => caseName.get(String(row.investigation_id)) ?? row.source_reference ?? "—",
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge value={row.status} /> },
          {
            key: "due",
            label: "Due",
            fields: ["due_at"],
            render: (row) => {
              const due = row.due_at ? String(row.due_at).slice(0, 10) : "";
              const late = due && due < today && !/closed/i.test(String(row.status));
              return late ? (
                <span className="uw-flag-critical">{formatDate(row.due_at)} · overdue</span>
              ) : (
                formatDate(row.due_at)
              );
            },
          },
        ]}
      />
    </Panel>
  );
}

/** Open a case for one of the organization's products: the question it must answer and the complaints behind it. */
function OpenInvestigation({ onOpened }: { onOpened: (id: string) => void }) {
  const { work, notify } = useWorkspace();
  const [question, setQuestion] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const complaints = (work.view?.complaints ?? []) as Array<Record<string, string | null>>;
  const product = work.products.find((item) => item.id === work.productId);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const made = await send<{ id: string; investigation_identifier: string }>("/api/v1/investigations", "POST", {
        product_id: work.productId,
        investigation_question: question.trim(),
        complaint_ids: chosen,
      });
      notify(`Investigation ${made.investigation_identifier} opened and assigned to you.`);
      onOpened(made.id);
    } catch (reason) {
      setError(errorText(reason, "The investigation could not be opened."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      eyebrow="New investigation"
      title={product ? `Open an investigation for ${product.name}` : "Open an investigation"}
    >
      {!work.productId ? (
        <Empty title="Choose a product first" detail="Pick the product in the context bar above." />
      ) : (
        <form className="ca-form" onSubmit={submit}>
          <label className="ca-field">
            The question this investigation must answer
            <textarea
              required
              minLength={10}
              maxLength={2000}
              rows={3}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="For example: Why did occlusion alarms rise after release B?"
            />
          </label>
          <fieldset className="ca-fieldset">
            <legend>Complaints that prompted it (optional)</legend>
            {complaints.length ? (
              complaints.slice(0, 50).map((row) => {
                const id = String(row.id ?? "");
                return (
                  <label className="ca-check" key={id || String(row.complaint_identifier)}>
                    <input
                      type="checkbox"
                      disabled={!id}
                      checked={chosen.includes(id)}
                      onChange={(event) =>
                        setChosen((value) =>
                          event.target.checked ? [...value, id] : value.filter((item) => item !== id),
                        )
                      }
                    />
                    {row.complaint_identifier ?? id} · {row.description ?? "No description"}
                  </label>
                );
              })
            ) : (
              <p className="ac-muted">No complaints recorded for the selected version.</p>
            )}
          </fieldset>
          {error && (
            <p className="ac-message tone-critical" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy || question.trim().length < 10}>
              {busy ? "Opening…" : "Open investigation"}
            </button>
          </div>
        </form>
      )}
    </Panel>
  );
}

/** Edit a case's question, assign it, close or reopen it. Every change carries a reason for the audit trail. */
function ManageInvestigation({ row, onClose, onSaved }: { row: any; onClose: () => void; onSaved: () => void }) {
  const { notify } = useWorkspace();
  const people = useResource<Array<{ id: string; display_name: string }>>("/api/v1/investigation-assignees");
  const closed = String(row.status ?? "").toLowerCase() === "closed";
  const [question, setQuestion] = useState(String(row.investigation_question ?? ""));
  const [assignee, setAssignee] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (change: Record<string, unknown>, done: string) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/investigations/${row.id}`, "PATCH", { ...change, reason: reason.trim() });
      notify(done);
      onSaved();
    } catch (failure) {
      setError(errorText(failure, "The change was not saved."));
    } finally {
      setBusy(false);
    }
  };
  const reasonReady = reason.trim().length >= 10;
  return (
    <Drawer title={`Manage ${row.investigation_identifier}`} onClose={onClose}>
      <label className="ca-field">
        Reason for the change (kept in the audit trail)
        <textarea rows={2} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      {closed ? (
        <div className="ca-action-row">
          <button
            type="button"
            className="ac-primary"
            disabled={!reasonReady || busy}
            onClick={() => void save({ status: "open" }, `${row.investigation_identifier} reopened.`)}
          >
            Reopen investigation
          </button>
        </div>
      ) : (
        <>
          <label className="ca-field">
            Question
            <textarea
              rows={3}
              minLength={10}
              maxLength={2000}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
          </label>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={
                !reasonReady || busy || question.trim().length < 10 || question.trim() === row.investigation_question
              }
              onClick={() => void save({ investigation_question: question.trim() }, "Question updated.")}
            >
              Save question
            </button>
          </div>
          <label className="ca-field">
            Assign to
            <select value={assignee} onChange={(event) => setAssignee(event.target.value)}>
              <option value="">Choose a colleague</option>
              {listOf(people.data).map((person) => (
                <option key={person.id} value={person.id}>
                  {person.display_name}
                </option>
              ))}
            </select>
          </label>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-secondary"
              disabled={!reasonReady || busy || !assignee}
              onClick={() => void save({ assignee_id: assignee }, `${row.investigation_identifier} assigned.`)}
            >
              Assign
            </button>
            <button
              type="button"
              className="ac-secondary"
              disabled={!reasonReady || busy}
              onClick={() => void save({ unassign: true }, `${row.investigation_identifier} has no owner now.`)}
            >
              Remove owner
            </button>
          </div>
          <div className="ca-action-row">
            <button
              type="button"
              className="ac-primary"
              disabled={!reasonReady || busy}
              onClick={() => void save({ status: "closed" }, `${row.investigation_identifier} closed.`)}
            >
              Close investigation
            </button>
          </div>
          <p className="ac-muted">A case with a decision still awaiting its human review cannot be closed.</p>
        </>
      )}
      {error && (
        <p className="ac-message tone-critical" role="alert">
          {error}
        </p>
      )}
    </Drawer>
  );
}
