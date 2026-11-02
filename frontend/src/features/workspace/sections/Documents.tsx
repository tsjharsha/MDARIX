import { useState } from "react";
import { DecideAndSign } from "./common";
import { Download, FileCheck2, FileText, FileWarning, PenLine } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { Drawer, errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { downloadFile } from "../../reports/download";
import { useCan, useWorkspace, type WorkspaceSection } from "../workspaceContext";
import { InlineError } from "./boardParts";
import {
  TYPES_PATH,
  DOCUMENTS_PATH,
  clauseText,
  documentLink,
  filePath,
  generateBody,
  judgementProblem,
  recordsText,
  signProblem,
  sourceTarget,
  versionPath,
  versionsPath,
  type DocumentCode,
  type DocumentTypes,
  type DocumentVersion,
  type Row,
  type Section,
  type Source,
  type Template,
  type VersionSummary,
} from "../documents";

/**
 * Records › Reports › Ready-to-use documents (T-G35): the management review report, the CAPA log, the investigation
 * report, the risk-review extract and the change-impact input. Each is generated from the records for a period (or a
 * case or change record) and a cut-off; every row opens the records behind it; the judgement sections are written by a
 * person; a signed version is never edited and downloads as PDF and DOCX.
 */
export function DocumentsPanel({
  initialCode,
  initialScope,
}: {
  initialCode?: DocumentCode | null;
  initialScope?: string | null;
}) {
  const types = useResource<DocumentTypes>(TYPES_PATH);
  const [code, setCode] = useState<DocumentCode>(initialCode ?? "MANAGEMENT_REVIEW");
  const template = types.data?.templates.find((item) => item.code === code);
  return (
    <Panel eyebrow="To file in your QMS" title="Ready-to-use documents" source={types}>
      <p className="ac-muted">
        Generated from your records for a period and a cut-off. Every figure opens its records; the judgement sections
        are yours to write; a signed version is never edited and downloads as PDF and DOCX.
      </p>
      <div className="uw-doc-types" role="tablist" aria-label="Documents">
        {(types.data?.templates ?? []).map((item) => (
          <button
            key={item.code}
            type="button"
            role="tab"
            aria-selected={item.code === code}
            className={item.code === code ? "uw-doc-type is-active" : "uw-doc-type"}
            onClick={() => setCode(item.code)}
          >
            <FileText size={15} aria-hidden="true" /> {item.title}
          </button>
        ))}
      </div>
      {template && types.data && (
        <TemplateBoard
          key={template.code}
          template={template}
          types={types.data}
          initialScope={template.code === initialCode ? (initialScope ?? "") : ""}
        />
      )}
    </Panel>
  );
}

function TemplateBoard({
  template,
  types,
  initialScope,
}: {
  template: Template;
  types: DocumentTypes;
  initialScope: string;
}) {
  const canExport = useCan("data.export");
  const [period, setPeriod] = useState(types.default_period);
  const [scope, setScope] = useState(initialScope);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const scoped = template.scope !== "ORGANIZATION";
  const list = useResource<{ items: VersionSummary[] }>(
    scoped && !scope ? null : versionsPath(template.code, scoped ? scope : null),
  );
  const body = generateBody(template, period, scope);
  const generate = async () => {
    if (!body) return;
    setBusy(true);
    setError("");
    try {
      const made = await send<DocumentVersion>(DOCUMENTS_PATH, "POST", body);
      list.reload();
      setOpen(made.id);
    } catch (reason) {
      setError(errorText(reason, "The document could not be generated."));
    } finally {
      setBusy(false);
    }
  };
  const choices = template.scope === "CASE" ? types.cases : types.changes;
  return (
    <div className="uw-doc-board">
      <p>{template.purpose}</p>
      <p className="uw-doc-clauses">
        <strong>Clauses it serves:</strong> {template.clauses.map(clauseText).join("; ") || "none printed"}.{" "}
        <span className="ac-muted">Template version {template.template_version}.</span>
      </p>
      <div className="ca-form-grid">
        {scoped ? (
          <label className="ca-field">
            {template.scope === "CASE" ? "Case" : "Change record"}
            <select value={scope} onChange={(event) => setScope(event.target.value)}>
              <option value="">Choose…</option>
              {choices.map((item) => (
                <option key={item.id} value={item.id}>
                  {"identifier" in item ? `${item.identifier} (${item.ref})` : `${item.ref} (${item.type})`}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label className="ca-field">
            Period
            <select value={period} onChange={(event) => setPeriod(Number(event.target.value))}>
              {types.periods.map((days) => (
                <option key={days} value={days}>
                  Last {days} days
                </option>
              ))}
            </select>
          </label>
        )}
        {canExport && (
          <div className="ca-action-row">
            <button type="button" className="ac-primary" disabled={busy || !body} onClick={() => void generate()}>
              <FileCheck2 size={15} aria-hidden="true" /> {busy ? "Generating…" : "Generate, cut-off now"}
            </button>
          </div>
        )}
      </div>
      <InlineError text={error} />
      {list.data && list.data.items.length === 0 && (
        <Empty title="No version yet" detail="Generate the first version: the data sections fill from your records." />
      )}
      {(list.data?.items.length ?? 0) > 0 && (
        <ul className="uw-doc-versions" aria-label="Versions">
          {list.data!.items.map((item) => (
            <li key={item.id}>
              <button type="button" className="ac-link" onClick={() => setOpen(item.id)}>
                Version {item.version}
              </button>{" "}
              <ToneBadge
                tone={item.status === "SIGNED" ? "good" : "neutral"}
                label={item.status === "SIGNED" ? "Signed" : "Draft"}
              />{" "}
              <span className="ac-muted">
                {item.scope_ref
                  ? `${item.scope_ref} · `
                  : item.period
                    ? `${item.period.from} to ${item.period.to} · `
                    : ""}
                cut-off {formatDate(item.cut_off)}
                {item.signed_by ? ` · signed by ${item.signed_by}` : ""}
                {item.superseded_by ? ` · superseded by version ${item.superseded_by}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {open && (
        <Drawer title={template.title} onClose={() => setOpen(null)}>
          <VersionView id={open} onChanged={list.reload} />
        </Drawer>
      )}
    </div>
  );
}

function VersionView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const found = useResource<DocumentVersion>(versionPath(id));
  const [version, setVersion] = useState<DocumentVersion | null>(null);
  const shown = version ?? found.data;
  if (!shown) return <p className="ac-muted">{found.error ? found.error : "Loading…"}</p>;
  const changed = (next: DocumentVersion) => {
    setVersion(next);
    onChanged();
  };
  return (
    <div className="uw-doc-view">
      <VersionHeader version={shown} />
      {shown.sections.map((section, index) => (
        <SectionView key={section.key} section={section} version={shown} open={index === 0} onChanged={changed} />
      ))}
      {shown.signature ? (
        <SignedPart version={shown} onChanged={changed} />
      ) : (
        <SignPart version={shown} onChanged={changed} />
      )}
      <Downloads version={shown} />
      <p className="ac-muted">{shown.data_note}</p>
    </div>
  );
}

function VersionHeader({ version }: { version: DocumentVersion }) {
  return (
    <header className="uw-doc-head">
      <p>
        <strong>
          Version {version.version} · {version.status === "SIGNED" ? "signed" : "draft, not signed"}
        </strong>
        {version.superseded_by ? ` · superseded by version ${version.superseded_by}` : ""}
      </p>
      <p className="ac-muted">
        Template version {version.template_version} ·{" "}
        {version.period
          ? `${version.period.from} to ${version.period.to} · `
          : version.scope_ref
            ? `${version.scope_ref} · `
            : ""}
        cut-off {formatDate(version.cut_off)}
      </p>
      <p className="uw-doc-clauses">{version.clauses.map(clauseText).join("; ")}</p>
      <p className="uw-ma-starter" role="note">
        <FileWarning size={15} aria-hidden="true" /> {version.starter_mark}
      </p>
    </header>
  );
}

function SectionView({
  section,
  version,
  open,
  onChanged,
}: {
  section: Section;
  version: DocumentVersion;
  open: boolean;
  onChanged: (next: DocumentVersion) => void;
}) {
  return (
    <details className="uw-doc-section" open={open}>
      <summary>
        {section.title}
        {section.kind === "judgement" && <span className="uw-doc-mark"> · Written by the manufacturer</span>}
      </summary>
      {section.kind === "judgement" ? (
        <JudgementView section={section} version={version} onChanged={onChanged} />
      ) : (
        <>
          {section.note && <p className="ac-muted">{section.note}</p>}
          <ul className="uw-doc-rows">
            {section.rows.map((row, index) => (
              <RowView key={index} row={row} />
            ))}
          </ul>
        </>
      )}
    </details>
  );
}

/** One data row: the statement, and its records behind a toggle (the long lists stay folded). */
export function RowView({ row }: { row: Row }) {
  return (
    <li>
      {row.text}
      {row.sources.length > 0 && (
        <details className="uw-doc-sources">
          <summary>{recordsText(row)}</summary>
          <span className="uw-doc-chips">
            {row.sources.map((source, index) => (
              <SourceLink key={`${source.type}-${source.id}-${index}`} source={source} />
            ))}
            {row.more ? <span className="ac-muted"> and {row.more} more</span> : null}
          </span>
        </details>
      )}
    </li>
  );
}

function SourceLink({ source }: { source: Source }) {
  const { open, work } = useWorkspace();
  const target = sourceTarget(source);
  if (!target) return <span className="uw-doc-chip">{source.ref}</span>;
  const go = () => {
    if (target.kind === "case") {
      work.setInvestigationId(target.caseId);
      open("Investigations", target.tab);
    } else open(target.section as WorkspaceSection, target.tab);
  };
  return (
    <button type="button" className="uw-doc-chip ac-link" onClick={go}>
      {source.ref}
    </button>
  );
}

function JudgementView({
  section,
  version,
  onChanged,
}: {
  section: Extract<Section, { kind: "judgement" }>;
  version: DocumentVersion;
  onChanged: (next: DocumentVersion) => void;
}) {
  const canWrite = useCan("quality.review");
  const written = version.judgement[section.key];
  const [text, setText] = useState(written?.text ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = judgementProblem(text);
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      onChanged(await send<DocumentVersion>(`${versionPath(version.id)}/judgement/${section.key}`, "PUT", { text }));
    } catch (reason) {
      setError(errorText(reason, "The section could not be saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="uw-doc-judgement">
      <p className="ac-muted">{section.prompt}</p>
      {version.editable && canWrite ? (
        <>
          <label className="ca-field">
            {section.title}
            <textarea rows={4} value={text} onChange={(event) => setText(event.target.value)} />
          </label>
          {written && (
            <p className="ac-muted">
              Saved by {written.written_by_name}, {formatDate(written.written_at)}
            </p>
          )}
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" disabled={busy || !!problem} onClick={() => void save()}>
              <PenLine size={15} aria-hidden="true" /> {busy ? "Saving…" : "Save the section"}
            </button>
            {problem && text && <span className="uw-hint">{problem}</span>}
          </div>
          <InlineError text={error} />
        </>
      ) : (
        <p>{written?.text ?? "Not written."}</p>
      )}
    </div>
  );
}

function SignPart({ version, onChanged }: { version: DocumentVersion; onChanged: (next: DocumentVersion) => void }) {
  const canSign = useCan("quality.review");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!canSign) return <p className="uw-hint">Signing a document needs quality review.</p>;
  const problem = signProblem(version, password);
  const sign = async () => {
    setBusy(true);
    setError("");
    try {
      onChanged(
        await send<DocumentVersion>(`${versionPath(version.id)}/sign`, "POST", { password, mfa_code: code || null }),
      );
    } catch (reason) {
      setError(errorText(reason, "The document could not be signed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ca-drawer-section uw-doc-sign">
      <h3>Sign version {version.version}</h3>
      <p className="ac-muted">
        The signature covers the data sections as generated and the judgement sections as written. A signed version is
        never edited: generate again for a new version.
      </p>
      <div className="ca-form-grid">
        <DecideAndSign />
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
      {problem && <p className="uw-hint">{problem}</p>}
      <div className="ca-action-row">
        <button type="button" className="ac-primary" disabled={busy || !!problem} onClick={() => void sign()}>
          {busy ? "Signing…" : "Sign the document"}
        </button>
      </div>
      <InlineError text={error} />
    </section>
  );
}

function SignedPart({ version, onChanged }: { version: DocumentVersion; onChanged: (next: DocumentVersion) => void }) {
  const canFile = useCan("quality.review");
  const signature = version.signature!;
  const [reference, setReference] = useState(version.filing?.qms_reference ?? "");
  const [minutes, setMinutes] = useState(version.filing?.minutes_spent?.toString() ?? "");
  const [error, setError] = useState("");
  const file = async () => {
    setError("");
    try {
      onChanged(
        await send<DocumentVersion>(`${versionPath(version.id)}/filing`, "PUT", {
          qms_reference: reference,
          minutes_spent: minutes ? Number(minutes) : null,
        }),
      );
    } catch (reason) {
      setError(errorText(reason, "The filing reference could not be saved."));
    }
  };
  return (
    <section className="ca-drawer-section uw-doc-signed">
      <h3>Signature</h3>
      <p>
        Signed by {signature.signer_name} ({signature.signer_role}), {formatDate(signature.signed_at)}.
      </p>
      <p className="ac-muted">{signature.meaning}</p>
      {version.writer_note && <p className="ac-muted">{version.writer_note}</p>}
      <details>
        <summary>Checksums</summary>
        <p className="uw-doc-hash">PDF SHA-256: {signature.pdf_sha256}</p>
        <p className="uw-doc-hash">Signed content: {signature.content_fingerprint}</p>
        <p className="ac-muted">Signature record {signature.record_business_id ?? signature.record_id}</p>
      </details>
      {canFile && (
        <div className="ca-form-grid">
          <label className="ca-field">
            QMS filing reference
            <input value={reference} maxLength={120} onChange={(event) => setReference(event.target.value)} />
          </label>
          <label className="ca-field">
            Minutes spent (optional)
            <input
              inputMode="numeric"
              value={minutes}
              onChange={(event) => setMinutes(event.target.value.replace(/\D/g, ""))}
            />
          </label>
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={() => void file()}>
              Save the filing
            </button>
          </div>
        </div>
      )}
      <InlineError text={error} />
    </section>
  );
}

function Downloads({ version }: { version: DocumentVersion }) {
  const canExport = useCan("data.export");
  const [error, setError] = useState("");
  if (!canExport) return null;
  const get = async (kind: "pdf" | "docx") => {
    setError("");
    try {
      await downloadFile(filePath(version.id, kind), {
        fallbackName: `mdarix-${version.code.toLowerCase().replace(/_/g, "-")}-v${version.version}.${kind}`,
      });
    } catch (reason) {
      setError(errorText(reason, "The file could not be downloaded."));
    }
  };
  return (
    <div className="ca-action-row uw-doc-downloads">
      <button type="button" className="ac-secondary" onClick={() => void get("pdf")}>
        <Download size={15} aria-hidden="true" /> PDF{version.signature ? " (the signed record)" : " (draft)"}
      </button>
      <button type="button" className="ac-secondary" onClick={() => void get("docx")}>
        <Download size={15} aria-hidden="true" /> DOCX
      </button>
      <InlineError text={error} />
    </div>
  );
}

/** The case page's way to its two documents: they open in Records › Reports with this case chosen. */
export function CaseDocumentLinks({ investigationId }: { investigationId: string }) {
  const { open } = useWorkspace();
  return (
    <p className="ca-action-row uw-doc-case-links">
      <span className="ac-muted">Documents for this investigation:</span>
      {(
        [
          ["INVESTIGATION_REPORT", "Investigation report"],
          ["RISK_REVIEW_EXTRACT", "Risk-review extract"],
        ] as const
      ).map(([code, label]) => (
        <button
          key={code}
          type="button"
          className="ac-link"
          onClick={() => open("Records", documentLink(code, investigationId))}
        >
          <FileText size={14} aria-hidden="true" /> {label}
        </button>
      ))}
    </p>
  );
}
