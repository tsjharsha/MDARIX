import type { ReportDetail } from "../authorityReports";

/**
 * tr30 (B9-D9 / B8-D9): while the organization allows it, the report's patient and reporter boxes, typed just before
 * Send for approval. The values travel only in that request and are kept only in the report's frozen snapshot; they
 * are never saved on the draft. Off: nothing here, the boxes say "Enter in the authority's route".
 */
export function PersonalAtSend({
  detail,
  values,
  onChange,
}: {
  detail: ReportDetail;
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  if (!detail.personal_data) return null;
  const fields = detail.sections.flatMap((section) => section.fields).filter((field) => field.personal);
  if (!fields.length) return null;
  const set = (id: string, value: string) => onChange({ ...values, [id]: value });
  return (
    <details className="ca-drawer-section" id="rp-personal">
      <summary>Patient and reporter details (optional)</summary>
      <p className="ac-muted">
        Typed here, they go into this report only: its approved version and the authority&apos;s file. They are never
        kept on the draft, used by AI, analytics or search, or written to an export. A follow-up or final report does
        not carry them: type them again there if the authority needs them.
      </p>
      {fields.map((field) => (
        <label className="ca-field" key={field.id}>
          <span>{`${field.number} ${field.label}`.trim()}</span>
          {field.options?.length ? (
            <select value={values[field.id] ?? ""} onChange={(event) => set(field.id, event.target.value)}>
              <option value="">Not given</option>
              {field.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : (
            <input
              value={values[field.id] ?? ""}
              maxLength={4000}
              autoComplete="off"
              onChange={(event) => set(field.id, event.target.value)}
            />
          )}
        </label>
      ))}
    </details>
  );
}

/** The Send for approval body: only the boxes typed (none: no body, as before). */
export const personalBody = (values: Record<string, string>) => {
  const personal = Object.fromEntries(Object.entries(values).filter(([, value]) => value.trim()));
  return Object.keys(personal).length ? { personal } : undefined;
};
