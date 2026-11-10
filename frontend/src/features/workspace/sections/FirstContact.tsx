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
  type Choice,
  clockTone,
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
  channel: string;
  channelRef: string;
  patients: string;
  harmText: string;
  tried: string;
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
    channel: "",
    channelRef: "",
    patients: "",
    harmText: "",
    tried: "",
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
        channel: form.channel,
        channel_ref: form.channelRef,
        patients: form.patients,
        harm_text: form.harmText,
        troubleshooting: form.tried,
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
              Channel
              <select value={form.channel} onChange={(event) => set({ channel: event.target.value })}>
                <option value="">Not chosen</option>
                {(guide.channels ?? []).map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              Reference in that channel (optional)
              <input value={form.channelRef} onChange={(event) => set({ channelRef: event.target.value })} />
            </label>
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
                  <option value="IMPORTER">An importer</option>
                  <option value="AUTHORISED_REPRESENTATIVE">An authorised representative</option>
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
          <summary>Patient and harm</summary>
          <div className="uw-fc-answers" role="radiogroup" aria-label="Patients involved">
            <span>Patients involved:</span>
            {(guide.patients ?? []).map((item) => (
              <label key={item.code}>
                <input
                  type="radio"
                  name="patients"
                  checked={form.patients === item.code}
                  onChange={() => set({ patients: item.code })}
                />
                {item.label}
              </label>
            ))}
          </div>
          <label className="ca-field">
            What happened to the patient (optional)
            <textarea rows={2} value={form.harmText} onChange={(event) => set({ harmText: event.target.value })} />
          </label>
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
            <label className="ca-field ca-wide">
              What was tried on the call
              <textarea rows={2} value={form.tried} onChange={(event) => set({ tried: event.target.value })} />
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
  const title = !data
    ? "Loading…"
    : data.kind === "URGENT"
      ? `${data.kind_label} ${data.reference}`
      : `Case check · ${data.reference}`;
  return (
    <Drawer title={title} onClose={onClose}>
      {data ? (
        <CheckBody
          key={`${data.version}-${data.row_version ?? ""}-${data.signed?.id ?? ""}`}
          item={data}
          guide={guide}
          onChanged={reload}
        />
      ) : null}
      <InlineError text={item.state === "error" ? "This case could not be read" : ""} />
    </Drawer>
  );
}

const ADDENDUM_KINDS: readonly [string, string][] = [
  ["STATEMENT", "Something more they said"],
  ["TECHNICIAN_FINDING", "A technician's finding"],
  ["CORRECTION_BY_REPORTER", "The reporter corrects a fact"],
  ["WITHDRAWAL", "The reporter withdraws the complaint"],
];
const SAID_BY: readonly [string, string][] = [
  ["REPORTER", "The reporter"],
  ["TECHNICIAN", "A technician"],
  ["DISTRIBUTOR", "A distributor"],
  ["OUR_STAFF", "Our staff"],
];
// The facts "Correct a fact" may change (backend intake/router.py CORRECTABLE); the reporter's words never.
const CORRECTABLE: readonly [string, string][] = [
  ["serial_number", "Serial number"],
  ["lot_text", "Lot (as typed)"],
  ["product_text", "Product (as typed)"],
  ["udi", "UDI"],
  ["software_version", "Software version"],
  ["hardware_revision", "Hardware revision"],
  ["firmware_version", "Firmware version"],
  ["reporter_site", "Site or organisation"],
  ["country_text", "Country where it happened (as typed)"],
  ["harm_text", "What happened to the patient"],
  ["troubleshooting", "What was tried on the call"],
];
const labelOf = (list: readonly [string, string][], code: string) =>
  list.find(([value]) => value === code)?.[1] ?? code;
/** The Case check's clock chip (spec 4.4, 5.2): "Provisional: US 30 days, due Mon 7 Dec 2026, 23:59 EST". */
export const clockChip = (clock: NonNullable<IntakeItem["clock"]>) =>
  `Provisional: ${clock.market} ${clock.days} days${clock.due_label ? `, due ${clock.due_label}` : ""}`;

/** The Case check drawer's body (spec 4.4), exported for its test. */
export function CheckBody({ item, guide, onChanged }: { item: IntakeItem; guide: Guide; onChanged: () => void }) {
  // B2 step 4 (spec 6.3): answers and signature need case.classify; follow-up case.log; the QA review quality.review.
  const canWrite = useCan("case.classify");
  const canLog = useCan("case.log");
  const canReview = useCan("quality.review");
  const [answers, setAnswers] = useState<Answers>({ ...blankAnswers(guide.questions), ...item.answers });
  const [editing, setEditing] = useState(item.draft || item.version === 0);
  const [adding, setAdding] = useState<"addendum" | "correct" | null>(null);
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
  const voided = item.status === "VOIDED";
  const row = guide.table.find((entry) => entry.row === item.outcome_row);
  return (
    <div className="uw-dp">
      {item.header && <CaseHeaderView header={item.header} status={item.status_label ?? null} />}
      {item.status === "ESCALATED" && item.kind !== "URGENT" && <Escalated item={item} />}
      {!item.flagged && item.kind !== "URGENT" && item.status !== "ESCALATED" && !voided && (
        <EscalateButton kind="INTAKE" id={item.id} onDone={onChanged} />
      )}
      <section className="ca-drawer-section">
        <h3>What was said</h3>
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
        {(item.addenda ?? []).length > 0 && (
          <ul className="uw-case-addenda" aria-label="Said later">
            {(item.addenda ?? []).map((entry) => (
              <li key={entry.id}>
                <strong>
                  {labelOf(SAID_BY, entry.said_by_role)} · {labelOf(ADDENDUM_KINDS, entry.kind).toLowerCase()} ·{" "}
                  {formatDate(entry.said_at)}
                </strong>
                <q className="uw-cr-text">{entry.text}</q>
                <span className="uw-cr-meta">
                  Added by {entry.added_by ?? "a colleague"}
                  {entry.masked ? " · personal data masked" : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        {canLog && !voided && (
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={() => setAdding("addendum")}>
              Add what they said later
            </button>
            <button type="button" className="ac-secondary" onClick={() => setAdding("correct")}>
              Correct a fact
            </button>
          </div>
        )}
        {adding === "addendum" && <AddendumForm id={item.id} onCancel={() => setAdding(null)} onDone={onChanged} />}
        {adding === "correct" && <CorrectForm item={item} onCancel={() => setAdding(null)} onDone={onChanged} />}
      </section>
      <section className="ca-drawer-section">
        <h3>Times</h3>
        <ul>
          {(
            [
              ["First knowledge", item.times.first_knowledge],
              ["Received", item.times.received],
              ["Awareness", item.times.awareness],
              ["Reached MDARIX", item.times.available],
              ["Event", item.times.event],
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
        {item.clock && (
          <p>
            <ToneBadge tone={clockTone(item.clock.state ?? "RUNNING")} label={clockChip(item.clock)} />{" "}
            <span className="uw-cr-meta">{item.clock.basis}</span>
          </p>
        )}
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
          <h3>The ten questions</h3>
          <Questions guide={guide} answers={answers} disabled={!editing || !canWrite || voided} onChange={setAnswers} />
          <details className="uw-ma-history">
            <summary>The outcomes table (fixed)</summary>
            <ol>
              {guide.table.map((entry) => (
                <li key={entry.row} className={entry.row === item.outcome_row ? "is-taken" : undefined}>
                  {entry.answers}: <strong>{entry.outcome}</strong>
                </li>
              ))}
            </ol>
          </details>
          {canWrite && !voided && (
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
      {item.kind !== "URGENT" && item.suggestion && (
        <section className="ca-drawer-section">
          <h3>Suggestion</h3>
          <p className="uw-fc-outcome">
            <strong>{item.suggestion_label}</strong>
            {row ? ` (row ${row.row}: ${row.answers})` : ""}
            {item.signed ? `. Signed: ${item.signed.classification_label}, version ${item.signed.version}.` : ""}
          </p>
        </section>
      )}
      {canWrite && item.draft && item.version > 0 && !voided && (
        <SignForm item={item} guide={guide} answers={answers} onSigned={onChanged} />
      )}
      {canWrite && item.escalate_signed && !item.draft && !voided && <SignedBefore item={item} onDone={onChanged} />}
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
      {item.kind !== "URGENT" && <CaseMoves item={item} canLog={canLog} canReview={canReview} onDone={onChanged} />}
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

/** After the escalation (spec 4.5): "CASE-… is now a complaint", and the main button "Next: Triage". */
function Escalated({ item }: { item: IntakeItem }) {
  const { open } = useWorkspace();
  const ref = item.complaint_ref ?? item.reference;
  return (
    <section className="ca-drawer-section" aria-label="Escalated">
      <h3>
        <CheckCircle2 size={15} aria-hidden="true" /> {item.reference} is now a complaint
        {ref !== item.reference ? ` (${ref})` : ""}
      </h3>
      <div className="ca-action-row">
        <button
          type="button"
          className="ac-primary"
          onClick={() => open("Complaint", `Summary?${new URLSearchParams({ ref })}`)}
        >
          Next: Triage
        </button>
      </div>
    </section>
  );
}

/** "Add what they said later" (IN-17, IN-18): a new row; the reporter's first words are never edited. */
function AddendumForm({ id, onCancel, onDone }: { id: string; onCancel: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ kind: "STATEMENT", said_by_role: "REPORTER", text: "" });
  const [error, setError] = useState("");
  const short = form.text.trim().length < REASON_MIN;
  return (
    <form
      className="ca-form-grid"
      aria-label="Add what they said later"
      onSubmit={async (event) => {
        event.preventDefault();
        if (short) return;
        setError("");
        try {
          await send(`${INTAKE}/${id}/addenda`, "POST", { ...form, said_zone: ZONE });
          onDone();
        } catch (reason) {
          setError(errorText(reason, "Not added"));
        }
      }}
    >
      <label className="ca-field">
        What it is
        <select value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value })}>
          {ADDENDUM_KINDS.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        Who said it
        <select value={form.said_by_role} onChange={(event) => setForm({ ...form, said_by_role: event.target.value })}>
          {SAID_BY.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field ca-wide">
        What they said, in their words
        <textarea rows={3} value={form.text} onChange={(event) => setForm({ ...form, text: event.target.value })} />
      </label>
      <p className="uw-hint ca-wide">
        Names, phone numbers and e-mail addresses are masked when you save.
        {form.kind === "WITHDRAWAL" ? " A complaint already made stands: the withdrawal is kept beside it." : ""}
      </p>
      <div className="ca-action-row ca-wide">
        <button type="submit" className="ac-primary" disabled={short}>
          Add it
        </button>
        <button type="button" className="ac-link" onClick={onCancel}>
          Cancel
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

/** "Correct a fact" (spec 2.5): the new value with why; the old one stays in the record's changes. */
function CorrectForm({ item, onCancel, onDone }: { item: IntakeItem; onCancel: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ field: CORRECTABLE[0][0], value: "", reason: "" });
  const [error, setError] = useState("");
  const short = form.reason.trim().length < REASON_MIN;
  return (
    <form
      className="ca-form-grid"
      aria-label="Correct a fact"
      onSubmit={async (event) => {
        event.preventDefault();
        if (short) return;
        setError("");
        try {
          await send(`${INTAKE}/${item.id}/correct`, "POST", { ...form, seen_version: item.row_version ?? null });
          onDone();
        } catch (reason) {
          setError(errorText(reason, "Not corrected"));
        }
      }}
    >
      <label className="ca-field">
        The fact
        <select value={form.field} onChange={(event) => setForm({ ...form, field: event.target.value })}>
          {CORRECTABLE.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="ca-field">
        The right value (empty clears it)
        <input value={form.value} onChange={(event) => setForm({ ...form, value: event.target.value })} />
      </label>
      <label className="ca-field ca-wide">
        Why it is corrected
        <input value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
      </label>
      <p className="uw-hint ca-wide">The reporter's words are never edited. The old value stays in the record.</p>
      <div className="ca-action-row ca-wide">
        <button type="submit" className="ac-primary" disabled={short}>
          Save the correction
        </button>
        <button type="button" className="ac-link" onClick={onCancel}>
          Cancel
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

/**
 * S-2 and spec 3.2: "Waiting for internal team" (and back when they answered), and "Withdraw: entered in error"
 * (signed; before escalation only; outside the trial by someone other than the logger, which the server checks).
 */
function CaseMoves({
  item,
  canLog,
  canReview,
  onDone,
}: {
  item: IntakeItem;
  canLog: boolean;
  canReview: boolean;
  onDone: () => void;
}) {
  const status = item.status ?? "OPEN";
  const [doing, setDoing] = useState<"wait" | "void" | null>(null);
  const [form, setForm] = useState({ reason: "", password: "", code: "" });
  const [error, setError] = useState("");
  const waiting = status === "WAITING_INTERNAL";
  const canWait = canLog && ["OPEN", "PENDING", "IN_REVIEW", "WAITING_INTERNAL"].includes(status);
  const canVoid = canReview && ["OPEN", "PENDING", "WAITING_INTERNAL"].includes(status);
  if (!canWait && !canVoid) return null;
  const short = form.reason.trim().length < REASON_MIN;
  const submit = async () => {
    setError("");
    try {
      if (doing === "wait")
        await send(`${INTAKE}/${item.id}/waiting`, "POST", { waiting: !waiting, reason: form.reason });
      else
        await send(`${INTAKE}/${item.id}/void`, "POST", {
          reason: form.reason,
          password: form.password,
          mfa_code: form.code || null,
        });
      onDone();
    } catch (reason) {
      setError(errorText(reason, "Not saved"));
    }
  };
  return (
    <section className="ca-drawer-section" aria-label="Move the case">
      <div className="ca-action-row">
        {canWait && (
          <button type="button" className="ac-secondary" onClick={() => setDoing("wait")}>
            <Hourglass size={15} aria-hidden="true" />{" "}
            {waiting ? "The internal team answered" : "Waiting for internal team"}
          </button>
        )}
        {canVoid && (
          <button type="button" className="ac-link" onClick={() => setDoing("void")}>
            Withdraw: entered in error
          </button>
        )}
      </div>
      {doing && (
        <div className="ca-form-grid">
          <label className="ca-field ca-wide">
            {doing === "void"
              ? "Why it was entered in error"
              : waiting
                ? "What the team answered"
                : "What the team is asked (engineering, technical support)"}
            <input value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
          </label>
          {doing === "void" && (
            <>
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
            </>
          )}
          <div className="ca-action-row ca-wide">
            <button
              type="button"
              className="ac-primary"
              disabled={short || (doing === "void" && !form.password)}
              onClick={() => void submit()}
            >
              {doing === "void" ? "Sign the withdrawal" : waiting ? "Back to the case" : "Send to the team"}
            </button>
            <button type="button" className="ac-link" onClick={() => setDoing(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      <InlineError text={error} />
    </section>
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
  const likely = item.likely_complaints ?? [];
  const [form, setForm] = useState({
    classification: (item.suggestion ?? "") as Outcome | "",
    override: "",
    reason: "",
    ticket: item.service_ticket ?? "",
    attach: preselected(likely),
    password: "",
    code: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Older drafts (the first guide) carry no choices: every outcome is listed and the server decides.
  const choices: Choice[] =
    item.choices ??
    guide.outcomes.map((outcome) => ({
      code: outcome.code,
      label: outcome.label,
      suggested: outcome.code === item.suggestion,
      escalates: outcome.code === "COMPLAINT" || outcome.code === "BOTH",
      disabled_reason: null,
    }));
  const chosen = choices.find((choice) => choice.code === form.classification);
  const escalates = !!chosen?.escalates;
  const saved = JSON.stringify(answers) === JSON.stringify({ ...blankAnswers(guide.questions), ...item.answers });
  const problem = !saved
    ? "Save the answers first"
    : (signProblem(item, form, unanswered(item.answers, guide.questions)) ??
      (escalates && likely.length > 0 && !form.attach
        ? "Attach this case to the complaint it may be, or create a new complaint"
        : null));
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
            ...(escalates && form.attach === NEW ? { create_new: true } : {}),
            ...(escalates && form.attach && form.attach !== NEW ? { attach_to: form.attach } : {}),
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
        <CheckCircle2 size={15} aria-hidden="true" /> Your classification
      </h3>
      <div className="uw-fc-answers uw-case-choices" role="radiogroup" aria-label="Your classification">
        {choices.map((choice) => (
          <label key={choice.code} className={choice.disabled_reason ? "is-disabled" : undefined}>
            <input
              type="radio"
              name="classification"
              disabled={!!choice.disabled_reason}
              checked={form.classification === choice.code}
              onChange={() => setForm({ ...form, classification: choice.code })}
            />
            {choice.label}
            {choice.suggested ? " (suggested)" : ""}
            {choice.disabled_reason && <span className="uw-cr-meta"> · {choice.disabled_reason}</span>}
          </label>
        ))}
      </div>
      <p className="uw-hint">Fixed on the call is still a complaint when a deficiency was alleged.</p>
      <p className="uw-hint">The customer calling it &lsquo;not a complaint&rsquo; does not change the answers.</p>
      {form.classification && form.classification !== item.suggestion && (
        <label className="ca-field">
          Why you override the suggestion
          <input value={form.override} onChange={(event) => setForm({ ...form, override: event.target.value })} />
        </label>
      )}
      {(form.classification === "SERVICE_ONLY" ||
        form.classification === "INQUIRY" ||
        form.classification === "NOT_A_COMPLAINT") && (
        <label className="ca-field">
          The written reason for &ldquo;{chosen?.label}&rdquo; (it goes to the QA review)
          <input value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
        </label>
      )}
      {form.classification === "BOTH" && (
        <label className="ca-field">
          Service ticket
          <input value={form.ticket} onChange={(event) => setForm({ ...form, ticket: event.target.value })} />
        </label>
      )}
      {escalates && (
        <EscalationPanel
          item={item}
          likely={likely}
          attach={form.attach}
          onAttach={(attach) => setForm({ ...form, attach })}
        />
      )}
      <div className="ca-form-grid">
        <DecideAndSign
          signs={`The case check of ${item.reference}: ${chosen?.label ?? "your classification"}.${
            escalates ? " It becomes a complaint in MDARIX now." : ""
          }`}
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
          {busy ? "Signing…" : escalates ? "Sign and escalate" : "Sign the case check"}
        </button>
      </div>
      <InlineError text={error} />
    </form>
  );
}

const NEW = "new";

/** Spec 3.3 step 2: one strong match (the only one, or the only one on the case's event day) is pre-selected
 * "Attach to …"; otherwise the signer chooses. */
function preselected(likely: NonNullable<IntakeItem["likely_complaints"]>): string {
  const sameDay = likely.filter((candidate) => candidate.same_day);
  return likely.length === 1 ? likely[0].id : sameDay.length === 1 ? sameDay[0].id : "";
}

/** "Signed before 0.10.93: escalate" (spec 9.3): a Case signed a complaint before signing escalated, never linked.
 * The signed check is the decision, so nothing is signed again; only the duplicate choice is made. */
function SignedBefore({ item, onDone }: { item: IntakeItem; onDone: () => void }) {
  const likely = item.likely_complaints ?? [];
  const [attach, setAttach] = useState(preselected(likely));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem =
    likely.length > 0 && !attach ? "Attach this case to the complaint it may be, or create a new complaint" : null;
  const escalate = async () => {
    setBusy(true);
    setError("");
    try {
      await send(
        `${INTAKE}/${item.id}/escalate`,
        "POST",
        attach === NEW ? { create_new: true } : attach ? { attach_to: attach } : {},
      );
      onDone();
    } catch (reason) {
      setError(errorText(reason, "Not escalated"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ca-drawer-section" aria-label="Signed before 0.10.93: escalate">
      <h3>
        <Siren size={15} aria-hidden="true" /> Signed before 0.10.93: escalate
      </h3>
      <p>
        Signed {item.signed?.classification_label?.toLowerCase() ?? "a complaint"} before a signature made the complaint
        at once. Escalate it now: the signed check stands, nothing is signed again.
      </p>
      <EscalationPanel item={item} likely={likely} attach={attach} onAttach={setAttach} />
      {problem && <p className="uw-hint">{problem}</p>}
      <div className="ca-action-row">
        <button type="button" className="ac-primary" disabled={busy || !!problem} onClick={() => void escalate()}>
          {busy ? "Escalating…" : "Escalate"}
        </button>
      </div>
      <InlineError text={error} />
    </section>
  );
}

/** The escalation panel inside the sign step (spec 4.5): what is carried, and the duplicate choice (attach or new). */
function EscalationPanel({
  item,
  likely,
  attach,
  onAttach,
}: {
  item: IntakeItem;
  likely: NonNullable<IntakeItem["likely_complaints"]>;
  attach: string;
  onAttach: (attach: string) => void;
}) {
  return (
    <section className="uw-case-escalation" aria-label="This case becomes a complaint">
      <h4>This case becomes a complaint</h4>
      <p>
        Nothing is typed again. {item.reference} keeps its reference and its awareness time, and its clock keeps
        running.
      </p>
      <p>
        <strong>Carried to the complaint:</strong> the words · the product, version and lot · the times · the incident
        country · the service ticket · the answers · the parties.
      </p>
      {likely.length > 0 && (
        <div className="uw-fc-answers" role="radiogroup" aria-label="Possible duplicate">
          {likely.map((candidate) => (
            <div key={candidate.id}>
              <p>
                Possibly the same event as {candidate.ref}: {candidate.reasons.join(", ")}
              </p>
              <label>
                <input
                  type="radio"
                  name="attach"
                  checked={attach === candidate.id}
                  onChange={() => onAttach(candidate.id)}
                />
                Attach this case to {candidate.ref}
              </label>
            </div>
          ))}
          <label>
            <input type="radio" name="attach" checked={attach === NEW} onChange={() => onAttach(NEW)} />
            Create a new complaint
          </label>
        </div>
      )}
    </section>
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
