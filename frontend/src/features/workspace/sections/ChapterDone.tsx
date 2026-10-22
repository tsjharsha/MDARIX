import { useEffect, useRef, useState } from "react";
import { CheckCircle2, ChevronRight, X } from "lucide-react";
import { requestJson } from "../../../app/apiClient";
import { TRIAL_PROGRESS_PATH, type StoryChapter, type TrialStory } from "../trialStory";

const POLL_MS = 30_000;

/** Whether the page is out of sight (another tab, a minimised window): the half-minute read then waits. */
export const pageHidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";

/** The chapters newly tried since ``before`` (codes), in story order. */
export function newlyTried(before: readonly string[] | null, story: TrialStory | null): StoryChapter[] {
  if (!before || !story) return [];
  return story.chapters.filter((chapter) => chapter.acted.done && !before.includes(chapter.code));
}

/**
 * "Chapter 2 done. Next: Turn a rising trend into a case": shown anywhere in a trial's workspace as soon as the
 * organization acts in a chapter, with a button that opens the next one, so nobody has to find their way back to
 * Getting started. The story is read when the screen changes and every half minute while the page is in sight, and
 * once more when it comes back into sight; nothing shows on first load. It reads which chapters were tried only
 * (TRIAL_PROGRESS_PATH), not what the records show in each: that is Getting started's own, much larger read.
 */
export function ChapterDone({ refreshKey, onOpen }: { refreshKey: number; onOpen: (chapter: StoryChapter) => void }) {
  const known = useRef<string[] | null>(null);
  const [done, setDone] = useState<{ chapter: StoryChapter; next: StoryChapter | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    const read = () =>
      // A background read: the poll must not keep an untouched page signed in past the idle timeout.
      requestJson<TrialStory>(TRIAL_PROGRESS_PATH, { background: true })
        .then((story) => {
          if (cancelled) return;
          const fresh = newlyTried(known.current, story);
          known.current = story.chapters.filter((chapter) => chapter.acted.done).map((chapter) => chapter.code);
          if (fresh.length) {
            const next = story.chapters.find((chapter) => chapter.code === story.next) ?? null;
            setDone({ chapter: fresh[fresh.length - 1], next });
          }
        })
        .catch(() => undefined);
    void read();
    const timer = window.setInterval(() => {
      if (!pageHidden()) void read();
    }, POLL_MS);
    const shown = () => {
      if (!pageHidden()) void read();
    };
    document.addEventListener("visibilitychange", shown);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", shown);
    };
  }, [refreshKey]);

  if (!done) return null;
  return (
    <div className="ac-message tone-good uw-chapter-done" role="status">
      <CheckCircle2 size={16} aria-hidden="true" />
      <span>
        <b>
          Chapter {done.chapter.number} done: {done.chapter.title}.
        </b>{" "}
        {done.next ? `Next: ${done.next.title}.` : "Every chapter tried: book your one-to-one demo in Getting started."}
      </span>
      {done.next && (
        <button
          type="button"
          className="ac-primary"
          onClick={() => {
            const next = done.next as StoryChapter;
            setDone(null);
            onOpen(next);
          }}
        >
          Continue <ChevronRight size={14} aria-hidden="true" />
        </button>
      )}
      <button type="button" className="ac-link" onClick={() => setDone(null)} aria-label="Dismiss">
        <X size={14} />
      </button>
    </div>
  );
}
