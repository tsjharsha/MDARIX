import { useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { canImportOwnData, useNavigation, useWorkspace } from "../workspaceContext";
import { IMPORTED_SOURCE, SAMPLE_SOURCE } from "../complaintList";
import type { Insights } from "../trialInsights";
import { ImportPanel, useReportChoice, type ImportResult } from "./ImportData";
import { IMPORT_REPORTS_ID, ImportReportsPanel } from "./ImportReports";
import { InsightsPanel } from "./TrialInsights";
import { RemoveSamplePanel } from "./RemoveSample";
import { DiscussPilot, newComplaints, ownInsights, type TrialStatus } from "./GettingStarted";
import { countOf } from "./common";

/** The trial's insights, of the data the top bar shows (0.10.80); without a choice, the server's own: the imported
 * data, else the sample. */
export const insightsPath = (source?: string) =>
  `/api/v1/trial/insights${source ? `?${new URLSearchParams({ source })}` : ""}`;

/** Complaints › All complaints, only the imported ones: where "See your complaints" goes after an import. */
export const YOUR_COMPLAINTS_TAB = `All complaints?${new URLSearchParams({ source_system: IMPORTED_SOURCE })}`;

/**
 * The trial's own data: the upload, each import's data-quality report and what the data shows (Automatic insights).
 * Getting started › Your data on the classic navigation; the Import your data page on the new one (0.10.80).
 */
export function YourData({
  focus,
  onImported,
  before,
  reportSecondary = false,
  detect = false,
}: {
  focus?: string;
  /** One drop zone that detects the object (the new navigation's Import page, 0.10.82 D1.10). */
  detect?: boolean;
  /** The page's main button is elsewhere (Import your data's "See your complaints"). */
  reportSecondary?: boolean;
  /** After an import, what else the screen reads again (Getting started: its story). */
  onImported?: (result: ImportResult, entity: string) => void;
  /** A line above the upload (Getting started: "Remove the sample data"). */
  before?: ReactNode;
}) {
  const { work, dataSource } = useWorkspace();
  // Complaints imported here: until the insights are read from them (a busy server takes a while, and the first read
  // may time out), the panel says it is reading them and reads again, rather than showing the sample's figures as if
  // they were current (item 9). Not while the top bar shows the sample: then the sample's insights are the right ones.
  const [ownImported, setOwnImported] = useState(false);
  const expectOwn = ownImported && dataSource !== SAMPLE_SOURCE;
  const insights = useResource<Insights>(insightsPath(dataSource), {
    refreshWhile: (data) => expectOwn && !ownInsights(data),
  });
  const readingImported = expectOwn && insights.state !== "error" && !ownInsights(insights.data);
  const reports = useReportChoice(focus);
  // On the new navigation the drop zone says each file is checked (0.10.87): only the link to the reports here.
  const fresh = useNavigation() === "new";
  return (
    <>
      {before}
      <p className="uw-cited-line">
        {!fresh && "Each import has a data-quality report: rows read, written and set aside, and why. "}
        <button
          type="button"
          className="ac-link"
          onClick={() => document.getElementById(IMPORT_REPORTS_ID)?.scrollIntoView({ behavior: "smooth" })}
        >
          See the data-quality reports
        </button>
      </p>
      <ImportPanel
        id="trial-import"
        onReport={reports.show}
        reportSecondary={reportSecondary}
        detect={detect}
        onImported={(result, entity) => {
          reports.imported(result.import_ref);
          if (newComplaints(entity, result) > 0) setOwnImported(true);
          insights.reload();
          work.refreshProducts();
          onImported?.(result, entity);
        }}
      />
      <ImportReportsPanel selected={reports.selected} onSelect={reports.setSelected} refreshKey={reports.refreshKey} />
      <InsightsPanel insights={insights.data} source={insights} reading={readingImported} />
    </>
  );
}

/**
 * Import your data (/app/import, 0.10.80): a trial's own import on the new navigation, opened by the top bar's button
 * (the avatar menu on a phone), the Complaints header and Help › Try your own data. The upload, its data-quality
 * reports and what the data shows; once the organization's complaints are in, one main button to them; removing the
 * sample is offered, never forced. A sample-only trial and a person who may not change records are told it is not
 * available (the server refuses their imports either way).
 */
export function ImportYourDataSection({ focus }: { focus?: string }) {
  const { session, open, notify, chooseDataSource, refreshTrial } = useWorkspace();
  const status = useResource<TrialStatus>("/api/v1/trial/status");
  if (session?.sample_only) return <DiscussPilot onOpen={() => open("Next steps")} />;
  if (!canImportOwnData(session))
    return (
      <Empty
        title="Import is not available to you"
        detail="Bringing in data needs a role that may change records. Ask the person who started the trial."
      />
    );
  const trial = status.data;
  const own = trial?.own_data?.complaints ?? 0;
  const hasSample = (trial?.sample?.complaints ?? 0) > 0;
  const seeYours = () => {
    chooseDataSource?.(IMPORTED_SOURCE);
    open("Complaints", YOUR_COMPLAINTS_TAB);
  };
  return (
    <>
      {own > 0 && (
        <Panel eyebrow="Your data is in" title={`${countOf(own, "complaint")} of your own`}>
          <p>
            Every screen works on them as usual.
            {hasSample ? " The sample stays beside them: the top bar shows one or the other." : ""}
          </p>
          <div className="ca-action-row">
            {/* "Choose a file" is the page's main button (0.10.82, D1.10). */}
            <button type="button" className="ac-secondary" onClick={seeYours}>
              See your complaints <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
        </Panel>
      )}
      <YourData
        focus={focus}
        detect
        reportSecondary
        onImported={() => {
          status.reload();
          refreshTrial?.();
        }}
      />
      {hasSample && trial?.is_owner && (
        <details className="uw-more uw-remove-option">
          <summary>Optional: remove the sample data, so every screen shows only your records</summary>
          <RemoveSamplePanel
            onRemoved={(text) => {
              notify(text);
              status.reload();
              refreshTrial?.();
            }}
          />
        </details>
      )}
    </>
  );
}
