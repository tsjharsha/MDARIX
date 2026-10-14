/**
 * "Start with:" sentence starters under a reason field (workspace/starters.ts): one click puts the start of a sentence
 * in the field, to be finished in the person's own words.
 */
export function Starters({ starters, onPick }: { starters: readonly string[]; onPick: (text: string) => void }) {
  if (!starters.length) return null;
  return (
    <div className="uw-starters" role="group" aria-label="Start the reason with">
      <span>Start with:</span>
      {starters.map((starter) => (
        <button key={starter} type="button" className="uw-starter" onClick={() => onPick(starter)}>
          {starter.trim()}…
        </button>
      ))}
    </div>
  );
}
