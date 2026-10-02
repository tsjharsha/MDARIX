import { useState } from "react";
import { ArrowRight, CheckCircle2, Plus, ShieldAlert } from "lucide-react";
import { errorText, listOf, send, useResource } from "../customer-admin/shared";
import {
  autoMatch,
  buildRules,
  columnLabel,
  defaultTransform,
  type FieldRule,
  type MappingCheck,
  withFilter,
} from "./mappingModel";
import "./mapping.css";

type Target = { entity: string; label: string; required: string[]; optional: string[] };
type Targets = { targets: Target[]; transforms: Array<{ code: string; label: string }> };
type StandardMapping = { code: string; target_entity: string; mapping_rules: Record<string, any> };

/**
 * A new connector mapping in three steps: what to connect, which customer field fills which MDARIX field, then a
 * check and save as a draft. It saves exactly the format the connector import uses, so a released mapping imports.
 * Used by Customer Administrators (their own systems) and by platform administrators.
 */
export function MappingWizard({
  onClose,
  onSaved,
  savePath = "/api/v1/admin/configuration/mappings",
}: {
  onClose: () => void;
  onSaved: (code: string) => void;
  /** Where the draft is saved: the signed-in administrator's tenant by default, or a customer tenant for staff. */
  savePath?: string;
}) {
  const apps = useResource<any[]>("/api/v1/admin/mapping/applications");
  const targets = useResource<Targets>("/api/v1/admin/configuration/mapping-targets");
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({ code: "", source_system: "", source_object: "", target_entity: "" });
  const [rules, setRules] = useState<FieldRule[]>([]);
  const [filter, setFilter] = useState({ field: "", values: "" });
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [standardUsed, setStandardUsed] = useState("");
  const [check, setCheck] = useState<MappingCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const objects = useResource<any[]>(
    form.source_system ? `/api/v1/admin/mapping/applications/${encodeURIComponent(form.source_system)}/objects` : null,
  );
  const sourceFields = useResource<any[]>(
    form.source_object ? `/api/v1/admin/mapping/objects/${encodeURIComponent(form.source_object)}/fields` : null,
  );
  const recordCode = form.source_object.split(":")[1]?.toLowerCase() ?? "";
  const standard = useResource<{ mappings: StandardMapping[] }>(
    form.source_system && recordCode
      ? `/api/v1/admin/configuration/standard-mappings?application=${encodeURIComponent(form.source_system)}&record=${encodeURIComponent(recordCode)}`
      : null,
  );
  const applyStandard = (mapping: StandardMapping) => {
    const { _filter, _defaults, ...fieldRules } = mapping.mapping_rules;
    setForm({ ...form, code: form.code || mapping.code, target_entity: mapping.target_entity });
    setRules(
      Object.entries(fieldRules).map(([source, rule]: [string, any]) => ({
        source,
        column: String(rule.target_field).split(".")[1] ?? "",
        transform: rule.transform ?? "identity",
      })),
    );
    setFilter(_filter ? { field: _filter.field, values: (_filter.in ?? []).join(", ") } : { field: "", values: "" });
    setDefaults(_defaults ?? {});
    setStandardUsed(mapping.code);
    setStep(2);
  };
  const target = targets.data?.targets.find((item) => item.entity === form.target_entity);
  const columns = target ? [...target.required, ...target.optional] : [];
  const sources = listOf(sourceFields.data).map((field) => ({
    name: String(field.field_name),
    label: String(field.field_label ?? field.field_name),
  }));
  const transforms = targets.data?.transforms ?? [{ code: "identity", label: "As is" }];
  const objectRow = listOf(objects.data).find((row) => row.source_object_id === form.source_object);
  const usedSources = rules.map((rule) => rule.source).filter(Boolean);
  const duplicateSource = usedSources.some((name, index) => usedSources.indexOf(name) !== index);
  const ready1 = form.code.trim().length >= 3 && form.source_object && form.target_entity;
  const update = (index: number, change: Partial<FieldRule>) =>
    setRules(rules.map((rule, at) => (at === index ? { ...rule, ...change } : rule)));
  const payload = () => ({
    target_entity: form.target_entity,
    mapping_rules: {
      ...withFilter(buildRules(form.target_entity, rules), filter.field, filter.values),
      ...(Object.keys(defaults).length ? { _defaults: defaults } : {}),
    },
  });
  const runCheck = async () => {
    setBusy(true);
    setError("");
    try {
      setCheck(await send<MappingCheck>("/api/v1/admin/configuration/mappings/check", "POST", payload()));
      setStep(3);
    } catch (reason) {
      setError(errorText(reason, "The mapping could not be checked."));
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    setBusy(true);
    setError("");
    const code = form.code
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, "_");
    try {
      await send(savePath, "POST", {
        code,
        source_system: form.source_system,
        version: "v1",
        source_table: objectRow?.object_name ?? null,
        target_table: form.target_entity,
        ...payload(),
      });
      onSaved(code);
    } catch (reason) {
      setError(errorText(reason, "The mapping was not saved."));
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation" onKeyDown={(event) => event.key === "Escape" && onClose()}>
      <div className="ac-modal mw-modal" role="dialog" aria-modal="true" aria-labelledby="mw-title">
        <p className="ac-eyebrow">Step {step} of 3</p>
        <h2 id="mw-title">New mapping</h2>
        <ol className="mw-steps" aria-label="Steps">
          {["What to connect", "Fields", "Check and save"].map((label, index) => (
            <li key={label} className={step === index + 1 ? "current" : step > index + 1 ? "done" : ""}>
              {label}
            </li>
          ))}
        </ol>
        {step === 1 && (
          <>
            <label className="ca-field">
              Name
              <input
                value={form.code}
                onChange={(event) => setForm({ ...form, code: event.target.value })}
                placeholder="e.g. TRACKWISE_COMPLAINTS"
              />
            </label>
            <div className="mw-two">
              <label className="ca-field">
                Customer system
                <select
                  value={form.source_system}
                  onChange={(event) => setForm({ ...form, source_system: event.target.value, source_object: "" })}
                >
                  <option value="">{apps.state === "loading" ? "Loading…" : "Choose a system"}</option>
                  {listOf(apps.data).map((app) => (
                    <option key={app.application_id} value={app.application_id}>
                      {app.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ca-field">
                Record in that system
                <select
                  value={form.source_object}
                  disabled={!form.source_system}
                  onChange={(event) => {
                    setForm({ ...form, source_object: event.target.value });
                    setRules([]);
                    setDefaults({});
                    setStandardUsed("");
                  }}
                >
                  <option value="">Choose a record</option>
                  {listOf(objects.data).map((row) => (
                    <option key={row.source_object_id} value={row.source_object_id}>
                      {row.object_name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="ca-field">
              MDARIX record it fills
              <select
                value={form.target_entity}
                onChange={(event) => {
                  setForm({ ...form, target_entity: event.target.value });
                  setRules([]);
                }}
              >
                <option value="">Choose a record</option>
                {(targets.data?.targets ?? []).map((item) => (
                  <option key={item.entity} value={item.entity}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            {(standard.data?.mappings ?? []).length > 0 && (
              <section className="mw-standard" aria-label="Standard mapping">
                <strong>MDARIX standard mapping available</strong>
                <p className="ac-muted">
                  Fills every field from this system's standard layout (the CSV templates). You can change anything
                  before saving; it is still approved and released like any mapping.
                </p>
                <div className="mw-actions">
                  {(standard.data?.mappings ?? []).map((mapping) => (
                    <button
                      key={mapping.code}
                      type="button"
                      className="ac-secondary"
                      onClick={() => applyStandard(mapping)}
                    >
                      Use the standard mapping for {mapping.target_entity}
                    </button>
                  ))}
                </div>
              </section>
            )}
            {apps.state === "error" && (
              <p className="ca-inline-error" role="alert">
                The list of systems could not be loaded: {apps.error}
              </p>
            )}
          </>
        )}
        {step === 2 && (
          <>
            <p>Choose which customer field fills each MDARIX field, and how the value is carried over.</p>
            {standardUsed && (
              <p className="ac-muted">
                Started from the standard mapping {standardUsed}
                {Object.keys(defaults).length > 0 &&
                  `; fixed values: ${Object.entries(defaults)
                    .map(([column, value]) => `${columnLabel(column)} = ${value}`)
                    .join(", ")}`}
                .
              </p>
            )}
            <div className="mw-actions">
              <button
                type="button"
                className="ac-secondary"
                onClick={() => setRules(autoMatch(rules, target?.required ?? [], sources))}
              >
                Add the required fields
              </button>
              <button
                type="button"
                className="ac-secondary"
                onClick={() => setRules([...rules, { source: "", column: "", transform: "identity" }])}
              >
                <Plus size={14} aria-hidden="true" /> Add a field
              </button>
            </div>
            <div className="mw-rules" role="table" aria-label="Field rules">
              {rules.map((rule, index) => (
                <div key={index} className="mw-rule" role="row">
                  <select
                    aria-label="Customer field"
                    value={rule.source}
                    onChange={(event) => update(index, { source: event.target.value })}
                  >
                    <option value="">Customer field…</option>
                    {sources.map((field) => (
                      <option key={field.name} value={field.name}>
                        {field.label}
                      </option>
                    ))}
                  </select>
                  <ArrowRight size={14} aria-hidden="true" />
                  <select
                    aria-label="MDARIX field"
                    value={rule.column}
                    onChange={(event) =>
                      update(index, { column: event.target.value, transform: defaultTransform(event.target.value) })
                    }
                  >
                    <option value="">MDARIX field…</option>
                    {columns.map((column) => (
                      <option key={column} value={column}>
                        {columnLabel(column)}
                        {target?.required.includes(column) ? " (required)" : ""}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="How"
                    value={rule.transform}
                    onChange={(event) => update(index, { transform: event.target.value })}
                  >
                    {transforms.map((item) => (
                      <option key={item.code} value={item.code}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="ac-link mw-remove"
                    onClick={() => setRules(rules.filter((_, at) => at !== index))}
                    aria-label="Remove this field"
                  >
                    Remove
                  </button>
                </div>
              ))}
              {!rules.length && <p className="ac-muted">No fields yet. Start with “Add the required fields”.</p>}
            </div>
            {duplicateSource && (
              <p className="ca-inline-error" role="alert">
                Each customer field can fill one MDARIX field; remove the repeated one.
              </p>
            )}
            <fieldset className="mw-filter">
              <legend>Only some records (optional)</legend>
              <p className="ac-muted">
                For a list that mixes kinds of records, for example items that are products and components, import only
                the records whose field holds one of these values.
              </p>
              <div className="mw-two">
                <label className="ca-field">
                  Customer field
                  <select
                    value={filter.field}
                    onChange={(event) => setFilter({ ...filter, field: event.target.value })}
                  >
                    <option value="">Import every record</option>
                    {sources.map((field) => (
                      <option key={field.name} value={field.name}>
                        {field.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="ca-field">
                  Values to keep (comma-separated)
                  <input
                    value={filter.values}
                    disabled={!filter.field}
                    placeholder="e.g. Product"
                    onChange={(event) => setFilter({ ...filter, values: event.target.value })}
                  />
                </label>
              </div>
            </fieldset>
          </>
        )}
        {step === 3 && check && <MappingCheckResult result={check} />}
        {step === 3 && check && check.status !== "READY" && (
          <p className="ac-muted">You can save it as a draft and finish it later; it cannot be released until ready.</p>
        )}
        {step === 3 && check?.status === "READY" && (
          <p className="ac-muted">
            Next: request approval under Releases, then choose this mapping on the connection and press Sync now.
          </p>
        )}
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={step === 1 ? onClose : () => setStep(step - 1)}>
            {step === 1 ? "Cancel" : "Back"}
          </button>
          {step === 1 && (
            <button type="button" className="ac-primary" disabled={!ready1} onClick={() => setStep(2)}>
              Next: fields
            </button>
          )}
          {step === 2 && (
            <button
              type="button"
              className="ac-primary"
              disabled={busy || !rules.length || duplicateSource || rules.some((rule) => !rule.source || !rule.column)}
              onClick={runCheck}
            >
              {busy ? "Checking…" : "Next: check"}
            </button>
          )}
          {step === 3 && (
            <button type="button" className="ac-primary" disabled={busy} onClick={save}>
              {busy ? "Saving…" : "Save as draft"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** The server's answer to "can this mapping import records?", in words. */
export function MappingCheckResult({ result }: { result: MappingCheck }) {
  const ready = result.status === "READY";
  return (
    <section className={`mw-result ${ready ? "ready" : "blocked"}`} aria-live="polite">
      <strong>
        {ready ? <CheckCircle2 size={16} aria-hidden="true" /> : <ShieldAlert size={16} aria-hidden="true" />}{" "}
        {ready ? "Ready: this mapping can import records" : "Needs changes before it can import"}
      </strong>
      <span className="ac-muted">{result.rule_count} field rules checked.</span>
      {result.problems.length > 0 && (
        <ul>
          {result.problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      {result.missing_required.length > 0 && (
        <p>Required MDARIX fields not filled: {result.missing_required.map(columnLabel).join(", ")}.</p>
      )}
    </section>
  );
}
