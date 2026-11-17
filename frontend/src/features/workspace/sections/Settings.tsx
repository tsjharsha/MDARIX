import { useState } from "react";
import { Download } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { Tabs, errorText, send, useResource } from "../../customer-admin/shared";
import { NEW_PLACES } from "../../../app/linkTable";
import { importTemplatesFor, offeredTab } from "../../../app/featureSet";
import {
  useCan,
  useFeatureSet,
  useIsTrial,
  useReportedTab,
  useRoutinePath,
  useWorkspace,
  type BusinessPermission,
} from "../workspaceContext";
import { OVERSIGHT, type OversightSettings } from "../oversight";
import { COMMUNICATIONS } from "../communications";
import { ReviewSettingsPanel } from "./Complaints";
import { ReportingWindows } from "./ReportingWindows";
import { DecisionGuides } from "./DecisionGuides";
import { CalendarPanel } from "./Oversight";
import { DetectionRules } from "./DetectionRules";
import { AttemptsSetting } from "./Communications";
import { IMPORT_PATH, type ImportSetup } from "./ImportData";
import { WhoCanChange } from "./Views";
import { PRODUCT_EDITORS, ProductIdentityPanel, ResponsibleParties } from "./ImportReports";
import { TRIAL_AI_GOVERNANCE_TAB, TRIAL_AI_TAB, TrialAiSettings, useTrialAiOwner } from "./TrialAi";
import { AiGovernance } from "../../customer-admin/sections/AiGovernance";

export const SETTINGS_TABS = NEW_PLACES.Settings.tabs;
type SettingsTab = (typeof SETTINGS_TABS)[number];
type OfferedTab = SettingsTab | typeof TRIAL_AI_TAB | typeof TRIAL_AI_GOVERNANCE_TAB;

/** Who may change each setting: the permission the server checks (each screen keeps its own check as well). */
export const SETTING_PERMISSIONS: Record<SettingsTab, readonly BusinessPermission[]> = {
  "Complaint review rules": ["signal.triage"],
  "Reporting windows": ["regulatory.approve"],
  "Reportability guides": ["regulatory.review", "regulatory.approve"],
  "Working calendar": ["quality.review", "regulatory.approve"],
  "Trend rules": ["signal.triage"],
  "Contact attempts": ["quality.review", "regulatory.approve"],
  "Alerts and files": ["quality.review", "regulatory.approve"],
  "Import templates": ["records.write"],
  Products: PRODUCT_EDITORS,
};

/**
 * Settings on the new navigation (0.10.68): every setting off the daily screens (7.7), in one place. Everyone reads
 * them; each says who can change it, and the form is shown only to them (the server refuses anyone else).
 */
export function SettingsSection({ tab }: { tab?: string }) {
  // A sample-only trial imports nothing, so it has no import templates (0.10.71).
  const sampleOnly = !!useWorkspace().session?.sample_only;
  const routine = useRoutinePath();
  // The person who started a free trial also switches its AI on here (F1); nobody else sees the tab.
  const trialAiOwner = useTrialAiOwner();
  const tabs: OfferedTab[] = [
    ...SETTINGS_TABS.filter(
      (item) => !(sampleOnly && item === "Import templates") && !(!routine && item === "Alerts and files"),
    ),
    ...(trialAiOwner ? [TRIAL_AI_TAB, TRIAL_AI_GOVERNANCE_TAB] : []),
  ];
  const [chosen, setActive] = useReportedTab<OfferedTab>(() =>
    // The AI tab is offered once the settings answer; a link to it waits for that instead of falling back.
    offeredTab(tab, [...tabs, TRIAL_AI_TAB, TRIAL_AI_GOVERNANCE_TAB], "Complaint review rules"),
  );
  const active = tabs.includes(chosen) ? chosen : tabs[0];
  return (
    <Tabs tabs={tabs} active={active} onChange={setActive} label="Settings">
      {active === TRIAL_AI_TAB ? (
        <TrialAiSettings />
      ) : active === TRIAL_AI_GOVERNANCE_TAB ? (
        <AiGovernance change={{ label: `Change in ${TRIAL_AI_TAB}`, onOpen: () => setActive(TRIAL_AI_TAB) }} />
      ) : (
        <SettingOwner tab={active} />
      )}
      {active === "Complaint review rules" && <ReviewSettingsPanel />}
      {active === "Reporting windows" && <ReportingWindows />}
      {active === "Reportability guides" && <DecisionGuides />}
      {active === "Working calendar" && <WorkingCalendar />}
      {active === "Trend rules" && <TrendRules />}
      {active === "Contact attempts" && <ContactAttempts />}
      {active === "Alerts and files" && <AlertsAndFiles />}
      {active === "Import templates" && <ImportTemplates />}
      {active === "Products" && <ProductSettings />}
    </Tabs>
  );
}

function SettingOwner({ tab }: { tab: SettingsTab }) {
  const permissions = SETTING_PERMISSIONS[tab];
  // Hooks in a fixed order: one per permission any setting names.
  const granted: Record<string, boolean> = {
    "signal.triage": useCan("signal.triage"),
    "regulatory.review": useCan("regulatory.review"),
    "regulatory.approve": useCan("regulatory.approve"),
    "quality.review": useCan("quality.review"),
    "records.write": useCan("records.write"),
  };
  return <WhoCanChange permissions={permissions} canChange={permissions.some((item) => granted[item])} />;
}

/** Settings › Products (0.10.77, C5): each product's identity and registrations per market, and the organization's
 * responsible parties with their SRN; the report forms read them. */
function ProductSettings() {
  const { work } = useWorkspace();
  return (
    <>
      <ProductIdentityPanel products={work.products} title="Products: identity and registrations" />
      <ResponsibleParties />
    </>
  );
}

function WorkingCalendar() {
  const settings = useResource<OversightSettings>(`${OVERSIGHT}/settings`);
  return settings.data ? (
    <CalendarPanel settings={settings.data} onSaved={settings.reload} />
  ) : (
    // Each panel names its topic; the page says Settings (0.10.87).
    <Panel eyebrow="Calendar" title="Working calendar and escalation" source={settings}>
      {null}
    </Panel>
  );
}

function TrendRules() {
  const { open } = useWorkspace();
  return (
    <DetectionRules onOpenSignal={(ref) => open("Trends", `Trends to review?signal=${encodeURIComponent(ref)}`)} />
  );
}

function ContactAttempts() {
  const list = useResource<{ attempts_limit: number }>(COMMUNICATIONS);
  return list.data ? (
    <AttemptsSetting value={list.data.attempts_limit} onDone={list.reload} readOnly />
  ) : (
    <Panel eyebrow="Requests" title="Unanswered attempts before a request moves on" source={list}>
      {null}
    </Panel>
  );
}

/**
 * Settings › Alerts and files (B7): the opt-in urgent e-mail ("an urgent case arrived, open MDARIX", nothing about the
 * case) and the organization's file storage for evidence, supplier and Case files. A free trial keeps 100 MB.
 */
export function AlertsAndFiles() {
  const settings = useResource<OversightSettings>(`${OVERSIGHT}/settings`);
  const quality = useCan("quality.review");
  const approve = useCan("regulatory.approve");
  const canSet = quality || approve;
  const trial = useIsTrial();
  const [quota, setQuota] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const shown = settings.data;
  const save = async (body: { urgent_email?: boolean; attachment_quota_mb?: number }, done: string) => {
    setBusy(true);
    setError("");
    setSaved("");
    try {
      await send(`${OVERSIGHT}/settings/alerts-and-files`, "PUT", body);
      setSaved(done);
      setQuota(null);
      settings.reload();
    } catch (reason) {
      setError(errorText(reason, "The setting was not saved."));
    } finally {
      setBusy(false);
    }
  };
  const mb = quota ?? shown?.attachment_quota_mb ?? 100;
  return (
    <Panel eyebrow="Alerts and files" title="Urgent e-mail and file storage" source={settings}>
      {shown && (
        <>
          <p className="ac-muted">
            The urgent e-mail says only that an urgent case arrived and to open MDARIX: no names, no product, no words.
            It goes at once to the people who must act; each delivery is tracked.
          </p>
          <label className="ca-check">
            <input
              type="checkbox"
              checked={!!shown.urgent_email}
              disabled={!canSet || busy}
              onChange={(event) =>
                void save(
                  { urgent_email: event.target.checked },
                  event.target.checked ? "Urgent e-mail is on." : "Urgent e-mail is off; the in-app alert stays.",
                )
              }
            />{" "}
            Send an e-mail when an urgent case arrives
          </label>
          <div className="ca-form-grid">
            <label className="ca-field">
              File storage for this organization (MB)
              <input
                type="number"
                min={1}
                max={10240}
                value={mb}
                disabled={!canSet || busy || trial}
                onChange={(event) => setQuota(Number(event.target.value))}
              />
            </label>
          </div>
          <p className="ac-muted">
            {trial
              ? "A free trial keeps 100 MB for evidence, supplier and case files."
              : "Evidence, supplier and case files count together. A new file over the limit is refused; nothing is deleted."}
          </p>
          {canSet && !trial && (
            <button
              type="button"
              className="ac-primary"
              disabled={busy || quota === null || quota < 1 || quota > 10240}
              onClick={() => void save({ attachment_quota_mb: mb }, `File storage is ${mb} MB.`)}
            >
              Save file storage
            </button>
          )}
          {error && (
            <p className="uw-flag-critical" role="alert">
              {error}
            </p>
          )}
          {saved && <p role="status">{saved}</p>}
        </>
      )}
    </Panel>
  );
}

/** The import templates, to download; importing itself is an action on Complaints ("Import your data"). */
function ImportTemplates() {
  const setup = useResource<ImportSetup>(`${IMPORT_PATH}/templates`);
  const { core, more } = importTemplatesFor(setup.data?.templates ?? [], useFeatureSet());
  return (
    <Panel eyebrow="Templates" title="Import templates" source={setup}>
      <p className="ac-muted">
        Each template names the columns MDARIX reads. Your own export works too: its headers are read under these names.
      </p>
      <ul className="uw-template-list">
        {[...core, ...more].map((item) => (
          <li key={item.entity}>
            <strong>{item.title}</strong>
            <span className="ac-muted"> Required: {item.required.join(", ")}</span>
            <a className="ac-secondary" href={item.download} download>
              <Download size={15} aria-hidden="true" /> {item.entity}.csv
            </a>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
