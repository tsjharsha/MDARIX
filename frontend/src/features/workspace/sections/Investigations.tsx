import { useState } from "react";
import { Empty, Panel } from "../../admin/console/charts";
import { Table, Tabs, listOf, useResource } from "../../customer-admin/shared";
import { InvestigationWorkspacePanel } from "../../investigator/InvestigationWorkspacePanel";
import { Stage2Experience } from "../../stage2/Stage2Experience";
import { useWorkspace } from "../workspaceContext";
import { Embedded, StatusBadge } from "./common";

const TABS = ["All investigations", "Workspace", "Story"] as const;
type Tab = (typeof TABS)[number];

export function InvestigationsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(
    (TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "All investigations",
  );
  const { work, open } = useWorkspace();
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
