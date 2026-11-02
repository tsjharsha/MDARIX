import { useState } from "react";
import { placeOf } from "../../../app/linkTable";
import {
  AlarmClock,
  Archive,
  ChevronRight,
  Download,
  FileCheck2,
  Hourglass,
  ScanSearch,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import { Panel, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { describeError } from "../../../app/apiClient";
import { downloadFile } from "../../reports/download";
import { useCan, useWorkspace, type WorkspaceSection, useReportedTab } from "../workspaceContext";
import {
  READINESS_PATH,
  SUMMARY_PERIODS,
  inspectionPackPath,
  basisIds,
  checkStateOf,
  checkValue,
  itemsText,
  readinessHeadline,
  summaryPdfPath,
  type Readiness,
  type ReadinessCheck,
} from "../readiness";
import { InlineError } from "./boardParts";
import { BasisChips, BasisNote } from "../../shared/Basis";
import { QualityLoop } from "./QualityLoop";
import { loopFromReadiness } from "../qualityLoop";
import { documentLink } from "../documents";
import { FINDING_SIGNALS_NOW, WHILE_FINDING_SIGNALS } from "../signals";
import { Tabs } from "../../customer-admin/shared";
import { READINESS_TABS, parseReadinessTab, type ReadinessTab } from "../oversight";
import { OversightView } from "./Oversight";

const HOME_ICONS: Record<string, typeof ScanSearch> = {
  COMPLAINTS_TO_RECHECK: ScanSearch,
  COMPLAINTS_PAST_TARGET: Hourglass,
  REPORTING_CLOCKS: AlarmClock,
  TRENDS_WITHOUT_ACTION: TrendingUp,
};

/** The check that reads the organization's signals: it waits for an import's signals while they are being found. */
const TRENDS_CHECK = "TRENDS_WITHOUT_ACTION";

/**
 * Readiness: what an investigator or a notified-body auditor would find in your records today, read from them (rules
 * only), the four home numbers first; every check opens the records behind it and shows its regulatory basis under
 * why it matters, with the disclaimer once at the foot. The summary for management review downloads as a PDF. Right
 * after an import the trend check says that its signals are being found, and the checks are read again once they are.
 */
export function ReadinessSection({ tab }: { tab?: string }) {
  // Readiness holds the inspection checks and, beside them, the oversight view (T-G9): one place for the head of QA.
  const [target] = useState(() => parseReadinessTab(tab));
  const [active, setActive] = useReportedTab<ReadinessTab>(target.tab);
  return (
    <Tabs tabs={READINESS_TABS} active={active} onChange={setActive} label="Readiness sections">
      {active === "Inspection checks" ? <InspectionChecks /> : <OversightView initialEvent={target.event} />}
    </Tabs>
  );
}

function InspectionChecks() {
  const { open } = useWorkspace();
  const data = useResource<Readiness>(READINESS_PATH, WHILE_FINDING_SIGNALS);
  const finding = !!data.data?.detection_pending;
  const headline = readinessHeadline(data.data);
  const go = (check: ReadinessCheck) => {
    if (!check.opens) return;
    const place = placeOf(check.opens);
    open(place.section as WorkspaceSection, place.tab);
  };
  const others = (data.data?.checks ?? []).filter(
    (check) => !(data.data?.home ?? []).some((home) => home.code === check.code),
  );
  return (
    <div className="ac-overview">
      <QualityLoop
        stations={loopFromReadiness(data.data)}
        eyebrow={`Inspection readiness${data.data ? ` · ${data.data.as_of}` : ""}`}
        title={headline.title}
        detail={headline.detail}
        doneLabel="clear"
        onOpen={(station) => {
          if (!station.opens) return;
          const place = placeOf(station.opens);
          open(place.section as WorkspaceSection, place.tab);
        }}
      >
        <SummaryDownload />
        <button
          type="button"
          className="ac-secondary uw-rd-document"
          onClick={() => open("Records", documentLink("MANAGEMENT_REVIEW"))}
        >
          <FileCheck2 size={15} aria-hidden="true" /> Management review report
        </button>
      </QualityLoop>
      <div className="uw-rd-home" aria-label="The four numbers">
        {(data.data?.home ?? []).map((check) => (
          <HomeTile
            key={check.code}
            check={check}
            onOpen={() => go(check)}
            finding={finding && check.code === TRENDS_CHECK}
          />
        ))}
      </div>
      <Panel eyebrow="Readiness" title="Further inspection checks" source={data}>
        <ul className="uw-rd-checks">
          {others.map((check) => (
            <CheckRow key={check.code} check={check} onOpen={() => go(check)} />
          ))}
        </ul>
        {data.data && <p className="ac-note">{data.data.note}</p>}
        {data.data && <BasisNote />}
      </Panel>
    </div>
  );
}

/** One of the four home numbers (exported for its unit test); `finding` while the signals it reads are being found. */
export function HomeTile({
  check,
  onOpen,
  finding = false,
}: {
  check: ReadinessCheck;
  onOpen: () => void;
  finding?: boolean;
}) {
  const state = finding ? { label: "Finding signals", tone: "neutral" as const } : checkStateOf(check.state);
  const Icon = HOME_ICONS[check.code] ?? ShieldCheck;
  const refs = finding ? null : itemsText(check);
  return (
    <button type="button" className={`uw-rd-tile tone-${state.tone}`} onClick={onOpen} disabled={!check.opens}>
      <span className="uw-rd-tile-head">
        <Icon size={18} aria-hidden="true" />
        <span>{check.title}</span>
      </span>
      <strong className="uw-rd-value">{finding ? "…" : checkValue(check)}</strong>
      <ToneBadge tone={state.tone} label={state.label} />
      {finding ? (
        <span className="uw-rd-detail" role="status">
          {FINDING_SIGNALS_NOW}
        </span>
      ) : (
        <span className="uw-rd-detail">{check.detail}</span>
      )}
      {refs && <span className="uw-rd-refs">{refs}</span>}
      <span className="uw-rd-why">{check.why}</span>
      <BasisChips ids={basisIds(check)} />
      {check.opens && (
        <span className="uw-rd-open">
          Open <ChevronRight size={14} aria-hidden="true" />
        </span>
      )}
    </button>
  );
}

/** A further inspection check (exported for its unit test). */
export function CheckRow({ check, onOpen }: { check: ReadinessCheck; onOpen: () => void }) {
  const state = checkStateOf(check.state);
  const refs = itemsText(check);
  return (
    <li className={`uw-cr-card`}>
      <span className={`uw-cr-rail tone-${state.tone}`} aria-hidden="true" />
      <div className="uw-cr-body">
        <div className="uw-cr-head">
          <ToneIcon tone={state.tone} />
          <strong className="uw-cr-id">{check.title}</strong>
          <ToneBadge tone={state.tone} label={`${checkValue(check)} · ${state.label}`} />
        </div>
        <p className="uw-cr-text">{check.detail}</p>
        {refs && <p className="uw-cr-meta">{refs}</p>}
        <p className="uw-cr-meta">Why it matters: {check.why}</p>
        <BasisChips ids={basisIds(check)} />
      </div>
      <div className="uw-cr-actions">
        {check.opens && (
          <button type="button" className="ac-secondary" onClick={onOpen}>
            Open <ChevronRight size={14} aria-hidden="true" />
          </button>
        )}
      </div>
    </li>
  );
}

function SummaryDownload() {
  const canExport = useCan("data.export");
  const [days, setDays] = useState<number>(365);
  const [busy, setBusy] = useState<"pdf" | "pack" | null>(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  if (!canExport) return null;
  const download = async (kind: "pdf" | "pack") => {
    setBusy(kind);
    setError("");
    setDone("");
    try {
      const name =
        kind === "pdf"
          ? await downloadFile(summaryPdfPath(days), { fallbackName: "mdarix-readiness-summary.pdf" })
          : await downloadFile(inspectionPackPath(days), { fallbackName: "mdarix-inspection-pack.zip" });
      setDone(`Downloaded ${name}.`);
    } catch (failure) {
      setError(
        describeError(
          failure,
          kind === "pdf"
            ? "The readiness summary could not be downloaded."
            : "The inspection pack could not be downloaded.",
        ),
      );
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="ac-hero-actions uw-rd-download">
      <label className="ca-field">
        Summary for management review
        <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
          {SUMMARY_PERIODS.map((period) => (
            <option key={period.days} value={period.days}>
              {period.label}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="ac-primary" disabled={busy !== null} onClick={() => void download("pdf")}>
        <Download size={15} aria-hidden="true" /> {busy === "pdf" ? "Preparing…" : "Download PDF"}
      </button>
      <button
        type="button"
        className="ac-secondary"
        disabled={busy !== null}
        onClick={() => void download("pack")}
        title="The summary PDF, every check and every record behind it as CSV, with SHA-256 fingerprints"
      >
        <Archive size={15} aria-hidden="true" /> {busy === "pack" ? "Preparing…" : "Inspection pack (ZIP)"}
      </button>
      {done && <small className="ac-muted">{done}</small>}
      <InlineError text={error} />
    </div>
  );
}
