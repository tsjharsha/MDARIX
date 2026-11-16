/** B5b: "Did it work?" after a signed decision (didItWork.ts), flat (G-2): on the investigation's Decisions & actions,
 * on a CAPA's effectiveness check (that CAPA only), and linked from Product 360. Hidden while the switch is off. */
import { Panel, ToneBadge } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { useClosedLoop } from "../workspaceContext";
import {
  actionHeading,
  actionsFor,
  countsLine,
  denominatorLine,
  didItWorkPath,
  resultTone,
  windowLine,
  type DidItWork as DidItWorkData,
  type LoopAction,
  type LoopGroup,
  type LoopRef,
} from "../didItWork";
import { FlatTable, useRecordOpener } from "./ProductHub";

const day = (value: string) => formatDay(value, "–");

function Complaints({ items, label }: { items?: LoopRef[]; label: string }) {
  const openRecord = useRecordOpener();
  if (!items?.length) return null;
  return (
    <details className="uw-more">
      <summary>
        {label} ({items.length})
      </summary>
      <span className="uw-doc-sources">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className="ac-link"
            onClick={() => openRecord("complaints", { complaint_identifier: item.ref, id: item.id })}
          >
            {item.ref}
          </button>
        ))}
      </span>
    </details>
  );
}

function GroupRow({ group }: { group: LoopGroup }) {
  return (
    <tr>
      <th scope="row">{group.name}</th>
      <td>
        <ToneBadge tone={resultTone(group.result)} label={group.word} />
      </td>
      <td>
        {countsLine(group)}
        <Complaints items={group.before_complaints} label="Complaints before" />
        <Complaints items={group.after_complaints} label="Complaints after" />
      </td>
      <td>{denominatorLine(group)}</td>
    </tr>
  );
}

const HEAD = ["Group", "Result", "Complaints", "Denominator"] as const;

function ActionBlock({ action }: { action: LoopAction }) {
  const groups = [...action.by_version, ...(action.new_vs_old ? [action.new_vs_old] : [])];
  return (
    <section className="ca-drawer-section" aria-label={actionHeading(action)}>
      <h3>{actionHeading(action)}</h3>
      <p className="uw-cr-meta">
        Action date {day(action.on)} · {windowLine(action, day)}
      </p>
      <FlatTable caption={`Before and after ${action.ref}`} head={HEAD}>
        {groups.map((group) => (
          <GroupRow key={group.name} group={group} />
        ))}
        {action.lot_cohorts && <GroupRow group={action.lot_cohorts} />}
      </FlatTable>
      {!!action.lot_cohorts?.lot_unknown && (
        <p className="ac-muted">{action.lot_cohorts.lot_unknown} complaints after the action have no lot.</p>
      )}
      {action.lots && action.lots.length > 0 && (
        <details className="uw-more">
          <summary>Each lot ({action.lots.length})</summary>
          <FlatTable
            caption={`Lots of ${action.ref}`}
            head={["Lot", "Version", "Released", "Cohort", "After", "Units"]}
          >
            {action.lots.map((lot) => (
              <tr key={lot.id}>
                <th scope="row">{lot.ref}</th>
                <td>{lot.version}</td>
                <td>{lot.released ? day(lot.released) : "–"}</td>
                <td>{lot.cohort === "after" ? "Released after the action" : "Released before"}</td>
                <td>{lot.after}</td>
                <td>{lot.units ?? "Units unknown"}</td>
              </tr>
            ))}
          </FlatTable>
        </details>
      )}
    </section>
  );
}

export function DidItWorkView({
  investigationId,
  caseLabel,
  capaRef,
}: {
  investigationId: string;
  caseLabel: string;
  /** On an effectiveness check: that CAPA's comparisons only. */
  capaRef?: string | null;
}) {
  const on = useClosedLoop();
  const resource = useResource<DidItWorkData>(on ? didItWorkPath(investigationId) : null);
  if (!on) return null;
  const view = resource.data;
  const actions = view ? actionsFor(view, capaRef) : [];
  return (
    <Panel eyebrow={caseLabel} title="Did it work?" source={resource}>
      {view && !view.decision && (
        <p className="ac-muted">Nothing signed yet. After the decision is signed, the later complaints show here.</p>
      )}
      {view?.decision && (
        <>
          <p className="ac-note">{view.notice}</p>
          <p className="uw-cr-meta">
            Decision {view.decision.ref} signed {day(view.decision.decided_at)}
            {view.scope?.versions.length ? ` · versions ${view.scope.versions.map((v) => v.ref).join(", ")}` : ""}
            {view.scope?.problems.length ? ` · problem codes ${view.scope.problems.join(", ")}` : ""} · rule version{" "}
            {view.rule_version}
          </p>
          {!capaRef && view.later && (
            <p>
              <strong>{view.later.count}</strong> later complaints with the same problem on these versions
              {view.later.version_unknown.count
                ? `; ${view.later.version_unknown.count} more have no version and are counted in no version`
                : ""}
              .
              <Complaints items={view.later.complaints} label="Later complaints" />
              <Complaints items={view.later.version_unknown.complaints} label="Version unknown" />
            </p>
          )}
          {actions.length ? (
            actions.map((action) => <ActionBlock key={`${action.kind}-${action.ref}-${action.on}`} action={action} />)
          ) : (
            <p className="ac-muted">
              No action date yet: a CAPA, a field action&apos;s effective date or a new version.
            </p>
          )}
          {!capaRef && !!view.field_actions?.length && (
            <ul className="uw-intel-list" aria-label="Field actions">
              {view.field_actions.map((item) => (
                <li key={item.follow_up}>
                  Field action {item.reference ?? item.follow_up}
                  {item.kind ? ` · ${item.kind.replace(/_/g, " ").toLowerCase()}` : ""}
                  {item.effective_on ? ` · effective ${day(item.effective_on)}` : " · no effective date yet"}
                </li>
              ))}
            </ul>
          )}
          {!!view.superseded.length && (
            <p className="ac-muted">
              Superseded decisions are not read: {view.superseded.map((item) => item.ref).join(", ")}.
            </p>
          )}
          <details className="uw-more">
            <summary>Limits of these counts</summary>
            <ul>
              {view.limits.map((limit) => (
                <li key={limit}>{limit}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </Panel>
  );
}
