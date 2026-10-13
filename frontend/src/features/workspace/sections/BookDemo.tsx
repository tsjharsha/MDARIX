import { useState, type FormEvent } from "react";
import { CalendarCheck, CheckCircle2 } from "lucide-react";
import { Drawer, errorText, send, useResource } from "../../customer-admin/shared";
import { formatDay } from "../../../app/dates";
import { CHAPTER_SHORT, type StoryChapter } from "../trialStory";

export type TrialDemoRequest = {
  id: string;
  business_id: string | null;
  status: string;
  created_at: string | null;
  preferred_time: string | null;
};

export const DEMO_REQUEST_PATH = "/api/v1/trial/demo-request";

/** What the trial's demo request says to the person: none yet, asked for, or followed up. */
export function demoRequestText(request: TrialDemoRequest | null | undefined): string | null {
  if (!request) return null;
  const on = request.created_at ? ` on ${formatDay(request.created_at)}` : "";
  if (request.status === "NEW")
    return `You asked for a one-to-one demo${on}. The MDARIX team will contact you to agree a time.`;
  if (request.status === "CONTACTED") return `The MDARIX team has been in touch about your demo (asked${on}).`;
  return null;
}

/**
 * Book a one-to-one demo from inside the trial: the button opens a short form (times that suit, an optional phone
 * number, the chapters to focus on, a note). The request reaches the MDARIX team with the trial's progress through the
 * story (POST /api/v1/trial/demo-request). Once asked, the button says so instead.
 */
export function BookDemo({
  chapters,
  variant = "secondary",
  onBooked,
}: {
  chapters: readonly StoryChapter[];
  variant?: "primary" | "secondary";
  /** Told when a request was sent, so other views of it (the trial journey) read it again. */
  onBooked?: () => void;
}) {
  const state = useResource<{ request: TrialDemoRequest | null }>(DEMO_REQUEST_PATH);
  const [open, setOpen] = useState(false);
  const request = state.data?.request ?? null;
  const pending = request?.status === "NEW";
  return (
    <>
      <button
        type="button"
        className={variant === "primary" ? "ac-primary" : "ac-secondary"}
        onClick={() => setOpen(true)}
        disabled={pending}
        title={pending ? (demoRequestText(request) ?? undefined) : undefined}
      >
        {pending ? <CheckCircle2 size={15} aria-hidden="true" /> : <CalendarCheck size={15} aria-hidden="true" />}{" "}
        {pending ? "Demo requested" : "Book a one-to-one demo"}
      </button>
      {open && (
        <DemoForm
          chapters={chapters}
          onClose={() => setOpen(false)}
          onBooked={() => {
            state.reload();
            onBooked?.();
          }}
        />
      )}
    </>
  );
}

function DemoForm({
  chapters,
  onClose,
  onBooked,
}: {
  chapters: readonly StoryChapter[];
  onClose: () => void;
  onBooked: () => void;
}) {
  const [preferredTime, setPreferredTime] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [focus, setFocus] = useState<string[]>(() =>
    chapters
      .filter((chapter) => !chapter.acted.done)
      .slice(0, 2)
      .map((chapter) => chapter.code),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const toggle = (code: string) =>
    setFocus((chosen) => (chosen.includes(code) ? chosen.filter((item) => item !== code) : [...chosen, code]));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const answer = await send<{ status: string; request: TrialDemoRequest }>(DEMO_REQUEST_PATH, "POST", {
        preferred_time: preferredTime.trim() || null,
        phone: phone.trim() || null,
        focus,
        note: note.trim() || null,
      });
      setDone(
        answer.status === "ALREADY_REQUESTED"
          ? (demoRequestText(answer.request) ?? "You already asked for a demo.")
          : "Thank you. The MDARIX team will contact you to agree a time, and the demo will start from your own trial.",
      );
      onBooked();
    } catch (failure) {
      setError(errorText(failure, "Your demo request was not sent. Please try again."));
    } finally {
      setBusy(false);
    }
  };
  if (done)
    return (
      <Drawer title="One-to-one demo" onClose={onClose}>
        <section className="ca-drawer-section" role="status">
          <h3>
            <CheckCircle2 size={18} aria-hidden="true" /> Demo requested
          </h3>
          <p>{done}</p>
          <button type="button" className="ac-primary" onClick={onClose}>
            Back to your trial
          </button>
        </section>
      </Drawer>
    );
  return (
    <Drawer title="Book a one-to-one demo" onClose={onClose}>
      <form className="ca-form" onSubmit={submit}>
        <section className="ca-drawer-section">
          <p>
            A one-to-one session with the MDARIX team on your own trial: what the quality loop found in your records,
            how a pilot on your live data would run, and your questions.
          </p>
          <label className="ca-field">
            Times that suit you
            <input
              value={preferredTime}
              maxLength={200}
              placeholder="For example: Tuesday or Wednesday afternoon, IST"
              onChange={(event) => setPreferredTime(event.target.value)}
            />
          </label>
          <label className="ca-field">
            Phone (optional)
            <input
              value={phone}
              maxLength={30}
              inputMode="tel"
              placeholder="+91 98450 12345"
              onChange={(event) => setPhone(event.target.value)}
            />
          </label>
          <fieldset className="uw-demo-focus">
            <legend>What should we focus on?</legend>
            {chapters.map((chapter) => (
              <label key={chapter.code} className="ca-check">
                <input type="checkbox" checked={focus.includes(chapter.code)} onChange={() => toggle(chapter.code)} />{" "}
                {CHAPTER_SHORT[chapter.code] ?? chapter.title}
              </label>
            ))}
          </fieldset>
          <label className="ca-field">
            Anything else (optional)
            <textarea
              value={note}
              maxLength={1000}
              rows={3}
              placeholder="For example: a notified body audit is coming up in March."
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          {error && (
            <p className="uw-flag-critical" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy}>
              <CalendarCheck size={15} aria-hidden="true" /> {busy ? "Sending…" : "Request the demo"}
            </button>
            <button type="button" className="ac-secondary" onClick={onClose} disabled={busy}>
              Cancel
            </button>
          </div>
          <p className="ac-muted">
            Your name and email come from your account. Nothing is booked until we agree a time.
          </p>
        </section>
      </form>
    </Drawer>
  );
}
