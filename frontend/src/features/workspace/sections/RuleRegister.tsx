import { useState } from "react";
import { BookOpenCheck } from "lucide-react";
import { Empty, Panel } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, useResource } from "../../customer-admin/shared";
import { BasisChips } from "../../shared/Basis";
import { Hero } from "./boardParts";
import {
  STATE_LABELS,
  inForceText,
  registerPath,
  rulesUsedLines,
  type RuleDetail,
  type RuleList,
  type RulesUsed,
} from "../ruleRegister";

const MARKETS: Array<[string, string]> = [
  ["US", "United States"],
  ["EU_NI", "EU and Northern Ireland"],
  ["GB", "Great Britain"],
  ["IN", "India"],
  ["CA", "Canada"],
];

/**
 * Decision trees › Rules (B4, R-D13): every rule MDARIX applies, read-only for every signed-in member. What it decides,
 * its source, version, the dates it is in force and who approved it. "As at" shows the version in force on a day.
 * Flat table (G-2); the hero styling stays on the page header.
 */
export function RuleRegister() {
  const [market, setMarket] = useState("");
  const [kind, setKind] = useState("");
  const [asAt, setAsAt] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const list = useResource<RuleList>(registerPath({ market, kind, asAt }));
  const summary = list.data?.summary;
  return (
    <div className="rr-page">
      <Hero
        tone="neutral"
        icon={<BookOpenCheck size={28} />}
        eyebrow="Decision trees › Rules"
        title={
          summary
            ? `${summary.rules} rules · ${summary.markets} markets · ${summary.held_as_data} held as data`
            : "The rules MDARIX applies"
        }
        detail={
          summary
            ? `All ${summary.starter_mark.charAt(0).toLowerCase()}${summary.starter_mark.slice(1)} A rule changes only by a new version with a date; a signed conclusion keeps the version it used.`
            : "Reading the register…"
        }
      />
      <Panel title="Rules" source={list}>
        <div className="ca-toolbar rr-filters">
          <select aria-label="Market" value={market} onChange={(event) => setMarket(event.target.value)}>
            <option value="">Every market</option>
            {MARKETS.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
          <select aria-label="Kind" value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="">Every kind</option>
            {(list.data?.kinds ?? []).map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>
          <label className="ca-inline-select">
            As at
            <input type="date" value={asAt} onChange={(event) => setAsAt(event.target.value)} />
          </label>
        </div>
        {list.state === "error" && <p className="ac-muted">{errorText(list.error, "The rules could not be read.")}</p>}
        {list.data && !list.data.items.length && (
          <Empty title="No rule matches" detail="Choose another market, kind or day." />
        )}
        {list.data && list.data.items.length > 0 && (
          <div className="ac-table-wrap">
            <table className="ac-table rr-table">
              <thead>
                <tr>
                  <th scope="col">Rule</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Market</th>
                  <th scope="col">Version</th>
                  <th scope="col">Source</th>
                  <th scope="col">In force</th>
                  <th scope="col">Approved</th>
                  <th scope="col">Held as</th>
                  <th scope="col">Fingerprint</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((rule) => (
                  <tr key={rule.code}>
                    <td>
                      <button type="button" className="ac-link" onClick={() => setOpen(rule.code)}>
                        {rule.title}
                      </button>
                      <small className="rr-plain">{rule.plain}</small>
                    </td>
                    <td>{rule.kind_label}</td>
                    <td>{rule.market_label}</td>
                    <td>
                      {rule.version_words} <code>{rule.code}</code>
                    </td>
                    <td>
                      <BasisChips ids={rule.source.map((source) => source.id)} label={`Source of ${rule.title}`} />
                      <small>{rule.source.map((source) => source.clause).join("; ")}</small>
                    </td>
                    <td>
                      {inForceText(rule)}
                      {rule.state !== "IN_FORCE" && <small> · {STATE_LABELS[rule.state]}</small>}
                    </td>
                    <td>
                      {rule.approved_by ?? "—"}
                      {rule.approved_on ? ` · ${formatDate(rule.approved_on)}` : ""}
                    </td>
                    <td>{rule.held_as === "DATA" ? "Data" : "MDARIX code"}</td>
                    <td>
                      <code>{rule.fingerprint ?? "—"}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {open && <RuleDrawer code={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

/** One rule: its logic as IF … THEN … lines (data rules), report types and periods, day counting, version history. */
function RuleDrawer({ code, onClose }: { code: string; onClose: () => void }) {
  const detail = useResource<RuleDetail>(`/api/v1/rule-register/${encodeURIComponent(code)}`);
  const rule = detail.data;
  return (
    <Drawer title={rule ? rule.title : "Rule"} onClose={onClose}>
      {detail.state === "error" && <p className="ac-muted">{errorText(detail.error, "The rule could not be read.")}</p>}
      {rule && (
        <div className="rr-detail">
          <p>{rule.plain}</p>
          <p className="ac-muted">
            {rule.version_words} <code>{rule.code}</code> · {inForceText(rule)} · {STATE_LABELS[rule.state]} · held as{" "}
            {rule.implementation_held.toLowerCase()} · {rule.starter_mark}
          </p>
          {rule.logic && (
            <>
              <h3>When a report is owed</h3>
              <ul className="rr-logic">
                {[...rule.logic.defined, ...rule.logic.reportable].map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <h3>Which report</h3>
              <ul className="rr-logic">
                {rule.logic.report_type.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <h3>Reports and their periods</h3>
              <ul className="rr-logic">
                {rule.logic.report_types.map((type) => (
                  <li key={type.code}>
                    {type.label}
                    {type.days
                      ? `: ${type.days} ${type.basis === "WORK" ? "work days" : "calendar days"}`
                      : ": no period in the floor"}
                  </li>
                ))}
              </ul>
              <h3>How days are counted</h3>
              <p>
                In the authority's time zone ({rule.logic.counting.authority_zone ?? "your organization's"}), from{" "}
                {rule.logic.counting.awareness_is_day_one ? "the awareness day as day 1" : "the day after awareness"};
                no weekend or holiday extension.
              </p>
              {rule.logic.not_asked.length > 0 && (
                <>
                  <h3>Questions not asked</h3>
                  <ul className="rr-logic">
                    {rule.logic.not_asked.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
          <h3>Versions</h3>
          <ul className="rr-logic">
            {rule.history.map((version) => (
              <li key={version.code}>
                <code>{version.code}</code> · {inForceText(version)} · {STATE_LABELS[version.state]}
                {version.change.reason ? ` · ${version.change.reason}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Drawer>
  );
}

/** "Rules used" on a market conclusion (B4, C4): at the event, today and decided, kept apart. Hidden when off. */
export function RulesUsedPanel({ used }: { used: RulesUsed | null | undefined }) {
  const lines = rulesUsedLines(used);
  if (!lines) return null;
  return (
    <section className="uw-card uw-card-pad rr-used" aria-label="Rules used">
      <h2>Rules used</h2>
      <dl className="ca-facts">
        <div>
          <dt>At the event</dt>
          <dd>{lines.atEvent}</dd>
        </div>
        <div>
          <dt>Today</dt>
          <dd>{lines.today}</dd>
        </div>
        <div>
          <dt>Decided</dt>
          <dd>{lines.decided}</dd>
        </div>
      </dl>
    </section>
  );
}
