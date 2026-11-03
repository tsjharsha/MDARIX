import { useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { useResource } from "../../customer-admin/shared";

/** One IMDRF code as the picker shows it (GET /api/v1/regulatory-reference/imdrf/codes?pick=1, 0.10.77). */
export type PickedCode = {
  code: string;
  term: string;
  definition: string | null;
  status: string | null;
  selectable: boolean;
  children: number;
  fda: { code: string; term: string } | null;
};

type PickList = { release: string | null; annex?: string; fda_version: string | null; codes: PickedCode[] };

export const ANNEX_TITLES: Record<string, string> = {
  A: "Annex A · Medical device problem",
  B: "Annex B · Type of investigation",
  C: "Annex C · Investigation findings",
  D: "Annex D · Investigation conclusion",
  E: "Annex E · Clinical signs, symptoms and conditions",
  F: "Annex F · Health impact",
  G: "Annex G · Medical device component",
};

/** The picker's address: a word search, or the annex tree under ``parent`` (the top headings without one). */
export function pickPath(annex: string, words: string, parent: string | null): string {
  const query = new URLSearchParams({ pick: "1", annex });
  if (words.trim()) query.set("q", words.trim());
  else if (parent) query.set("parent", parent);
  return `/api/v1/regulatory-reference/imdrf/codes?${query}`;
}

/**
 * The code picker (0.10.77, C5): search an IMDRF annex by word, or browse its tree heading by heading; each code shows
 * its definition and, where FDA's published mapping has one, its FDA code (one choice fills both on the FDA's form).
 * Retired codes are not offered; a heading IMDRF marks "Not selectable" opens but cannot be chosen.
 */
export function CodePicker({
  annex,
  label,
  busy,
  onChoose,
  onCancel,
}: {
  annex: string;
  label: string;
  busy?: boolean;
  onChoose: (code: PickedCode) => void;
  onCancel: () => void;
}) {
  const [words, setWords] = useState("");
  const [trail, setTrail] = useState<PickedCode[]>([]);
  const parent = trail.length ? trail[trail.length - 1].code : null;
  const list = useResource<PickList>(pickPath(annex, words, parent));
  const codes = list.data?.codes ?? [];
  return (
    <div className="uw-picker" role="group" aria-label={`Choose a code: ${label}`}>
      <div className="uw-picker-head">
        <strong>{ANNEX_TITLES[annex] ?? `Annex ${annex}`}</strong>
        <span className="ac-muted">
          {list.data?.release ? `IMDRF release ${list.data.release}` : "IMDRF codes"}
          {list.data?.fda_version ? ` · FDA codes ${list.data.fda_version}` : ""}
        </span>
      </div>
      <label className="uw-picker-search">
        <Search size={15} aria-hidden="true" />
        <input
          type="search"
          placeholder="Search by word, for example alarm or reading"
          aria-label="Search the codes by word"
          value={words}
          onChange={(event) => setWords(event.target.value)}
        />
      </label>
      {!words.trim() && (
        <nav className="uw-picker-trail" aria-label="Where you are in the annex">
          <button type="button" className="ac-link" onClick={() => setTrail([])}>
            All headings
          </button>
          {trail.map((item, index) => (
            <span key={item.code}>
              <span aria-hidden="true"> › </span>
              <button type="button" className="ac-link" onClick={() => setTrail(trail.slice(0, index + 1))}>
                {item.code} {item.term}
              </button>
            </span>
          ))}
        </nav>
      )}
      <ul className="uw-picker-list">
        {codes.map((item) => (
          <li key={item.code}>
            <div className="uw-picker-code">
              <span className="uw-mono">{item.code}</span> <strong>{item.term}</strong>
              {item.fda && <span className="ms-chip">FDA {item.fda.code}</span>}
              {item.definition && <p className="ac-muted">{item.definition}</p>}
            </div>
            <div className="uw-picker-actions">
              {item.children > 0 && (
                <button
                  type="button"
                  className="ac-link"
                  onClick={() => {
                    setWords("");
                    setTrail(words.trim() ? [item] : [...trail, item]);
                  }}
                >
                  {item.children} under it <ChevronRight size={14} aria-hidden="true" />
                </button>
              )}
              {item.selectable ? (
                <button type="button" className="ac-secondary" disabled={busy} onClick={() => onChoose(item)}>
                  Choose
                </button>
              ) : (
                <span className="ac-muted">Heading: choose a code under it</span>
              )}
            </div>
          </li>
        ))}
      </ul>
      {list.state !== "loading" && !codes.length && (
        <p className="ac-muted">
          {list.data?.release ? "No code matches. Try another word." : "No IMDRF release is loaded yet."}
        </p>
      )}
      <div className="ca-action-row">
        <button type="button" className="ac-link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
