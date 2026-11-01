import { useState } from "react";
import { GitCompare, Pencil } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { SearchBox, Table, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { safeText } from "../../../app/displayId";
import { roleLabel } from "../../../app/roles";
import { useCan, useWorkspace } from "../workspaceContext";
import {
  CHANGE_REASON_MAX,
  EXCLUSION_REASON_MAX,
  QUESTION_HINT,
  QUESTION_MAX,
  chooseComplaint,
  compareScopes,
  complaintChoice,
  diffLines,
  parseMarkets,
  scopeBody,
  scopeFormFrom,
  scopeOptions,
  scopeParts,
  scopePath,
  scopeProblems,
  setExclusionReason,
  visibleOptions,
  type CaseScope,
  type ComplaintChoice,
  type ScopeForm,
  type ScopeOption,
  type ScopeSaveResult,
  type ScopeVersion,
  type ScopeVersionSummary,
} from "../scopeModel";

/**
 * The Scope tab of a case: what the investigation covers now, the form for its next version, what a save changed,
 * and every earlier version with a side-by-side comparison of any two. Editing needs investigation.work.
 */
export function CaseScopePanel({
  investigationId,
  caseQuestion,
  onChanged,
}: {
  investigationId: string;
  caseQuestion?: string;
  /** Told when a new scope version is saved here (the Lot impact section below reads the scope's lots). */
  onChanged?: () => void;
}) {
  const canEdit = useCan("investigation.work");
  const scope = useResource<CaseScope>(scopePath(investigationId));
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState<ScopeSaveResult | null>(null);
  const current = scope.data?.current ?? null;
  const versions = [...(scope.data?.versions ?? [])].sort((a, b) => b.version - a.version);
  return (
    <>
      <Panel
        eyebrow="Scope"
        title={current ? `What this case covers · version ${current.version}` : "What this case covers"}
        source={scope}
        action={
          canEdit && !editing ? (
            <button
              type="button"
              className="ac-primary"
              onClick={() => {
                setSaved(null);
                setEditing(true);
              }}
            >
              <Pencil size={15} aria-hidden="true" /> {current ? "Change the scope" : "Set the scope"}
            </button>
          ) : undefined
        }
      >
        {saved && <SaveOutcome result={saved} />}
        {current ? (
          <ScopeView scope={current} />
        ) : (
          <Empty
            title="No scope recorded yet"
            detail={
              canEdit
                ? "Set the scope: the question, the versions, complaints, lots, markets and failure modes this case covers."
                : "The case's investigator sets what it covers."
            }
          />
        )}
      </Panel>
      {editing && (
        <ScopeEditor
          investigationId={investigationId}
          current={current}
          fallbackQuestion={caseQuestion ?? ""}
          onCancel={() => setEditing(false)}
          onSaved={(result) => {
            setEditing(false);
            setSaved(result);
            scope.reload();
            onChanged?.();
          }}
        />
      )}
      {versions.length > 0 && <ScopeHistory investigationId={investigationId} versions={versions} />}
    </>
  );
}

function SaveOutcome({ result }: { result: ScopeSaveResult }) {
  const lines = diffLines(result.diff);
  const warnings = (result.warnings ?? []).map((item) => safeText(item)).filter((item): item is string => !!item);
  return (
    <section className="ca-drawer-section" aria-live="polite">
      <h3>Saved as version {result.scope?.version ?? "—"}</h3>
      {lines.length ? (
        <ul className="ca-timeline">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">No complaints or versions changed.</p>
      )}
      {warnings.map((warning) => (
        <p key={warning} className="ac-message tone-warning" role="status">
          {warning}
        </p>
      ))}
    </section>
  );
}

/** The scope as it stands: each part with its items, and why it last changed. */
function ScopeView({ scope }: { scope: ScopeVersion }) {
  // Lots left out exist only where a lot impact list left one out (a free trial): no empty line elsewhere.
  const parts = scopeParts(scope).filter((part) => part.key !== "lots_left_out" || part.items.length > 0);
  return (
    <>
      <dl className="ca-facts uw-scope-facts">
        {parts.map((part) => (
          <div key={part.key} className={part.key === "question" || part.key === "objectives" ? "uw-wide" : undefined}>
            <dt>{part.label}</dt>
            <dd>
              {part.items.length === 0 ? (
                <span className="ac-muted">None</span>
              ) : part.key === "question" || part.key === "objectives" || part.key === "period" ? (
                part.items[0]
              ) : (
                <ul className="ca-pill-list">
                  {part.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="ac-muted">
        Version {scope.version}
        {scope.created_at ? ` · saved ${formatDate(scope.created_at)}` : ""}
        {safeText(scope.created_by_name) ? ` by ${scope.created_by_name}` : ""}
        {safeText(scope.change_reason) ? ` · ${scope.change_reason}` : ""}
      </p>
      {(scope.reviews_must_restart || scope.conclusions_invalidated) && (
        <ul className="ca-pill-list">
          {scope.reviews_must_restart && <li>Risk and regulatory reviews must restart</li>}
          {scope.conclusions_invalidated && <li>Earlier conclusions are no longer valid</li>}
        </ul>
      )}
    </>
  );
}

const CHOICES: Array<{ value: ComplaintChoice; label: string }> = [
  { value: "none", label: "Not in scope" },
  { value: "included", label: "In scope" },
  { value: "excluded", label: "Kept out (give a reason)" },
];

function ScopeEditor({
  investigationId,
  current,
  fallbackQuestion,
  onCancel,
  onSaved,
}: {
  investigationId: string;
  current: ScopeVersion | null;
  fallbackQuestion: string;
  onCancel: () => void;
  onSaved: (result: ScopeSaveResult) => void;
}) {
  const { work, notify } = useWorkspace();
  const hasVersion = !!current;
  const [form, setForm] = useState<ScopeForm>(() => scopeFormFrom(current, fallbackQuestion));
  const [marketsText, setMarketsText] = useState(() => form.markets.join(", "));
  const [complaintSearch, setComplaintSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tried, setTried] = useState(false);
  const options = scopeOptions(work.view, current);
  const problems = scopeProblems(form, hasVersion);
  const chosenComplaints = [...form.included, ...form.excluded.map((row) => row.id)];
  const complaints = visibleOptions(options.complaints, complaintSearch, chosenComplaints);
  const toggle = (key: "versionIds" | "lotIds" | "failureModeIds", id: string, on: boolean) =>
    setForm((value) => ({
      ...value,
      [key]: on ? [...value[key], id] : value[key].filter((item) => item !== id),
    }));
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (problems.length || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await send<ScopeSaveResult>(scopePath(investigationId), "PUT", scopeBody(form, hasVersion));
      notify(result?.scope?.version ? `Scope saved as version ${result.scope.version}.` : "Scope saved.");
      onSaved(result);
    } catch (failure) {
      setError(errorText(failure, "The scope was not saved."));
      setBusy(false);
    }
  };
  return (
    <Panel
      eyebrow="Scope"
      title={hasVersion ? `Change the scope (next: version ${(current?.version ?? 0) + 1})` : "Set the scope"}
    >
      <form className="ca-form" onSubmit={submit}>
        <label className="ca-field">
          The question this investigation must answer
          <textarea
            required
            rows={3}
            maxLength={QUESTION_MAX}
            value={form.question}
            aria-describedby="scope-question-hint"
            onChange={(event) => setForm({ ...form, question: event.target.value })}
          />
          <small id="scope-question-hint" className="ac-muted">
            {QUESTION_HINT}
          </small>
        </label>

        <PickList
          legend="Product versions"
          empty="No versions are recorded for this product."
          options={options.versions}
          chosen={form.versionIds}
          onToggle={(id, on) => toggle("versionIds", id, on)}
        />

        <fieldset className="ca-fieldset uw-pick-fieldset">
          <legend>Complaints</legend>
          <p className="ac-muted">
            Put a complaint in the scope, or keep it out with a reason. The selected version's complaints are listed,
            with those the scope already names.
          </p>
          {options.complaints.length > 0 && (
            <SearchBox
              value={complaintSearch}
              onChange={setComplaintSearch}
              label="Search complaints by ID or description"
            />
          )}
          <p className="ac-note" role="status">
            {form.included.length} in scope · {form.excluded.length} kept out · showing {complaints.shown.length} of{" "}
            {complaints.total}
          </p>
          {options.complaints.length ? (
            <ul className="uw-pick-list">
              {complaints.shown.map((option) => {
                const choice = complaintChoice(form, option.id);
                const exclusion = form.excluded.find((row) => row.id === option.id);
                return (
                  <li key={option.id} className="uw-scope-complaint">
                    <span>
                      <strong>{option.label}</strong>
                      {option.detail && <small> · {option.detail}</small>}
                    </span>
                    <select
                      aria-label={`${option.label} in the scope`}
                      value={choice}
                      onChange={(event) =>
                        setForm((value) => chooseComplaint(value, option.id, event.target.value as ComplaintChoice))
                      }
                    >
                      {CHOICES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    {choice === "excluded" && (
                      <input
                        aria-label={`Why ${option.label} is kept out`}
                        placeholder="Why it is kept out (at least 5 characters)"
                        maxLength={EXCLUSION_REASON_MAX}
                        value={exclusion?.reason ?? ""}
                        onChange={(event) =>
                          setForm((value) => setExclusionReason(value, option.id, event.target.value))
                        }
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="ac-muted">No complaints recorded for the selected version.</p>
          )}
        </fieldset>

        <PickList
          legend="Lots"
          empty="No lots recorded for the selected version."
          options={options.lots}
          chosen={form.lotIds}
          onToggle={(id, on) => toggle("lotIds", id, on)}
        />

        <label className="ca-field">
          Markets (countries or regions, separated by commas)
          <input
            value={marketsText}
            placeholder="e.g. DE, FR, US"
            onChange={(event) => {
              setMarketsText(event.target.value);
              setForm((value) => ({ ...value, markets: parseMarkets(event.target.value) }));
            }}
          />
        </label>
        {options.markets.filter((market) => !form.markets.some((item) => item.toLowerCase() === market.toLowerCase()))
          .length > 0 && (
          <div className="ca-chips" aria-label="Markets from the complaints">
            {options.markets
              .filter((market) => !form.markets.some((item) => item.toLowerCase() === market.toLowerCase()))
              .map((market) => (
                <button
                  type="button"
                  key={market}
                  onClick={() => {
                    const next = [...form.markets, market];
                    setMarketsText(next.join(", "));
                    setForm((value) => ({ ...value, markets: next }));
                  }}
                >
                  + {market}
                </button>
              ))}
          </div>
        )}

        <PickList
          legend="Failure modes"
          empty="No failure modes are recorded."
          options={options.failureModes}
          chosen={form.failureModeIds}
          onToggle={(id, on) => toggle("failureModeIds", id, on)}
        />

        <div className="ca-form-grid">
          <label className="ca-field">
            Period from (optional)
            <input
              type="date"
              value={form.dateFrom}
              onChange={(event) => setForm({ ...form, dateFrom: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Period to (optional)
            <input
              type="date"
              value={form.dateTo}
              onChange={(event) => setForm({ ...form, dateTo: event.target.value })}
            />
          </label>
        </div>
        <label className="ca-field">
          Objectives (optional)
          <textarea
            rows={2}
            maxLength={2000}
            value={form.objectives}
            onChange={(event) => setForm({ ...form, objectives: event.target.value })}
          />
        </label>
        <label className="ca-field">
          {hasVersion ? "Why the scope changes (required)" : "Note on this first version (optional)"}
          <textarea
            required={hasVersion}
            rows={2}
            maxLength={CHANGE_REASON_MAX}
            value={form.changeReason}
            placeholder={hasVersion ? "At least 10 characters" : undefined}
            onChange={(event) => setForm({ ...form, changeReason: event.target.value })}
          />
        </label>
        <label className="ca-check">
          <input
            type="checkbox"
            checked={form.reviewsMustRestart}
            onChange={(event) => setForm({ ...form, reviewsMustRestart: event.target.checked })}
          />
          Risk and regulatory reviews must restart
        </label>
        <label className="ca-check">
          <input
            type="checkbox"
            checked={form.conclusionsInvalidated}
            onChange={(event) => setForm({ ...form, conclusionsInvalidated: event.target.checked })}
          />
          Existing conclusions are no longer valid
        </label>
        {(tried || form.question.trim()) && problems.length > 0 && (
          <ul className="uw-problems" aria-live="polite">
            {problems.map((problem) => (
              <li key={problem} className="uw-hint">
                {problem}
              </li>
            ))}
          </ul>
        )}
        <p className="ac-muted">Every version is kept; earlier versions stay readable and comparable.</p>
        {error && (
          <p className="ac-message tone-critical" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || problems.length > 0}>
            {busy ? "Saving…" : hasVersion ? "Save new version" : "Save scope"}
          </button>
        </div>
      </form>
    </Panel>
  );
}

function PickList({
  legend,
  empty,
  options,
  chosen,
  onToggle,
}: {
  legend: string;
  empty: string;
  options: ScopeOption[];
  chosen: string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  return (
    <fieldset className="ca-fieldset uw-pick-fieldset">
      <legend>
        {legend} ({chosen.length} selected)
      </legend>
      {options.length ? (
        <ul className="uw-pick-list">
          {options.map((option) => (
            <li key={option.id}>
              <label className="ca-check">
                <input
                  type="checkbox"
                  checked={chosen.includes(option.id)}
                  onChange={(event) => onToggle(option.id, event.target.checked)}
                />
                <span>
                  {option.label}
                  {option.detail && option.detail !== option.label && (
                    <small className="ac-muted"> · {option.detail}</small>
                  )}
                </span>
              </label>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ac-muted">{empty}</p>
      )}
    </fieldset>
  );
}

/** Every version of the scope, newest first, and a side-by-side comparison of any two. */
function ScopeHistory({ investigationId, versions }: { investigationId: string; versions: ScopeVersionSummary[] }) {
  const [left, setLeft] = useState(() => String(versions[1]?.version ?? versions[0]?.version ?? ""));
  const [right, setRight] = useState(() => String(versions[0]?.version ?? ""));
  const [comparing, setComparing] = useState<{ left: number; right: number } | null>(null);
  return (
    <Panel eyebrow="Scope" title="Scope versions">
      <Table
        caption="Scope versions"
        rows={versions}
        rowKey={(row) => String(row.version)}
        empty={{ title: "No versions yet", detail: "Each saved scope is kept as a version." }}
        columns={[
          { key: "version", label: "Version", numeric: true, render: (row) => row.version },
          { key: "created_at", label: "Saved", render: (row) => formatDate(row.created_at) },
          {
            key: "created_by_name",
            label: "By",
            render: (row) => (
              <span className="ca-person">
                <span>{safeText(row.created_by_name) ?? "—"}</span>
                {row.created_role && <small>{roleLabel(row.created_role)}</small>}
              </span>
            ),
          },
          { key: "change_reason", label: "Reason", render: (row) => safeText(row.change_reason) ?? "—" },
          {
            key: "effects",
            label: "Effects",
            fields: ["reviews_must_restart", "conclusions_invalidated"],
            render: (row) =>
              row.reviews_must_restart || row.conclusions_invalidated ? (
                <span className="ca-person">
                  {row.reviews_must_restart && <ToneBadge tone="warning" label="Reviews restart" />}
                  {row.conclusions_invalidated && <ToneBadge tone="serious" label="Conclusions invalid" />}
                </span>
              ) : (
                "—"
              ),
          },
        ]}
      />
      {versions.length > 1 && (
        <div className="ca-action-row uw-compare-row">
          <label className="ca-inline-select">
            Compare version
            <select value={left} onChange={(event) => setLeft(event.target.value)}>
              {versions.map((row) => (
                <option key={row.version} value={row.version}>
                  {row.version}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-inline-select">
            with version
            <select value={right} onChange={(event) => setRight(event.target.value)}>
              {versions.map((row) => (
                <option key={row.version} value={row.version}>
                  {row.version}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="ac-secondary"
            disabled={!left || !right || left === right}
            onClick={() => setComparing({ left: Number(left), right: Number(right) })}
          >
            <GitCompare size={15} aria-hidden="true" /> Compare
          </button>
        </div>
      )}
      {comparing && (
        <ScopeCompare
          key={`${comparing.left}:${comparing.right}`}
          investigationId={investigationId}
          left={comparing.left}
          right={comparing.right}
        />
      )}
    </Panel>
  );
}

function ScopeCompare({ investigationId, left, right }: { investigationId: string; left: number; right: number }) {
  const before = useResource<ScopeVersion>(scopePath(investigationId, left));
  const after = useResource<ScopeVersion>(scopePath(investigationId, right));
  const failed = [before, after].find((item) => item.state === "error" || item.state === "forbidden");
  if (failed) return <p className="ca-inline-error">{failed.error ?? "A version could not be read."}</p>;
  if (!before.data || !after.data)
    return (
      <p className="ac-muted">
        Loading versions {left} and {right}…
      </p>
    );
  const rows = compareScopes(before.data, after.data);
  return (
    <div className="ac-table-wrap">
      <table className="ac-table uw-compare">
        <caption className="ca-sr-only">
          Scope version {left} compared with version {right}
        </caption>
        <thead>
          <tr>
            <th scope="col">Part</th>
            <th scope="col">Version {left}</th>
            <th scope="col">Version {right}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className={row.same ? undefined : "uw-changed"}>
              <th scope="row">
                {row.label}
                {!row.same && <small className="uw-flag-warning"> · changed</small>}
              </th>
              <td>
                {row.left.length ? (
                  row.left.map((item) => (
                    <div key={item} className={row.removed.includes(item) ? "uw-removed" : undefined}>
                      {row.removed.includes(item) ? `− ${item}` : item}
                    </div>
                  ))
                ) : (
                  <span className="ac-muted">None</span>
                )}
              </td>
              <td>
                {row.right.length ? (
                  row.right.map((item) => (
                    <div key={item} className={row.added.includes(item) ? "uw-added" : undefined}>
                      {row.added.includes(item) ? `+ ${item}` : item}
                    </div>
                  ))
                ) : (
                  <span className="ac-muted">None</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
