import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Boxes, Download, Factory, PackageCheck, Save, ShieldCheck, Truck } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { useCan, useWorkspace } from "../workspaceContext";
import { InlineError } from "./boardParts";
import { countOf } from "./common";
import {
  KIND_GROUPS,
  LOT_IMPACT_ANCHOR,
  countriesText,
  exclusionBody,
  exclusionProblem,
  exclusionsOf,
  factorKey,
  factorOf,
  groupLots,
  lotImpactBase,
  lotImpactPath,
  optionText,
  unitsText,
  type Factor,
  type ImpactList,
  type ImpactLot,
  type LotImpactView,
} from "../lotImpact";

/**
 * A case's Lot impact (free trial, T-G5), a section of the case's Scope step: the person picks the suspect factor (a component lot, a supplier or a
 * product version; MDARIX suggests the one the case's lots share) and MDARIX lists every lot that shares it, with and
 * without complaints, its units released, shipped by country and consignee, and still in stock. Lots left out need a
 * reason; the list is kept with the case scope and signed. MDARIX lists; the person decides any field action in the QMS.
 */
export function LotImpactPanel({
  investigationId,
  caseLabel,
  focus = false,
  onChanged,
}: {
  investigationId: string;
  caseLabel: string;
  /** Scroll to the section once it is read (the case summary's Lot impact button). */
  focus?: boolean;
  /** Told when the list is kept or signed: each writes a new version of the case scope. */
  onChanged?: () => void;
}) {
  const { open, notify } = useWorkspace();
  const [preview, setPreview] = useState<Factor | null>(null);
  const screen = useResource<LotImpactView>(lotImpactPath(investigationId, preview));
  const view = screen.data;
  const canWork = useCan("investigation.work");
  const signer = [useCan("decision.sign"), useCan("quality.review"), useCan("regulatory.approve")].some(Boolean);
  const [excluded, setExcluded] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const list = view?.list ?? null;
  const fingerprint = list?.fingerprint;
  useEffect(() => {
    setExcluded(view?.source === "saved" ? exclusionsOf(list) : {});
  }, [fingerprint, view?.source]);
  const anchor = useRef<HTMLDivElement>(null);
  const loaded = !!view;
  useEffect(() => {
    if (!focus || !loaded) return;
    anchor.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    // Once more after the scope above has been read too, so the section stays at the top.
    const timer = window.setTimeout(() => anchor.current?.scrollIntoView({ block: "start" }), 700);
    return () => window.clearTimeout(timer);
  }, [focus, loaded]);
  const keep = async () => {
    if (!list) return;
    setBusy(true);
    setError("");
    try {
      await send(lotImpactBase(investigationId), "PUT", {
        factor: { kind: list.factor.kind, id: list.factor.id, lot: list.factor.lot },
        excluded: exclusionBody(excluded),
      });
      setPreview(null);
      screen.reload();
      onChanged?.();
      notify("Kept with the case scope.");
    } catch (reason) {
      setError(errorText(reason, "The list was not kept."));
    } finally {
      setBusy(false);
    }
  };
  const title = `Lot impact: what else is out there for ${caseLabel}`;
  if (!view)
    return (
      <div id={LOT_IMPACT_ANCHOR} className="uw-anchor" ref={anchor}>
        <Panel eyebrow="Case scope" title={title} source={screen}>
          {null}
        </Panel>
      </div>
    );
  const closed = view.investigation.closed;
  const savedKey = factorKey(view.saved?.factor);
  const shownKey = factorKey(list?.factor);
  const editsPending =
    view.source !== "saved" ||
    JSON.stringify(exclusionBody(excluded)) !== JSON.stringify(exclusionBody(exclusionsOf(list)));
  const problem = list ? exclusionProblem(excluded, list.lots, view.reason_min) : "";
  return (
    <div id={LOT_IMPACT_ANCHOR} className="uw-anchor uw-li" ref={anchor}>
      <Panel eyebrow="Case scope" title={title} source={screen}>
        <p className="uw-li-never">
          <ShieldCheck size={16} aria-hidden="true" /> {view.never_decides}
        </p>
        {view.practice_label && <p className="ac-note">{view.practice_label}</p>}
        <label className="ca-field uw-li-factor">
          Suspect factor
          <select
            value={shownKey}
            onChange={(event) =>
              setPreview(event.target.value === savedKey ? null : factorOf(event.target.value, view.options))
            }
          >
            {!shownKey && <option value="">Choose a component lot, a supplier or a product version</option>}
            {KIND_GROUPS.map(([kind, label]) => {
              const items = view.options.filter((item) => item.kind === kind);
              return items.length ? (
                <optgroup key={kind} label={label}>
                  {items.map((item) => (
                    <option key={factorKey(item)} value={factorKey(item)}>
                      {optionText(item)}
                    </option>
                  ))}
                </optgroup>
              ) : null;
            })}
          </select>
        </label>
        <FactorNote view={view} />
        {!view.genealogy && (
          <p className="ac-note">
            No lot genealogy yet: import it (Import data, Lot genealogy) to compare lots by component lot or supplier.{" "}
            <button type="button" className="ac-link" onClick={() => open("Import data")}>
              Open Import data
            </button>
          </p>
        )}
        {list ? (
          <ImpactBody
            view={view}
            list={list}
            excluded={excluded}
            onExclude={canWork && !closed ? setExcluded : undefined}
          />
        ) : (
          <Empty title="Choose the suspect factor" detail="MDARIX then lists every lot that shares it." />
        )}
        {list && canWork && !closed && (
          <>
            {editsPending && (
              <p className="ac-muted">
                {view.source === "saved"
                  ? "Keep the list again to update its totals and the case scope."
                  : "Nothing is kept yet: keep this factor with the case to use it and sign the list."}
              </p>
            )}
            <div className="ca-action-row">
              <button
                type="button"
                className="ac-primary"
                disabled={busy || !!problem || !editsPending}
                onClick={() => void keep()}
              >
                <Save size={15} aria-hidden="true" /> {busy ? "Keeping…" : "Keep this list with the case"}
              </button>
            </div>
            <InlineError text={problem || error} />
          </>
        )}
      </Panel>
      {view.signed && <SignedList view={view} />}
      {view.saved &&
        list &&
        view.source === "saved" &&
        !editsPending &&
        !closed &&
        (!view.signed || view.signed.changed) && (
          <SignForm
            investigationId={investigationId}
            list={list}
            allowed={signer}
            again={!!view.signed}
            onSigned={() => {
              screen.reload();
              onChanged?.();
              notify("The lot impact list is signed.");
            }}
          />
        )}
      {(view.saved || view.signed) && (
        <Downloads investigationId={investigationId} label={view.investigation.business_id} signed={!!view.signed} />
      )}
    </div>
  );
}

function FactorNote({ view }: { view: LotImpactView }) {
  if (view.source === "saved" && view.saved)
    return (
      <p className="ac-muted">
        Kept with the case scope{view.saved.scope_version ? ` (version ${view.saved.scope_version})` : ""}
        {view.saved.saved_by_name ? ` by ${view.saved.saved_by_name}` : ""}
        {view.saved.saved_at ? `, ${formatDate(view.saved.saved_at)}` : ""}.
      </p>
    );
  if (view.source === "suggested" && view.suggestion)
    return (
      <p className="uw-li-suggestion">
        Suggested from the case's lots: <strong>{view.suggestion.label}</strong> ({view.suggestion.why}). You choose:
        pick another factor above if the evidence points elsewhere.
      </p>
    );
  if (view.source === "preview")
    return <p className="ac-muted">A preview: nothing is kept until you keep it with the case.</p>;
  return null;
}

function ImpactBody({
  view,
  list,
  excluded,
  onExclude,
}: {
  view: LotImpactView;
  list: ImpactList;
  excluded: Record<string, string>;
  onExclude?: (next: Record<string, string>) => void;
}) {
  const { totals } = list;
  const groups = groupLots(list.lots);
  return (
    <>
      <div className="uw-trial-stats">
        <StatTile
          label="Lots that share it"
          value={totals.lots}
          detail={totals.excluded ? `${countOf(totals.excluded, "lot")} left out` : "None left out"}
          icon={<Boxes size={18} />}
        />
        <StatTile
          label="With complaints"
          value={totals.with_complaints}
          detail={countOf(totals.complaints, "complaint")}
          icon={<AlertTriangle size={18} />}
          tone={totals.with_complaints ? "warning" : "good"}
        />
        <StatTile
          label="Without complaints yet"
          value={totals.without_complaints}
          detail="Built with the same factor"
          icon={<Factory size={18} />}
        />
        <StatTile
          label="Units released"
          value={unitsText(totals.released)}
          detail={`${unitsText(totals.shipped)} shipped`}
          icon={<Truck size={18} />}
        />
        <StatTile
          label="Still in stock"
          value={unitsText(totals.in_stock)}
          detail={
            totals.not_imported
              ? `${countOf(totals.not_imported, "lot")}: ${view.not_imported.toLowerCase()}`
              : "Released minus shipped"
          }
          icon={<PackageCheck size={18} />}
          tone={totals.not_imported ? "warning" : undefined}
        />
      </div>
      <p className="uw-li-countries">
        <strong>Units shipped by country:</strong> {countriesText(totals.by_country, "no distribution imported")}
      </p>
      {list.truncated && <p className="ac-note">Only the first 2,000 lots are listed.</p>}
      <LotGroup
        title="Lots with complaints"
        lots={groups.withComplaints}
        view={view}
        excluded={excluded}
        onExclude={onExclude}
      />
      <LotGroup
        title="Lots without complaints yet"
        lots={groups.withoutComplaints}
        view={view}
        excluded={excluded}
        onExclude={onExclude}
      />
      {groups.excluded.length > 0 && (
        <LotGroup
          title="Left out of the list"
          lots={groups.excluded}
          view={view}
          excluded={excluded}
          onExclude={onExclude}
        />
      )}
    </>
  );
}

function LotGroup({
  title,
  lots,
  view,
  excluded,
  onExclude,
}: {
  title: string;
  lots: ImpactLot[];
  view: LotImpactView;
  excluded: Record<string, string>;
  onExclude?: (next: Record<string, string>) => void;
}) {
  if (!lots.length) return null;
  const toggle = (lot: ImpactLot) => {
    if (!onExclude) return;
    const next = { ...excluded };
    if (lot.id in next) delete next[lot.id];
    else next[lot.id] = lot.exclusion_reason ?? "";
    onExclude(next);
  };
  return (
    <section className="ca-drawer-section uw-li-group" aria-label={title}>
      <h3>
        {title} · {lots.length}
      </h3>
      <ul className="uw-li-lots">
        {lots.map((lot) => {
          const leaving = lot.id in excluded;
          return (
            <li key={lot.id} className="uw-li-lot">
              <p className="uw-li-lot-head">
                <strong>{lot.lot_identifier}</strong>
                {lot.version && <small className="ac-muted"> {lot.version}</small>}
              </p>
              <dl className="ca-facts">
                <div>
                  <dt>Complaints</dt>
                  <dd>
                    {lot.complaints
                      ? `${lot.complaints}${lot.per_1000 !== null ? ` · ${lot.per_1000} per 1,000 units` : ""}`
                      : "None yet"}
                  </dd>
                </div>
                <div>
                  <dt>Released</dt>
                  <dd>{unitsText(lot.released)}</dd>
                </div>
                <div>
                  <dt>Shipped</dt>
                  <dd>
                    {lot.distribution_imported ? (
                      `${unitsText(lot.shipped)}: ${countriesText(lot.by_country)}`
                    ) : (
                      <ToneBadge tone="warning" label={view.not_imported} />
                    )}
                  </dd>
                </div>
                <div>
                  <dt>In stock</dt>
                  <dd>
                    {lot.distribution_imported ? unitsText(lot.in_stock) : "Not known"}
                    {lot.over_shipped && <small className="tone-bad"> more shipped than released</small>}
                  </dd>
                </div>
              </dl>
              {lot.shipments.length > 0 && (
                <details className="uw-li-shipments">
                  <summary>Consignees ({lot.shipments.length})</summary>
                  <ul>
                    {lot.shipments.map((item) => (
                      <li key={`${item.consignee}|${item.country}|${item.ship_date}`}>
                        {item.ship_date} · {item.country} · {item.consignee}
                        {item.consignee_type ? ` (${item.consignee_type})` : ""}: {unitsText(item.units)}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <p className="uw-li-evidence">{lot.evidence.join("; ")}</p>
              {onExclude ? (
                <div className="uw-li-exclude">
                  <label>
                    <input type="checkbox" checked={leaving} onChange={() => toggle(lot)} /> Leave out of the list
                  </label>
                  {leaving && (
                    <textarea
                      rows={2}
                      aria-label={`Why ${lot.lot_identifier} is left out`}
                      placeholder={`Why (at least ${view.reason_min} characters)`}
                      value={excluded[lot.id]}
                      onChange={(event) => onExclude({ ...excluded, [lot.id]: event.target.value })}
                    />
                  )}
                </div>
              ) : (
                lot.excluded && <p className="uw-li-evidence">Left out: {lot.exclusion_reason}</p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function SignedList({ view }: { view: LotImpactView }) {
  const signed = view.signed!;
  const { signature } = signed;
  return (
    <Panel
      eyebrow="Signed list"
      title={`${countOf(signed.list.totals.lots, "lot")} sharing ${signed.list.factor.label}`}
      action={
        <ToneBadge
          tone={signed.changed ? "warning" : "good"}
          label={signed.changed ? "Changed since signed" : "Matches the records"}
        />
      }
    >
      <p>
        Signed by <strong>{signature.signer_name}</strong>
        {signature.signer_role ? ` (${signature.signer_role})` : ""} on {formatDate(signature.signed_at)}
        {signature.scope_version ? `, kept as case scope version ${signature.scope_version}` : ""}.
      </p>
      <p className="ac-muted">Meaning: {signature.meaning}</p>
      <p className="ac-muted">
        Signature record {signature.record_business_id ?? signature.record_id} · checksum{" "}
        {signature.content_fingerprint.slice(0, 12)}…
      </p>
      {signed.changed && (
        <section className="ca-drawer-section uw-li-changed" aria-label="Changed since signed">
          <h3>Changed since signed</h3>
          <ul>
            {signed.changes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="ac-muted">
            The signed list stays as it was signed. Read the list above and sign it again if it is the one to keep.
          </p>
        </section>
      )}
    </Panel>
  );
}

function SignForm({
  investigationId,
  list,
  allowed,
  again,
  onSigned,
}: {
  investigationId: string;
  list: ImpactList;
  allowed: boolean;
  again: boolean;
  onSigned: () => void;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!allowed)
    return (
      <Panel eyebrow="Signature" title="Sign the list">
        <p className="ac-note">
          A colleague who signs decisions signs the list. Your role can prepare it and keep it with the case.
        </p>
      </Panel>
    );
  const sign = async () => {
    setBusy(true);
    setError("");
    try {
      await send(`${lotImpactBase(investigationId)}/sign`, "POST", {
        password,
        mfa_code: code || null,
        fingerprint: list.fingerprint,
      });
      setPassword("");
      setCode("");
      onSigned();
    } catch (reason) {
      setError(errorText(reason, "The list was not signed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel eyebrow="Signature" title={again ? "Sign the list again" : "Sign the list"}>
      <form
        className="uw-rp-approval"
        aria-label="Sign the lot impact list"
        onSubmit={(event) => {
          event.preventDefault();
          void sign();
        }}
      >
        <p>
          You sign the list of {countOf(list.totals.lots, "lot")} sharing <strong>{list.factor.label}</strong> as the
          records show it now. Your signature is not a field action: decide any field action in your QMS.
        </p>
        <div className="ca-form-grid">
          <label className="ca-field">
            Your password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <label className="ca-field">
            Authenticator code
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
        </div>
        <div className="ca-action-row">
          <button type="submit" className="ac-primary" disabled={busy || !password}>
            <ShieldCheck size={15} aria-hidden="true" /> {busy ? "Signing…" : "Sign the list"}
          </button>
        </div>
        <InlineError text={error} />
      </form>
    </Panel>
  );
}

function Downloads({
  investigationId,
  label,
  signed,
}: {
  investigationId: string;
  label: string | null;
  signed: boolean;
}) {
  const canExport = useCan("data.export");
  const [error, setError] = useState("");
  if (!canExport) return null;
  const get = async (kind: "csv" | "pdf") => {
    setError("");
    try {
      await downloadFile(`${lotImpactBase(investigationId)}/list.${kind}`, {
        fallbackName: `mdarix-lot-impact-${label ?? "case"}.${kind}`,
      });
    } catch (reason) {
      setError(errorText(reason, "The file could not be downloaded."));
    }
  };
  return (
    <Panel eyebrow="Export" title={signed ? "The signed list" : "The list kept with the case"}>
      <div className="ca-action-row uw-doc-downloads">
        <button type="button" className="ac-secondary" onClick={() => void get("pdf")}>
          <Download size={15} aria-hidden="true" /> PDF
        </button>
        <button type="button" className="ac-secondary" onClick={() => void get("csv")}>
          <Download size={15} aria-hidden="true" /> CSV
        </button>
      </div>
      <InlineError text={error} />
    </Panel>
  );
}
