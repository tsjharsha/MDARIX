// The regulatory basis MDARIX cites, from one catalog: the web app's mirror of backend/app/standards.py (the data is in
// standards.json; tests/test_standards_unit.py keeps the two identical). Screens show a basis as chips with the
// disclaimer once per page; references elsewhere (the sample story, the trial's citation themes) are built from it.
import catalog from "./standards.json";

/** The one wording of the starter mark, on starter content only (0.10.83, D2.9; usability U-11). */
export const STARTER_LABEL = "Starter, for your consultant to confirm";

/** A question set or guide version that is MDARIX's starter ("US-starter-1"), not the organization's approved one. */
export const isStarterVersion = (code: string | null | undefined) => /starter/i.test(code ?? "");

/** ``starter``: the wording awaits the regulatory consultant's confirmation (shown with ``STARTER_LABEL``). */
export type Standard = { id: string; short: string; title: string; jurisdiction: string; starter?: boolean };

export const STANDARDS: readonly Standard[] = catalog.standards;

/** Carried once by every page that shows a basis (never once per chip). */
export const BASIS_DISCLAIMER: string = catalog.disclaimer;

const BY_ID: ReadonlyMap<string, Standard> = new Map(STANDARDS.map((standard) => [standard.id, standard]));

export const standardOf = (id: string): Standard | undefined => BY_ID.get(id);

/** The catalog entries of ``ids``, once each, in their order; an id outside the catalog is left out. */
export function basisOf(ids: readonly string[] | null | undefined): Standard[] {
  const found: Standard[] = [];
  for (const id of ids ?? []) {
    const standard = BY_ID.get(id);
    if (standard && !found.includes(standard)) found.push(standard);
  }
  return found;
}

/** One reference line: catalog ids by their short form, any other part (no catalog entry) as written. */
export const cite = (...parts: string[]) => parts.map((part) => BY_ID.get(part)?.short ?? part).join("; ");

/**
 * What every signed record keeps, in the words of 21 CFR 11.50 and 11.70: the time of signing, the meaning and the
 * exact record signed (its id, version and content fingerprint). The signer is kept by their account, and their name
 * is read from the user directory when the record is shown, so the name is not claimed here.
 */
export const SIGNATURE_BASIS =
  "Records, as 21 CFR 11.50 and 11.70 call for, the date and time of signing, its meaning, and a link to the exact record signed.";
