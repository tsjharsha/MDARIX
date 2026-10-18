import { BASIS_DISCLAIMER, SIGNATURE_BASIS, basisOf } from "./standards";

/**
 * A finding's or a window's regulatory basis as small chips, each with its title on hover (the catalog in
 * standards.ts). Spans, so it can sit inside a button. Nothing is shown when no basis is known.
 */
export function BasisChips({ ids, label = "Basis" }: { ids: readonly string[] | null | undefined; label?: string }) {
  const basis = basisOf(ids);
  if (!basis.length) return null;
  return (
    <span className="uw-basis" role="list" aria-label={label}>
      {basis.map((standard) => (
        <span key={standard.id} role="listitem" className="uw-basis-chip" title={standard.title}>
          {standard.short}
        </span>
      ))}
    </span>
  );
}

/** A short line naming the basis of a whole screen (Basis: ISO 13485 8.4, EU MDR Art. 88 as chips), with the disclaimer. */
export function BasisLine({ ids }: { ids: readonly string[] }) {
  const basis = basisOf(ids);
  if (!basis.length) return null;
  return (
    <p className="ac-note uw-basis-line">
      Basis: <BasisChips ids={ids} /> {BASIS_DISCLAIMER}
    </p>
  );
}

/** The disclaimer every page that shows a basis carries once. */
export function BasisNote() {
  return <p className="ac-note uw-basis-note">{BASIS_DISCLAIMER}</p>;
}

/** Under a signed record: what the signature keeps, in the words of 21 CFR 11.50 and 11.70, with the disclaimer. */
export function SignatureBasis() {
  return (
    <p className="ac-note uw-basis-note">
      {SIGNATURE_BASIS} {BASIS_DISCLAIMER}
    </p>
  );
}
