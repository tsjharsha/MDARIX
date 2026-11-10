import { SampleDates } from "../../../app/chips";
import { useState, type ReactNode } from "react";
import { zoneLabel } from "../../../app/labels";
import { CheckCircle2, Copy, FileWarning, Hourglass, Link2, PhoneCall, Siren, Unlink, Wrench } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { useCan, useTabParam, useWorkspace } from "../workspaceContext";
import { DecideAndSign } from "./common";
import { WhyAsked } from "../../shared/Basis";
import { FIRST_CONTACT_WHY } from "../whyAsked";
import { Hero, InlineError } from "./boardParts";
import { EscalateButton } from "./Triage";
import { CaseHeaderView, CasesList } from "./CasesList";
import {
  INTAKE,
  REASON_MIN,
  FIRST_KNOWLEDGE_BASES,
  NEW_IDENTIFIER,
  answerChoices,
  identifierChip,
  blankAnswers,
  daysEarlier,
  startingZone,
  linkBody,
  signProblem,
  zonedInput,
  unanswered,
  type Answers,
  type Duplicate,
  type Guide,
  type IntakeItem,
  type IdentifierEntry,
  type Identifiers,
  type Outcome,
} from "../intake";

const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

/** A wall-clock time typed in a datetime field ("2026-11-03T21:50"), in the product's one format: "3 Nov 2026, 21:50". */
export function wallClockText(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!match) return "";
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][
    Number(match[2]) - 1
  ];
  return `Reads: ${Number(match[3])} ${month} ${match[1]}, ${match[4]}:${match[5]}`;
}

/**
 * Complaints › First contact: the calls the service desk logged and the urgent intakes, each with the first-contact
 * check (complaint, service only, both or pending, by the starter guide's table), the follow-ups, the QMS-complaint
 * task and the QA review of every "service only"; and the possible duplicates across sources, to link or dismiss.
 */
export function FirstContact({
  onOpenTab,
  part = "all",
  startLogging = null,
}: {
  onOpenTab?: (tab: "Triage") => void;
  /** The new navigation's queues (0.10.68): My work › Queues › Calls to check, or Possible duplicates. */
  part?: "all" | "calls" | "duplicates";
  /** A link's "Log a call" (Complaints' header action): the log opens at once. */
  startLogging?: "CONTACT" | "URGENT" | null;
}) {
  const [logging, setLogging] = useState<"CONTACT" | "URGENT" | null>(startLogging);
  // The Case whose check is open is part of the address (First contact?check=<id>).
  const [open, setOpen] = useTabParam("check");
  // A save in a drawer reads the list again (the Cases list pages on the server, A5).
  const [reloadKey, setReloadKey] = useState(0);
  const reload = () => setReloadKey((key) => key + 1);
  const guide = useResource<Guide>(`${INTAKE}/guide`);
  const canWrite = useCan("case.log");
  if (part === "duplicates") return <Duplicates onChanged={reload} />;
  return (
    <div className="ac-overview">
      <Hero
        tone="neutral"
        icon={<PhoneCall size={28} />}
        eyebrow="First contact"
        title="Cases"
        detail="A service call can hide a complaint. Log the reporter's words, answer the ten questions, and the table gives complaint, complaint and service, service only, inquiry, pending or not a complaint. A harm answer or a harm word goes to triage at once."
      >
        {canWrite && (
          <div className="uw-entry-actions">
            <button type="button" className="ac-primary" onClick={() => setLogging("CONTACT")}>
              <PhoneCall size={15} aria-hidden="true" /> Log a case
            </button>
            <button type="button" className="ac-secondary" onClick={() => setLogging("URGENT")}>
              <Siren size={15} aria-hidden="true" /> Urgent: death or serious injury
            </button>
            {onOpenTab && (
              <button type="button" className="ac-link" onClick={() => onOpenTab("Triage")}>
                Open the triage list
              </button>
            )}
          </div>
        )}
      </Hero>
      <CasesList onOpen={setOpen} reloadKey={reloadKey} />
      {guide.data && (
        <p className="uw-ma-starter" role="note">
          <FileWarning size={15} aria-hidden="true" /> Guide {guide.data.version}. {guide.data.starter_mark}
        </p>
      )}
      {part === "all" && <Duplicates onChanged={reload} />}
      {logging && guide.data && (
        <LogDrawer
          kind={logging}
          guide={guide.data}
          onClose={() => setLogging(null)}
          onLogged={(id) => {
            setLogging(null);
            reload();
            setOpen(id);
          }}
        />
      )}
      {open && guide.data && (
        <CheckDrawer id={open} guide={guide.data} onClose={() => setOpen(null)} onChanged={reload} />
      )}
    </div>
  );
}

// Logging a call or an urgent intake ---------------------------------------------------------------------------------

type LogForm = {
  kind: "CONTACT" | "URGENT";
  words: string;
  reporterType: string;
  site: string;
  country: string;
  product: string;
  productText: string;
  lot: string;
  serial: string;
  udi: string;
  software: string;
  hardware: string;
  firmware: string;
  ids: Identifiers;
  category: string;
  requested: string;
  ticket: string;
  environment: string;
  userType: string;
  received: string;
  event: string;
  firstKnowledge: string;
  party: string;
  basis: string;
  awareness: string;
  zone: string;
  /** Whether the person typed the case's time: until then it follows "now" in the zone chosen. */
  receivedTyped: boolean;
  answers: Answers;
  unknowns: string;
};

/** One device identifier (ID-1, S-3): the value, "Not sure" where allowed, its source and whether it is confirmed. */
function IdentifierField({
  code,
  label,
  value,
  onValue,
  entry,
  onEntry,
  guide,
  children,
}: {
  code: string;
  label: string;
  value?: string;
  onValue?: (value: string) => void;
  entry: IdentifierEntry;
  onEntry: (entry: IdentifierEntry) => void;
  guide: Guide;
  children?: ReactNode;
}) {
  const notSureAllowed = guide.identifiers?.not_sure.includes(code) ?? false;
  const given = !!value?.trim();
  const chip = identifierChip(entry, given);
  return (
    <div className="ca-field uw-id-field">
      <span>
        {label} {chip && <span className={`uw-cr-chip tone-${chip.tone}`}>{chip.label}</span>}
      </span>
      {children ??
        (onValue && (
          <input
            aria-label={label}
            value={value ?? ""}
            disabled={entry.not_sure}
            onChange={(event) => onValue(event.target.value)}
          />
        ))}
      <span className="uw-id-meta">
        {notSureAllowed && (
          <label className="ca-check">
            <input
              type="checkbox"
              checked={entry.not_sure}
              onChange={(event) => {
                onEntry({ ...entry, not_sure: event.target.checked, status: "UNCONFIRMED" });
                if (event.target.checked) onValue?.("");
              }}
            />
            Not sure
          </label>
        )}
        {given && !entry.not_sure && (
          <>
            <select
              aria-label={`${label}: source`}
              value={entry.source}
              onChange={(event) =>
                onEntry({
                  ...entry,
                  source: event.target.value,
                  // As told by the caller stays unconfirmed until a record or label confirms it.
                  status: event.target.value === "CALLER" ? "UNCONFIRMED" : entry.status,
                })
              }
            >
              {(guide.identifiers?.sources ?? []).map((source) => (
                <option key={source.code} value={source.code}>
                  {source.label}
                </option>
              ))}
            </select>
            <label className="ca-check">
              <input
                type="checkbox"
                checked={entry.status === "CONFIRMED"}
                disabled={entry.source === "CALLER"}
                onChange={(event) => onEntry({ ...entry, status: event.target.checked ? "CONFIRMED" : "UNCONFIRMED" })}
              />
              Confirmed
            </label>
          </>
        )}
      </span>
    </div>
  );
}

function LogDrawer({
  kind: startKind,
  guide,
  onClose,
  onLogged,
}: {
  kind: "CONTACT" | "URGENT";
  guide: Guide;
  onClose: () => void;
  onLogged: (id: string) => void;
}) {
  const { work } = useWorkspace();
  // A4: one key per drawer, so a retried save returns the Case it made, never a second one.
  const [requestKey] = useState(() => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`);
  const [form, setForm] = useState<LogForm>({
    kind: startKind,
    words: "",
    reporterType: "",
    site: "",
    country: "",
    product: "",
    productText: "",
    lot: "",
    serial: "",
    udi: "",
    software: "",
    hardware: "",
    firmware: "",
    ids: {},
    category: "",
    requested: "NONE",
    ticket: "",
    environment: "UNKNOWN",
    userType: "UNKNOWN",
    received: zonedInput(new Date(), startingZone(guide, ZONE)),
    event: "",
    firstKnowledge: "",
    party: "",
    basis: "",
    awareness: "",
    zone: startingZone(guide, ZONE),
    receivedTyped: false,
    answers: blankAnswers(guide.questions),
    unknowns: "",
  });
  const [typeProduct, setTypeProduct] = useState(false);
  const [earlier, setEarlier] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (patch: Partial<LogForm>) => setForm((current) => ({ ...current, ...patch }));
  const entry = (code: string) => form.ids[code] ?? NEW_IDENTIFIER;
  const setEntry = (code: string) => (value: IdentifierEntry) => set({ ids: { ...form.ids, [code]: value } });
  const urgent = form.kind === "URGENT";
  const problem = form.words.trim().length < REASON_MIN ? "Write down the reporter's words, as they said them" : null;
  const idProps = (code: string) => ({
    code,
    label: guide.identifiers?.keys.find((key) => key.code === code)?.label ?? code,
    entry: entry(code),
    onEntry: setEntry(code),
    guide,
  });
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const saved = await send<IntakeItem>(INTAKE, "POST", {
        kind: form.kind,
        reporter_words: form.words,
        reporter_type: form.reporterType,
        reporter_site: form.site,
        country: form.country,
        product_id: typeProduct ? null : form.product || null,
        product_text: typeProduct ? form.productText : "",
        lot: form.lot,
        serial_number: form.serial,
        udi: form.udi,
        software_version: form.software,
        hardware_revision: form.hardware,
        firmware_version: form.firmware,
        identifiers: form.ids,
        issue_category: form.category,
        requested: form.requested,
        service_ticket: form.ticket,
        use_environment: form.environment,
        user_type: form.userType,
        // Wall-clock times in the case's time zone: the server converts them in it (J28: Chicago 09:00 is 15:00 UTC).
        received_at: form.received || null,
        received_zone: form.zone,
        event_at: form.event || null,
        event_zone: form.event ? form.zone : "",
        first_knowledge_at: form.firstKnowledge || null,
        first_knowledge_zone: form.firstKnowledge ? form.zone : "",
        first_knowledge_party: form.party,
        first_knowledge_basis: form.basis,
        awareness_at: urgent ? form.awareness || null : null,
        awareness_zone: form.zone,
        answers: urgent ? {} : form.answers,
        unknowns: form.unknowns,
        request_key: requestKey,
      });
      onLogged(saved.id);
    } catch (reason) {
      setError(errorText(reason, "Not saved"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Drawer title="Log a case" onClose={onClose}>
      <form
        className="uw-dp"
        onSubmit={(event) => {
          event.preventDefault();
          if (!problem) void submit();
        }}
      >
        <div className="uw-entry-actions" role="radiogroup" aria-label="Kind of case">
          {(
            [
              ["CONTACT", "Case"],
              ["URGENT", "Urgent: death or serious injury"],
            ] as const
          ).map(([code, label]) => (
            <label key={code} className="ca-check">
              <input type="radio" name="case-kind" checked={form.kind === code} onChange={() => set({ kind: code })} />
              {label}
            </label>
          ))}
        </div>
        <p className="uw-hint">
          {urgent
            ? "An urgent case is a complaint at once. It goes to triage now, its clock running from awareness. Leave awareness empty if nobody has confirmed it: the clock then runs from first knowledge or receipt, marked provisional."
            : "Awareness is when the case was received, or earlier when someone acting for you knew first. It never moves, even if the case is reclassified."}
        </p>
        <details className="ca-drawer-section uw-more" open>
          <summary>What was said</summary>
          <label className="ca-field">
            The reporter's words, as they said them
            <textarea rows={4} value={form.words} onChange={(event) => set({ words: event.target.value })} />
            <small>Names, phone numbers and e-mail addresses are masked when you save.</small>
          </label>
        </details>
        <details className="ca-drawer-section uw-more" open>
          <summary>How it came in ({zoneLabel(form.zone)})</summary>
          <div className="ca-form-grid">
            <label className="ca-field">
              Received
              <input
                type="datetime-local"
                value={form.received}
                aria-describedby="log-received-reads"
                onChange={(event) => set({ received: event.target.value, receivedTyped: true })}
              />
              {/* The browser's own field may show 11/03/2026; MDARIX's one format reads it back (0.10.85, D3.10). */}
              <small id="log-received-reads">{wallClockText(form.received)}</small>
            </label>
            <label className="ca-field">
              Time zone
              <select
                value={form.zone}
                onChange={(event) =>
                  set({
                    zone: event.target.value,
                    // A time the person typed stays as typed (09:00 in Chicago); "now" follows the zone.
                    ...(form.receivedTyped ? {} : { received: zonedInput(new Date(), event.target.value) }),
                  })
                }
              >
                {(guide.zones ?? [form.zone]).map((zone) => (
                  <option key={zone} value={zone}>
                    {zoneLabel(zone)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!earlier ? (
            <button type="button" className="ac-link" onClick={() => setEarlier(true)}>
              Someone acting for you knew earlier
            </button>
          ) : (
            <div className="ca-form-grid">
              <label className="ca-field">
                Who knew first
                <select value={form.party} onChange={(event) => set({ party: event.target.value })}>
                  <option value="">Not known</option>
                  <option value="MANUFACTURER">Our own staff</option>
                  <option value="DISTRIBUTOR">A distributor</option>
                  <option value="SERVICE_AGENT">A service agent</option>
                </select>
              </label>
              <label className="ca-field">
                Acting for you?
                <select value={form.basis} onChange={(event) => set({ basis: event.target.value })}>
                  <option value="">Not known</option>
                  {FIRST_KNOWLEDGE_BASES.map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ca-field">
                When they knew
                <input
                  type="datetime-local"
                  value={form.firstKnowledge}
                  onChange={(event) => set({ firstKnowledge: event.target.value })}
                />
              </label>
            </div>
          )}
          {urgent && (
            <label className="ca-field">
              Awareness (if confirmed)
              <input
                type="datetime-local"
                value={form.awareness}
                onChange={(event) => set({ awareness: event.target.value })}
              />
            </label>
          )}
        </details>
        <details className="ca-drawer-section uw-more">
          <summary>Customer</summary>
          <div className="ca-form-grid">
            <label className="ca-field">
              Reporter type
              <input value={form.reporterType} onChange={(event) => set({ reporterType: event.target.value })} />
            </label>
            <label className="ca-field">
              Site or organisation (no person's name)
              <input value={form.site} onChange={(event) => set({ site: event.target.value })} />
            </label>
            <label className="ca-field">
              Reporter's country
              <input value={form.country} onChange={(event) => set({ country: event.target.value })} />
            </label>
          </div>
        </details>
        <details className="ca-drawer-section uw-more" open>
          <summary>Product</summary>
          <div className="ca-form-grid">
            <IdentifierField {...idProps("product")} value={typeProduct ? form.productText : form.product}>
              {typeProduct ? (
                <input
                  aria-label="Product, as typed"
                  value={form.productText}
                  onChange={(event) => set({ productText: event.target.value })}
                />
              ) : (
                <select value={form.product} onChange={(event) => set({ product: event.target.value })}>
                  <option value="">Not named</option>
                  {work.products.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.name}
                    </option>
                  ))}
                </select>
              )}
            </IdentifierField>
            <IdentifierField {...idProps("version")} value="">
              <small className="uw-cr-meta">From the lot, when the lot is loaded</small>
            </IdentifierField>
            <IdentifierField {...idProps("lot")} value={form.lot} onValue={(lot) => set({ lot })} />
            <IdentifierField {...idProps("serial")} value={form.serial} onValue={(serial) => set({ serial })} />
            <IdentifierField {...idProps("udi")} value={form.udi} onValue={(udi) => set({ udi })} />
            <IdentifierField
              {...idProps("software_version")}
              value={form.software}
              onValue={(software) => set({ software })}
            />
            <IdentifierField
              {...idProps("hardware_revision")}
              value={form.hardware}
              onValue={(hardware) => set({ hardware })}
            />
            <IdentifierField
              {...idProps("firmware_version")}
              value={form.firmware}
              onValue={(firmware) => set({ firmware })}
            />
          </div>
          <button type="button" className="ac-link" onClick={() => setTypeProduct((typed) => !typed)}>
            {typeProduct ? "Choose from your products" : "Not in your products: type it"}
          </button>
          <p className="uw-cr-meta">A lot not in your lots is kept as typed and flagged.</p>
        </details>
        <details className="ca-drawer-section uw-more">
          <summary>Event</summary>
          <div className="ca-form-grid">
            <label className="ca-field">
              When it happened (leave empty if not known)
              <input
                type="datetime-local"
                value={form.event}
                onChange={(event) => set({ event: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Where it was used
              <select value={form.environment} onChange={(event) => set({ environment: event.target.value })}>
                {guide.use_environments.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Who used it
              <select value={form.userType} onChange={(event) => set({ userType: event.target.value })}>
                {guide.user_types.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </details>
        <details className="ca-drawer-section uw-more">
          <summary>Service</summary>
          <div className="ca-form-grid">
            <label className="ca-field">
              Issue category
              <select value={form.category} onChange={(event) => set({ category: event.target.value })}>
                <option value="">Not chosen</option>
                {(guide.issue_categories ?? []).map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
              <small>For the service team only: it never decides a complaint or a report.</small>
            </label>
            <label className="ca-field">
              What they asked for
              <select value={form.requested} onChange={(event) => set({ requested: event.target.value })}>
                {guide.requests.map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Service ticket (optional)
              <input value={form.ticket} onChange={(event) => set({ ticket: event.target.value })} />
            </label>
          </div>
        </details>
        {!urgent && (
          // The ten questions fold in the log (0.10.85, D3.10): they can be answered now or at the Case check.
          <details className="ca-drawer-section uw-more">
            <summary>The ten questions: answer now, or at the Case check</summary>
            <p className="uw-hint">{guide.note}</p>
            <Questions guide={guide} answers={form.answers} onChange={(answers) => set({ answers })} />
            <label className="ca-field">
              10. What is still unknown and needs a follow-up with the reporter?
              <textarea rows={2} value={form.unknowns} onChange={(event) => set({ unknowns: event.target.value })} />
            </label>
          </details>
        )}
        {problem && <p className="uw-hint">{problem}</p>}
        <div className="ca-action-row">
          <button type="submit" className="ac-primary" disabled={busy || !!problem}>
            {busy ? "Saving…" : urgent ? "Send to triage now" : "Save the case"}
          </button>
        </div>
        <InlineError text={error} />
      </form>
    </Drawer>
  );
}

function Questions({
  guide,
  answers,
  disabled,
  onChange,
}: {
  guide: Guide;
  answers: Answers;
  disabled?: boolean;
  onChange: (answers: Answers) => void;
}) {
  return (
    <ol className="uw-fc-questions">
      {guide.questions
        .filter((question) => !question.free_text)
        .map((question) => {
          const current = answers[question.id] ?? { answer: null, note: "" };
          const harm = question.not_stated && (current.answer === "YES" || current.answer === "UNKNOWN");
          return (
            <li key={question.id} className={`uw-fc-question${harm ? " is-flag" : ""}`}>
              <strong>
                {question.id.replace("Q", "")}. {question.text}
              </strong>
              <WhyAsked why={FIRST_CONTACT_WHY[question.id]} />
              <div className="uw-fc-answers" role="radiogroup" aria-label={`Question ${question.id.replace("Q", "")}`}>
                {answerChoices(guide, question).map((choice) => (
                  <label key={choice.code}>
                    <input
                      type="radio"
                      name={question.id}
                      disabled={disabled}
                      checked={current.answer === choice.code}
                      onChange={() => onChange({ ...answers, [question.id]: { ...current, answer: choice.code } })}
                    />
                    {choice.label}
                  </label>
                ))}
              </div>
              {(current.answer === "NOT_APPLICABLE" || current.note) && (
                <input
                  aria-label={`Question ${question.id.replace("Q", "")}: reason or evidence`}
                  placeholder="Reason or evidence (needed for Not applicable)"
                  disabled={disabled}
                  value={current.note}
                  onChange={(event) =>
                    onChange({ ...answers, [question.id]: { ...current, note: event.target.value } })
                  }
                />
              )}
              {harm && <span className="uw-cr-meta">Raises the triage flag at once.</span>}
            </li>
          );
        })}
    </ol>
  );
}

// The check -----------------------------------------------------------------------------------------------------------

function CheckDrawer({
  id,
  guide,
  onClose,
  onChanged,
}: {
  id: string;
  guide: Guide;
  onClose: () => void;
  onChanged: () => void;
}) {
  const item = useResource<IntakeItem>(`${INTAKE}/${id}`);
  const data = item.data;
  const reload = () => {
    item.reload();
    onChanged();
  };
  return (
    <Drawer title={data ? `${data.kind_label} ${data.reference}` : "Loading…"} onClose={onClose}>
      {data ? (
        <CheckBody key={`${data.version}-${data.signed?.id ?? ""}`} item={data} guide={guide} onChanged={reload} />
      ) : null}
      <InlineError text={item.state === "error" ? "This call could not be read" : ""} />
    </Drawer>
  );
}

function CheckBody({ item, guide, onChanged }: { item: IntakeItem; guide: Guide; onChanged: () => void }) {
  // B2 step 4 (spec 6.3): answers and signature need case.classify; follow-up case.log; the QA review quality.review.
  const canWrite = useCan("case.classify");
  const canLog = useCan("case.log");
  const canReview = useCan("quality.review");
  const [answers, setAnswers] = useState<Answers>({ ...blankAnswers(guide.questions), ...item.answers });
  const [editing, setEditing] = useState(item.draft || item.version === 0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (work: () => Promise<unknown>, fallback: string) => {
    setBusy(true);
    setError("");
    try {
      await work();
      onChanged();
    } catch (reason) {
      setError(errorText(reason, fallback));
    } finally {
      setBusy(false);
    }
  };
  const followUp = item.tasks.find((task) => task.type === "FIRST_CONTACT_FOLLOW_UP" && task.open);
  const review = item.signed?.classification === "SERVICE_ONLY" && !item.signed.review_outcome;
  return (
    <div className="uw-dp">
      {item.header && <CaseHeaderView header={item.header} status={item.status_label ?? null} />}
      {!item.flagged && item.kind !== "URGENT" && item.status !== "ESCALATED" && (
        <EscalateButton kind="INTAKE" id={item.id} onDone={onChanged} />
      )}
      <q className="uw-cr-text">{item.reporter_words}</q>
      <p className="uw-cr-meta">
        {[
          item.product_name,
          item.lot,
          item.requested_label && `asked for: ${item.requested_label}`,
          item.reporter_type,
          item.reporter_site,
          item.country,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <section className="ca-drawer-section">
        <h3>Times</h3>
        <ul>
          {(
            [
              ["Event", item.times.event],
              ["First knowledge", item.times.first_knowledge],
              ["Received", item.times.received],
              ["Awareness", item.times.awareness],
              ["Reached MDARIX", item.times.available],
            ] as const
          ).map(([label, time]) => (
            <li key={label}>
              {label}:{" "}
              {time?.at
                ? `${formatDate(time.at)}${time.zone && time.zone !== "UTC" ? ` (entered in ${time.zone})` : ""}`
                : "not recorded"}
            </li>
          ))}
        </ul>
        <p>
          Clocks count from {formatDate(item.awareness.at)}: {item.awareness.source_label}.
          {item.awareness.label ? ` ${item.awareness.label}.` : ""}
        </p>
      </section>
      {item.flags.length > 0 && (
        <section className="ca-drawer-section">
          <h3>
            <Siren size={15} aria-hidden="true" /> On the triage list now
          </h3>
          <ul className="uw-cr-chips">
            {item.flags.map((flag, index) => (
              <li key={`${flag.code}-${index}`} className="uw-cr-chip tone-serious">
                {flag.label}
              </li>
            ))}
          </ul>
          <p className="uw-hint">Safety never waits for the check or a signature.</p>
        </section>
      )}
      {item.kind !== "URGENT" && (
        <section className="ca-drawer-section">
          <h3>The first-contact check</h3>
          {item.suggestion && (
            <p className="uw-fc-outcome">
              The table gives: <strong>{item.suggestion_label}</strong> (row {item.outcome_row}).
              {item.signed && ` Signed: ${item.signed.classification_label}, version ${item.signed.version}.`}
            </p>
          )}
          <Questions guide={guide} answers={answers} disabled={!editing || !canWrite} onChange={setAnswers} />
          <details className="uw-ma-history">
            <summary>The outcomes table (fixed)</summary>
            <ol>
              {guide.table.map((row) => (
                <li key={row.row} className={row.row === item.outcome_row ? "is-taken" : undefined}>
                  {row.answers}: <strong>{row.outcome}</strong>
                </li>
              ))}
            </ol>
          </details>
          {canWrite && (
            <div className="ca-action-row">
              {editing ? (
                <button
                  type="button"
                  className="ac-secondary"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => send(`${INTAKE}/${item.id}/check`, "PUT", { answers, seen_version: item.version }),
                      "The answers were not saved",
                    )
                  }
                >
                  {item.signed ? "Save as a new version" : "Save the answers"}
                </button>
              ) : (
                <button type="button" className="ac-link" onClick={() => setEditing(true)}>
                  New information: answer again (a new version; awareness stays)
                </button>
              )}
            </div>
          )}
        </section>
      )}
      {canWrite && item.draft && item.version > 0 && (
        <SignForm item={item} guide={guide} answers={answers} onSigned={onChanged} />
      )}
      {followUp && canLog && <FollowUp item={item} dueAt={followUp.due_at} onDone={onChanged} />}
      {item.qms_task && (
        <section className="ca-drawer-section">
          <h3>
            <Wrench size={15} aria-hidden="true" /> QMS complaint
          </h3>
          <p>
            {item.qms_task.label}
            {item.qms_ref ? `: ${item.qms_ref}` : ""}
            {item.qms_task.open && item.qms_task.due_at ? ` · due ${formatDate(item.qms_task.due_at)}` : ""}
            {item.qms_task.overdue ? " (overdue)" : ""}. Reporting never waits for it.
          </p>
          {item.qms_task.open && (canLog || canReview) && <QmsForm id={item.id} onDone={onChanged} />}
        </section>
      )}
      {review && canReview && <ReviewForm item={item} onDone={onChanged} />}
      {item.history && item.history.length > 0 && (
        <details className="uw-ma-history" open>
          <summary>Signed versions ({item.history.length})</summary>
          <ul>
            {item.history.map((version) => (
              <li key={version.id}>
                Version {version.version}: {version.classification_label} · {version.signed_by} ·{" "}
                {formatDate(version.signed_at)}
                {version.override_reason ? ` · ${version.override_reason}` : ""}
                {version.reason ? ` · ${version.reason}` : ""}
                {version.review_outcome
                  ? ` · QA review ${version.review_outcome.toLowerCase()} by ${version.reviewed_by}${version.same_person ? " (same person)" : ""}`
                  : ""}
                <SampleDates sample={item.sample} />
                {version.superseded ? " · superseded" : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
      {item.links && item.links.length > 0 && <Links links={item.links} onChanged={onChanged} />}
      {item.duplicates && item.duplicates.length > 0 && (
        <section className="ca-drawer-section">
          <h3>
            <Copy size={15} aria-hidden="true" /> Possible duplicate
          </h3>
          {item.duplicates.map((pair) => (
            <DuplicatePair key={`${pair.left.id}-${pair.right.id}`} pair={pair} onDone={onChanged} />
          ))}
        </section>
      )}
      <InlineError text={error} />
    </div>
  );
}

function SignForm({
  item,
  guide,
  answers,
  onSigned,
}: {
  item: IntakeItem;
  guide: Guide;
  answers: Answers;
  onSigned: () => void;
}) {
  const [form, setForm] = useState({
    classification: (item.suggestion ?? "") as Outcome | "",
    override: "",
    reason: "",
    ticket: item.service_ticket ?? "",
    password: "",
    code: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const saved = JSON.stringify(answers) === JSON.stringify({ ...blankAnswers(guide.questions), ...item.answers });
  const problem = saved ? signProblem(item, form, unanswered(item.answers, guide.questions)) : "Save the answers first";
  return (
    <form
      className="ca-drawer-section uw-dp-sign"
      onSubmit={async (event) => {
        event.preventDefault();
        if (problem) return;
        setBusy(true);
        setError("");
        try {
          await send(`${INTAKE}/${item.id}/check/sign`, "POST", {
            classification: form.classification,
            override_reason: form.override,
            reason: form.reason,
            service_ticket: form.ticket,
            seen_version: item.version,
            password: form.password,
            mfa_code: form.code || null,
          });
          onSigned();
        } catch (reason) {
          setError(errorText(reason, "Not signed"));
        } finally {
          setBusy(false);
        }
      }}
    >
      <h3>
        <CheckCircle2 size={15} aria-hidden="true" /> Sign as the coordinator
      </h3>
      <label className="ca-field">
        Classification
        <select
          value={form.classification}
          onChange={(event) => setForm({ ...form, classification: event.target.value as Outcome })}
        >
          {guide.outcomes
            .filter(
              (outcome) =>
                (outcome.code !== "SERVICE_ONLY" && outcome.code !== "PENDING_CONFIRM") ||
                outcome.code === item.suggestion,
            )
            .map((outcome) => (
              <option key={outcome.code} value={outcome.code}>
                {outcome.label}
                {outcome.code === item.suggestion ? " (suggested)" : ""}
              </option>
            ))}
        </select>
      </label>
      {form.classification !== item.suggestion && (
        <label className="ca-field">
          Why you override the suggestion
          <input value={form.override} onChange={(event) => setForm({ ...form, override: event.target.value })} />
        </label>
      )}
      {form.classification === "SERVICE_ONLY" && (
        <label className="ca-field">
          The written reason for "service only" (it goes to the QA review)
          <input value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
        </label>
      )}
      {form.classification === "BOTH" && (
        <label className="ca-field">
          Service ticket
          <input value={form.ticket} onChange={(event) => setForm({ ...form, ticket: event.target.value })} />
        </label>
      )}
      <div className="ca-form-grid">
        <DecideAndSign
          signs={`The first-contact check of ${item.reference}: ${
            guide.outcomes.find((outcome) => outcome.code === form.classification)?.label ?? "your classification"
          }.`}
          restsOn={[
            `Your answers to ${guide.questions.filter((question) => !question.free_text && item.answers?.[question.id]?.answer).length} questions, as saved.`,
            `The reporter's words as logged, and the awareness time of the call.`,
          ]}
        />
        <label className="ca-field">
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value })}
          />
        </label>
      </div>
      {problem && <p className="uw-hint">{problem}</p>}
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={busy || !!problem}>
          {busy ? "Signing…" : "Sign the check"}
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

function FollowUp({ item, dueAt, onDone }: { item: IntakeItem; dueAt: string | null; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const close = async (outcome: "ANSWERED" | "UNRESOLVED") => {
    setError("");
    try {
      await send(`${INTAKE}/${item.id}/follow-up`, "POST", { outcome, note });
      onDone();
    } catch (reason) {
      setError(errorText(reason, "Not saved"));
    }
  };
  const short = note.trim().length < REASON_MIN;
  return (
    <section className="ca-drawer-section">
      <h3>
        <Hourglass size={15} aria-hidden="true" /> Follow-up with the caller
      </h3>
      <p>
        Due {formatDate(dueAt)}. Ask about every Unknown and Not stated answer. The follow-up is a dated task on the
        check.
      </p>
      <label className="ca-field">
        What the caller said, or what you tried
        <input value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" disabled={short} onClick={() => close("ANSWERED")}>
          Answered: I will update the answers
        </button>
        <button type="button" className="ac-link" disabled={short} onClick={() => close("UNRESOLVED")}>
          Unresolved after attempts
        </button>
      </div>
      <InlineError text={error} />
    </section>
  );
}

function QmsForm({ id, onDone }: { id: string; onDone: () => void }) {
  const [ref, setRef] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const post = async (body: object) => {
    setError("");
    try {
      await send(`${INTAKE}/${id}/qms`, "POST", body);
      onDone();
    } catch (failure) {
      setError(errorText(failure, "Not saved"));
    }
  };
  return (
    <div className="ca-form-grid">
      <label className="ca-field">
        QMS complaint ID (closes when an upload brings it)
        <input value={ref} onChange={(event) => setRef(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button type="button" className="ac-secondary" disabled={!ref.trim()} onClick={() => post({ qms_ref: ref })}>
          Save the ID
        </button>
      </div>
      <label className="ca-field">
        Or: why no QMS complaint is needed
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-link"
          disabled={reason.trim().length < REASON_MIN}
          onClick={() => post({ not_needed_reason: reason })}
        >
          No QMS complaint needed
        </button>
      </div>
      <InlineError text={error} />
    </div>
  );
}

function ReviewForm({ item, onDone }: { item: IntakeItem; onDone: () => void }) {
  const [form, setForm] = useState({
    outcome: "AGREED",
    note: "",
    summary: item.resolution_summary ?? "",
    password: "",
    code: "",
  });
  const [error, setError] = useState("");
  const words = [...(item.fault_words ?? []), ...(item.harm_words ?? [])];
  // S-2: agreeing closes a service-only Case, which needs what was done for the customer.
  const closes = form.outcome === "AGREED" && item.signed?.classification === "SERVICE_ONLY";
  const problem =
    form.note.trim().length < REASON_MIN
      ? `Say what you checked (at least ${REASON_MIN} characters)`
      : closes && form.summary.trim().length < REASON_MIN
        ? `Write the resolution summary (at least ${REASON_MIN} characters) before a service-only case is closed`
        : !form.password
          ? "Enter your password to sign"
          : null;
  return (
    <form
      className="ca-drawer-section"
      onSubmit={async (event) => {
        event.preventDefault();
        if (problem) return;
        setError("");
        try {
          await send(`${INTAKE}/${item.id}/check/review`, "POST", {
            outcome: form.outcome,
            note: form.note,
            resolution_summary: form.summary,
            password: form.password,
            mfa_code: form.code || null,
          });
          onDone();
        } catch (reason) {
          setError(errorText(reason, "Not signed"));
        }
      }}
    >
      <h3>QA review of "service only"</h3>
      <p>
        Every service-only call is reviewed in the trial. Ideally by someone other than the signer; the record says if
        it is the same person.
        {words.length ? ` The words match the starter lists: ${words.join(", ")}.` : ""}
      </p>
      <div className="uw-fc-answers">
        <label>
          <input
            type="radio"
            checked={form.outcome === "AGREED"}
            onChange={() => setForm({ ...form, outcome: "AGREED" })}
          />
          Agree: service only
        </label>
        <label>
          <input
            type="radio"
            checked={form.outcome === "RECLASSIFIED"}
            onChange={() => setForm({ ...form, outcome: "RECLASSIFIED" })}
          />
          Disagree: it is a complaint (awareness stays the time of the call)
        </label>
      </div>
      <label className="ca-field">
        What you checked
        <input value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
      </label>
      {closes && (
        <label className="ca-field">
          Resolution summary: what was done for the customer
          <textarea
            rows={2}
            value={form.summary}
            onChange={(event) => setForm({ ...form, summary: event.target.value })}
          />
        </label>
      )}
      <div className="ca-form-grid">
        <DecideAndSign />
        <label className="ca-field">
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input
            inputMode="numeric"
            value={form.code}
            onChange={(event) => setForm({ ...form, code: event.target.value })}
          />
        </label>
      </div>
      {problem && <p className="uw-hint">{problem}</p>}
      <div className="ca-action-row">
        <button type="submit" className="ac-primary" disabled={!!problem}>
          Sign the review
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

// Duplicates and links -----------------------------------------------------------------------------------------------

type DuplicateList = {
  items: Duplicate[];
  window_days: number;
  links: {
    id: string;
    state: "LINKED" | "DISMISSED" | "UNLINKED";
    left: { ref: string };
    right: { ref: string };
    reason: string;
    decided_at: string;
    awareness_before: string | null;
    awareness_after: string | null;
    conflict: boolean;
    undo_reason: string | null;
  }[];
};

function Duplicates({ onChanged }: { onChanged: () => void }) {
  const list = useResource<DuplicateList>(`${INTAKE}/duplicates`);
  const reload = () => {
    list.reload();
    onChanged();
  };
  const items = list.data?.items ?? [];
  const links = list.data?.links ?? [];
  return (
    <Panel
      id="first-contact-duplicates"
      eyebrow="Duplicates"
      title="Possible duplicates across uploads, the sample, calls and urgent intakes"
      source={list}
    >
      <p className="uw-hint">
        Same product and lot or serial number, events within {list.data?.window_days ?? 2} days, and the same site or
        country. Link them into one event, or dismiss the warning, with a reason. A link uses the earliest awareness of
        its sources and recomputes every deadline from it.
      </p>
      {items.length ? (
        items.map((pair) => <DuplicatePair key={`${pair.left.id}-${pair.right.id}`} pair={pair} onDone={reload} />)
      ) : (
        <Empty title="No possible duplicate" detail="A warning shows when two sources describe the same event." />
      )}
      {links.length > 0 && (
        <details className="uw-ma-history" open>
          <summary>Decisions ({links.length})</summary>
          <ul>
            {links.map((link) => (
              <LinkRow key={link.id} link={link} onDone={reload} />
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}

function DuplicatePair({ pair, onDone }: { pair: Duplicate; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const decide = async (decision: "LINKED" | "DISMISSED") => {
    setError("");
    try {
      await send(`${INTAKE}/links`, "POST", linkBody(pair, decision, reason));
      onDone();
    } catch (failure) {
      setError(errorText(failure, "Not saved"));
    }
  };
  const earlier = Date.parse(pair.left.awareness_at) < Date.parse(pair.right.awareness_at) ? pair.left : pair.right;
  const later = earlier === pair.left ? pair.right : pair.left;
  return (
    <div className="ca-drawer-section">
      <p>
        <ToneBadge tone="warning" label="Possible duplicate" /> {pair.reasons.join(" · ")}
      </p>
      <div className="uw-fc-pair">
        {[pair.left, pair.right].map((side) => (
          <div key={side.id}>
            <strong>{side.ref}</strong> <span className="uw-cr-meta">{side.source}</span>
            <q className="uw-cr-text uw-cr-clip">{side.words}</q>
            <p className="uw-cr-meta">
              Aware {formatDate(side.awareness_at)} ({side.awareness_source})
            </p>
          </div>
        ))}
      </div>
      {earlier.awareness_at !== later.awareness_at && (
        <p className="uw-hint">
          Linking moves {later.ref}'s awareness {daysEarlier(later.awareness_at, earlier.awareness_at)} days earlier, to{" "}
          {earlier.ref}'s: an awareness conflict on the triage list until it is confirmed.
        </p>
      )}
      <label className="ca-field">
        Why
        <input value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          disabled={reason.trim().length < REASON_MIN}
          onClick={() => decide("LINKED")}
        >
          <Link2 size={14} aria-hidden="true" /> Link into one event
        </button>
        <button
          type="button"
          className="ac-link"
          disabled={reason.trim().length < REASON_MIN}
          onClick={() => decide("DISMISSED")}
        >
          Not the same: dismiss
        </button>
      </div>
      <InlineError text={error} />
    </div>
  );
}

function LinkRow({ link, onDone }: { link: DuplicateList["links"][number]; onDone: () => void }) {
  const [undoing, setUndoing] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const label = link.state === "LINKED" ? "Linked" : link.state === "DISMISSED" ? "Dismissed" : "Link undone";
  return (
    <li>
      {label}: {link.left.ref} and {link.right.ref} · {formatDate(link.decided_at)} · {link.reason}
      {link.conflict && link.state === "LINKED"
        ? ` · awareness ${daysEarlier(link.awareness_before, link.awareness_after)} days earlier`
        : ""}
      {link.undo_reason ? ` · undone: ${link.undo_reason}` : ""}
      {link.state === "LINKED" &&
        (undoing ? (
          <span className="uw-escalate">
            <input
              aria-label="Why the link is undone"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <button
              type="button"
              className="ac-secondary"
              disabled={reason.trim().length < REASON_MIN}
              onClick={async () => {
                setError("");
                try {
                  await send(`${INTAKE}/links/${link.id}/undo`, "POST", { reason });
                  onDone();
                } catch (failure) {
                  setError(errorText(failure, "Not undone"));
                }
              }}
            >
              Undo the link
            </button>
          </span>
        ) : (
          <>
            {" "}
            <button type="button" className="ac-link" onClick={() => setUndoing(true)}>
              <Unlink size={13} aria-hidden="true" /> Undo
            </button>
          </>
        ))}
      <InlineError text={error} />
    </li>
  );
}

function Links({ links, onChanged }: { links: NonNullable<IntakeItem["links"]>; onChanged: () => void }) {
  return (
    <section className="ca-drawer-section">
      <h3>
        <Link2 size={15} aria-hidden="true" /> Linked records
      </h3>
      <ul>
        {links.map((link) => (
          <LinkRow
            key={link.id}
            link={{ ...link, left: { ref: "This call" }, right: { ref: link.other.ref } }}
            onDone={onChanged}
          />
        ))}
      </ul>
    </section>
  );
}
