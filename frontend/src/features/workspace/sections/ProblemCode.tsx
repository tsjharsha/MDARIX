import { useResource } from "../../customer-admin/shared";

type ImdrfLink = { release: string; annex: string; code: string; term: string | null };
export type ImdrfLinks = Record<string, ImdrfLink[]>;

/**
 * The approved IMDRF links of a page's problem codes, read once for the whole list (GET
 * /api/v1/regulatory-reference/imdrf/links): the customer's code stays as recorded; the IMDRF term is shown beside it.
 */
export function useImdrfLinks(codes: readonly (string | null | undefined)[]): ImdrfLinks {
  const wanted = [...new Set(codes.filter((code): code is string => !!code))].sort();
  const links = useResource<{ links: ImdrfLinks }>(
    wanted.length
      ? `/api/v1/regulatory-reference/imdrf/links?${new URLSearchParams(wanted.map((code) => ["code", code]))}`
      : null,
  );
  return links.data?.links ?? {};
}

/**
 * A problem code as a person reads it (0.10.70): the IMDRF term is the label, and the customer's own code, never
 * altered, is the small "your code" detail. `{ term: "Infusion or Flow Problem; Protective Measures Problem",
 * imdrf: "A14, A16", code }`; without an approved link the term is null and the code is all there is.
 */
export function problemCodeParts(
  code: string,
  links: ImdrfLinks,
): { term: string | null; imdrf: string; code: string } {
  const found = links[code] ?? [];
  return {
    term: found.length ? found.map((link) => link.term ?? link.code).join("; ") : null,
    imdrf: found.map((link) => link.code).join(", "),
    code,
  };
}

/** The same in one line, for a choice in a list: "Protective Measures Problem (IMDRF A16) · your code PRESSURE_ALARM". */
export function problemCodeText(code: string, links: ImdrfLinks): string {
  const parts = problemCodeParts(code, links);
  return parts.term ? `${parts.term} (IMDRF ${parts.imdrf}) · your code ${code}` : code;
}

/** A problem code: its IMDRF term first, the customer's own code as the small "your code" detail. */
export function ProblemCode({
  code,
  links,
  loaded = false,
}: {
  code: string | null | undefined;
  links: ImdrfLinks;
  /** The links are read: an unmapped code then says so. */
  loaded?: boolean;
}) {
  if (!code) return null;
  const parts = problemCodeParts(code, links);
  if (!parts.term)
    return (
      <span className="uw-problem-code">
        <code>{code}</code>
        <small> · your code{loaded ? "; no IMDRF term mapped yet" : ""}</small>
      </span>
    );
  return (
    <span className="uw-problem-code">
      <span title={`IMDRF ${parts.imdrf}`}>{parts.term}</span>
      <small>
        {" "}
        · IMDRF {parts.imdrf} · your code <code>{code}</code>
      </small>
    </span>
  );
}

/** One problem code that reads its own links (a drawer, a card). */
export function ProblemCodeOf({ code }: { code: string | null | undefined }) {
  const links = useResource<{ links: ImdrfLinks }>(
    code ? `/api/v1/regulatory-reference/imdrf/links?${new URLSearchParams({ code })}` : null,
  );
  return <ProblemCode code={code} links={links.data?.links ?? {}} loaded={!!links.data} />;
}
