/**
 * A question another screen hands to Ask MDARIX (Getting started › Automatic insights, "Ask MDARIX to look further"):
 * the Ask page opens with it in the question box, focused and not sent; the person presses "Ask MDARIX" to run it.
 * It is taken once: coming back to Ask later shows an empty box again, never an old question.
 */
let pending: string | null = null;
const listeners = new Set<(question: string) => void>();

/** Leave a question for Ask MDARIX. An Ask page already on screen takes it at once. */
export function handQuestionToAsk(question: string): void {
  const text = question.trim();
  if (!text) return;
  pending = text;
  listeners.forEach((listener) => listener(text));
}

/** The question waiting for Ask MDARIX, if any (reading does not take it). */
export function pendingQuestion(): string | null {
  return pending;
}

/** Mark the question as taken; a newer one handed over meanwhile stays. */
export function takeQuestion(question: string | null): void {
  if (question !== null && pending === question) pending = null;
}

/** Hear of questions handed over while an Ask page is open; returns the unsubscribe. */
export function onQuestionHanded(listener: (question: string) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
