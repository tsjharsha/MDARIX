import { useEffect, useRef, useState } from "react";
import { CheckCircle2, ChevronRight, Circle, Printer } from "lucide-react";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { highlightParts } from "../complaintReview";
import { FLAGSHIP, SCENARIOS } from "../entrance";
import { eventPath, type EventView } from "../oversight";
import { SHORT_STORY_PATH, SHORT_STORY_SAVED, resumeText, storySaved, type ShortStory } from "../shortStory";
import { requestJson } from "../../../app/apiClient";
import { InlineError } from "./boardParts";
import { PRACTICE_APPROVAL } from "./PracticeApproval";
import { INTAKE } from "../intake";

/** The short story's progress, read again whenever a step is saved anywhere on the page. */
export function useShortStory(enabled = true) {
  const story = useResource<ShortStory>(enabled ? SHORT_STORY_PATH : null);
  const reload = story.reload;
  useEffect(() => {
    window.addEventListener(SHORT_STORY_SAVED, reload);
    return () => window.removeEventListener(SHORT_STORY_SAVED, reload);
  }, [reload]);
  return story;
}

/** Today plus ``days``, as the date input reads it (the person's own calendar). */
const dayAfter = (days: number) => {
  const day = new Date();
  day.setDate(day.getDate() + days);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
};

const HOSPITAL = "Biomedical engineering, the reporting hospital (sample)";
/** The triage severity proposed from the reporter's "No harm was reported": never saved until the person confirms it. */
export const PROPOSED_SEVERITY = "NEGLIGIBLE";

/**
 * The short story on SAMPLE-RV-11 (0.10.71, A4), on the complaint's own page: the step to do now, from what was saved
 * on the record. 1 Read the call, 2 Decide the route, 3 Name the open question, 4 The intake decision summary, whose
 * main button continues into the full evaluation. MDARIX shows what it already knows; the person confirms it.
 */
export function ShortStoryPanel({ view, onChanged }: { view: EventView; onChanged: (view: EventView) => void }) {
  const story = useShortStory();
  const data = story.data;
  if (!data?.available) return null;
  const saved = () => {
    story.reload();
    storySaved();
  };
  return (
    <section className="uw-short" aria-labelledby="short-title">
      <header className="uw-short-head">
        <h2 id="short-title">Should Quality review this too?</h2>
        <ol className="uw-short-steps" aria-label="The short story's steps">
          {data.steps.map((step, index) => (
            <li
              key={step.key}
              className={step.done ? "is-done" : index === data.current ? "is-current" : undefined}
              aria-current={index === data.current ? "step" : undefined}
            >
              {step.done ? <CheckCircle2 size={16} aria-hidden="true" /> : <Circle size={16} aria-hidden="true" />}
              <span>
                {index + 1}. {step.label}
              </span>
              <span className="ca-sr-only">{step.done ? " (done)" : ""}</span>
            </li>
          ))}
        </ol>
      </header>
      {data.current === 0 && <ReadTheCall story={data} onSaved={saved} />}
      {data.current === 1 && <DecideTheRoute story={data} view={view} onChanged={onChanged} onSaved={saved} />}
      {data.current === 2 && <OpenQuestion story={data} view={view} onSaved={saved} />}
      {data.current >= 3 && <IntakeSummary story={data} onSaved={saved} />}
    </section>
  );
}

function useSave(onSaved: () => void, failure: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await work();
      onSaved();
    } catch (reason) {
      setError(errorText(reason, failure));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

/** Step 1: the reporter's words, the phrases that make it a possible complaint marked, the known facts beside them. */
export function ReadTheCall({ story, onSaved }: { story: ShortStory; onSaved: () => void }) {
  const save = useSave(onSaved, "Your reading was not saved.");
  const phrases = story.call.phrases;
  const parts = highlightParts(
    story.call.words,
    phrases.map((item) => item.text),
  );
  return (
    <div className="uw-short-body">
      <div className="uw-short-call">
        <div>
          <h3>Step 1 of 4: read the call</h3>
          <blockquote className="uw-short-words">
            {parts.map((part, index) => (part.match ? <mark key={index}>{part.text}</mark> : part.text))}
          </blockquote>
          <ul className="uw-short-why" aria-label="Why it may be a complaint">
            {phrases.map((item) => (
              <li key={item.text}>
                <mark>{item.text}</mark>: {item.why}
              </li>
            ))}
          </ul>
        </div>
        <dl className="uw-short-facts" aria-label="What the record already holds">
          {story.call.facts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>{fact.label === "Awareness" ? formatDate(fact.value) : fact.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          disabled={save.busy}
          onClick={() => void save.run(() => send(`${SHORT_STORY_PATH}/marks`, "POST", { step: "read" }))}
        >
          Decide the route <ChevronRight size={15} aria-hidden="true" />
        </button>
      </div>
      <InlineError text={save.error} />
    </div>
  );
}

/** Step 2: the route (a complaint, with its linked service work) and an owner for each, prefilled from the record. */
export function DecideTheRoute({
  story,
  view,
  onChanged,
  onSaved,
}: {
  story: ShortStory;
  view: EventView;
  onChanged: (view: EventView) => void;
  onSaved: () => void;
}) {
  const { session } = useWorkspace();
  const me = view.people.some((person) => person.id === session?.user_id) ? (session?.user_id ?? "") : "";
  const [owner, setOwner] = useState(view.event.owner_id ?? me);
  const [serviceOwner, setServiceOwner] = useState(view.service?.owner_id ?? me);
  const [action, setAction] = useState(
    story.route.immediate_action ??
      `Monitor out of use and sent for service${view.service ? `, under ${view.service.reference}` : ""}.`,
  );
  const save = useSave(onSaved, "The route was not saved.");
  // The triage needs a severity: the proposal and its basis are shown, and nothing is saved until the person confirms
  // it or chooses another level (0.10.72, F1: "Confirm the route" saved Negligible silently).
  const guide = useResource<{ levels: Array<{ code: string; label: string }> }>(`${INTAKE}/guide`);
  const [severity, setSeverity] = useState(PROPOSED_SEVERITY);
  const [severityConfirmed, setSeverityConfirmed] = useState(false);
  const levelLabel = (code: string) => guide.data?.levels.find((level) => level.code === code)?.label ?? code;
  const complaint = view.event.complaint_id;
  const confirm = () =>
    save.run(async () => {
      await send(`/api/v1/triage/COMPLAINT/${complaint}/record`, "POST", {
        // The severity the person confirmed or chose here; the market assessments start from it.
        severity,
        event_owner: owner,
        triage_owner: owner,
        immediate_action: action,
      });
      onChanged(
        await send<EventView>(`${eventPath(complaint)}/service`, "PUT", {
          reference: view.service?.reference ?? "Service requested by the hospital",
          status: view.service?.status ?? "OPEN",
          owner_id: serviceOwner,
        }),
      );
    });
  const people = view.people;
  return (
    <div className="uw-short-body">
      <h3>Step 2 of 4: decide the route</h3>
      <dl className="uw-short-route">
        <div>
          <dt>Route</dt>
          <dd>
            <strong>{story.route.decision}</strong>
          </dd>
        </div>
        <div>
          <dt>Because</dt>
          <dd>
            {story.route.source_quote && (
              <>
                <q>{story.route.source_quote}</q>.
              </>
            )}{" "}
            {story.route.source_fact}
          </dd>
        </div>
        <div>
          <dt>The reporter says</dt>
          <dd>
            <q>No harm was reported</q>.
          </dd>
        </div>
        <div>
          <dt>Effect on treatment</dt>
          <dd>Unknown: asked of the hospital in step 3.</dd>
        </div>
      </dl>
      <div className="uw-short-form">
        <label className="ca-field">
          Complaint owner (Quality)
          <select value={owner} onChange={(event) => setOwner(event.target.value)}>
            <option value="">Choose a person</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Service owner
          <select value={serviceOwner} onChange={(event) => setServiceOwner(event.target.value)}>
            <option value="">Choose a person</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field uw-short-wide">
          Immediate action
          <input value={action} onChange={(event) => setAction(event.target.value)} />
        </label>
        <label className="ca-field">
          Triage severity
          <select
            value={severity}
            onChange={(event) => {
              setSeverity(event.target.value);
              setSeverityConfirmed(event.target.value !== "");
            }}
          >
            <option value="">Choose a level</option>
            {(guide.data?.levels ?? [{ code: PROPOSED_SEVERITY, label: "Negligible" }]).map((level) => (
              <option key={level.code} value={level.code}>
                {level.label}
              </option>
            ))}
          </select>
          <small className="ms-reason">
            Proposed: {levelLabel(PROPOSED_SEVERITY)}, from the reporter's statement "No harm was reported". The effect
            on treatment is still unknown; change it if you judge otherwise.
          </small>
        </label>
        <label className="ca-check uw-short-wide">
          <input
            type="checkbox"
            checked={severityConfirmed}
            disabled={!severity}
            onChange={(event) => setSeverityConfirmed(event.target.checked)}
          />
          I confirm the triage severity: {severity ? levelLabel(severity) : "none chosen"}
        </label>
      </div>
      <section className="uw-short-records" aria-label="What Confirm the route records">
        <h4>Confirm the route records</h4>
        <ul>
          <li>
            The triage record of {FLAGSHIP}: severity {severity ? levelLabel(severity).toLowerCase() : "(choose one)"},
            complaint owner {people.find((person) => person.id === owner)?.name ?? "(choose one)"}, immediate action as
            written above.
          </li>
          <li>
            The service work's owner: {people.find((person) => person.id === serviceOwner)?.name ?? "(choose one)"}.
          </li>
        </ul>
      </section>
      <p className="ac-note">
        Service: {view.service ? `${view.service.status_label} · ${view.service.reference}` : "none linked yet"}.
        Completing the service never closes the complaint.
      </p>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          disabled={
            save.busy || !owner || !serviceOwner || action.trim().length < 10 || !severity || !severityConfirmed
          }
          aria-describedby="route-why"
          onClick={() => void confirm()}
        >
          Confirm the route <ChevronRight size={15} aria-hidden="true" />
        </button>
        <small id="route-why" className="ms-reason">
          {!owner || !serviceOwner
            ? "Name both owners first."
            : !severityConfirmed
              ? "Confirm or change the triage severity first."
              : "Saves the triage record and the service owner, as listed above."}
        </small>
      </div>
      <InlineError text={save.error} />
    </div>
  );
}

/** Step 3: the one question that decides the consequence, asked of the hospital with an owner and a reply date. */
export function OpenQuestion({ story, view, onSaved }: { story: ShortStory; view: EventView; onSaved: () => void }) {
  const { session } = useWorkspace();
  const me = view.people.some((person) => person.id === session?.user_id) ? (session?.user_id ?? "") : "";
  const [subject, setSubject] = useState(story.question.suggested);
  const [owner, setOwner] = useState(me);
  const [due, setDue] = useState(dayAfter(2));
  const save = useSave(onSaved, "The question was not recorded.");
  const complaint = view.event.complaint_id;
  const record = () =>
    save.run(async () => {
      // The hospital as a party of this complaint: the one recorded before, else added now.
      const known = await requestJson<{ parties: Array<{ id: string; name: string; complaint_id: string | null }> }>(
        "/api/v1/communications/parties",
      );
      const party =
        known.parties.find((item) => item.complaint_id === complaint && item.name === HOSPITAL) ??
        (await send<{ id: string }>("/api/v1/communications/parties", "POST", {
          type: "HOSPITAL",
          name: HOSPITAL,
          complaint_id: complaint,
        }));
      const asked = await send<{ id: string }>("/api/v1/communications", "POST", {
        complaint_id: complaint,
        party_id: party.id,
        direction: "SENT",
        purpose: "INFORMATION_REQUEST",
        subject,
        channel: "EMAIL",
        occurred_at: new Date().toISOString(),
        owner_id: owner,
        reply_due_on: due,
      });
      // Step 3 is this request, kept with the story: a later, unrelated request never stands for it (0.10.72, F2).
      await send(`${SHORT_STORY_PATH}/marks`, "POST", { step: "question", request_id: asked.id });
    });
  return (
    <div className="uw-short-body">
      <h3>Step 3 of 4: name the open question</h3>
      <p>{story.question.why}</p>
      <div className="uw-short-form">
        <label className="ca-field uw-short-wide">
          The question to the hospital
          <textarea value={subject} rows={2} maxLength={200} onChange={(event) => setSubject(event.target.value)} />
        </label>
        <label className="ca-field">
          Owner
          <select value={owner} onChange={(event) => setOwner(event.target.value)}>
            <option value="">Choose a person</option>
            {view.people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
        </label>
        <label className="ca-field">
          Reply due
          <input type="date" value={due} onChange={(event) => setDue(event.target.value)} />
        </label>
      </div>
      <p className="ac-note">
        Recorded in the communications log as asked of {HOSPITAL}: MDARIX sends nothing. Consequence:{" "}
        {story.question.consequence.toLowerCase()}.
      </p>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          disabled={save.busy || !owner || !due || subject.trim().length < 5}
          onClick={() => void record()}
        >
          Record the question <ChevronRight size={15} aria-hidden="true" />
        </button>
      </div>
      <InlineError text={save.error} />
    </div>
  );
}

/** Step 4: the intake decision summary, the first payoff; printable as PDF; then the full evaluation. */
export function IntakeSummary({ story, onSaved }: { story: ShortStory; onSaved: () => void }) {
  const { open, startStory } = useWorkspace();
  const marked = useRef(false);
  // Seeing the summary is the step's saved action (once the route and the question are recorded).
  useEffect(() => {
    if (story.steps[3]?.done || marked.current) return;
    marked.current = true;
    void send(`${SHORT_STORY_PATH}/marks`, "POST", { step: "summary" }).then(onSaved, () => undefined);
  }, [story.steps]);
  const print = () => {
    document.body.classList.add("uw-print-summary");
    window.print();
    document.body.classList.remove("uw-print-summary");
  };
  const full = SCENARIOS.find((item) => item.key === "reportable")!;
  const asked = story.question.asked;
  const people = story.people;
  return (
    <div className="uw-short-body uw-intake-summary" aria-labelledby="intake-summary-title">
      <h3 id="intake-summary-title">Intake decision summary · {FLAGSHIP}</h3>
      {story.practice_label && <p className="uw-short-practice">{story.practice_label}</p>}
      <dl className="uw-short-summary">
        <div>
          <dt>Route chosen</dt>
          <dd>{story.route.decision}</dd>
        </div>
        <div>
          <dt>The fact it rests on</dt>
          <dd>
            {story.route.source_quote && (
              <>
                <q>{story.route.source_quote}</q>.
              </>
            )}{" "}
            {story.route.source_fact}
          </dd>
        </div>
        <div>
          <dt>Open question</dt>
          <dd>
            {asked
              ? `${asked.subject} Owner: ${asked.owner_name ?? "not named"}; reply due ${formatDate(asked.due_on)}.`
              : "Not asked yet."}{" "}
            Consequence: {story.question.consequence}
            {story.question.consequence.endsWith(".") ? "" : "."}
          </dd>
        </div>
        <div>
          <dt>Service</dt>
          <dd>
            {story.service
              ? `${story.service.status_label} · ${story.service.reference} · owner ${story.service.owner_name ?? "not named"}`
              : "None linked"}
          </dd>
        </div>
        <div>
          <dt>Market assessments ({story.markets.map((row) => row.label.split(" (")[0]).join(", ")})</dt>
          <dd>
            <ul className="uw-short-markets">
              {story.markets.map((row) => (
                <li key={row.market}>
                  <strong>{row.label}:</strong> {row.open ? "still open" : row.state}
                  {row.deadline
                    ? `; ${/provisional/i.test(row.deadline_title ?? "") ? "provisional deadline" : "deadline"} ${row.deadline}`
                    : ""}
                  {row.why ? `. ${row.why}` : ""}
                </li>
              ))}
            </ul>
          </dd>
        </div>
        <div>
          <dt>Who acts next</dt>
          <dd>
            {story.next.who ?? "The complaint owner"}: {story.next.action ?? "nothing is open"}
          </dd>
        </div>
        <div>
          <dt>Prepared by</dt>
          <dd>{people.prepared_by.join(", ") || "Not recorded yet"}</dd>
        </div>
        <div>
          <dt>May approve</dt>
          <dd>{people.may_approve.join(", ") || "Nobody holds the role yet"}</dd>
        </div>
        <div>
          <dt>Approved by</dt>
          <dd>
            {people.approved_by.join(", ") || "Not yet: the market assessments are still open"}
            {people.practice && <span className="uw-practice-approval"> {PRACTICE_APPROVAL}</span>}
          </dd>
        </div>
      </dl>
      <p className="ac-note">
        You decide and sign. MDARIX prepared this from your records; it never decides or submits.
      </p>
      <div className="ca-action-row uw-no-print">
        <button
          type="button"
          className="ac-primary"
          onClick={() => {
            startStory?.(full.key);
            open(full.start.section as WorkspaceSection, full.start.tab);
          }}
        >
          Continue the full evaluation <ChevronRight size={15} aria-hidden="true" />
        </button>
        <button type="button" className="ac-secondary" onClick={print}>
          <Printer size={15} aria-hidden="true" /> Print or save as PDF
        </button>
      </div>
    </div>
  );
}

/** "Resume SAMPLE-RV-11 · step N of 4", first on the entrance and on My work while the short story is unfinished. */
export function ResumeShortStory() {
  const { open, startStory, isTrial, navigation } = useWorkspace();
  const story = useShortStory(!!isTrial && navigation === "new");
  const text = resumeText(story.data);
  const ref = story.data?.complaint?.ref;
  if (!text || !ref) return null;
  return (
    <p className="uw-short-resume">
      <button
        type="button"
        className="ac-primary"
        onClick={() => {
          startStory?.("short");
          open("Complaint", `Summary?ref=${encodeURIComponent(ref)}`);
        }}
      >
        {text} <ChevronRight size={15} aria-hidden="true" />
      </button>
    </p>
  );
}
