import { useId, useState } from "react";
import { ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX } from "lucide-react";
import { CHECK_TITLE, TRUST_TONE, trustOf, trustSentence, type TrustSummary } from "../trust";

/**
 * The automatic trust check of one AI result, as a badge that opens its checks. Shown beside every AI result: the
 * case's AI steps, a signal summary, an Ask answer, a second-look explanation. Nothing is shown when there is no
 * check (a rules result that is not an AI result).
 */
export function TrustBadge({ trust: value }: { trust: TrustSummary | unknown }) {
  const trust = trustOf(value);
  const [open, setOpen] = useState(false);
  const panel = useId();
  if (!trust) return null;
  const tone = TRUST_TONE[trust.status];
  const Icon =
    trust.status === "PASS"
      ? ShieldCheck
      : trust.status === "BLOCKED"
        ? ShieldX
        : trust.status === "NOT_CHECKED"
          ? ShieldQuestion
          : ShieldAlert;
  const checks = trust.checks ?? [];
  return (
    <span className="uw-trust">
      <button
        type="button"
        className={`ac-badge tone-${tone} uw-trust-badge`}
        aria-expanded={open}
        aria-controls={panel}
        aria-label={`${trustSentence(trust).replace(/[.\s]+$/, "")}. Show the checks`}
        onClick={() => setOpen((shown) => !shown)}
      >
        <Icon size={14} aria-hidden="true" />
        {trust.label}
      </button>
      {open && (
        <span id={panel} className="uw-trust-panel" role="note">
          {trust.status === "BLOCKED" && (
            <strong className="uw-flag-critical">
              Do not rely on this result: a check failed. Review it against the records before using any of it.
            </strong>
          )}
          {checks.length > 0 && (
            <span className="uw-trust-checks">
              {checks.map((check) => (
                <span key={check.check} className={`uw-trust-check is-${check.status.toLowerCase()}`}>
                  <b>{CHECK_TITLE[check.check] ?? check.check}</b>
                  <span>{check.message}</span>
                </span>
              ))}
            </span>
          )}
          {(trust.limitations ?? []).map((text) => (
            <small key={text}>{text}</small>
          ))}
          {trust.policy && <small className="ac-muted">Policy {trust.policy}</small>}
        </span>
      )}
    </span>
  );
}
