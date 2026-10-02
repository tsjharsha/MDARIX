import { useState } from "react";
import { FilePlus2 } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { Table, Tabs, errorText, listOf, send, useResource } from "../../customer-admin/shared";
import { InvestigationWorkspacePanel } from "../../investigator/InvestigationWorkspacePanel";
import { Stage2Experience } from "../../stage2/Stage2Experience";
import { useCan, useWorkspace } from "../workspaceContext";
import { Embedded, StatusBadge } from "./common";

const TABS = ["All investigations", "Workspace", "Story"] as const;
type Tab = (typeof TABS)[number];

export function InvestigationsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "All investigations",
  );
  const { work, open } = useWorkspace();
  const canOpen = useCan("records.write");
  const [starting, setStarting] = useState(false);
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
      {selected && active !== "All investigations" && (
        <p className="ac-note">
          Showing {selected.investigation_identifier} · {selected.status}
        </p>
      )}
    </>
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
