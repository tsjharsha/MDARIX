import { useMemo } from "react";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  FileSearch,
  FileText,
  Gavel,
  Layers,
  Package,
  Sparkles,
} from "lucide-react";
import { BarList, Empty, Panel, RingMeter, ToneBadge, ToneIcon } from "../../admin/console/charts";
import { titleCase, worstTone, type Slice, type Tone } from "../../admin/console/dashboardModel";
import { KpiTile, TrendChart, toPoints, type DailyRow } from "../../admin/console/trendCharts";
import { formatDate, listOf, useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { isHighSeverity, isOpenInvestigation, isVerified, workspaceAttention } from "../workspaceModel";
import { StatusBadge } from "./common";

type Breakdown = Array<{ label: string; count: number }>;
type Trends = {
  days: number;
  signals: DailyRow[];
  investigations_opened: DailyRow[];
  investigations_closed: DailyRow[];
  evidence: DailyRow[];
  decisions: DailyRow[];
  ai_runs: DailyRow[];
  signals_by_status: Breakdown;
  investigations_by_status: Breakdown;
  evidence_by_reliability: Breakdown;
  evidence_by_type: Breakdown;
  decisions_by_status: Breakdown;
};

const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);
const slices = (rows: Breakdown | undefined): Slice[] =>
  (rows ?? []).map((row) => ({ key: row.label, label: titleCase(row.label), count: row.count, tone: "neutral" }));

/** The quality work of the organization at a glance: what came in, what is open, what was decided, and what needs
 * attention. Every figure is read from the signed-in user's own tenant. */
export function DashboardSection() {
  const { session, work, open } = useWorkspace();
  const counts = useResource<any>("/api/v1/analytics/command-center");
  const signals = useResource<any>("/api/v1/analytics/signals");
  const investigations = useResource<any>("/api/v1/analytics/investigations");
  const evidence = useResource<any>("/api/v1/analytics/evidence");
  const trends = useResource<Trends>("/api/v1/analytics/trends?days=30");

  const model = useMemo(() => {
    const signalRows = listOf(signals.data?.signals);
    const caseRows = listOf(investigations.data?.investigations);
    const evidenceRows = listOf(evidence.data?.evidence);
    const openCases = caseRows.filter((row) => isOpenInvestigation(row.status));
    const verified = evidenceRows.filter((row) => isVerified(row.reliability_status)).length;
    const data = trends.data;
    const ai = toPoints(data?.ai_runs, "completed", "failed", true);
    return {
      signalRows,
      caseRows,
      openCases,
      evidenceRows,
      verified,
      signals: toPoints(data?.signals, "count"),
      opened: toPoints(data?.investigations_opened, "count"),
      closed: toPoints(data?.investigations_closed, "count"),
      evidence: toPoints(data?.evidence, "count"),
      decisions: toPoints(data?.decisions, "count"),
      ai,
      aiTotal: sum(ai.map((point) => point.primary)),
      aiFailed: sum(ai.map((point) => point.secondary ?? 0)),
      caseStatus: slices(data?.investigations_by_status),
      reliability: slices(data?.evidence_by_reliability),
      decisionStatus: slices(data?.decisions_by_status),
      signalStatus: slices(data?.signals_by_status),
      attention: workspaceAttention({
        openInvestigations: openCases.length,
        unreliableEvidence: evidenceRows.length - verified,
        limitations: work.view?.limitations ?? [],
        highSeveritySignals: signalRows.filter((row) => isHighSeverity(row.severity)).length,
      }),
    };
  }, [signals.data, investigations.data, evidence.data, trends.data, work.view]);

  const loading = [counts, signals, investigations, evidence].some((resource) => resource.state === "loading");
  const tone: Tone = loading ? "neutral" : worstTone(model.attention.map((item) => item.tone));
  const c = counts.data?.counts ?? {};
  const countsReady = counts.state === "ready";
  const trendsReady = trends.state === "ready";
  const days = trends.data?.days ?? 30;
  const total = (points: { primary: number }[]) => sum(points.map((point) => point.primary));
  const firstName = (session?.display_name ?? "").trim().split(/\s+/)[0] || "there";

  return (
    <div className="ac-overview ac-dashboard">
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
          <RingMeter
            value={model.aiTotal - model.aiFailed}
            total={model.aiTotal}
            label={`AI runs completed · ${days} days`}
          />
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

      <section className="ac-kpis" aria-label="Key figures">
        <KpiTile
          label="Products"
          value={countsReady ? (c.products ?? 0) : null}
          detail={`${c.product_versions ?? 0} versions`}
          icon={<Package size={18} />}
          onOpen={() => open("Products")}
        />
        <KpiTile
          label="Versions"
          value={countsReady ? (c.product_versions ?? 0) : null}
          detail="Released and in development"
          icon={<Layers size={18} />}
          onOpen={() => open("Products", "Version story")}
        />
        <KpiTile
          label="Signals"
          value={countsReady ? (c.complaints ?? 0) : null}
          detail={`${total(model.signals)} in the last ${days} days`}
          icon={<AlertTriangle size={18} />}
          series={model.signals.map((point) => point.primary)}
          seriesLabel={`Signals per day, last ${days} days`}
          goodWhenUp={false}
          onOpen={() => open("Signals", "All signals")}
        />
        <KpiTile
          label="Investigations"
          value={countsReady ? (c.investigations ?? 0) : null}
          detail={`${model.openCases.length} open · ${total(model.opened)} opened in ${days} days`}
          icon={<FileSearch size={18} />}
          series={model.opened.map((point) => point.primary)}
          seriesLabel={`Investigations opened per day, last ${days} days`}
          goodWhenUp={null}
          onOpen={() => open("Investigations")}
        />
        <KpiTile
          label="Closed"
          value={trendsReady ? total(model.closed) : null}
          detail={`Investigations closed · last ${days} days`}
          icon={<CheckCircle2 size={18} />}
          series={model.closed.map((point) => point.primary)}
          seriesLabel={`Investigations closed per day, last ${days} days`}
          onOpen={() => open("Investigations")}
        />
        <KpiTile
          label="Evidence"
          value={countsReady ? (c.evidence ?? 0) : null}
          detail={`${model.verified} verified · ${total(model.evidence)} added in ${days} days`}
          icon={<FileText size={18} />}
          series={model.evidence.map((point) => point.primary)}
          seriesLabel={`Evidence added per day, last ${days} days`}
          onOpen={() => open("Evidence")}
        />
        <KpiTile
          label="Decisions"
          value={countsReady ? (c.decisions ?? 0) : null}
          detail={`${total(model.decisions)} in the last ${days} days`}
          icon={<Gavel size={18} />}
          series={model.decisions.map((point) => point.primary)}
          seriesLabel={`Decisions per day, last ${days} days`}
          onOpen={() => open("Decisions")}
        />
        <KpiTile
          label="AI runs"
          value={trendsReady ? model.aiTotal : null}
          detail={`${model.aiFailed} failed · last ${days} days`}
          tone={trendsReady && model.aiTotal ? (model.aiFailed ? "warning" : "good") : undefined}
          icon={<Sparkles size={18} />}
          series={model.ai.map((point) => point.primary)}
          seriesLabel={`AI runs per day, last ${days} days`}
          onOpen={() => open("Trust & Audit")}
        />
      </section>

      <section className="ac-grid three" aria-label={`Activity, last ${days} days`}>
        <Panel
          eyebrow={`Last ${days} days`}
          title="Signals"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Signals", "Trends")} />}
        >
          <TrendChart data={model.signals} primaryLabel="signals" unit="signals" />
        </Panel>
        <Panel
          eyebrow={`Last ${days} days`}
          title="Investigations opened"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Investigations")} />}
        >
          <TrendChart data={model.opened} primaryLabel="opened" unit="investigations opened" />
        </Panel>
        <Panel
          eyebrow={`Last ${days} days`}
          title="Evidence added"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Evidence")} />}
        >
          <TrendChart data={model.evidence} primaryLabel="records" unit="evidence records" />
        </Panel>
      </section>

      <section className="ac-grid three" aria-label="Where the work stands">
        <Panel eyebrow="Investigations" title="By status" state={trends.state} error={trends.error}>
          {model.caseStatus.length ? (
            <BarList items={model.caseStatus} colour="series" />
          ) : (
            <Empty title="No investigations yet" detail="Investigations opened in your organization appear here." />
          )}
        </Panel>
        <Panel
          eyebrow="Evidence"
          title="Evidence by reliability"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Evidence")} />}
        >
          {model.reliability.length ? (
            <BarList items={model.reliability} colour="series" />
          ) : (
            <Empty title="No evidence yet" detail="Evidence appears once source records are ingested." />
          )}
        </Panel>
        <Panel
          eyebrow="Decisions"
          title="Decisions by status"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Decisions")} />}
        >
          {model.decisionStatus.length ? (
            <BarList items={model.decisionStatus} colour="series" />
          ) : (
            <Empty title="No decisions yet" detail="Decisions recorded by authorized people appear here." />
          )}
        </Panel>
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
      </div>

      <div className="ac-grid two">
        <Panel
          eyebrow="Signals"
          title="Latest signals"
          state={signals.state}
          error={signals.error}
          action={<OpenLink onClick={() => open("Signals", "All signals")} />}
        >
          {model.signalRows.length ? (
            <ol className="ac-timeline">
              {model.signalRows.slice(0, 6).map((row, index) => (
                <li key={String(row.signal_id ?? index)}>
                  <span className="ac-timeline-dot" aria-hidden="true" />
                  <span className="ac-timeline-text">
                    <strong>{row.signal_id}</strong>
                    <small>{row.description ?? "No description"}</small>
                  </span>
                  <time className="ac-muted">{formatDate(row.event_timestamp)}</time>
                </li>
              ))}
            </ol>
          ) : (
            <Empty title="No signals recorded" detail="Complaints and other signals appear here as they arrive." />
          )}
        </Panel>
        <Panel
          eyebrow="Signals"
          title="Signals by status"
          state={trends.state}
          error={trends.error}
          action={<OpenLink onClick={() => open("Signals", "Trends")} />}
        >
          {model.signalStatus.length ? (
            <BarList items={model.signalStatus} colour="series" />
          ) : (
            <Empty title="No signals recorded" detail="Signal statuses appear as complaints arrive." />
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
