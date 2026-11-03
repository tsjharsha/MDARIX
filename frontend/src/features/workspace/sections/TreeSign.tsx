import { useState } from "react";
import { ChevronRight, PenLine } from "lucide-react";
import { deadlineLabel, formatDateTime, timeLeft } from "../../../app/dates";
import { errorText, send } from "../../customer-admin/shared";
import { collapsed } from "../complaintReview";
import { useWorkspace } from "../workspaceContext";
import { reportPlace } from "../authorityReports";
import {
  ASSESSMENT_LIMITS,
  CONCLUSION_LABELS,
  assessmentPath,
  trainingMissing,
  type AssessmentDetail,
  type Conclusion,
  type MarketItem,
  type Question,
  type Suggestion,
} from "../marketAssessment";
import { signChecklist, type CheckItem, type QuestionGroup, type TreeForm } from "../treeAnswer";
import type { TreeMarket, TreePath } from "../decisionTrees";
import { InlineError } from "./boardParts";
import { STARTER_LABEL } from "../../shared/standards";

export type HarmState = { level: string; reason: string; disagreement: string };

/** What a signature means, in words, as it is shown wherever the signature is (21 CFR 11.50). */
export const signedMeaning = (conclusion: Conclusion | null | undefined) =>
  conclusion === "REPORTABLE" ? "signed reportable" : "signed not reportable";

/** The conclusion the person signs: the outcome when they follow it, else the other one (pending can only be
 * overridden to reportable: Unknown is never No). */
export function conclusionOf(outcome: Suggestion | null, choice: "follow" | "override"): Conclusion | null {
  if (!outcome) return null;
  if (choice === "follow") return outcome === "PENDING_INFORMATION" ? null : outcome;
  return outcome === "REPORTABLE" ? "NOT_REPORTABLE" : "REPORTABLE";
}

/** Everything that stands before Sign, as the short checklist under the outcome (the server checks it all again). */
export function signItems({
  groups,
  item,
  form,
  folded,
  harm,
  choice,
  overrideReason,
  trainingNeeded,
  trained,
}: {
  groups: QuestionGroup[];
  item: MarketItem;
  form: TreeForm;
  folded: Record<string, string>;
  harm: HarmState;
  choice: "follow" | "override";
  overrideReason: string;
  trainingNeeded: boolean;
  trained: boolean;
}): CheckItem[] {
  const items = signChecklist(groups, item, form, folded);
  if (!harm.level) items.push({ ok: false, text: "The harm level" });
  if (item.disagreement && collapsed(harm.disagreement).length < ASSESSMENT_LIMITS.reasonMin)
    items.push({ ok: false, text: "Why the answers differ from the harm level" });
  if (choice === "override" && collapsed(overrideReason).length < ASSESSMENT_LIMITS.reasonMin)
    items.push({ ok: false, text: "Your reason for overriding the outcome" });
  if (trainingNeeded && !trained) items.push({ ok: false, text: "Your training confirmation" });
  return items;
}

/**
 * The outcome and Sign in one card (0.10.83, D2.4): the outcome live from the saved answers (Reportable · type · due
 * date, Not reportable, or Pending information) with its "Why" chips; then "Follow the outcome" by default, the short
 * checklist, the harm level, the password and authenticator code with the training confirmation as one line, and
 * Sign. The real role decides who may sign, never the persona. Once signed: who signed, when, and what it means.
 */
export function SignCard({
  detail,
  item,
  tree,
  outcome,
  chips,
  signed,
  canDecide,
  groups,
  form,
  folded,
  harm,
  onHarm,
  flush,
  onSigned,
}: {
  detail: AssessmentDetail;
  item: MarketItem;
  tree: TreeMarket | null;
  path: TreePath | null;
  outcome: Suggestion | null;
  chips: { id: string; label: string }[];
  signed: boolean;
  canDecide: boolean;
  groups: QuestionGroup[];
  form: TreeForm;
  folded: Record<string, string>;
  harm: HarmState;
  onHarm: (next: HarmState) => void;
  flush: () => Promise<MarketItem | null>;
  onSigned: (next: MarketItem) => void;
  flat: readonly Question[];
}) {
  const { session } = useWorkspace();
  const [picked, setPicked] = useState<"follow" | "override" | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [trained, setTrained] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const version = signed ? item.current : item.draft;
  const tone = outcome === "REPORTABLE" ? "is-rep" : outcome === "NOT_REPORTABLE" ? "is-not" : "is-open";
  const clock = signed && item.current?.due_on ? { due_date: item.current.due_on } : item.clock;
  const definite = outcome === "REPORTABLE" || outcome === "NOT_REPORTABLE";
  // "Follow the outcome" is the default once there is one; pending information can only be overridden.
  const choice = picked ?? (definite || !outcome ? "follow" : "override");
  const conclusion = conclusionOf(outcome, choice);
  const missing = trainingMissing(item);
  const trainingNeeded = detail.training_required && missing.length > 0;
  const items = signItems({
    groups,
    item,
    form,
    folded,
    harm,
    choice,
    overrideReason,
    trainingNeeded,
    trained,
  });
  const ready = !!outcome && !!conclusion && items.every((entry) => entry.ok) && !!password && !busy;
  const levels = detail.scale.levels;
  const fromMapping = detail.severity_level;
  const sign = async () => {
    setBusy(true);
    setError("");
    try {
      const saved = await flush();
      if (!saved?.draft) throw new Error("The answers were not saved.");
      if (trained)
        for (const document of missing)
          await send(`/api/v1/signer-training/${encodeURIComponent(document.code)}/acknowledge`, "POST", {
            version: document.version,
            statement: document.statement,
          });
      const out = await send<AssessmentDetail>(assessmentPath(detail.complaint.id, item.market, "/sign"), "POST", {
        conclusion,
        override_reason: choice === "override" ? overrideReason : "",
        version: saved.draft.version,
        saved_at: saved.draft.saved_at,
        password,
        mfa_code: code || null,
      });
      const next = out.markets.find((entry) => entry.market === item.market);
      setPassword("");
      setCode("");
      if (next) onSigned(next);
    } catch (reason) {
      setError(errorText(reason, "The conclusion was not signed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className={`uw-card dt-outcome ${tone}`} id="dt-outcome" aria-label="The outcome">
      <div aria-live="polite" className="dt-outcome-top">
        <p className="ac-eyebrow">{signed ? "Signed conclusion" : "Points to"}</p>
        <p className="dt-big">{outcome ? CONCLUSION_LABELS[outcome] : "Not decided yet"}</p>
        {outcome === "REPORTABLE" && version?.report_type_label && (
          <p className="dt-type">{version.report_type_label}</p>
        )}
        {outcome && outcome !== "NOT_REPORTABLE" && clock && (
          <p>
            Due <b>{deadlineLabel(clock)}</b>
            {"days_left" in clock ? ` · ${timeLeft(clock)}` : ""}
          </p>
        )}
        {!outcome && <p className="ac-muted">The outcome updates as you answer.</p>}
        {!signed &&
          (item.evaluation?.notes ?? []).map((note) => (
            <p key={note} className="dt-hint">
              {note}
            </p>
          ))}
        {chips.length > 0 && (
          <p className="dt-whys">
            <span className="ac-muted">Why:</span>
            {chips.map((chip) => (
              <a key={chip.id} className="dt-whychip" href={`#q-${chip.id}`}>
                {chip.label}
              </a>
            ))}
          </p>
        )}
      </div>
      {signed && item.current && (
        <p className="dt-signature">
          <b>{item.current.signed_by ?? "A colleague"}</b> · {formatDateTime(item.current.signed_at)} · meaning:{" "}
          {signedMeaning(item.current.conclusion)}
          {item.current.override_reason ? ` · overrode the outcome: ${item.current.override_reason}` : ""}
        </p>
      )}
      {!signed && !canDecide && (
        <p className="ac-muted">Your role reads this tree. A Regulatory Leader or Quality Leader signs it.</p>
      )}
      {!signed && canDecide && (
        <form
          className="dt-sign"
          aria-label={`Sign the ${item.label} conclusion`}
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) void sign();
          }}
        >
          <div className="dt-choice" role="radiogroup" aria-label="Your conclusion">
            <label className="ca-check">
              <input
                type="radio"
                name={`choice-${item.market}`}
                checked={choice === "follow"}
                disabled={!definite}
                onChange={() => setPicked("follow")}
              />
              Follow the outcome
            </label>
            <label className="ca-check">
              <input
                type="radio"
                name={`choice-${item.market}`}
                checked={choice === "override"}
                disabled={!outcome}
                onChange={() => setPicked("override")}
              />
              Override it
              {outcome && choice === "override" && conclusion
                ? ` (${CONCLUSION_LABELS[conclusion].toLowerCase()})`
                : ""}
            </label>
          </div>
          {choice === "override" && outcome && (
            <input
              className="dt-input"
              aria-label="Your reason for overriding the outcome"
              placeholder="Your reason for overriding (required)"
              value={overrideReason}
              onChange={(event) => setOverrideReason(event.target.value)}
            />
          )}
          <ul className="dt-check" id={`dt-check-${item.market}`} aria-label="Before you sign">
            {items.map((entry) => (
              <li key={entry.text} className={entry.ok ? "is-ok" : ""}>
                <span aria-hidden="true">{entry.ok ? "✓" : "○"}</span> {entry.text}
              </li>
            ))}
          </ul>
          <label className="dt-harm">
            <span>Harm level</span>
            <select value={harm.level} onChange={(event) => onHarm({ ...harm, level: event.target.value })}>
              <option value="">Choose</option>
              {levels.map((level) => (
                <option key={level.code} value={level.code}>
                  {level.label}
                </option>
              ))}
            </select>
            {fromMapping && harm.level === fromMapping && detail.severity_source && (
              <small>{`From ${detail.severity_source.replace(/^The /, "the ").replace(/^Your /, "your ")}`}</small>
            )}
          </label>
          {fromMapping && harm.level && harm.level !== fromMapping && (
            <input
              className="dt-input"
              aria-label="Why this harm level"
              placeholder="Why this level (it differs from the record)"
              value={harm.reason}
              onChange={(event) => onHarm({ ...harm, reason: event.target.value })}
            />
          )}
          {item.disagreement && (
            <input
              className="dt-input"
              aria-label="Why the answers differ from the harm level"
              placeholder={`${item.disagreement}: say why`}
              value={harm.disagreement}
              onChange={(event) => onHarm({ ...harm, disagreement: event.target.value })}
            />
          )}
          <div className="dt-creds">
            <input
              type="password"
              aria-label="Your password"
              placeholder="Your password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <input
              inputMode="numeric"
              aria-label="Authenticator code"
              placeholder="Authenticator code"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </div>
          {missing.length > 0 && (
            <label className="ca-check dt-trained">
              <input type="checkbox" checked={trained} onChange={(event) => setTrained(event.target.checked)} />I have
              read this version of the questions and the harm scale (training record, ISO 13485 6.2)
            </label>
          )}
          <button
            type="submit"
            className="ac-primary dt-sign-btn"
            disabled={!ready}
            aria-describedby={`dt-check-${item.market}`}
          >
            <PenLine size={15} aria-hidden="true" />{" "}
            {busy ? "Signing…" : `Sign as ${session?.display_name ?? "yourself"}`}
          </button>
          {/* The tree's head names its version already (0.10.84: fewer words beside Sign). */}
          <p className="dt-hint">
            {tree?.tests.passed ?? 0} of {tree?.tests.total ?? 0} worked complaints pass
          </p>
          <InlineError text={error} />
        </form>
      )}
    </section>
  );
}

/** "Form FDA 3500A worksheet (eMDR)" -> "Form FDA 3500A (eMDR)": the form's name as people say it. */
export const formName = (title: string) => title.replace(" worksheet", "");

/**
 * The form for the incident's country (0.10.83, D2.5): a reportable outcome names the form signing creates (US 3500A,
 * India MDAE, EU/NI MIR, GB MHRA MIR, the Health Canada report), then opens it. Where another market's reporting may
 * also apply to an incident outside it, an advice-only flag: it creates no second report.
 */
export function FormCard({
  item,
  tree,
  trees,
  outcome,
  signed,
  path,
  enabled,
}: {
  item: MarketItem;
  tree: TreeMarket | null;
  trees: TreeMarket[];
  outcome: Suggestion | null;
  signed: boolean;
  path: TreePath | null;
  enabled: string[];
}) {
  const { open } = useWorkspace();
  if (!tree?.form || !outcome) return null;
  const incident = item.preselected;
  const others = incident
    ? trees.filter((other) => other.market !== item.market && enabled.includes(other.market))
    : [];
  const report = signed ? path?.report : null;
  return (
    <section className="uw-card uw-card-pad dt-form" aria-label="The form">
      <h2>{incident ? "The form for this incident's country" : "The form for this market"}</h2>
      {outcome === "NOT_REPORTABLE" ? (
        <p className="ac-muted">No report for {item.label}.</p>
      ) : (
        <>
          <p className="dt-form-name">
            <b>{formName(tree.form.title)}</b>
            {tree.form.starter && <span className="dt-tag">{STARTER_LABEL}</span>}
          </p>
          {report ? (
            <button
              type="button"
              className="ac-primary"
              onClick={() => {
                const place = reportPlace(report.id);
                open(place.section, place.tab);
              }}
            >
              Open the report <ChevronRight size={15} aria-hidden="true" />
            </button>
          ) : (
            <p className="ac-muted">
              {signed
                ? "Record where and when you reported on the signed conclusion."
                : "Created when you sign reportable, with the fields your records already hold."}
            </p>
          )}
          {outcome === "REPORTABLE" && others.length > 0 && (
            <div className="dt-flag" role="note">
              <b>May also apply</b>
              {others.map((other) => (
                <span key={other.market}>{other.foreign}</span>
              ))}
              <span className="dt-tag">{STARTER_LABEL} · no second report is created</span>
            </div>
          )}
        </>
      )}
    </section>
  );
}
