import { useState } from "react";
import { REPORTS, isSimilarTable, similarRows, type ReportDetail, type WorksheetField } from "../authorityReports";
import { SimilarGrid } from "./SimilarTable";
import { formatDateTime } from "../../../app/dates";
import { formName } from "./TreeSign";
import { FieldRow, useAction } from "./Reports";
import { InlineError } from "./boardParts";
import { TraceLink } from "./TraceValue";
import { useWorkspace } from "../workspaceContext";
import "./decide.css";

export type GiveGroup = { scope: "PRODUCT" | "ORGANIZATION" | "EVENT"; title: string; things: WorksheetField[][] };

const TITLES = {
  PRODUCT: "Your product · enter once",
  ORGANIZATION: "Your organization · enter once",
  EVENT: "This event",
} as const;

/** What the report still needs (0.10.83, D2.7): its missing mandatory fields as things to give, grouped by who knows
 * them. Fields entered together (a US registration's product code and number) are one thing. */
export function thingsToGive(detail: Pick<ReportDetail, "sections" | "mandatory">): {
  groups: GiveGroup[];
  things: number;
  fields: number;
} {
  const missing = new Set(detail.mandatory?.missing ?? []);
  const fields = detail.sections.flatMap((section) => section.fields).filter((item) => missing.has(item.id));
  const groups: GiveGroup[] = (["PRODUCT", "ORGANIZATION", "EVENT"] as const).map((scope) => ({
    scope,
    title: TITLES[scope],
    things: [],
  }));
  for (const item of fields) {
    const group = groups.find((entry) => entry.scope === (item.scope ?? "EVENT"))!;
    const key = item.once ? (item.once_key ?? item.id) : item.id;
    const together = group.things.find((thing) => thing[0].once && (thing[0].once_key ?? thing[0].id) === key);
    if (together && item.once) together.push(item);
    else group.things.push([item]);
  }
  const shown = groups.filter((group) => group.things.length);
  return { groups: shown, things: shown.reduce((sum, group) => sum + group.things.length, 0), fields: fields.length };
}

/** The report's body while anything is missing: "N things to give (M fields)", each naming its form box and rule. */
export function ThingsToGive({
  detail,
  onChanged,
  canEdit,
}: {
  detail: ReportDetail;
  onChanged: (detail: ReportDetail) => void;
  canEdit: boolean;
}) {
  const { groups, things, fields } = thingsToGive(detail);
  if (!things) return null;
  const rule = detail.form.clauses[0]?.short;
  return (
    <section className="uw-card rp-give" aria-labelledby="rp-give-title">
      <div className="rp-give-head">
        <h2 id="rp-give-title">
          {things} thing{things === 1 ? "" : "s"} to give ({fields} field{fields === 1 ? "" : "s"})
        </h2>
        {/* The form is the page's heading (0.10.87): only its rule here. */}
        {rule && <span className="ac-muted">{rule}</span>}
      </div>
      {groups.map((group) => (
        <div key={group.scope} className="rp-give-group">
          <h3>{group.title}</h3>
          <ul className="uw-rp-fields">
            {group.things.map((thing) =>
              thing[0].once ? (
                <OnceRow
                  key={thing[0].id}
                  detail={detail}
                  fields={thing}
                  onChanged={onChanged}
                  canEdit={canEdit && detail.editable}
                />
              ) : (
                <FieldRow
                  key={thing[0].id}
                  detail={detail}
                  item={thing[0]}
                  onChanged={onChanged}
                  canEdit={canEdit && detail.editable}
                />
              ),
            )}
          </ul>
        </div>
      ))}
    </section>
  );
}

/** Confirm all codes (0.10.96, D8): every code the mapping suggests, confirmed as suggested in one click; each one
 * confirmed is listed after. A code a person chose stays as chosen. */
export function ConfirmAllCodes({
  detail,
  onChanged,
}: {
  detail: ReportDetail;
  onChanged: (detail: ReportDetail) => void;
}) {
  const action = useAction(onChanged, "The codes were not confirmed.");
  const [done, setDone] = useState<string[]>([]);
  const waiting = detail.sections.flatMap((section) => section.fields).filter((item) => item.status === "SUGGESTED");
  if (!detail.editable || (!waiting.length && !done.length)) return null;
  const names = waiting.map((item) => `${item.number ? `${item.number} ` : ""}${item.label}: ${item.suggestion}`);
  const confirm = async () => {
    if (await action.run(`${REPORTS}/${detail.id}/codes/confirm`, "POST")) setDone(names);
  };
  return (
    <section className="uw-card uw-card-pad rp-confirm-all" aria-label="Suggested codes">
      {waiting.length > 0 && (
        <>
          <p className="ac-muted">Suggested from your approved mapping: {names.join("; ")}.</p>
          <button type="button" className="ac-primary" disabled={action.busy} onClick={() => void confirm()}>
            Confirm all codes ({waiting.length})
          </button>
        </>
      )}
      {done.length > 0 && (
        <p className="dt-success" role="status">
          ✓ Confirmed as suggested: {done.join("; ")}.
        </p>
      )}
      <InlineError text={action.error} />
    </section>
  );
}

/** A product's or the organization's fact, entered once and reused on every report for that product. */
function OnceRow({
  detail,
  fields,
  onChanged,
  canEdit,
}: {
  detail: ReportDetail;
  fields: WorksheetField[];
  onChanged: (detail: ReportDetail) => void;
  canEdit: boolean;
}) {
  const { open } = useWorkspace();
  const [values, setValues] = useState<Record<string, string>>({});
  const action = useAction(onChanged, "It was not saved.");
  const product = fields[0].scope === "PRODUCT";
  const whom = product ? (detail.complaint.product_name ?? "this product") : "your organization";
  const ready = fields.every((item) => (values[item.id] ?? "").trim());
  // What a value given needs before approval (0.10.92, A5: the eMDR's contact office e-mail): said here, with the
  // place it is set, the responsible party in Settings › Products. The e-mail alone is asked for here too.
  const problems = fields.map((item) => item.problem).filter((text): text is string => !!text);
  const askEmail = fields.find((item) => item.ask === "CONTACT_EMAIL");
  const [email, setEmail] = useState("");
  return (
    <li className="uw-rp-field rp-once">
      <div className="uw-rp-field-head">
        <span className="uw-rp-number">{fields.map((item) => item.number).join(" · ")}</span>
        <span className="uw-rp-label">{fields.map((item) => item.label).join(" and ")}</span>
      </div>
      {problems.length > 0 && (
        <p className="ac-message tone-warning" role="status">
          {problems.join(" ")}
        </p>
      )}
      {problems.length > 0 && !product && (
        <button type="button" className="ac-link" onClick={() => open("Settings", "Products")}>
          Set a responsible party in Settings › Products
        </button>
      )}
      {canEdit && askEmail && (
        <form
          className="uw-rp-edit"
          onSubmit={(event) => {
            event.preventDefault();
            if (email.trim()) void action.run(`${REPORTS}/${detail.id}/once`, "PUT", { contact_email: email.trim() });
          }}
        >
          <input
            type="email"
            maxLength={50}
            aria-label={`${askEmail.number} ${askEmail.label}: e-mail`.trim()}
            placeholder="Contact e-mail"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <button type="submit" className="ac-secondary" disabled={action.busy || !email.trim()}>
            Save the e-mail for {whom}
          </button>
        </form>
      )}
      {canEdit && !problems.length && (
        <form
          className="uw-rp-edit"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) void action.run(`${REPORTS}/${detail.id}/once`, "PUT", { values });
          }}
        >
          {fields.map((item) => (
            <input
              key={item.id}
              aria-label={`${item.number} ${item.label}`.trim()}
              placeholder={item.label}
              value={values[item.id] ?? ""}
              onChange={(event) => setValues({ ...values, [item.id]: event.target.value })}
            />
          ))}
          <button type="submit" className="ac-secondary" disabled={action.busy || !ready}>
            Save for {whom}
          </button>
        </form>
      )}
      <p className="uw-cr-meta">
        Entered once for {whom}: used on every report{product ? " for that product" : ""}.
      </p>
      <InlineError text={action.error} />
    </li>
  );
}

/** "Rahul Iyer · 2 Nov 2026, 14:32 · approved for submission": a signature as it is shown everywhere (21 CFR 11.50). */
export const signatureLine = (item: { name: string; at: string | null; meaning: string }) =>
  `${item.name} · ${formatDateTime(item.at)} · ${item.meaning}`;

/** "What you are approving" (0.10.83, D2.8): the values as frozen for approval, in the form's order, each with its
 * source, read like the document before the password and Approve. */
export function ApprovingDoc({ detail }: { detail: ReportDetail }) {
  const sections = detail.pending_snapshot?.sections ?? detail.sections;
  return (
    <section className="uw-card rp-doc" aria-labelledby="rp-doc-title">
      <div className="rp-doc-head">
        <p className="ac-eyebrow">What you are approving</p>
        <h2 id="rp-doc-title">
          {formName(detail.form.title)} · {detail.complaint.ref}
        </h2>
        <p className="ac-muted">
          The values as they will be submitted, in the form's order, each with where it came from.
        </p>
      </div>
      {sections
        .filter((section) => section.fields.length)
        .map((section) => (
          <div key={section.code} className="rp-doc-part">
            <h3>{section.title}</h3>
            <dl>
              {section.fields
                // What is submitted: every value, and every mandatory field; empty optional boxes are left out.
                .filter((item) => item.value || item.missing_class === "MUST_HAVE")
                .map((item) => (
                  <div key={item.id}>
                    <dt>
                      {item.number ? <b>{item.number}</b> : null} {item.label}
                    </dt>
                    <dd>
                      {/* 4.3.3c as its table, never its stored text (B8 run 6, whatever the switch). */}
                      {isSimilarTable(item.value) && (item.kind === "TABLE" || item.id === "4_3_3C") ? (
                        <SimilarGrid rows={similarRows(item.value)} edit={null} />
                      ) : (
                        (item.value ?? "—")
                      )}
                      {item.source ? (
                        <small>
                          {item.source.label}
                          {item.source.ref ? `: ${item.source.ref}` : ""}
                        </small>
                      ) : item.by ? (
                        <small>Entered by {item.by}</small>
                      ) : null}
                      {item.value && (
                        <TraceLink
                          reportId={detail.id}
                          fieldId={item.id}
                          title={`${item.number} ${item.label}`.trim()}
                        />
                      )}
                    </dd>
                  </div>
                ))}
            </dl>
          </div>
        ))}
    </section>
  );
}
