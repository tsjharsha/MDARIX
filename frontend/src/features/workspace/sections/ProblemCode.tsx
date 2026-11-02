import { useResource } from "../../customer-admin/shared";
import { imdrfText } from "./ImportReports";

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

/** "IMDRF A0601 Loss of signal": the IMDRF terms a problem code maps to, or null when none is approved yet. */
export function imdrfTermText(code: string | null | undefined, links: ImdrfLinks): string | null {
  const found = (code && links[code]) || [];
  return found.length ? `IMDRF ${found.map(imdrfText).join("; ")}` : null;
}

/** The customer's problem code as recorded, with its IMDRF term beside it (0.10.68). */
export function ProblemCode({ code, links }: { code: string | null | undefined; links: ImdrfLinks }) {
  if (!code) return null;
  const term = imdrfTermText(code, links);
  return (
    <span className="uw-problem-code">
      <code>{code}</code>
      {term && <small> · {term}</small>}
    </span>
  );
}
