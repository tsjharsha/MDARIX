import { useState } from "react";
import { PhoneCall, Upload } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { Table, idColumn, listOf, useResource } from "../../customer-admin/shared";
import { displayId } from "../../../app/displayId";
import { NEW_PLACES } from "../../../app/linkTable";
import { offeredTab } from "../../../app/featureSet";
import { chooseCase, sectionAllowed, useCan, useReportedTab, useWorkspace } from "../workspaceContext";
import { tabParam } from "../workspaceAddress";
import { renamed } from "../workspaceContext";
import { parseComplaintListTab } from "../complaintList";
import { StatusBadge } from "./common";
import { Triage } from "./Triage";
import { ReportabilityWatch } from "./ReportabilityWatch";
import { Reports } from "./Reports";
import { Communications } from "./Communications";
import { ComplaintList } from "./ComplaintList";
import { Backlog, SecondLook } from "./Complaints";
import { ViewChooser } from "./Views";

/** The views of the one complaint list (linkTable.json newPlaces): the same complaints, filtered (7.3). */
export const COMPLAINT_VIEWS = NEW_PLACES.Complaints.tabs;
export type ComplaintView = (typeof COMPLAINT_VIEWS)[number];

/**
 * Complaints on the new navigation (0.10.68): one list of complaints with views, not 12 tabs. "To triage" first;
 * "Due soon" and "Past target" against the organization's target; "Second look" and "Dismissed" for possible hidden
 * complaints; "Reporting", the one home of the reportability decisions and the authority reports; "Communications";
 * "Investigations"; and "All complaints", the list itself (an extra view: the unfiltered list, with its own filters).
 * "Import your data" and "Log a call" are actions on the list's header. Each complaint opens its own page.
 */
export function ComplaintViews({ tab }: { tab?: string }) {
  const { open, session } = useWorkspace();
  const [carried] = useState(() => tab);
  const [view, setView] = useReportedTab<ComplaintView>(() => offeredTab(tab, COMPLAINT_VIEWS, "To triage"));
  // The screens these views came from still name their former tabs (Triage's "Open the reporting clock"): the link
  // table opens each one's new home.
  const go = (classic: string) => open("Complaints", classic);
  const canImport = sectionAllowed("Import data", session?.allowed_menu, session?.business_permissions);
  const canLog = useCan("signal.triage") || useCan("investigation.create") || useCan("quality.review");
  const complaint = tabParam(carried, "complaint");
  return (
    <>
      <div className="ca-action-row uw-list-actions">
        {canLog && (
          <button
            type="button"
            className="ac-secondary"
            onClick={() => open("Complaints", "First contact?log=CONTACT")}
          >
            <PhoneCall size={15} aria-hidden="true" /> Log a call
          </button>
        )}
        {canImport && (
          <button type="button" className="ac-secondary" onClick={() => open("Import data")}>
            <Upload size={15} aria-hidden="true" /> Import your data
          </button>
        )}
      </div>
      <ViewChooser views={COMPLAINT_VIEWS} active={view} onChange={setView} label="Complaint views">
        {view === "To triage" && <Triage onOpenTab={go} />}
        {view === "Due soon" && <Backlog initial="due_soon" fixed />}
        {view === "Past target" && <Backlog initial="past_target" fixed />}
        {view === "Second look" && <SecondLook initial="open" fixed />}
        {view === "Dismissed" && <SecondLook initial="dismissed" fixed />}
        {view === "Reporting" && (
          <>
            {!complaint && <ReportabilityWatch onOpenTab={go} />}
            <Reports complaintId={complaint} />
          </>
        )}
        {view === "Communications" && <Communications key={complaint ?? "all"} complaintId={complaint} />}
        {view === "Investigations" && <InvestigationList />}
        {view === "All complaints" && (
          <ComplaintList
            eyebrow="Complaints"
            initialFilters={parseComplaintListTab(renamed(carried, "Complaint list")).filters}
            work
          />
        )}
      </ViewChooser>
    </>
  );
}

/**
 * Every investigation in the organization, across products (the view Complaints › Investigations, also opened from
 * Trends): a row opens the case page on its own product.
 */
export function InvestigationList() {
  const { work, open, notify } = useWorkspace();
  const cases = useResource<any>("/api/v1/data-plane/investigations?limit=500");
  const openCase = async (row: any) => {
    const ref = displayId(row, "investigation_identifier");
    if (await chooseCase(work, String(row.business_id ?? row.investigation_identifier ?? row.id)))
      open("Investigations", "Workspace");
    else notify(`${ref} could not be opened right now.`, "critical");
  };
  return (
    <Panel eyebrow="Complaints" title="Investigations" source={cases}>
      <Table
        caption="Investigations"
        rows={listOf(cases.data?.records)}
        rowKey={(row) => String(row.id)}
        empty={{
          title: "No investigations yet",
          detail: "Open one from a complaint's page or from a trend.",
        }}
        columns={[
          idColumn("Investigation", "investigation_identifier"),
          {
            key: "question",
            label: "Question",
            render: (row) => row.investigation_question ?? "—",
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge value={row.workflow_state ?? row.status} /> },
          {
            key: "open",
            label: "",
            render: (row) => (
              <button
                type="button"
                className="ac-secondary"
                aria-label={`Open ${displayId(row, "investigation_identifier")}`}
                onClick={() => void openCase(row)}
              >
                Open
              </button>
            ),
          },
        ]}
      />
    </Panel>
  );
}
