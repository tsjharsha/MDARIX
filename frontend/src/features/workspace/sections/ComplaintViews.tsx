import { useState } from "react";
import { PhoneCall, Upload } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { Table, listOf, useResource } from "../../customer-admin/shared";
import { displayId } from "../../../app/displayId";
import { NEW_PLACES } from "../../../app/linkTable";
import { offeredTab } from "../../../app/featureSet";
import { canImportOwnData, chooseCase, openImport, useCan, useReportedTab, useWorkspace } from "../workspaceContext";
import { tabParam } from "../workspaceAddress";
import { renamed } from "../workspaceContext";
import { IMPORTED_SOURCE, parseComplaintListTab } from "../complaintList";
import { inData } from "../home";
import { listTitle } from "./common";
import { Triage } from "./Triage";
import { ReportabilityWatch } from "./ReportabilityWatch";
import { ReportsSection } from "./ReportsTab";
import { Communications } from "./Communications";
import { ComplaintList } from "./ComplaintList";
import { Backlog, SecondLook } from "./Complaints";
import { ListViewPicker } from "./Views";
import { FirstContact } from "./FirstContact";
import {
  COMPLAINT_LIST_VIEWS,
  INVESTIGATION_VIEWS,
  SERVER_VIEWS,
  inInvestigationView,
  listViewsFor,
  type InvestigationView,
} from "../listViews";
import { CaseDue, CasePriority, CaseStateBadge, ownerText } from "./CaseHeader";

/** The views of the one complaint list (linkTable.json newPlaces): the same complaints, filtered (7.3; 0.10.74). */
export const COMPLAINT_VIEWS = NEW_PLACES.Complaints.tabs;

/**
 * Complaints on the new navigation: one list of complaints with list views, not 12 tabs (0.10.68). From 0.10.74
 * (Release C part C2) one "List view" choice holds them, the persona's own views first (listViews.ts): the views the
 * server filters show six columns (Urgency, What happened, Product · version · lot, Markets, Owner, Stage) and one row
 * action, cards on a phone; stage 7's work queues keep their own screens. "Log a call" and, outside a trial, "Import
 * your data" are actions on the list's header. Each complaint opens its own page.
 */
export function ComplaintViews({ tab }: { tab?: string }) {
  const { open, session, isTrial, persona, personaLabel } = useWorkspace();
  const [carried] = useState(() => tab);
  const { mine, more } = listViewsFor(persona);
  const [view, setView] = useReportedTab<string>(() => offeredTab(tab, COMPLAINT_LIST_VIEWS, mine[0]));
  // The screens these views came from still name their former tabs (Triage's "Open the reporting clock"): the link
  // table opens each one's new home.
  const go = (classic: string) => open("Complaints", classic);
  // Who may import, by the Import data screen's rule; a trial's button opens its own import, as Help › Try your own
  // data does (0.10.79; until then a trial had it only under Help).
  const canImport = canImportOwnData(session);
  const canLog = useCan("signal.triage") || useCan("investigation.create") || useCan("quality.review");
  const complaint = tabParam(carried, "complaint");
  const server = SERVER_VIEWS[view];
  return (
    <>
      <div className="ca-action-row uw-list-actions">
        <ListViewPicker
          mine={mine}
          more={more}
          active={view}
          onChange={setView}
          forLabel={personaLabel ?? undefined}
          detail={server?.detail ?? QUEUE_DETAIL[view]}
        />
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
          <button type="button" className="ac-secondary" onClick={() => openImport(open, !!isTrial)}>
            <Upload size={15} aria-hidden="true" /> Import your data
          </button>
        )}
      </div>
      {server && <ComplaintList key={view} eyebrow="Complaints" view={{ name: view, code: server.code }} />}
      {view === "To triage" && <Triage onOpenTab={go} />}
      {view === "Calls to check" && <FirstContact part="calls" />}
      {view === "Due soon" && <Backlog initial="due_soon" fixed />}
      {view === "Past target" && <Backlog initial="past_target" fixed />}
      {view === "Second look" && <SecondLook initial="open" fixed />}
      {view === "Dismissed" && <SecondLook initial="dismissed" fixed />}
      {view === "Reporting" && (
        <>
          {/* A market assessment's link (part=assess) opens the complaint's assessment; a report's link its reports. */}
          {(!complaint || tabParam(carried, "part") === "assess") && <ReportabilityWatch onOpenTab={go} />}
          <ReportsSection complaintId={complaint} />
        </>
      )}
      {/* The Reports tab's own list (0.10.81, navigation M7): one status word per state, one count, no "Start the
          worksheet" on the new navigation, where a report is created when its conclusion is signed. */}
      {view === "Authority reports" && <ReportsSection complaintId={complaint} />}
      {view === "Communications" && <Communications key={complaint ?? "all"} complaintId={complaint} />}
      {view === "Investigations" && <InvestigationList />}
      {view === "All complaints" && (
        <ComplaintList
          eyebrow="Complaints"
          initialFilters={parseComplaintListTab(renamed(carried, "Complaint list")).filters}
          work
        />
      )}
    </>
  );
}

/** What each work queue holds, beside the List view choice. */
const QUEUE_DETAIL: Record<string, string> = {
  "To triage": "Urgent intakes, flagged calls and records that suggest harm, most urgent first.",
  "Calls to check": "Calls logged that may be complaints: the first-contact check.",
  "Due soon": "Open complaints within a week of your target.",
  "Past target": "Open complaints older than your target.",
  "Second look": "Records that may be hidden complaints, to confirm or dismiss.",
  Reporting: "Reportability decisions and authority reports.",
  "Authority reports": "Every authority report, with its fields, approval and submission.",
  Communications: "Every message and request with reporters and partners.",
  Investigations: "Every investigation, across products.",
  Dismissed: "Records decided as not complaints, with the reason.",
  "All complaints": "Every complaint, with filters by product, version, lot, problem code, country and status.",
};

/**
 * Every investigation in the organization, across products (the Investigations tab's list, 0.10.74; also the view
 * Complaints › Investigations): a "List view" (open, assigned to me, all) and six columns, Due · Investigation ·
 * Product · Priority · Owner · Stage, with one action; a row opens the investigation's page on its own product.
 */
export function InvestigationList() {
  const { work, open, notify, session, dataSource } = useWorkspace();
  const cases = useResource<any>("/api/v1/data-plane/investigations?limit=500");
  // The Sample · Your data switch decides the investigations listed (0.10.85, D3.9).
  const yours = dataSource === IMPORTED_SOURCE;
  const [view, setView] = useState<InvestigationView>("Open investigations");
  const productName = (id: unknown) => work.products.find((item) => item.id === String(id ?? ""))?.name ?? "—";
  const openCase = async (row: any) => {
    const ref = displayId(row, "investigation_identifier");
    if (await chooseCase(work, String(row.business_id ?? row.investigation_identifier ?? row.id)))
      open("Investigations", "Summary");
    else notify(`${ref} could not be opened right now.`, "critical");
  };
  const rows = listOf(cases.data?.records).filter(
    (row: any) =>
      inInvestigationView(row, view, session?.user_id) &&
      inData(String(row.investigation_identifier ?? row.business_id ?? ""), dataSource),
  );
  return (
    <>
      <div className="ca-action-row uw-list-actions">
        <ListViewPicker
          mine={INVESTIGATION_VIEWS}
          active={view}
          onChange={(next) => setView(next as InvestigationView)}
          detail={
            view === "Assigned to me"
              ? "Open investigations you own."
              : view === "Open investigations"
                ? "Every investigation not closed or cancelled, across products."
                : "Every investigation, closed ones too."
          }
        />
      </div>
      <Panel eyebrow="Investigations" title={listTitle(view, cases.data ? rows.length : undefined)} source={cases}>
        <Table
          caption={view}
          rows={rows}
          rowKey={(row) => String(row.id)}
          empty={{
            title: yours
              ? "No investigation on your data yet"
              : view === "All investigations"
                ? "No investigations yet"
                : "Nothing in this view",
            detail: yours
              ? "Open one from your product's trend: the complaints it groups come into its scope."
              : "An investigation opens from a complaint's page or from a trend.",
            action: (
              <button
                type="button"
                className={yours ? "ac-primary" : "ac-secondary"}
                onClick={() => open("Trends", "Trend check")}
              >
                {yours ? "Open one from the trend" : "See the trends"}
              </button>
            ),
          }}
          columns={[
            { key: "due", label: "Due", render: (row) => <CaseDue row={row} /> },
            {
              key: "question",
              label: "Investigation",
              render: (row) => (
                <span className="uw-what">
                  <button type="button" className="ac-link" onClick={() => void openCase(row)}>
                    <strong>{displayId(row, "investigation_identifier")}</strong>
                  </button>{" "}
                  <span className="uw-what-text">{row.investigation_question ?? "No question recorded"}</span>
                </span>
              ),
            },
            { key: "product", label: "Product", render: (row) => productName(row.product_id) },
            { key: "priority", label: "Priority", render: (row) => <CasePriority priority={row.priority} /> },
            { key: "owner", label: "Owner", render: (row) => ownerText(row) },
            { key: "status", label: "Stage", render: (row) => <CaseStateBadge row={row} /> },
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
    </>
  );
}
