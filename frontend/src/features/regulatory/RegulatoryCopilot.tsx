import { useEffect, useState } from "react";
import { AlertTriangle, BadgeCheck, FileSignature, Sparkles } from "lucide-react";
import { AI_TIMEOUT_MS, describeError, postJson, requestJson } from "../../app/apiClient";
import { Empty, Panel, ToneBadge } from "../admin/console/charts";
import { ConfirmDialog, Table, idColumn, listOf, useResource, type Confirmation } from "../customer-admin/shared";
import { DialogBehaviour } from "../shared/DialogBehaviour";
import { useCan } from "../workspace/workspaceContext";
import {
  AUTHORING_SECTIONS,
  NEXT_STATUSES,
  TEMPLATES,
  TEMPLATE_LABELS,
  approvalError,
  approvalRequest,
  authoringSections,
  checkFindings,
  claimSections,
  draftOutcome,
  draftRequest,
  sectionTitle,
  type Assistance,
  type DraftForm,
  type DraftSection,
  type Template,
} from "./regulatoryModel";
import "./regulatory.css";
import { displayId, referenceId } from "../../app/displayId";

type DocumentRow = {
  id: string;
  // The Document ID people see (RDOC000003); document_identifier is the number the author gave it.
  business_id?: string | null;
  document_identifier: string;
  document_type: string;
  title: string;
  status: string;
  current_version: number;
  lock_version: number;
};
type DocumentVersion = {
  id: string;
  version: number;
  status: string;
  change_reason?: string;
  content_hash?: string;
  content: { sections?: DraftSection[]; limitations?: string[]; ai_assistance?: Assistance } | null;
};
type DocumentDetail = DocumentRow & { versions: DocumentVersion[] };
type DraftResult = {
  status: string;
  reason_code?: string | null;
  user_message?: string;
  document_id: string;
  document_business_id?: string | null;
  document_identifier: string;
  version: number;
};

const EMPTY_FORM: DraftForm = {
  template: "GSPR",
  identifier: "",
  title: "",
  investigationId: "",
  claims: "",
  sections: {},
};

const STATUS_ACTION: Record<string, string> = {
  IN_REVIEW: "Submit for human review",
  DRAFT: "Return to draft",
  ARCHIVED: "Archive",
  APPROVED: "Approve / sign",
};

/**
 * Regulatory copilot: drafts eSTAR, GSPR, CER and IFU sections from the organization's own records. The model's text
 * is advisory, every section needs human review, and its citations and wording are checked per section; when AI is
 * off or unavailable the draft is the section layout only and the screen says why. Approval is a signature: the
 * approver re-enters their password (and authenticator code). MDARIX gives no regulatory advice and submits nothing.
 */
export function RegulatoryCopilot() {
  const documents = useResource<DocumentRow[]>("/api/v1/regulatory/documents");
  const [selectedId, setSelectedId] = useState("");
  const [lastDraft, setLastDraft] = useState<DraftResult | null>(null);
  const canDraft = useCan("ai.run");
  return (
    <div className="rg-copilot">
      <p className="ac-note">
        Prepares reviewable drafts from your records. MDARIX does not give regulatory advice, decide on submissions or
        submit dossiers; a person reviews and approves every document.
      </p>
      {canDraft ? (
        <DraftPanel
          onDrafted={(result) => {
            setLastDraft(result);
            setSelectedId(result.document_id);
            documents.reload();
          }}
        />
      ) : (
        <p className="ac-note" role="note">
          View only: your role can read and review drafts but not ask the AI to write them.
        </p>
      )}
      {lastDraft && <DraftOutcomeBanner result={lastDraft} />}
      <Panel eyebrow="Versioned drafts" title="Regulatory documents" source={documents}>
        <Table
          caption="Regulatory documents"
          rows={listOf(documents.data)}
          rowKey={(row) => row.id}
          empty={{ title: "No regulatory drafts yet", detail: "Drafts you create appear here with their versions." }}
          columns={[
            idColumn("Document ID", "document_identifier"),
            {
              key: "document",
              label: "Document",
              render: (row) => (
                <span className="ca-person">
                  <strong>{row.title || row.document_type}</strong>
                  <small>{row.document_identifier}</small>
                </span>
              ),
            },
            {
              key: "type",
              label: "Template",
              render: (row) => TEMPLATE_LABELS[row.document_type as Template] ?? row.document_type,
            },
            { key: "version", label: "Version", numeric: true, render: (row) => row.current_version },
            { key: "status", label: "Status", render: (row) => <StatusText status={row.status} /> },
            {
              key: "open",
              label: "",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => setSelectedId(row.id)}>
                  {selectedId === row.id ? "Open below" : "Open"}
                </button>
              ),
            },
          ]}
        />
      </Panel>
      {selectedId && (
        <DocumentPanel
          key={selectedId}
          id={selectedId}
          onClose={() => setSelectedId("")}
          onChanged={() => documents.reload()}
        />
      )}
    </div>
  );
}

function StatusText({ status }: { status: string }) {
  const tone = status === "APPROVED" ? "good" : status === "IN_REVIEW" ? "warning" : "neutral";
  return <ToneBadge tone={tone} label={sectionTitle(status.toLowerCase())} />;
}

function DraftOutcomeBanner({ result }: { result: DraftResult }) {
  const outcome = draftOutcome({ status: result.status, user_message: result.user_message });
  return (
    <div className={`rg-outcome ${outcome.aiDrafted ? "is-ai" : "is-rules"}`} role="status">
      {outcome.aiDrafted ? <Sparkles size={18} aria-hidden="true" /> : <AlertTriangle size={18} aria-hidden="true" />}
      <div>
        <strong>
          {referenceId(result, "document", result.document_identifier)} version {result.version}: {outcome.title}
        </strong>
        <span>{outcome.message}</span>
        {!outcome.aiDrafted && result.reason_code && <small>Reason: {result.reason_code}</small>}
        <small>Human review required for every section.</small>
      </div>
    </div>
  );
}

function DraftPanel({ onDrafted }: { onDrafted: (result: DraftResult) => void }) {
  const [form, setForm] = useState<DraftForm>({ ...EMPTY_FORM, sections: {} });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const investigations = useResource<any>("/api/v1/data-plane/investigations?limit=500");
  const cases = listOf(investigations.data?.records);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await postJson<DraftResult>("/api/v1/regulatory/draft", draftRequest(form), {
        timeoutMs: AI_TIMEOUT_MS,
      });
      onDrafted(result);
      setForm({ ...EMPTY_FORM, template: form.template, sections: {} });
    } catch (reason) {
      setError(describeError(reason, "The draft could not be created."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel eyebrow="AI drafting · advisory" title="Draft a regulatory document">
      <form className="ca-form" onSubmit={submit}>
        <div className="ca-form-grid">
          <label className="ca-field">
            Template
            <select
              value={form.template}
              onChange={(event) => setForm({ ...form, template: event.target.value as Template })}
            >
              {TEMPLATES.map((item) => (
                <option key={item} value={item}>
                  {TEMPLATE_LABELS[item]}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Draft from this investigation (optional)
            <select
              value={form.investigationId}
              onChange={(event) => setForm({ ...form, investigationId: event.target.value })}
            >
              <option value="">
                {investigations.state === "loading" ? "Loading…" : "No investigation: search all your records"}
              </option>
              {cases.map((row) => (
                <option key={row.id} value={row.id}>
                  {displayId(row, "investigation_identifier", "Investigation")}
                  {row.investigation_question ? ` · ${String(row.investigation_question).slice(0, 60)}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="ca-field">
            Title (optional)
            <input
              value={form.title}
              maxLength={255}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="e.g. GSPR checklist for Infusion Pump X"
            />
          </label>
          <label className="ca-field">
            Document identifier (optional)
            <input
              value={form.identifier}
              maxLength={120}
              onChange={(event) => setForm({ ...form, identifier: event.target.value })}
              placeholder="Leave empty for a new document; reuse one to add a version"
            />
          </label>
        </div>
        <label className="ca-field">
          Claims the document should support (optional, one per line)
          <textarea
            rows={3}
            value={form.claims}
            onChange={(event) => setForm({ ...form, claims: event.target.value })}
            placeholder="e.g. The occlusion alarm meets its performance requirement"
          />
        </label>
        <details className="rg-sections-input">
          <summary>Your own text or licensed source excerpts per section (optional)</summary>
          <p className="ac-muted">
            The model keeps your text and drafts around it. Use official sources or excerpts you are licensed to use.
          </p>
          {AUTHORING_SECTIONS[form.template].map((id) => (
            <label className="ca-field" key={`${form.template}:${id}`}>
              {sectionTitle(id)}
              <textarea
                rows={2}
                maxLength={2000}
                value={form.sections[id] ?? ""}
                onChange={(event) => setForm({ ...form, sections: { ...form.sections, [id]: event.target.value } })}
                placeholder="Paste your text or a source excerpt with its reference"
              />
            </label>
          ))}
        </details>
        <p className="ac-muted">
          Statements without a verified citation stay marked as unknown. The AI may take up to a minute.
        </p>
        {error && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="submit" className="ac-primary" disabled={busy}>
            <Sparkles size={16} aria-hidden="true" /> {busy ? "Drafting…" : "Generate draft"}
          </button>
        </div>
      </form>
    </Panel>
  );
}

function DocumentPanel({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const detail = useResource<DocumentDetail>(`/api/v1/regulatory/documents/${encodeURIComponent(id)}`);
  const canWrite = useCan("records.write");
  const canApprove = useCan("regulatory.approve");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [approving, setApproving] = useState(false);
  const [message, setMessage] = useState("");
  const document = detail.data;
  const latest = document?.versions?.[0];
  const content = latest?.content ?? null;
  const outcome = draftOutcome(content?.ai_assistance);
  const transitions = (NEXT_STATUSES[document?.status ?? ""] ?? []).filter((status) =>
    status === "APPROVED" ? canApprove : canWrite,
  );
  const changed = (text: string) => {
    setMessage(text);
    detail.reload();
    onChanged();
  };
  const move = (status: string) => {
    if (!document) return;
    if (status === "APPROVED") return setApproving(true);
    setConfirm({
      title: `${STATUS_ACTION[status]}: ${displayId(document, "document_identifier")}?`,
      body:
        status === "ARCHIVED"
          ? "An archived document can no longer change status; new content goes into a new document."
          : status === "IN_REVIEW"
            ? "The text is frozen for review; approvers can approve it or return it to draft."
            : "The document returns to draft so its text can change again.",
      confirmLabel: STATUS_ACTION[status],
      reason: { label: "Reason (kept with the document's history)", min: 5 },
      run: (reason) =>
        postJson(`/api/v1/regulatory/documents/${encodeURIComponent(document.id)}/status`, {
          status,
          expected_lock_version: document.lock_version,
          reason,
        }),
      done: `${displayId(document, "document_identifier")} is now ${sectionTitle(status.toLowerCase()).toLowerCase()}.`,
    });
  };
  return (
    <Panel
      eyebrow={
        document ? `${displayId(document, "document_identifier")} · version ${document.current_version}` : "Document"
      }
      title={document?.title || document?.document_type || "Regulatory document"}
      source={detail}
      action={
        <button type="button" className="ac-link" onClick={onClose}>
          Close
        </button>
      }
    >
      {document && (
        <>
          <div className="rg-head">
            <StatusText status={document.status} />
            <span className={`rg-origin ${outcome.aiDrafted ? "is-ai" : "is-rules"}`}>
              {outcome.aiDrafted ? (
                <Sparkles size={14} aria-hidden="true" />
              ) : (
                <AlertTriangle size={14} aria-hidden="true" />
              )}
              {outcome.title}
            </span>
            <strong className="rg-review">Human review required</strong>
          </div>
          {!outcome.aiDrafted && <p className="ac-note">{outcome.message}</p>}
          {message && (
            <p className="ca-inline-ok" role="status">
              {message}
            </p>
          )}
          {!!transitions.length && (
            <div className="ca-action-row">
              {transitions.map((status) => (
                <button
                  key={status}
                  type="button"
                  className={status === "APPROVED" ? "ac-primary" : "ac-secondary"}
                  onClick={() => move(status)}
                >
                  {status === "APPROVED" && <FileSignature size={15} aria-hidden="true" />} {STATUS_ACTION[status]}
                </button>
              ))}
            </div>
          )}
          <Sections sections={content?.sections} />
          {!!content?.limitations?.length && (
            <section className="rg-limitations">
              <h3>Limitations</h3>
              <ul>
                {content.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          )}
          {document.versions.length > 1 && (
            <details className="rg-history">
              <summary>Earlier versions ({document.versions.length - 1})</summary>
              <ul>
                {document.versions.slice(1).map((version) => (
                  <li key={version.id}>
                    Version {version.version} · {sectionTitle(version.status.toLowerCase())} ·{" "}
                    {version.change_reason ?? "—"}
                    {version.content_hash ? (
                      <>
                        {" "}
                        · <code>{version.content_hash.slice(0, 12)}</code>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          changed(text);
        }}
      />
      {approving && document && (
        <ApproveDialog
          document={document}
          onClose={() => setApproving(false)}
          onApproved={() => {
            setApproving(false);
            changed(
              `${displayId(document, "document_identifier")} version ${document.current_version} is approved and signed.`,
            );
          }}
        />
      )}
    </Panel>
  );
}

function Sections({ sections }: { sections: DraftSection[] | undefined }) {
  const authored = authoringSections(sections);
  const claims = claimSections(sections);
  if (!authored.length && !claims.length)
    return <Empty title="No sections" detail="This version has no section content." />;
  return (
    <div className="rg-sections">
      {authored.map((section) => {
        const findings = checkFindings(section.ai_checks);
        return (
          <article className="rg-section" key={section.section_id}>
            <header>
              <h3>{section.title || sectionTitle(section.section_id ?? "")}</h3>
              <span className="rg-review">Human review required</span>
            </header>
            {section.content ? (
              <div className="rg-text">
                <small>Your text</small>
                <p>{section.content}</p>
              </div>
            ) : null}
            {section.ai_draft ? (
              <div className="rg-text is-ai">
                <small>
                  <Sparkles size={12} aria-hidden="true" /> AI draft (advisory)
                </small>
                <p>{section.ai_draft}</p>
                <div className="rg-checks">
                  {section.ai_checks?.flagged ? (
                    <ToneBadge tone="warning" label="Checks found problems" />
                  ) : (
                    <ToneBadge tone="good" label="Citations and wording checked" />
                  )}
                  {!!section.ai_checks?.cited?.length && <span>Cites {section.ai_checks.cited.join(", ")}</span>}
                </div>
                {!!findings.length && (
                  <ul className="rg-findings">
                    {findings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              !section.content && <p className="ac-muted">No text yet for this section.</p>
            )}
          </article>
        );
      })}
      {!!claims.length && (
        <article className="rg-section">
          <header>
            <h3>Claims</h3>
          </header>
          <ul className="rg-claims">
            {claims.map((claim) => (
              <li key={claim.claim_id}>
                {claim.text}{" "}
                <ToneBadge
                  tone={claim.unsupported ? "warning" : "good"}
                  label={
                    claim.unsupported ? "Unsupported: no verified citation" : `Confidence ${claim.confidence ?? "—"}`
                  }
                />
              </li>
            ))}
          </ul>
        </article>
      )}
    </div>
  );
}

/**
 * Approving is an electronic signature: the reason, the approver's password and, when their account has an
 * authenticator, its current code. Every refusal the server can give is explained in words.
 */
function ApproveDialog({
  document,
  onClose,
  onApproved,
}: {
  document: DocumentDetail;
  onClose: () => void;
  onApproved: () => void;
}) {
  const [reason, setReason] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [enrolled, setEnrolled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    requestJson<{ mfa_enrolled?: boolean }>("/api/v1/auth/session")
      .then((session) => current && setEnrolled(!!session?.mfa_enrolled))
      .catch(() => current && setEnrolled(null));
    return () => {
      current = false;
    };
  }, []);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await postJson(
        `/api/v1/regulatory/documents/${encodeURIComponent(document.id)}/status`,
        approvalRequest(document.lock_version, reason, password, code),
      );
      onApproved();
    } catch (reason) {
      setError(approvalError(reason));
      setPassword("");
      setCode("");
      setBusy(false);
    }
  };
  return (
    <div className="ac-modal-backdrop" role="presentation">
      <DialogBehaviour onClose={onClose} />
      <form className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="rg-approve-title" onSubmit={submit}>
        <p className="ac-eyebrow">Electronic signature · recorded in the audit trail</p>
        <h2 id="rg-approve-title">
          Approve {displayId(document, "document_identifier")} version {document.current_version}
        </h2>
        <p>
          You confirm that you reviewed every section of this version, including the AI-written text, and approve it.
          The approval is signed with your identity and the content's fingerprint.
        </p>
        <label className="ca-field">
          Reason for approval
          <textarea
            required
            rows={3}
            minLength={5}
            maxLength={1000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="At least 5 characters"
          />
        </label>
        <label className="ca-field">
          Your password
          <input
            required
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {enrolled !== false && (
          <label className="ca-field">
            Authenticator code{enrolled ? "" : " (if your account has one)"}
            <input
              required={enrolled === true}
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9 ]{6,8}"
              maxLength={8}
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
        )}
        {error && (
          <p className="ca-inline-error" role="alert">
            <AlertTriangle size={15} aria-hidden="true" /> {error}
          </p>
        )}
        <div className="ac-modal-actions">
          <button type="button" className="ac-secondary" onClick={onClose} disabled={busy} autoFocus>
            Cancel
          </button>
          <button type="submit" className="ac-primary" disabled={busy || reason.trim().length < 5 || !password}>
            <BadgeCheck size={15} aria-hidden="true" /> {busy ? "Signing…" : "Approve and sign"}
          </button>
        </div>
      </form>
    </div>
  );
}
