/** W1c: the Investigation Brief as one page a Quality or Regulatory leader reads (and prints). Every part is built from
 * what is recorded: the brief version's stored content and narrative, the decision summary read (round 3) and the
 * case's lot impact read. A part with no record has no lines, and the page says "Not recorded"; nothing is guessed. */
import { safeText } from "../../app/displayId";
import { formatDay } from "../../app/dates";
import { actionsOf, forAndAgainst, type BriefVersion } from "./decisionBrief";
import { NOT_RECORDED, headline, mfaText, type DecisionSummary } from "./decisionSummary";
import type { LotImpactView } from "./lotImpact";

export const VERSION_NOT_KNOWN = "Version not known (unverified)";

export type BriefPagePart = { key: string; title: string; lines: string[] };

const rec = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
const rows = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.map(rec).filter((item) => Object.keys(item).length > 0) : [];
const text = (value: unknown) => safeText(value) ?? null;
const joined = (...parts: Array<string | null | undefined>) => parts.filter(Boolean).join(" · ");
const day = (value: string | null | undefined) => (value ? formatDay(value, NOT_RECORDED) : NOT_RECORDED);

function hypothesisLine(row: Record<string, unknown>, lead: boolean): string {
  const statement = text(row.statement) ?? NOT_RECORDED;
  const status = text(row.human_status_label) ?? "not judged by a person yet";
  // The AI proposals keep their review label ("AI proposal, not reviewed").
  const kind = text(row.origin) === "AI" ? (text(row.kind_label) ?? "AI proposal") : null;
  const counts = `${Number(row.supporting_count ?? 0)} for, ${Number(row.contradicting_count ?? 0)} against`;
  return joined(`${lead ? "Leading: " : ""}${text(row.business_id) ?? "—"}: ${statement}`, status, kind, counts);
}

/** The page's parts, in reading order. */
export function briefPage(
  version: BriefVersion,
  summary: DecisionSummary | null | undefined,
  lotImpact: LotImpactView | null | undefined,
): BriefPagePart[] {
  const content = rec(version.content);
  const narrative = version.narrative ?? {};
  const scope = rec(content.scope);
  const product = rec(content.product);

  // The product and its exact version: only versions the scope records; never one guessed from the lots.
  const versions = [...rows(scope.product_versions), ...(scope.product_versions ? [] : rows(product.versions))]
    .map((item) => text(item.version_identifier))
    .filter((item): item is string => !!item);
  const unknownVersions = Number(scope.unknown_version_count ?? 0);
  const productLines = text(product.name)
    ? [
        `${text(product.name)}: ${versions.length ? versions.join(", ") : VERSION_NOT_KNOWN}`,
        ...(versions.length && unknownVersions > 0
          ? [`${unknownVersions} ${unknownVersions === 1 ? "complaint" : "complaints"} in scope: ${VERSION_NOT_KNOWN}`]
          : []),
      ]
    : [];

  // Components and supplier: the factors the case's own lots share (lot genealogy), the one a person chose marked.
  const saved = lotImpact?.saved?.factor;
  const factors = (lotImpact?.options ?? [])
    .filter((item) => item.kind !== "PRODUCT_VERSION" && item.case_lots > 0)
    .map((item) => {
      const chosen = saved && saved.kind === item.kind && saved.id === item.id && (saved.lot ?? null) === item.lot;
      return `${item.kind_label}: ${item.label}${chosen ? " (chosen as the suspect factor)" : ""}`;
    });
  const lots = rows(scope.lots).map(
    (item) => `Lot ${text(item.lot_number) ?? "—"} (${text(item.version_identifier) ?? VERSION_NOT_KNOWN})`,
  );

  const { supporting, contradicting } = forAndAgainst(content);
  const evidence = (items: typeof supporting) => items.map((line) => joined(line.label, line.detail));

  const leading = rec(content.leading_hypothesis);
  const hypotheses = [
    ...(Object.keys(leading).length ? [hypothesisLine(leading, true)] : []),
    ...rows(content.alternative_hypotheses).map((row) => hypothesisLine(row, false)),
  ];

  const unknowns = rec(content.unknowns);
  const unknownLines = [
    ...rows(unknowns.open).map((row) =>
      joined(
        `${text(row.business_id) ?? "—"}: ${text(row.description) ?? NOT_RECORDED}`,
        text(row.evidence_needed) ? `needs ${text(row.evidence_needed)}` : null,
      ),
    ),
    ...rows(unknowns.accepted_limitations).map((row) =>
      joined(`Accepted limitation: ${text(row.description) ?? NOT_RECORDED}`, text(row.resolution)),
    ),
    ...(Array.isArray(content.unavailable) && content.unavailable.length
      ? [`Not read when the brief was composed: ${content.unavailable.join(", ")}`]
      : []),
  ];

  const riskReview = rec(content.risk_review);
  const review = rec(riskReview.review);
  const risks = summary?.affects?.risks ?? summary?.risks ?? [];
  const riskLines = [
    ...(Object.keys(review).length
      ? [
          joined(
            `Risk review ${text(review.business_id) ?? ""}`.trim(),
            text(review.outcome),
            text(review.rationale),
            text(review.reviewer_name) ? `by ${text(review.reviewer_name)}` : null,
          ),
        ]
      : text(riskReview.text)
        ? [`Risk review: ${text(riskReview.text)}`]
        : []),
    ...risks.map((risk) => joined(`Risk file ${risk.ref}: ${risk.description}`, risk.status)),
  ];

  const conclusion = text(narrative.proposed_conclusion);
  const actionLines = [
    ...(conclusion ? [`Proposed conclusion: ${conclusion}`] : []),
    ...actionsOf(narrative.recommended_actions),
  ];

  const decision = summary?.decision;
  const signature = summary?.signature;
  const decisionLines = decision
    ? [
        headline(decision),
        signature?.signed_at
          ? joined(
              `Signed by ${signature.name ?? NOT_RECORDED}${signature.role_label ? ` (${signature.role_label})` : ""} on ${day(signature.signed_at)}`,
              mfaText(signature.mfa_verified),
            )
          : "Not signed",
      ]
    : [
        "No decision signed yet",
        joined(
          `Brief ${text(version.business_id) ?? ""} version ${version.version}`.replace("  ", " ") +
            `: ${text(version.status_label) ?? NOT_RECORDED}`,
          version.reviewed_at
            ? `reviewed by ${text(version.reviewed_by_name) ?? NOT_RECORDED} on ${day(version.reviewed_at)}`
            : null,
        ),
      ];

  const effectiveness = (summary?.capas ?? [])
    .filter((capa) => capa.check)
    .map((capa) =>
      joined(
        `${capa.ref}: ${capa.check?.criteria ?? "criteria not recorded"}`,
        `check planned for ${day(capa.check?.planned_on)}`,
        capa.check?.result_summary,
      ),
    );
  if (effectiveness.length && summary?.worked?.text) effectiveness.push(summary.worked.text);

  return [
    {
      key: "problem",
      title: "Problem statement",
      lines: text(narrative.problem_statement) ? [text(narrative.problem_statement)!] : [],
    },
    { key: "product", title: "Product and exact version", lines: productLines },
    {
      key: "affected",
      title: "Affected components, supplier and lots",
      lines: factors.length || lots.length ? [...factors, ...(lots.length ? lots : ["Lots: " + NOT_RECORDED])] : [],
    },
    { key: "for", title: "Evidence for", lines: evidence(supporting) },
    { key: "against", title: "Evidence against", lines: evidence(contradicting) },
    { key: "hypotheses", title: "Competing hypotheses and their status", lines: hypotheses },
    { key: "unknowns", title: "Unknowns and limitations", lines: unknownLines },
    { key: "risk", title: "Risk implications", lines: riskLines },
    { key: "action", title: "Recommended action", lines: actionLines },
    { key: "decision", title: "Decision and approval", lines: decisionLines },
    { key: "effectiveness", title: "Effectiveness criteria for the follow-up", lines: effectiveness },
  ];
}
