import { BASIS_DISCLAIMER, SIGNATURE_BASIS, STARTER_LABEL, basisOf } from "./standards";

/** The starter mark: once per page that shows MDARIX's default rules, never a chip per question or item (G-17). */
export function StarterNote() {
  return (
    <p className="ac-note uw-starter-note" role="note">
      {STARTER_LABEL}
    </p>
  );
}

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

/**
 * "Why am I asked?" (stage 8, 8.2): one line under a question or a step, its reason and the clause it answers to
 * (features/workspace/whyAsked.ts; a market's question passes its guide's locked clause).
 */
export function WhyAsked({
  why,
  clause,
}: {
  why: { why: string; basis: readonly string[] } | null | undefined;
  clause?: string | null;
}) {
  if (!why) return null;
  return (
    <small className="uw-why-asked">
      <strong>Why am I asked?</strong> {why.why} {clause && <span className="uw-basis-chip">{clause}</span>}
      <BasisChips ids={why.basis} label="Clause" />
    </small>
  );
}
