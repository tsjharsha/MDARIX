import { Download } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { Tabs, useResource } from "../../customer-admin/shared";
import { NEW_PLACES } from "../../../app/linkTable";
import { importTemplatesFor, offeredTab } from "../../../app/featureSet";
import { useCan, useFeatureSet, useReportedTab, useWorkspace, type BusinessPermission } from "../workspaceContext";
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

export const SETTINGS_TABS = NEW_PLACES.Settings.tabs;
type SettingsTab = (typeof SETTINGS_TABS)[number];

/** Who may change each setting: the permission the server checks (each screen keeps its own check as well). */
export const SETTING_PERMISSIONS: Record<SettingsTab, readonly BusinessPermission[]> = {
  "Complaint review rules": ["signal.triage"],
  "Reporting windows": ["regulatory.approve"],
  "Reportability guides": ["regulatory.review", "regulatory.approve"],
  "Working calendar": ["quality.review", "regulatory.approve"],
  "Trend rules": ["signal.triage"],
  "Contact attempts": ["quality.review", "regulatory.approve"],
  "Import templates": ["records.write"],
};

/**
 * Settings on the new navigation (0.10.68): every setting off the daily screens (7.7), in one place. Everyone reads
 * them; each says who can change it, and the form is shown only to them (the server refuses anyone else).
 */
export function SettingsSection({ tab }: { tab?: string }) {
  const [active, setActive] = useReportedTab<SettingsTab>(() =>
    offeredTab(tab, SETTINGS_TABS, "Complaint review rules"),
  );
  return (
    <Tabs tabs={SETTINGS_TABS} active={active} onChange={setActive} label="Settings">
      <SettingOwner tab={active} />
      {active === "Complaint review rules" && <ReviewSettingsPanel />}
      {active === "Reporting windows" && <ReportingWindows />}
      {active === "Reportability guides" && <DecisionGuides />}
      {active === "Working calendar" && <WorkingCalendar />}
      {active === "Trend rules" && <TrendRules />}
      {active === "Contact attempts" && <ContactAttempts />}
      {active === "Import templates" && <ImportTemplates />}
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

function WorkingCalendar() {
  const settings = useResource<OversightSettings>(`${OVERSIGHT}/settings`);
  return settings.data ? (
    <CalendarPanel settings={settings.data} onSaved={settings.reload} />
  ) : (
    <Panel eyebrow="Settings" title="Working calendar and escalation" source={settings}>
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
    <Panel eyebrow="Settings" title="Unanswered attempts before a request moves on" source={list}>
      {null}
    </Panel>
  );
}

/** The import templates, to download; importing itself is an action on Complaints ("Import your data"). */
function ImportTemplates() {
  const setup = useResource<ImportSetup>(`${IMPORT_PATH}/templates`);
  const { core, more } = importTemplatesFor(setup.data?.templates ?? [], useFeatureSet());
  return (
    <Panel eyebrow="Settings" title="Import templates" source={setup}>
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
