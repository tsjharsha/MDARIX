import { useMemo } from "react";
import { AlertTriangle, Bot, ChevronRight, FileSearch, FileText, Gavel, Layers, Package } from "lucide-react";
import {
  BarList,
  ColumnChart,
  Empty,
  Panel,
  RingMeter,
  StatTile,
  ToneBadge,
  ToneIcon,
} from "../../admin/console/charts";
import { dailyCounts, worstTone, type Tone } from "../../admin/console/dashboardModel";
import { formatDate, listOf, useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import {
  countBy,
  investigationStatusSlices,
  isHighSeverity,
  isOpenInvestigation,
  isVerified,
  workspaceAttention,
} from "../workspaceModel";
import { StatusBadge } from "./common";

const TREND_DAYS = 30;

export function OverviewSection() {
  const { session, work, open } = useWorkspace();
  const counts = useResource<any>("/api/v1/analytics/command-center");
  const signals = useResource<any>("/api/v1/analytics/signals");
  const investigations = useResource<any>("/api/v1/analytics/investigations");
  const evidence = useResource<any>("/api/v1/analytics/evidence");

  const model = useMemo(() => {
    const signalRows = listOf(signals.data?.signals);
    const caseRows = listOf(investigations.data?.investigations);
    const evidenceRows = listOf(evidence.data?.evidence);
    const openCases = caseRows.filter((row) => isOpenInvestigation(row.status));
    const verified = evidenceRows.filter((row) => isVerified(row.reliability_status)).length;
    const highSignals = signalRows.filter((row) => isHighSeverity(row.severity)).length;
    return {
      signalRows,
      caseRows,
      openCases,
      evidenceRows,
      verified,
      trend: dailyCounts(
        signalRows.map((row) => row.event_timestamp),
        TREND_DAYS,
      ),
      caseStatus: investigationStatusSlices(caseRows),
      reliability: countBy(evidenceRows, "reliability_status"),
      attention: workspaceAttention({
        openInvestigations: openCases.length,
        unreliableEvidence: evidenceRows.length - verified,
        limitations: work.view?.limitations ?? [],
        highSeveritySignals: highSignals,
      }),
    };
  }, [signals.data, investigations.data, evidence.data, work.view]);

  const loading = [counts, signals, investigations, evidence].some((resource) => resource.state === "loading");
  const tone: Tone = loading ? "neutral" : worstTone(model.attention.map((item) => item.tone));
  const c = counts.data?.counts ?? {};
  const firstName = (session?.display_name ?? "").trim().split(/\s+/)[0] || "there";

  return (
    <div className="ac-overview">
      <section className={`ac-hero tone-${tone}`} aria-live="polite">
        <div className="ac-hero-status">
          <span className="ac-hero-icon">
            <ToneIcon tone={tone} size={34} />
          </span>
          <div>
            <p className="ac-eyebrow">Hello {firstName}</p>
            <h2>
              {loading
                ? "Checking your workspace…"
                : model.attention.length
                  ? `${model.attention.length} ${model.attention.length === 1 ? "thing needs" : "things need"} your attention`
                  : "Nothing needs your attention"}
            </h2>
            <p>
              {work.view?.product.name ? `Working on ${work.view.product.name}` : "No product selected"}
              {work.view?.selected_version?.version_identifier
                ? ` · version ${work.view.selected_version.version_identifier}`
                : ""}
            </p>
          </div>
        </div>
        <div className="ac-hero-meters">
          <RingMeter value={model.openCases.length} total={model.caseRows.length} label="Investigations open" />
          <RingMeter value={model.verified} total={model.evidenceRows.length} label="Evidence verified" />
        </div>
        <div className="ac-hero-actions">
          <button type="button" className="ac-primary" onClick={() => open("Investigations")}>
            <FileSearch size={16} /> Investigations
          </button>
          <button type="button" className="ac-secondary" onClick={() => open("Intelligence", "Ask MDARIX")}>
            <Bot size={16} /> Ask MDARIX
          </button>
        </div>
      </section>

      <section className="ac-stats" aria-label="Key figures">
        <StatTile
          label="Products"
          value={counts.state === "ready" ? (c.products ?? 0) : null}
          detail={`${c.product_versions ?? 0} versions`}
          icon={<Package size={18} />}
          onOpen={() => open("Products")}
        />
        <StatTile
          label="Versions"
          value={counts.state === "ready" ? (c.product_versions ?? 0) : null}
          detail="Released and in development"
          icon={<Layers size={18} />}
          onOpen={() => open("Products", "Version story")}
        />
        <StatTile
          label="Signals"
          value={counts.state === "ready" ? (c.complaints ?? 0) : null}
          detail="Recorded complaints"
          icon={<AlertTriangle size={18} />}
          onOpen={() => open("Signals", "All signals")}
        />
        <StatTile
          label="Investigations"
          value={counts.state === "ready" ? (c.investigations ?? 0) : null}
          detail={`${model.openCases.length} open`}
          icon={<FileSearch size={18} />}
          onOpen={() => open("Investigations")}
        />
        <StatTile
          label="Evidence"
          value={counts.state === "ready" ? (c.evidence ?? 0) : null}
          detail={`${model.verified} verified`}
          icon={<FileText size={18} />}
          onOpen={() => open("Evidence")}
        />
        <StatTile
          label="Decisions"
          value={counts.state === "ready" ? (c.decisions ?? 0) : null}
          detail="Recorded by authorized people"
          icon={<Gavel size={18} />}
          onOpen={() => open("Decisions")}
        />
      </section>

      <div className="ac-grid two">
        <Panel
          eyebrow="Needs attention"
          title="What to do next"
          state={loading ? "loading" : "ready"}
          action={
            model.attention.length ? (
              <ToneBadge tone={tone} label={`${model.attention.length} open`} />
            ) : (
              <ToneBadge tone="good" />
            )
          }
        >
          {model.attention.length ? (
            <ul className="ac-attention">
              {model.attention.map((item) => (
                <li key={item.key}>
                  <ToneIcon tone={item.tone} size={18} />
                  <span>
                    <strong>{item.title}</strong>
                    <small>{item.detail}</small>
                  </span>
                  <button
                    type="button"
                    className="ac-link ca-push"
                    onClick={() => open(item.section as WorkspaceSection, item.tab)}
                  >
                    {item.section} <ChevronRight size={14} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="You're all caught up" detail="New signals, open cases and evidence gaps will appear here." />
          )}
        </Panel>
        <Panel eyebrow="Investigations" title="By status" state={investigations.state} error={investigations.error}>
          {model.caseRows.length ? (
            <BarList items={model.caseStatus} />
          ) : (
            <Empty title="No investigations yet" detail="Investigations opened in your organization appear here." />
          )}
        </Panel>
      </div>

      <div className="ac-grid two">
        <Panel
          eyebrow="Signals"
          title={`Signals by event date · last ${TREND_DAYS} days`}
          state={signals.state}
          error={signals.error}
          action={<OpenLink onClick={() => open("Signals", "Trends")} />}
        >
          <ColumnChart data={model.trend} unit="signals" caption="latest 100 recorded signals" />
        </Panel>
        <Panel
          eyebrow="Evidence"
          title="Evidence by reliability"
          state={evidence.state}
          error={evidence.error}
          action={<OpenLink onClick={() => open("Evidence")} />}
        >
          {model.evidenceRows.length ? (
            <BarList items={model.reliability} colour="series" />
          ) : (
            <Empty title="No evidence yet" detail="Evidence appears once source records are ingested." />
          )}
        </Panel>
      </div>

      <div className="ac-grid two">
        <Panel
          eyebrow="Investigations"
          title="Open cases"
          state={investigations.state}
          error={investigations.error}
          action={<OpenLink onClick={() => open("Investigations")} />}
        >
          {model.openCases.length ? (
            <ul className="uw-list">
              {model.openCases.slice(0, 6).map((row) => (
                <li key={String(row.id)}>
                  <span>
                    <strong>{row.investigation_identifier}</strong>
                    <small>{row.investigation_question ?? "No question recorded"}</small>
                  </span>
                  <StatusBadge value={row.status} />
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No open investigations" detail="Open cases in your organization appear here." />
          )}
        </Panel>
        <Panel
          eyebrow="Signals"
          title="Latest signals"
          state={signals.state}
          error={signals.error}
          action={<OpenLink onClick={() => open("Signals", "All signals")} />}
        >
          {model.signalRows.length ? (
            <ul className="uw-list">
              {model.signalRows.slice(0, 6).map((row, index) => (
                <li key={String(row.signal_id ?? index)}>
                  <span>
                    <strong>{row.signal_id}</strong>
                    <small>
                      {formatDate(row.event_timestamp)} · {row.description ?? "No description"}
                    </small>
                  </span>
                  <StatusBadge value={row.severity ?? row.status} />
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No signals recorded" detail="Complaints and other signals appear here as they arrive." />
          )}
        </Panel>
      </div>
    </div>
  );
}

function OpenLink({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" className="ac-link" onClick={onClick}>
      Open <ChevronRight size={14} aria-hidden="true" />
    </button>
  );
}
