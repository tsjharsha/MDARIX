import { useState } from "react";
import { errorText, send } from "../../customer-admin/shared";
import { InlineError } from "./boardParts";
import { useCanReport } from "./Reports";

/** A fact a reporting step needs and the complaint's record does not give (0.10.81, the server's facts.py). */
export type FactNeed = {
  fact: "COUNTRY" | "AWARENESS_DATE";
  label: string;
  /** What the record holds, when it is not a country MDARIX knows ("Atlantis"). */
  given: string | null;
  message: string;
  rule: string;
  /** The answers to choose from: "United Kingdom" is Great Britain or Northern Ireland (OD-2, 0.10.88). */
  choices?: string[];
};

const today = () => new Date().toISOString().slice(0, 10);

/**
 * Asks for the incident country or the awareness date at the step that needs it, with why and which rule needs it.
 * MDARIX never guesses them: until they are entered the clocks are provisional and no market conclusion is signed.
 */
export function ReportingFacts({
  complaintId,
  needs,
  onSaved,
  quiet = false,
}: {
  complaintId: string;
  needs: FactNeed[] | null | undefined;
  onSaved: () => void;
  /** Another form on the page holds the main button (the triage record): this one is secondary (0.10.82). */
  quiet?: boolean;
}) {
  const canEnter = useCanReport();
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!needs?.length) return null;
  // B6a G10: every change of the country or the awareness date says why (kept in the audit trail).
  const ready = needs.some((need) => values[need.fact]?.trim()) && Boolean(values.REASON?.trim());
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/complaints/${complaintId}/reporting-facts`, "PUT", {
        country: values.COUNTRY?.trim() || null,
        awareness_date: values.AWARENESS_DATE || null,
        reason: values.REASON?.trim() || null,
      });
      setValues({});
      onSaved();
    } catch (reason) {
      setError(errorText(reason, "It was not saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ac-message tone-warning uw-facts" aria-label="Facts the reporting steps need">
      {needs.map((need) => (
        <div key={need.fact} className="uw-fact">
          <p>
            <b>{need.label} needed.</b> {need.message}
          </p>
          <p className="ac-note">Needed by {need.rule}.</p>
          {canEnter && (
            <label>
              {need.label}{" "}
              {need.choices?.length ? (
                <select
                  value={values[need.fact] ?? ""}
                  onChange={(event) => setValues({ ...values, [need.fact]: event.target.value })}
                >
                  <option value="">Choose…</option>
                  {need.choices.map((choice) => (
                    <option key={choice} value={choice}>
                      {choice}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={need.fact === "AWARENESS_DATE" ? "date" : "text"}
                  max={need.fact === "AWARENESS_DATE" ? today() : undefined}
                  maxLength={need.fact === "COUNTRY" ? 60 : undefined}
                  placeholder={need.fact === "COUNTRY" ? "For example India, IN, Germany or GB" : undefined}
                  value={values[need.fact] ?? ""}
                  onChange={(event) => setValues({ ...values, [need.fact]: event.target.value })}
                />
              )}
            </label>
          )}
        </div>
      ))}
      {canEnter && (
        <label className="uw-fact">
          Why it changes{" "}
          <input
            maxLength={2000}
            placeholder="For example: the reporter's e-mail of 3 November"
            value={values.REASON ?? ""}
            onChange={(event) => setValues({ ...values, REASON: event.target.value })}
          />
        </label>
      )}
      {canEnter ? (
        <button
          type="button"
          className={quiet ? "ac-secondary" : "ac-primary"}
          disabled={busy || !ready}
          onClick={save}
        >
          {busy ? "Saving…" : "Save"}
        </button>
      ) : (
        <p className="ac-note">A colleague with regulatory rights enters it.</p>
      )}
      <InlineError text={error} />
    </section>
  );
}
