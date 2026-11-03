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
}: {
  complaintId: string;
  needs: FactNeed[] | null | undefined;
  onSaved: () => void;
}) {
  const canEnter = useCanReport();
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!needs?.length) return null;
  const ready = needs.some((need) => values[need.fact]?.trim());
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      await send(`/api/v1/complaints/${complaintId}/reporting-facts`, "PUT", {
        country: values.COUNTRY?.trim() || null,
        awareness_date: values.AWARENESS_DATE || null,
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
          <p className="ac-note">Needed by {need.rule}. Starter rule, for your consultant to confirm.</p>
          {canEnter && (
            <label>
              {need.label}{" "}
              <input
                type={need.fact === "AWARENESS_DATE" ? "date" : "text"}
                max={need.fact === "AWARENESS_DATE" ? today() : undefined}
                maxLength={need.fact === "COUNTRY" ? 60 : undefined}
                placeholder={need.fact === "COUNTRY" ? "For example India, IN, Germany or GB" : undefined}
                value={values[need.fact] ?? ""}
                onChange={(event) => setValues({ ...values, [need.fact]: event.target.value })}
              />
            </label>
          )}
        </div>
      ))}
      {canEnter ? (
        <button type="button" className="ac-primary" disabled={busy || !ready} onClick={save}>
          {busy ? "Saving…" : "Save"}
        </button>
      ) : (
        <p className="ac-note">A colleague with regulatory rights enters it.</p>
      )}
      <InlineError text={error} />
    </section>
  );
}
