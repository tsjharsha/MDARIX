import { useContext, useRef, useState } from "react";
import { AlertTriangle, ClipboardCheck, Download, GitBranch, Link2, ListChecks, Upload } from "lucide-react";
import { describeError, postJson } from "../../app/apiClient";
import { Empty, Panel, StatTile, ToneBadge } from "../admin/console/charts";
import {
  ConfirmDialog,
  Drawer,
  SearchBox,
  Table,
  Tabs,
  formatDate,
  idColumn,
  referenceIdColumn,
  sourceIdColumn,
  useResource,
  type Confirmation,
} from "../customer-admin/shared";
import { displayId } from "../../app/displayId";
import { useServerSort } from "../../app/tableSort";
import { WorkspaceContext, sectionAllowed, useCan } from "../workspace/workspaceContext";
import { downloadFile } from "../reports/download";
import {
  NOT_CAPTURED,
  PAGE_SIZE,
  REGISTER_SORTS,
  fieldOrNotCaptured,
  filterChains,
  linkedId,
  linkedIds,
  missingLinks,
  notCapturedLabels,
  pageSummary,
  registerPath,
  residualLabel,
  reviewRequestPath,
  traceabilityGaps,
  type Chain,
  type RegisterPage,
  type RiskItem,
  type Traceability,
} from "./riskModel";
import "../reports/reports.css";

const VIEWS = ["Risk register", "Traceability"] as const;
type View = (typeof VIEWS)[number];

type ReviewTarget = { id: string; identifier: string };

/**
 * Risk & Traceability from the organization's own quality-system records: the risk register (risks with their
 * failure modes, controls, verification evidence and requirements) and the ISO 14971 chain requirement -> risk ->
 * failure mode -> control -> verification, with every unlinked record listed as a gap to close. Risk decisions stay
 * with people: the screen can ask the organization's approvers to review a risk, never change one.
 */
export function RiskTraceabilityWorkspace() {
  const [view, setView] = useState<View>("Risk register");
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  const [chainQuery, setChainQuery] = useState("");
  const notified = useRef<boolean | null>(null);
  const confirmation: Confirmation | null = review
    ? {
        title: `Request a residual-risk review of ${review.identifier}?`,
        body: "Your organization's approvers are asked to review this risk and its controls. The request and your reason are recorded in the audit trail; nothing about the risk itself changes.",
        confirmLabel: "Request review",
        reason: { label: "Why does this risk need review?", min: 10 },
        run: async (reason) => {
          const result = await postJson<{ approvers_notified?: boolean }>(reviewRequestPath(review.id), { reason });
          notified.current = result?.approvers_notified ?? null;
        },
        done: `Review of ${review.identifier} requested.`,
      }
    : null;
  return (
    <div className="rk-workspace">
      {message && (
        <div className={`ac-message tone-${message.tone}`} role="status">
          {message.text}
        </div>
      )}
      <Tabs tabs={VIEWS} active={view} onChange={setView} label="Risk and traceability views">
        {view === "Risk register" && <Register onReview={setReview} />}
        {view === "Traceability" && (
          <TraceabilityView query={chainQuery} onQuery={setChainQuery} onReview={setReview} />
        )}
      </Tabs>
      <ConfirmDialog
        request={confirmation}
        onClose={() => setReview(null)}
        onDone={(text) => {
          setReview(null);
          setMessage({
            tone: "good",
            text:
              notified.current === false
                ? `${text} The request is recorded; no approver could be emailed, so tell them directly.`
                : `${text} Your organization's approvers are notified.`,
          });
          notified.current = null;
        }}
      />
    </div>
  );
}

/** Shown when the organization has no risk records yet, with the way to bring them in. */
function NoRisks() {
  const workspace = useContext(WorkspaceContext);
  const canImport =
    !!workspace &&
    sectionAllowed("Import data", workspace.session?.allowed_menu, workspace.session?.business_permissions);
  return (
    <>
      <Empty
        title="No risks recorded yet"
        detail={
          canImport
            ? "Import your risks, failure modes, controls and requirements from your quality system as CSV files, or ask your administrator to connect it."
            : "Risks appear once your administrator connects your quality system or imports its risk records."
        }
      />
      {canImport && (
        <div className="ca-action-row">
          <button type="button" className="ac-primary" onClick={() => workspace?.open("Import data")}>
            <Upload size={16} aria-hidden="true" /> Import data
          </button>
        </div>
      )}
    </>
  );
}

function ReviewButton({ target, onReview }: { target: ReviewTarget; onReview: (target: ReviewTarget) => void }) {
  const canWrite = useCan("records.write");
  return (
    <button
      type="button"
      className="ac-link"
      disabled={!canWrite}
      title={canWrite ? undefined : "Your role cannot request reviews"}
      onClick={() => onReview(target)}
    >
      <ClipboardCheck size={14} aria-hidden="true" /> Request residual-risk review
    </button>
  );
}

function ExportRegister() {
  const canExport = useCan("data.export");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!canExport) return null;
  return (
    <span className="rp-actions">
      <button
        type="button"
        className="ac-secondary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await downloadFile("/api/v1/risk/export.csv", { fallbackName: "mdarix-risk-register.csv" });
          } catch (reason) {
            setError(describeError(reason, "The register could not be exported."));
          } finally {
            setBusy(false);
          }
        }}
      >
        <Download size={15} aria-hidden="true" /> {busy ? "Exporting…" : "Export CSV"}
      </button>
      {error && (
        <span className="ca-inline-error" role="alert">
          <AlertTriangle size={15} aria-hidden="true" /> {error}
        </span>
      )}
    </span>
  );
}

function Register({ onReview }: { onReview: (target: ReviewTarget) => void }) {
  const [offset, setOffset] = useState(0);
  const { sort, onSort } = useServerSort(() => setOffset(0));
  const register = useResource<RegisterPage>(registerPath(offset, PAGE_SIZE, sort));
  const [open, setOpen] = useState<RiskItem | null>(null);
  const data = register.data;
  const rows = data?.items ?? [];
  const missing = notCapturedLabels(data?.fields_not_captured);
  return (
    <Panel
      eyebrow="ISO 14971 · from your quality-system records"
      title="Risk register"
      source={register}
      action={data && data.total > 0 ? <ExportRegister /> : undefined}
    >
      {data && data.total === 0 ? (
        <NoRisks />
      ) : (
        <>
          {data?.data_notice && <p className="ac-note">{data.data_notice}</p>}
          {!!missing.length && (
            <p className="ac-muted">
              {NOT_CAPTURED}: {missing.join(", ")}.
            </p>
          )}
          <Table
            caption="Risk register"
            rows={rows}
            rowKey={(row) => row.id}
            empty={{ title: "No risks on this page", detail: "Go back to the previous page." }}
            serverSort={{ sort, onSort, keys: REGISTER_SORTS }}
            columns={[
              idColumn("Risk ID", "risk_identifier"),
              sourceIdColumn("risk_identifier"),
              {
                key: "risk",
                label: "Risk",
                fields: ["description"],
                render: (row) => row.description || <span className="ac-muted">No description recorded</span>,
              },
              {
                key: "product",
                label: "Product",
                render: (row) =>
                  row.product
                    ? `${displayId(row.product, "product_identifier")}${row.product_version ? ` · ${row.product_version.version_identifier}` : ""}`
                    : "—",
              },
              { key: "hazard", label: "Hazard", render: (row) => <NotCaptured value={row.hazard} /> },
              {
                key: "severity",
                label: "Severity × probability",
                render: (row) =>
                  row.severity == null && row.probability == null ? (
                    <NotCaptured value={null} />
                  ) : (
                    `${fieldOrNotCaptured(row.severity)} × ${fieldOrNotCaptured(row.probability)}`
                  ),
              },
              {
                key: "residual",
                label: "Residual risk",
                render: (row) => <ToneBadge {...residualLabel(row.residual_risk?.state)} />,
              },
              {
                key: "links",
                label: "Linked",
                render: (row) =>
                  `${row.controls.length} controls · ${row.requirements.length} requirements · ${row.failure_modes.length} failure modes`,
              },
              {
                key: "open",
                label: "",
                render: (row) => (
                  <button type="button" className="ac-link" onClick={() => setOpen(row)}>
                    Details
                  </button>
                ),
              },
            ]}
          />
          {data && (
            <div className="rk-pager">
              {/* The server pages and sorts the register: a heading click orders every page. */}
              <span>{pageSummary(data.total, data.offset, rows.length)}</span>
              <button
                type="button"
                className="ac-secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <button
                type="button"
                className="ac-secondary"
                disabled={data.next_offset == null}
                onClick={() => data.next_offset != null && setOffset(data.next_offset)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
      {open && <RiskDetail risk={open} onClose={() => setOpen(null)} onReview={onReview} />}
    </Panel>
  );
}

function NotCaptured({ value }: { value: unknown }) {
  const text = fieldOrNotCaptured(value);
  return text === NOT_CAPTURED ? <span className="ac-muted">{text}</span> : <>{text}</>;
}

const ISO_FIELDS: Array<[string, keyof RiskItem]> = [
  ["Hazard", "hazard"],
  ["Harm", "harm"],
  ["Severity", "severity"],
  ["Probability", "probability"],
  ["Risk level", "risk_level"],
];

function RiskDetail({
  risk,
  onClose,
  onReview,
}: {
  risk: RiskItem;
  onClose: () => void;
  onReview: (target: ReviewTarget) => void;
}) {
  const residual = residualLabel(risk.residual_risk?.state);
  return (
    <Drawer title={`${displayId(risk, "risk_identifier")} · ${risk.description || "Risk"}`} onClose={onClose}>
      <dl className="ca-facts">
        <div>
          <dt>Risk ID</dt>
          <dd>{linkedId(risk.risk_identifier, risk.business_id)}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{risk.status || "—"}</dd>
        </div>
        <div>
          <dt>Product</dt>
          <dd>
            {risk.product
              ? `${linkedId(risk.product.product_identifier, risk.product.business_id)} · ${risk.product.name ?? ""}`
              : "—"}
            {risk.product_version ? ` (version ${risk.product_version.version_identifier})` : ""}
          </dd>
        </div>
        {ISO_FIELDS.map(([label, key]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>
              <NotCaptured value={risk[key]} />
            </dd>
          </div>
        ))}
        <div>
          <dt>Residual risk</dt>
          <dd>
            <ToneBadge tone={residual.tone} label={residual.label} /> {risk.residual_risk?.basis}
          </dd>
        </div>
        <div>
          <dt>Open complaints on the product</dt>
          <dd>{risk.open_complaints_on_product}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>
            {risk.source_system || "—"}
            {risk.recorded_at ? ` · recorded ${formatDate(risk.recorded_at)}` : ""}
          </dd>
        </div>
      </dl>
      <section className="ca-drawer-section">
        <h3>Failure modes</h3>
        <LinkedList
          items={risk.failure_modes.map((row) => [
            linkedId(row.failure_mode_identifier, row.business_id),
            row.name ?? "",
          ])}
        />
      </section>
      <section className="ca-drawer-section">
        <h3>Controls and their verification evidence</h3>
        {risk.controls.length ? (
          <ul className="rk-list">
            {risk.controls.map((control) => (
              <li key={control.id}>
                <strong>{linkedId(control.control_identifier, control.business_id)}</strong> {control.description ?? ""}
                {control.status ? ` · ${control.status}` : ""}
                <br />
                <small className={control.verification_evidence.length ? "" : "ac-muted"}>
                  {control.verification_evidence.length
                    ? `Verification evidence: ${control.verification_evidence
                        .map(
                          (item) =>
                            `${linkedId(item.evidence_identifier, item.business_id)}${item.title ? ` · ${item.title}` : ""}`,
                        )
                        .join(", ")}`
                    : "No verification evidence linked"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="ac-muted">No control is linked to this risk.</p>
        )}
      </section>
      <section className="ca-drawer-section">
        <h3>Requirements</h3>
        <LinkedList
          items={risk.requirements.map((row) => [
            linkedId(row.requirement_identifier, row.business_id),
            row.text ?? "",
          ])}
        />
      </section>
      <p className="ac-note">
        Linked records come from your quality system; change them there and import again. Any change to a control needs
        its requirement, verification evidence and decisions reviewed first.
      </p>
      <div className="ca-action-row">
        <ReviewButton
          target={{ id: risk.id, identifier: displayId(risk, "risk_identifier") }}
          onReview={(target) => {
            onClose();
            onReview(target);
          }}
        />
      </div>
    </Drawer>
  );
}

function LinkedList({ items }: { items: Array<[string, string]> }) {
  if (!items.length) return <p className="ac-muted">None linked.</p>;
  return (
    <ul className="rk-list">
      {items.map(([identifier, text]) => (
        <li key={identifier}>
          <strong>{identifier}</strong> {text}
        </li>
      ))}
    </ul>
  );
}

function TraceabilityView({
  query,
  onQuery,
  onReview,
}: {
  query: string;
  onQuery: (value: string) => void;
  onReview: (target: ReviewTarget) => void;
}) {
  const trace = useResource<Traceability>("/api/v1/risk/traceability");
  const [gapsOnly, setGapsOnly] = useState(false);
  const data = trace.data;
  const nothing =
    !!data && !data.counts.risks && !data.counts.requirements && !data.counts.failure_modes && !data.counts.controls;
  const gaps = traceabilityGaps(data?.unlinked, data?.unlinked_business_ids);
  const chains = filterChains(data?.chains ?? [], query, gapsOnly);
  if (nothing)
    return (
      <Panel eyebrow="ISO 14971" title="Traceability">
        <NoRisks />
      </Panel>
    );
  return (
    <>
      <Panel eyebrow={data?.standard ?? "ISO 14971 traceability"} title="Traceability at a glance" source={trace}>
        {data && (
          <>
            <section className="ac-grid three" aria-label="Traceability counts">
              <StatTile
                label="Complete chains"
                value={`${data.counts.complete_chains} of ${data.counts.risks}`}
                detail="Requirement, failure mode, control and verification evidence all linked"
                icon={<GitBranch size={18} />}
                tone={data.counts.risks && data.counts.complete_chains === data.counts.risks ? "good" : "warning"}
              />
              <StatTile
                label="Requirements"
                value={data.counts.requirements}
                detail={`${data.counts.unlinked.requirements_without_risk ?? 0} not linked to a risk`}
                icon={<ListChecks size={18} />}
              />
              <StatTile
                label="Controls"
                value={data.counts.controls}
                detail={`${data.counts.unlinked.controls_without_verification_evidence ?? 0} without verification evidence`}
                icon={<Link2 size={18} />}
              />
            </section>
            <p className="ac-note">{data.data_notice}</p>
          </>
        )}
      </Panel>
      {data && (
        <Panel eyebrow="Gaps to close" title="What is not linked yet">
          {gaps.length ? (
            <ul className="rk-gaps">
              {gaps.map((gap) => (
                <li key={gap.key}>
                  <strong>
                    {gap.label} ({gap.items.length})
                  </strong>
                  <small>{gap.fix}</small>
                  <span className="rk-ids">
                    {gap.items.slice(0, 30).map((identifier, index) =>
                      gap.risks ? (
                        <button
                          type="button"
                          key={identifier}
                          className="ac-link"
                          onClick={() => onQuery(gap.search[index] ?? identifier)}
                          title="Show this risk's chain below"
                        >
                          {identifier}
                        </button>
                      ) : (
                        <code key={identifier}>{identifier}</code>
                      ),
                    )}
                    {gap.items.length > 30 && <span className="ac-muted">and {gap.items.length - 30} more</span>}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ca-inline-ok">Every record is linked into a chain.</p>
          )}
          <ImportHint />
        </Panel>
      )}
      {data && (
        <Panel eyebrow="Requirement → risk → failure mode → control → verification" title="Traceability chains">
          <div className="rk-toolbar">
            <SearchBox value={query} onChange={onQuery} label="Search risk, product or linked record by ID" />
            <label className="ca-check">
              <input type="checkbox" checked={gapsOnly} onChange={(event) => setGapsOnly(event.target.checked)} />
              Only incomplete chains
            </label>
          </div>
          <Table
            caption="Traceability chains"
            rows={chains}
            rowKey={(row) => row.risk_id}
            empty={{ title: "No matching chains", detail: "Change the search or show complete chains too." }}
            columns={[
              referenceIdColumn("Risk ID", "risk", "risk_identifier"),
              sourceIdColumn("risk_identifier"),
              {
                key: "product",
                label: "Product",
                render: (row) => (row.product ? linkedId(row.product, row.product_business_id) : "—"),
              },
              {
                key: "requirements",
                label: "Requirements",
                render: (row) => <Ids items={linkedIds(row.requirements, row.requirement_business_ids)} />,
              },
              {
                key: "failure_modes",
                label: "Failure modes",
                render: (row) => <Ids items={linkedIds(row.failure_modes, row.failure_mode_business_ids)} />,
              },
              {
                key: "controls",
                label: "Controls",
                render: (row) => <Ids items={linkedIds(row.controls, row.control_business_ids)} />,
              },
              {
                key: "verification",
                label: "Verification evidence",
                render: (row) => (
                  <Ids items={linkedIds(row.verification_evidence, row.verification_evidence_business_ids)} />
                ),
              },
              { key: "complete", label: "Chain", render: (row) => <ChainState chain={row} /> },
              {
                key: "review",
                label: "",
                render: (row) => (
                  <ReviewButton
                    target={{ id: row.risk_id, identifier: linkedId(row.risk_identifier, row.risk_business_id) }}
                    onReview={onReview}
                  />
                ),
              },
            ]}
          />
        </Panel>
      )}
    </>
  );
}

function ImportHint() {
  const workspace = useContext(WorkspaceContext);
  const canImport =
    !!workspace &&
    sectionAllowed("Import data", workspace.session?.allowed_menu, workspace.session?.business_permissions);
  return (
    <p className="ac-note">
      Links come from your quality system. Add them there and import the records again
      {canImport ? (
        <>
          {" "}
          (
          <button type="button" className="ac-link" onClick={() => workspace?.open("Import data")}>
            Import data
          </button>
          )
        </>
      ) : (
        ", or ask your administrator to"
      )}
      .
    </p>
  );
}

function Ids({ items }: { items: string[] }) {
  return items.length ? <>{items.join(", ")}</> : <span className="ac-muted">None</span>;
}

function ChainState({ chain }: { chain: Chain }) {
  if (chain.complete) return <ToneBadge tone="good" label="Complete" />;
  return <ToneBadge tone="warning" label={`Missing ${missingLinks(chain).join(", ")}`} />;
}
