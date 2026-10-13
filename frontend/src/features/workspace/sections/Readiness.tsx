import { useState } from "react";
import { AlarmClock, ChevronRight, Download, Hourglass, ScanSearch, ShieldCheck, TrendingUp } from "lucide-react";
import { Panel, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { describeError } from "../../../app/apiClient";
import { downloadFile } from "../../reports/download";
import { useCan, useWorkspace, type WorkspaceSection } from "../workspaceContext";
import {
  READINESS_PATH,
  SUMMARY_PERIODS,
  checkStateOf,
  checkValue,
  itemsText,
  readinessHeadline,
  summaryPdfPath,
  type Readiness,
  type ReadinessCheck,
} from "../readiness";
import { Hero, InlineError } from "./boardParts";

const HOME_ICONS: Record<string, typeof ScanSearch> = {
  COMPLAINTS_TO_RECHECK: ScanSearch,
  COMPLAINTS_PAST_TARGET: Hourglass,
  REPORTING_CLOCKS: AlarmClock,
  TRENDS_WITHOUT_ACTION: TrendingUp,
};

/**
 * Readiness: what an investigator or a notified-body auditor would find in your records today, read from them (rules
 * only), the four home numbers first; every check opens the records behind it. The summary for management review
 * downloads as a PDF.
 */
export function ReadinessSection() {
  const { open } = useWorkspace();
  const data = useResource<Readiness>(READINESS_PATH);
  const headline = readinessHeadline(data.data);
  const go = (check: ReadinessCheck) => {
    if (check.opens) open(check.opens.section as WorkspaceSection, check.opens.tab);
  };
  const others = (data.data?.checks ?? []).filter(
    (check) => !(data.data?.home ?? []).some((home) => home.code === check.code),
  );
  return (
    <div className="ac-overview">
      <Hero
        tone={data.data ? headline.tone : "neutral"}
        icon={<ShieldCheck size={28} />}
        eyebrow={`Inspection readiness${data.data ? ` · ${data.data.as_of}` : ""}`}
        title={headline.title}
        detail={headline.detail}
      >
        <SummaryDownload />
      </Hero>
      <div className="uw-rd-home" aria-label="The four numbers">
        {(data.data?.home ?? []).map((check) => (
          <HomeTile key={check.code} check={check} onOpen={() => go(check)} />
        ))}
      </div>
      <Panel eyebrow="Readiness" title="Further inspection checks" source={data}>
        <ul className="uw-rd-checks">
          {others.map((check) => (
            <CheckRow key={check.code} check={check} onOpen={() => go(check)} />
          ))}
        </ul>
        {data.data && <p className="ac-note">{data.data.note}</p>}
      </Panel>
    </div>
  );
}

/** One of the four home numbers (exported for its unit test). */
export function HomeTile({ check, onOpen }: { check: ReadinessCheck; onOpen: () => void }) {
  const state = checkStateOf(check.state);
  const Icon = HOME_ICONS[check.code] ?? ShieldCheck;
  const refs = itemsText(check);
  return (
    <button type="button" className={`uw-rd-tile tone-${state.tone}`} onClick={onOpen} disabled={!check.opens}>
      <span className="uw-rd-tile-head">
        <Icon size={18} aria-hidden="true" />
        <span>{check.title}</span>
      </span>
      <strong className="uw-rd-value">{checkValue(check)}</strong>
      <ToneBadge tone={state.tone} label={state.label} />
      <span className="uw-rd-detail">{check.detail}</span>
      {refs && <span className="uw-rd-refs">{refs}</span>}
      <span className="uw-rd-why">{check.why}</span>
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");
  if (!canExport) return null;
  const download = async () => {
    setBusy(true);
    setError("");
    setDone("");
    try {
      const name = await downloadFile(summaryPdfPath(days), { fallbackName: "mdarix-readiness-summary.pdf" });
      setDone(`Downloaded ${name}.`);
    } catch (failure) {
      setError(describeError(failure, "The readiness summary could not be downloaded."));
    } finally {
      setBusy(false);
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
      <button type="button" className="ac-primary" disabled={busy} onClick={() => void download()}>
        <Download size={15} aria-hidden="true" /> {busy ? "Preparing…" : "Download PDF"}
      </button>
      {done && <small className="ac-muted">{done}</small>}
      <InlineError text={error} />
    </div>
  );
}
