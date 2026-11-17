/** E1: AI governance on one screen. Read only: what AI may use, what it produced, and what people decided about it.
 * Flat (G-2). The switches are changed on the AI settings screen, never here. */
import "./aiGovernance.css";
import { Bot, Handshake, ShieldCheck, Sparkles } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { RecordedChip } from "../../shared/AiReview";
import { Table, formatDate, useResource } from "../shared";
import {
  AI_GOVERNANCE_PATH,
  NOT_RECORDED,
  PLATFORM_AI_GOVERNANCE_PATH,
  agreementShare,
  disagreementWord,
  type AiGovernance as Governance,
  type PlatformAiGovernance,
  type Providers,
} from "../aiGovernance";
import { reviewText } from "../../workspace/decisionSummary";

const or = (value: string | null | undefined) => (value && value.trim() ? value : NOT_RECORDED);

function Statement({ text }: { text: string }) {
  return (
    <p className="ai-gov-statement" role="note">
      <ShieldCheck size={18} aria-hidden="true" /> <strong>{text}</strong>
    </p>
  );
}

function ProviderPanels({ providers }: { providers: Providers }) {
  return (
    <div className="ac-grid two">
      <Panel eyebrow="From the provider register" title={`Approved providers · ${providers.approved.length}`}>
        <Table
          caption="Approved AI providers"
          rows={providers.approved}
          rowKey={(row) => row.name}
          empty={{ title: "No approved provider", detail: "AI stays off until a provider is approved." }}
          columns={[
            {
              key: "name",
              label: "Provider",
              render: (row) => (
                <>
                  <strong>{row.name}</strong>
                  <small className="ac-muted"> · {row.kind}</small>
                </>
              ),
            },
            { key: "trains", label: "Trains on data", render: (row) => row.trains_on_data },
            { key: "region", label: "Region", render: (row) => or(row.region) },
            {
              key: "terms",
              label: "Terms checked",
              render: (row) =>
                row.terms?.startsWith("https://") ? (
                  <a href={row.terms} target="_blank" rel="noreferrer">
                    {or(row.checked_on)}
                  </a>
                ) : (
                  or(row.checked_on)
                ),
            },
            { key: "why", label: "Why approved", render: (row) => row.warning ?? row.why },
          ]}
        />
      </Panel>
      <Panel eyebrow="Never sent your data" title="Not used">
        <ul className="ai-gov-list">
          {providers.not_used.map((item) => (
            <li key={item.name}>
              <strong>{item.name}</strong> <span className="ac-muted">{item.why}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

/** The organization's view: for its administrator, or the person who started a free trial. */
export function AiGovernance({ change }: { change?: { label: string; onOpen: () => void } }) {
  const source = useResource<Governance>(AI_GOVERNANCE_PATH);
  const data = source.data;
  if (!data)
    return (
      <Panel title="AI governance" source={source}>
        {null}
      </Panel>
    );
  const { controls, outputs, agreement } = data;
  const share = agreementShare(agreement.live);
  const recordedShare = agreementShare(agreement.recorded);
  return (
    <div className="ai-gov">
      <Statement text={data.statement} />
      <section className="ac-stats four" aria-label="AI governance figures">
        <StatTile
          label="AI for the organization"
          value={controls.organization_on ? "On" : "Off"}
          detail={controls.organization_on ? "Proposals only; a person decides" : "Every step works by hand"}
          tone={controls.organization_on ? "good" : "neutral"}
          icon={<Bot size={18} />}
        />
        <StatTile
          label="Live AI outputs"
          value={outputs.live}
          detail={`${data.calls.total} model ${data.calls.total === 1 ? "call" : "calls"} recorded`}
          icon={<Sparkles size={18} />}
        />
        <StatTile
          label="Recorded sample answers"
          value={outputs.recorded}
          detail={data.recorded_label}
          icon={<Sparkles size={18} />}
        />
        <StatTile
          label="Accepted as proposed (live)"
          value={share === null ? NOT_RECORDED : `${share}%`}
          detail={`${agreement.live.EDITED} edited, ${agreement.live.REJECTED} rejected · sample: ${
            recordedShare === null ? "none reviewed" : `${recordedShare}% accepted`
          }`}
          icon={<Handshake size={18} />}
        />
      </section>
      <ProviderPanels providers={data.providers} />
      <div className="ac-grid two">
        <Panel
          eyebrow="Read only"
          title="AI on and off"
          action={
            change ? (
              <button type="button" className="ac-link" onClick={change.onOpen}>
                {change.label}
              </button>
            ) : undefined
          }
        >
          <ul className="ai-gov-list">
            <li>
              <strong>Organization:</strong> {controls.organization_on ? "On" : "Off"}
              {controls.free_trial && (
                <span className="ac-muted">
                  {" "}
                  · free trial: sample data only
                  {controls.trial_chain_on ? "" : "; the trial AI services are not set up yet"}
                </span>
              )}
            </li>
            {controls.features.map((feature) => (
              <li key={feature.key}>
                <strong>{feature.label}:</strong> {feature.enabled ? "On" : "Off"}
              </li>
            ))}
          </ul>
          {controls.people ? (
            <>
              <strong>Each person</strong>
              <ul className="ai-gov-list" aria-label="AI for each person">
                {controls.people.map((person, index) => (
                  <li key={`${person.name}-${index}`}>
                    {or(person.name)}: {person.ai}
                  </li>
                ))}
              </ul>
              <p className="ac-muted">A person's AI is set by MDARIX support at your request.</p>
            </>
          ) : (
            <p className="ac-muted">The per-person AI switch applies to free trials only.</p>
          )}
        </Panel>
        <Panel eyebrow="Every edit and rejection, with its reason" title="Reviewer disagreements">
          {agreement.disagreements.length ? (
            <ul className="ai-gov-list" aria-label="Reviewer disagreements">
              {agreement.disagreements.map((item, index) => (
                <li key={`${item.at}-${index}`}>
                  <ToneBadge
                    tone={item.decision === "REJECTED" ? "serious" : "warning"}
                    label={disagreementWord(item.decision)}
                  />{" "}
                  {item.ref ? <strong>{item.ref} </strong> : null}
                  {or(item.reason)}
                  <small className="ac-muted">
                    {" "}
                    · {or(item.reviewer)} · {formatDate(item.at)}
                  </small>{" "}
                  <RecordedChip recorded={item.recorded} />
                </li>
              ))}
            </ul>
          ) : (
            <Empty title="No disagreements yet" detail="Each edit or rejection of an AI proposal is listed here." />
          )}
          <p className="ac-muted">
            Disagreements are counted and kept with their reasons. MDARIX does not train any model on them.
          </p>
        </Panel>
      </div>
      <Panel eyebrow="Saved AI results, newest first" title="AI outputs">
        <Table
          caption="AI outputs"
          rows={outputs.items}
          rowKey={(row) => row.id}
          pageSize={10}
          pageNoun="output"
          empty={{ title: "No AI outputs yet", detail: "Outputs appear when AI proposes something on a case." }}
          columns={[
            {
              key: "what",
              label: "What",
              render: (row) => (
                <>
                  <strong>{or(row.ref)}</strong> {row.what} <RecordedChip recorded={row.recorded} />
                </>
              ),
            },
            { key: "at", label: "When", render: (row) => formatDate(row.at) },
            { key: "model", label: "Provider · model", render: (row) => `${or(row.provider)} · ${or(row.model)}` },
            { key: "prompt", label: "Prompt version", render: (row) => or(row.prompt_version) },
            { key: "sources", label: "Sources", numeric: true, render: (row) => row.sources },
            { key: "review", label: "Review", render: (row) => reviewText(row.reviews) },
          ]}
        />
      </Panel>
      {data.calls.total > 0 && (
        <Panel eyebrow="Every request sent to a model" title="Model calls">
          <Table
            caption="Model calls"
            rows={data.calls.items}
            rowKey={(row) => row.id}
            pageSize={10}
            pageNoun="call"
            empty={{ title: "No model calls yet", detail: "Calls appear when a feature asks a model." }}
            columns={[
              { key: "feature", label: "Feature", render: (row) => row.feature },
              { key: "at", label: "When", render: (row) => formatDate(row.at) },
              { key: "model", label: "Provider · model", render: (row) => `${or(row.provider)} · ${or(row.model)}` },
              { key: "prompt", label: "Prompt version", render: (row) => or(row.prompt_version) },
              { key: "sources", label: "Records sent", numeric: true, render: (row) => row.sources },
              { key: "outcome", label: "Outcome", render: (row) => row.outcome.toLowerCase() },
              { key: "review", label: "Review", render: (row) => reviewText({ [row.review]: 1 }) },
            ]}
          />
        </Panel>
      )}
    </div>
  );
}

/** The platform view: the register and every organization's AI counts. No record content. */
export function PlatformAiGovernanceView() {
  const source = useResource<PlatformAiGovernance>(PLATFORM_AI_GOVERNANCE_PATH);
  const data = source.data;
  if (!data)
    return (
      <Panel title="AI governance" source={source}>
        {null}
      </Panel>
    );
  return (
    <div className="ai-gov">
      <Statement text={data.statement} />
      <ProviderPanels providers={data.providers} />
      <Panel eyebrow="All organizations · counts only" title="AI outputs and reviews">
        <Table
          caption="AI governance by organization"
          rows={data.organizations}
          rowKey={(row) => row.tenant_id}
          pageSize={15}
          pageNoun="organization"
          empty={{ title: "No AI outputs yet", detail: "Organizations appear once AI proposes something." }}
          columns={[
            { key: "organization", label: "Organization", render: (row) => or(row.organization) },
            {
              key: "on",
              label: "AI",
              render: (row) => (row.organization_on === null ? NOT_RECORDED : row.organization_on ? "On" : "Off"),
            },
            { key: "live", label: "Live outputs", numeric: true, render: (row) => row.live },
            { key: "recorded", label: "Recorded sample", numeric: true, render: (row) => row.recorded },
            { key: "calls", label: "Model calls", numeric: true, render: (row) => row.calls },
            {
              key: "reviews",
              label: "Reviews",
              render: (row) => reviewText({ ACCEPTED: row.ACCEPTED, EDITED: row.EDITED, REJECTED: row.REJECTED }),
            },
          ]}
        />
        <p className="ac-muted">{data.recorded_label}: counted apart from live outputs.</p>
      </Panel>
    </div>
  );
}
