/** E3 + W6: the decision-and-impact summary of a signed investigation decision, on one screen (readable on a
 * projector at 1280×720), with its formal decision record below. Flat (G-2). Read from
 * GET /api/v1/investigations/{id}/decision/summary; nothing shows before a decision is signed. */
import { ToneBadge } from "../../admin/console/charts";
import { useResource } from "../../customer-admin/shared";
import { formatDay, formatDateTime } from "../../../app/dates";
import { followUpStatusView, followUpTypeLabel } from "../afterDecision";
import {
  NOT_RECORDED,
  decisionSummaryPath,
  headline,
  listText,
  lockedAiLines,
  mfaText,
  reviewText,
  workedTone,
  type DecisionSummary,
  type SummaryHypothesis,
} from "../decisionSummary";

const day = (value: string | null | undefined) => (value ? formatDay(value, NOT_RECORDED) : NOT_RECORDED);

function Hypotheses({ items, none }: { items: SummaryHypothesis[] | undefined; none: string }) {
  if (!items?.length) return <p className="ac-muted">{none}</p>;
  return (
    <ul className="uw-intel-list">
      {items.map((item, index) => (
        <li key={item.ref ?? index}>
          {item.statement ?? NOT_RECORDED}
          <small className="ac-muted">
            {" "}
            · {item.ref ?? "—"}
            {item.origin === "AI" ? " · proposed by AI" : ""}
            {item.status_label ? ` · ${item.status_label}` : ""}
          </small>
        </li>
      ))}
    </ul>
  );
}

/** The formal decision record: ten parts, each exactly as recorded, or "Not recorded". */
export function DecisionRecordParts({ data }: { data: DecisionSummary }) {
  const decision = data.decision;
  if (!decision) return null;
  const signature = data.signature;
  const evidence = data.evidence;
  const ai = data.ai;
  const hypotheses = data.hypotheses;
  return (
    <dl className="uw-dsum-record">
      <div>
        <dt>Decision asked</dt>
        <dd>{data.investigation.question ?? NOT_RECORDED}</dd>
      </div>
      <div>
        <dt>Owner and authority</dt>
        <dd>
          {data.owner?.name ?? NOT_RECORDED}
          {data.owner?.role_label ? `, signed as ${data.owner.role_label}` : ""}
          {" · "}
          {data.owner?.authority_recorded ? "approval authority on record" : "approval authority: not recorded"}
        </dd>
      </div>
      <div>
        <dt>Outcome</dt>
        <dd>
          {decision.outcome_label ?? NOT_RECORDED}
          {decision.conditions ? ` · Conditions: ${decision.conditions}` : ""}
          {decision.conclusion && <p className="uw-intel-statement">{decision.conclusion}</p>}
          <small className="ac-muted">
            Brief {decision.brief_ref ?? NOT_RECORDED}
            {decision.brief_version ? ` version ${decision.brief_version}` : ""} · root cause{" "}
            {decision.root_cause_category_label ?? NOT_RECORDED} ·{" "}
            {decision.root_cause_attribution_label ?? "attribution not recorded"}
          </small>
        </dd>
      </div>
      <div>
        <dt>Evidence considered</dt>
        <dd>
          {evidence?.supporting.length ? (
            <ul className="uw-intel-list" aria-label="Supporting evidence">
              {evidence.supporting.map((item, index) => (
                <li key={item.ref ?? index}>
                  <strong>{item.ref ?? "—"}</strong> {item.title ?? ""} <small className="ac-muted">· supports</small>
                </li>
              ))}
              {evidence.contradicting.map((item, index) => (
                <li key={`c-${item.ref ?? index}`}>
                  <strong>{item.ref ?? "—"}</strong> {item.title ?? ""} <small className="ac-muted">· against</small>
                </li>
              ))}
            </ul>
          ) : (
            NOT_RECORDED
          )}
        </dd>
      </div>
      <div>
        <dt>AI recommendation</dt>
        <dd>
          {ai?.in_brief.length
            ? `Used in the signed brief: ${ai.in_brief.join(", ")}.`
            : "None used in the signed brief."}
          {ai?.proposals.map((item, index) => (
            <p key={item.ref ?? index} className="uw-dsum-line">
              AI proposal {item.ref ?? "—"}
              {item.recorded ? " (recorded with the sample, no model called)" : ""}: {reviewText(item.reviews)} by a
              person.
            </p>
          ))}
          <strong>As locked at signing</strong>
          <ul className="uw-intel-list" aria-label="AI used, as locked at signing">
            {lockedAiLines(ai?.locked).map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </dd>
      </div>
      <div>
        <dt>Hypotheses</dt>
        <dd>
          <strong>Accepted as the root cause</strong>
          <Hypotheses items={hypotheses?.accepted} none={NOT_RECORDED} />
          <strong>Alternatives considered</strong>
          <Hypotheses items={hypotheses?.alternatives} none="None recorded" />
          <strong>Rejected</strong>
          <Hypotheses items={hypotheses?.rejected} none="None rejected by a person" />
        </dd>
      </div>
      <div>
        <dt>Rationale</dt>
        <dd>{decision.rationale ?? NOT_RECORDED}</dd>
      </div>
      <div>
        <dt>Signature</dt>
        <dd>
          {signature ? (
            <>
              {signature.name ?? NOT_RECORDED}
              {signature.role_label ? `, ${signature.role_label}` : ""} ·{" "}
              {signature.signed_at ? formatDateTime(signature.signed_at, NOT_RECORDED) : NOT_RECORDED} ·{" "}
              {mfaText(signature.mfa_verified)} ·{" "}
              {signature.verification === "VALID"
                ? "verified by the server"
                : `verification: ${signature.verification ?? NOT_RECORDED}`}
              {signature.meaning && <p className="uw-dsum-line">Meaning: {signature.meaning}</p>}
            </>
          ) : (
            NOT_RECORDED
          )}
        </dd>
      </div>
      <div>
        <dt>Dates</dt>
        <dd>
          Effective {day(decision.effective_on)} · review{" "}
          {decision.review_on
            ? `${day(decision.review_on)} (the effectiveness check)`
            : `${NOT_RECORDED.toLowerCase()} yet`}
        </dd>
      </div>
      <div>
        <dt>Linked actions</dt>
        <dd>
          {data.follow_ups?.length || data.capas?.length ? (
            <ul className="uw-intel-list" aria-label="Linked actions">
              {data.follow_ups?.map((item) => (
                <li key={item.id}>
                  {followUpTypeLabel(item)}
                  {item.title ? `: ${item.title}` : ""} · {followUpStatusView(item).label}
                  {item.due_at ? ` · due ${day(item.due_at)}` : ""}
                </li>
              ))}
              {data.capas?.map((capa) => (
                <li key={capa.id}>
                  CAPA {capa.ref}: {capa.title} ·{" "}
                  {capa.check
                    ? capa.check.signed_at
                      ? `effectiveness check signed ${capa.check.status === "EFFECTIVE" ? "effective" : "not effective"}`
                      : `effectiveness check planned for ${day(capa.check.planned_on)}: too early`
                    : "no effectiveness check planned"}
                </li>
              ))}
            </ul>
          ) : (
            "None recorded"
          )}
        </dd>
      </div>
    </dl>
  );
}

/** The one-screen summary: what was decided, on what evidence, by whom; what it affects; what happens next; whether
 * it worked so far. Then the full record, folded. */
export function DecisionSummaryView({
  investigationId,
  recordOpen = false,
}: {
  investigationId: string;
  recordOpen?: boolean;
}) {
  const resource = useResource<DecisionSummary>(decisionSummaryPath(investigationId));
  const data = resource.data;
  const decision = data?.decision;
  if (!data || !decision) return null;
  const affects = data.affects;
  const worked = data.worked;
  const evidence = data.evidence;
  const next = data.next ?? [];
  const accepted =
    data.ai?.proposals.reduce((sum, item) => sum + (item.reviews.ACCEPTED ?? 0) + (item.reviews.EDITED ?? 0), 0) ?? 0;
  return (
    <section className="uw-card uw-dsum" aria-labelledby="uw-dsum-title">
      <header className="uw-dsum-head">
        <span className="ac-eyebrow">
          Decision and impact · {data.investigation.ref ?? "Investigation"} · {decision.ref ?? "decision"}
        </span>
        <h2 id="uw-dsum-title">{headline(decision)}</h2>
        <p className="uw-dsum-by">
          Signed by <strong>{data.signature?.name ?? NOT_RECORDED}</strong>
          {data.signature?.role_label ? `, ${data.signature.role_label}` : ""} · {day(decision.effective_on)} ·{" "}
          {mfaText(data.signature?.mfa_verified)}
          {decision.superseded_by ? ` · superseded by ${decision.superseded_by.business_id ?? "a later decision"}` : ""}
        </p>
      </header>
      <div className="uw-dsum-grid">
        <article className="uw-dsum-tile">
          <h3>Decided on this evidence</h3>
          <p>
            <strong>{evidence?.supporting.length ?? 0}</strong> pieces of evidence for,{" "}
            <strong>{evidence?.contradicting.length ?? 0}</strong> against.
          </p>
          <ul className="uw-dsum-list">
            {evidence?.supporting.slice(0, 3).map((item, index) => (
              <li key={item.ref ?? index}>{item.title ?? item.ref}</li>
            ))}
          </ul>
          <p className="uw-dsum-line">
            {data.ai?.proposals.length
              ? `AI proposed; a person accepted ${accepted} of its outputs. People made the decision.`
              : "No AI was used. People made the decision."}
          </p>
        </article>
        <article className="uw-dsum-tile">
          <h3>What it affects</h3>
          <dl className="uw-dsum-facts">
            <div>
              <dt>Product</dt>
              <dd>
                {affects?.product?.name ?? NOT_RECORDED}
                {affects?.versions.length ? ` · ${listText(affects.versions)}` : ""}
              </dd>
            </div>
            <div>
              <dt>Lots</dt>
              <dd>{listText(affects?.lots)}</dd>
            </div>
            <div>
              <dt>Markets</dt>
              <dd>{listText(affects?.markets)}</dd>
            </div>
            <div>
              <dt>Risk file</dt>
              <dd>{listText(affects?.risks.map((risk) => risk.ref))}</dd>
            </div>
          </dl>
        </article>
        <article className="uw-dsum-tile">
          <h3>What happens next</h3>
          {next.length ? (
            <ol className="uw-dsum-list">
              {next.slice(0, 4).map((item, index) => (
                <li key={`${item.ref}-${index}`}>
                  <strong>{item.due ? day(item.due) : "No date"}</strong> {item.what}
                </li>
              ))}
            </ol>
          ) : (
            <p className="ac-muted">Nothing open: no follow-up or check is waiting.</p>
          )}
        </article>
        <article className={`uw-dsum-tile is-${workedTone(worked?.state)}`}>
          <h3>Did it work so far?</h3>
          <p className="uw-dsum-worked">
            <ToneBadge
              tone={workedTone(worked?.state)}
              label={
                worked?.state === "EFFECTIVE"
                  ? "Signed effective"
                  : worked?.state === "NOT_EFFECTIVE"
                    ? "Signed not effective"
                    : worked?.state === "TOO_EARLY"
                      ? "Too early"
                      : "No check planned"
              }
            />
          </p>
          <p>
            {worked?.state === "TOO_EARLY" && worked.on
              ? `The effectiveness check is planned for ${day(worked.on)}. Only a signed check says an action worked.`
              : (worked?.text ?? NOT_RECORDED)}
          </p>
        </article>
      </div>
      <details className="uw-more uw-dsum-more" open={recordOpen}>
        <summary>The full decision record, as signed</summary>
        <DecisionRecordParts data={data} />
      </details>
    </section>
  );
}
