/** Failure chains: the AI's, adopted, or built by people, drawn left to right with each link's state. (Part of CaseIntelligence.tsx.) */
import { useState } from "react";
import { GitBranch, Plus, Trash2 } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../../admin/console/charts";
import { titleCase } from "../../../admin/console/dashboardModel";
import { Drawer, errorText, listOf, send, useResource } from "../../../customer-admin/shared";
import { safeText } from "../../../../app/displayId";
import { AiInterpretationNote, StatementKind } from "../../../shared/StatementKind";
import { useCan, usePanelFlag, usePanelState, useWorkspace } from "../../workspaceContext";
import {
  LINK_LEGEND,
  LINK_STATE,
  LINK_STATES,
  TEXT_MAX,
  aiChainId,
  aiChainLayout,
  chainLayout,
  chainName,
  intelligencePath,
  linkStateBody,
  linkStateLabel,
  linkStateProblem,
  manualChainBody,
  manualChainProblem,
  newManualChain,
  stateNeedsEvidence,
  withNode,
  withoutNode,
  type ChainLayout,
  type ChainSegment,
  type FailureChains,
  type LinkState,
  type LinkStateForm,
  type ManualChainForm,
} from "../../intelligence";
import {
  DrawerActions,
  DrawerError,
  EvidenceSelect,
  Problem,
  ReasonField,
  evidenceOption,
  useCaseEvidence,
  useSend,
} from "./shared";

/** What each line style means; the chain is never read from colour alone. */
export function ChainLegend() {
  return (
    <ul className="uw-chain-legend" aria-label="Failure chain legend">
      {LINK_LEGEND.map((item) => (
        <li key={item.state}>
          <span className={`uw-chain-line line-${item.line}`} aria-hidden="true">
            <span />
            <span />
          </span>
          <span>
            <strong>{item.label}</strong> <small className="ac-muted">{item.help}</small>
          </span>
        </li>
      ))}
    </ul>
  );
}

function SegmentText({ segment }: { segment: ChainSegment }) {
  return (
    <>
      <strong>{segment.stateLabel}</strong>
      {segment.relationship && <small>{segment.relationship}</small>}
      {segment.evidence && <small>Evidence {segment.evidence}</small>}
    </>
  );
}

/** A chain drawn left to right: each step, then the link to the next one in its line style. */
export function ChainDiagram({
  layout,
  label,
  onLink,
}: {
  layout: ChainLayout;
  label: string;
  onLink?: (segment: ChainSegment) => void;
}) {
  if (!layout.nodes.length) return <p className="ac-muted">This chain has no steps recorded.</p>;
  return (
    <>
      <ol className="uw-chain" aria-label={`${label}, left to right`}>
        {layout.nodes.map((node, index) => {
          const segment = layout.segments[index];
          return (
            <li key={node.key} className="uw-chain-item">
              <span className="uw-chain-node">{node.label}</span>
              {segment && index < layout.nodes.length - 1 && (
                <span className={`uw-chain-link state-${segment.state.toLowerCase()}`}>
                  <span className={`uw-chain-line line-${LINK_STATE[segment.state].line}`} aria-hidden="true">
                    <span />
                    <span />
                  </span>
                  <span className="uw-chain-link-text" title={segment.rationale ?? undefined}>
                    <span className="ca-sr-only">Link to the next step: </span>
                    <SegmentText segment={segment} />
                    {onLink && segment.linkId && (
                      <button type="button" className="ac-link" onClick={() => onLink(segment)}>
                        Change state
                      </button>
                    )}
                  </span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {layout.other.length > 0 && (
        <ul className="uw-intel-list">
          {layout.other.map((segment) => (
            <li key={segment.key}>
              {segment.from} → {segment.to}: <SegmentText segment={segment} />
              {onLink && segment.linkId && (
                <button type="button" className="ac-link" onClick={() => onLink(segment)}>
                  Change state
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function FailureChainView({
  investigationId,
  caseLabel,
  readOnly,
}: {
  investigationId: string;
  caseLabel: string;
  readOnly: boolean;
}) {
  const canWork = useCan("investigation.work") && !readOnly;
  const chains = useResource<FailureChains>(intelligencePath(investigationId, "failure-chains"));
  const [adopting, setAdopting] = useState<string | null>(null);
  const [adoptError, setAdoptError] = useState("");
  const { notify } = useWorkspace();
  const stored = listOf(chains.data?.stored);
  // Each drawer has its own address (panel=<kind>:<id>), so Back closes it and a refresh reopens it.
  const [building, setBuilding] = usePanelFlag("build-chain");
  const [changing, setChanging] = usePanelState<{ chainId: string; segment: ChainSegment }>(
    "chain-link",
    ({ chainId, segment }) => `${chainId}.${segment.linkId}`,
    (key) => {
      const [chainId, linkId] = key.split(".");
      const chain = stored.find((item) => String(item.id) === chainId);
      const layout = chain ? chainLayout(chain) : null;
      const segment = [...(layout?.segments ?? []), ...(layout?.other ?? [])].find((item) => item.linkId === linkId);
      return segment ? { chainId, segment } : null;
    },
  );
  const aiLatest = chains.data?.ai_latest ?? null;
  const aiChains = listOf(aiLatest?.chains);
  const done = () => {
    setBuilding(false);
    setChanging(null);
    chains.reload();
  };
  const adopt = async (chainId: string) => {
    if (adopting || !aiLatest?.ai_execution_id) return;
    setAdopting(chainId);
    setAdoptError("");
    try {
      await send(intelligencePath(investigationId, "failure-chains/adopt"), "POST", {
        ai_execution_id: aiLatest.ai_execution_id,
        ai_chain_id: chainId,
      });
      notify("AI chain adopted as a working chain. Judge each link before relying on it.");
      chains.reload();
    } catch (failure) {
      setAdoptError(errorText(failure, "The AI chain was not adopted."));
    } finally {
      setAdopting(null);
    }
  };
  return (
    <Panel
      eyebrow={caseLabel}
      title="Failure chain"
      source={chains}
      action={
        canWork ? (
          <button type="button" className="ac-primary" onClick={() => setBuilding(true)}>
            <GitBranch size={15} aria-hidden="true" /> Build a chain by hand
          </button>
        ) : undefined
      }
    >
      <p className="ac-note">
        A failure chain shows how one condition may lead to the next. Each link's state says how well evidence supports
        it; an unresolved chain is a valid result, not a failure.
      </p>
      <ChainLegend />
      {stored.length ? (
        stored.map((chain) => (
          <section key={chain.id} className="uw-intel-card uw-chain-card" aria-label={chainName(chain)}>
            <header>
              <strong>{chainName(chain)}</strong>
              <StatementKind
                kind={
                  String(chain.origin ?? "")
                    .toUpperCase()
                    .startsWith("AI")
                    ? "AI_INTERPRETATION"
                    : "HYPOTHESIS"
                }
                origin={chain.origin}
                kindLabel="Working chain"
              />
              {safeText(chain.status) && <ToneBadge tone="neutral" label={titleCase(String(chain.status))} />}
            </header>
            {safeText(chain.created_by_name) && <small className="ac-muted">Recorded by {chain.created_by_name}</small>}
            <ChainDiagram
              layout={chainLayout(chain)}
              label={chainName(chain)}
              onLink={canWork ? (segment) => setChanging({ chainId: chain.id, segment }) : undefined}
            />
          </section>
        ))
      ) : (
        <Empty
          title="No working chain yet"
          detail="Build one by hand, or adopt the latest AI chain below and judge its links."
        />
      )}
      {aiChains.length > 0 && (
        <section className="ca-drawer-section">
          <h3>Latest AI chains</h3>
          <AiInterpretationNote />
          {aiChains.map((chain, index) => {
            const id = aiChainId(chain);
            const layout = aiChainLayout(chain);
            return (
              <section key={id || index} className="uw-intel-card is-ai uw-chain-card">
                <header>
                  <strong>AI chain {index + 1}</strong>
                  <StatementKind kind="AI_INTERPRETATION" origin="AI" />
                  {safeText(chain.overall_status) && (
                    <ToneBadge tone="neutral" label={titleCase(String(chain.overall_status))} />
                  )}
                </header>
                {safeText(chain.chain_statement) && <p className="uw-intel-statement">{chain.chain_statement}</p>}
                <ChainDiagram layout={layout} label={`AI chain ${index + 1}`} />
                {canWork && id && aiLatest?.ai_execution_id && (
                  <div className="ca-action-row">
                    <button
                      type="button"
                      className="ac-secondary"
                      disabled={Boolean(adopting)}
                      onClick={() => void adopt(id)}
                    >
                      {adopting === id ? "Adopting…" : "Adopt this AI chain"}
                    </button>
                    <small className="ac-muted">
                      Adopting copies it as a working chain marked as AI-made; its links still need a person's
                      judgement.
                    </small>
                  </div>
                )}
              </section>
            );
          })}
          <DrawerError error={adoptError} />
        </section>
      )}
      {building && (
        <ManualChainDrawer investigationId={investigationId} onClose={() => setBuilding(false)} onDone={done} />
      )}
      {changing && (
        <LinkStateDrawer
          investigationId={investigationId}
          chainId={changing.chainId}
          segment={changing.segment}
          onClose={() => setChanging(null)}
          onDone={done}
        />
      )}
    </Panel>
  );
}

function LinkStateDrawer({
  investigationId,
  chainId,
  segment,
  onClose,
  onDone,
}: {
  investigationId: string;
  chainId: string;
  segment: ChainSegment;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<LinkStateForm>({ state: "", reason: "", evidenceId: "" });
  const { busy, error, run } = useSend(onDone);
  const problem = linkStateProblem(form, segment.state);
  return (
    <Drawer title="Change a link's state" onClose={onClose}>
      <p className="ac-muted">
        Now: {linkStateLabel(segment.state, segment.stateLabel)}
        {segment.evidence ? ` · evidence ${segment.evidence}` : ""}
      </p>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem && segment.linkId)
            void run(
              intelligencePath(
                investigationId,
                `failure-chains/${encodeURIComponent(chainId)}/links/${encodeURIComponent(segment.linkId)}/state`,
              ),
              linkStateBody(form),
              "Link state recorded.",
              "The link's state was not changed.",
            );
        }}
      >
        <label className="ca-field">
          New state
          <select
            value={form.state}
            onChange={(event) => setForm((value) => ({ ...value, state: event.target.value as LinkState | "" }))}
          >
            <option value="">Choose</option>
            {LINK_STATES.map((state) => (
              <option key={state} value={state}>
                {LINK_STATE[state].label}
              </option>
            ))}
          </select>
          {form.state && <small className="ac-muted">{LINK_STATE[form.state].help}</small>}
        </label>
        <EvidenceSelect
          investigationId={investigationId}
          label={form.state && stateNeedsEvidence(form.state) ? "Evidence behind it" : "Evidence behind it (optional)"}
          optional={!(form.state && stateNeedsEvidence(form.state))}
          value={form.evidenceId}
          onChange={(evidenceId) => setForm((value) => ({ ...value, evidenceId }))}
        />
        <ReasonField
          label="Reason (kept in the history)"
          value={form.reason}
          onChange={(reason) => setForm((value) => ({ ...value, reason }))}
        />
        <Problem problem={problem} touched={Boolean(form.state || form.reason.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Record state" />
      </form>
    </Drawer>
  );
}

function ManualChainDrawer({
  investigationId,
  onClose,
  onDone,
}: {
  investigationId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState<ManualChainForm>(newManualChain);
  const [touched, setTouched] = useState(false);
  const { busy, error, run } = useSend(onDone);
  const { items } = useCaseEvidence(investigationId);
  const problem = manualChainProblem(form);
  const setNode = (index: number, text: string) =>
    setForm((value) => ({ ...value, nodes: value.nodes.map((node, position) => (position === index ? text : node)) }));
  const setLink = (index: number, change: Partial<ManualChainForm["links"][number]>) =>
    setForm((value) => ({
      ...value,
      links: value.links.map((link, position) => (position === index ? { ...link, ...change } : link)),
    }));
  const stepName = (index: number) => `${index + 1}. ${form.nodes[index]?.trim() || "(not described)"}`;
  return (
    <Drawer title="Build a failure chain" onClose={onClose}>
      <form
        className="ca-form ca-drawer-section"
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (!problem)
            void run(
              intelligencePath(investigationId, "failure-chains"),
              manualChainBody(form),
              "Failure chain recorded.",
              "The failure chain was not recorded.",
            );
        }}
      >
        <label className="ca-field">
          Name
          <input
            required
            maxLength={200}
            value={form.name}
            onChange={(event) => setForm((value) => ({ ...value, name: event.target.value }))}
            placeholder="e.g. Seal wear to occlusion alarm"
          />
        </label>
        <fieldset className="ca-fieldset">
          <legend>Steps, in order</legend>
          {form.nodes.map((node, index) => (
            <div className="uw-chain-row" key={index}>
              <label className="ca-field">
                Step {index + 1}
                <input
                  maxLength={255}
                  value={node}
                  onChange={(event) => setNode(index, event.target.value)}
                  placeholder={index === 0 ? "e.g. Supplier changed seal material" : "e.g. Seal hardness lower"}
                />
              </label>
              {form.nodes.length > 2 && (
                <button
                  type="button"
                  className="ac-link"
                  aria-label={`Remove step ${index + 1}`}
                  onClick={() => setForm((value) => withoutNode(value, index))}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              )}
            </div>
          ))}
          <button type="button" className="ac-secondary" onClick={() => setForm(withNode)}>
            <Plus size={15} aria-hidden="true" /> Add step
          </button>
        </fieldset>
        <fieldset className="ca-fieldset">
          <legend>Links between steps</legend>
          {form.links.map((link, index) => (
            <div className="uw-chain-link-form" key={index}>
              <div className="ca-form-grid">
                <label className="ca-field">
                  From
                  <select
                    value={link.fromIndex}
                    onChange={(event) => setLink(index, { fromIndex: Number(event.target.value) })}
                  >
                    {form.nodes.map((_, position) => (
                      <option key={position} value={position}>
                        {stepName(position)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ca-field">
                  To
                  <select
                    value={link.toIndex}
                    onChange={(event) => setLink(index, { toIndex: Number(event.target.value) })}
                  >
                    {form.nodes.map((_, position) => (
                      <option key={position} value={position}>
                        {stepName(position)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ca-field">
                  State
                  <select
                    value={link.state}
                    onChange={(event) => setLink(index, { state: event.target.value as LinkState })}
                  >
                    {LINK_STATES.map((state) => (
                      <option key={state} value={state}>
                        {LINK_STATE[state].label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ca-field">
                  {stateNeedsEvidence(link.state) ? "Evidence" : "Evidence (optional)"}
                  <select
                    value={link.evidenceId}
                    onChange={(event) => setLink(index, { evidenceId: event.target.value })}
                  >
                    <option value="">No evidence</option>
                    {items
                      .filter((item) => item.evidence?.id)
                      .map((item) => (
                        <option key={item.evidence.id} value={String(item.evidence.id)}>
                          {evidenceOption(item)}
                        </option>
                      ))}
                  </select>
                </label>
              </div>
              <label className="ca-field">
                Rationale (optional)
                <input
                  maxLength={TEXT_MAX}
                  value={link.rationale}
                  onChange={(event) => setLink(index, { rationale: event.target.value })}
                />
              </label>
              {form.links.length > 1 && (
                <button
                  type="button"
                  className="ac-link"
                  onClick={() =>
                    setForm((value) => ({ ...value, links: value.links.filter((_, position) => position !== index) }))
                  }
                >
                  Remove link {index + 1}
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            className="ac-secondary"
            onClick={() =>
              setForm((value) => ({
                ...value,
                links: [
                  ...value.links,
                  {
                    fromIndex: 0,
                    toIndex: value.nodes.length - 1,
                    state: "HYPOTHESIZED",
                    evidenceId: "",
                    rationale: "",
                  },
                ],
              }))
            }
          >
            <Plus size={15} aria-hidden="true" /> Add link
          </button>
        </fieldset>
        <p className="ac-muted">
          A supported or partially supported link names the evidence behind it. The chain is recorded as yours; it is a
          working explanation, not a concluded root cause.
        </p>
        <Problem problem={problem} touched={touched || Boolean(form.name.trim())} />
        <DrawerError error={error} />
        <DrawerActions onClose={onClose} busy={busy} disabled={!!problem} label="Record chain" />
      </form>
    </Drawer>
  );
}
