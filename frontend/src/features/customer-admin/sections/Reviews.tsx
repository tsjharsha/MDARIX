import { useState } from "react";
import { Download } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { Table, Tabs, errorText, formatDate, send, useResource } from "../shared";
import { plural } from "../labels";

/**
 * B6a Part C: the reviews the organization signs (flat operational screens, G-2). The server decides who may read and
 * sign each one; this screen only shows the answer: the audit trail review (a Leader or Quality Reviewer signs; own
 * flags need a second reviewer), the access review (a customer administrator signs once every row is marked) and the
 * configuration snapshot (signed, downloadable, compared with now or another snapshot).
 */
const TABS = ["Audit trail review", "Access review", "Configuration"] as const;
type Tab = (typeof TABS)[number];
const REVIEWS = "/api/v1/reviews";

type Flag = { code: string; label: string; count: number; actors: string[]; events: AuditLine[] };
type AuditLine = {
  id: string;
  plane: string;
  at: string;
  actor: string | null;
  action: string;
  entity_type: string;
  reason: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
};
type Signed = { review_id: string; signed_at: string; signed_by: string; findings: string; fingerprint: string };
type AuditReview = {
  period: { from: string; to: string };
  flags: Flag[];
  chain_valid: boolean;
  planes: { plane: string; events: number; chain_valid: boolean; first_broken_seq: number | null }[];
  events: number;
  incomplete: string[];
  own_flags: string[];
  may_sign: boolean;
  last_signed: Signed | null;
  next_due: string;
  awaiting_confirmation: Signed[];
};

export function ReviewsSection() {
  const [tab, setTab] = useState<Tab>(TABS[0]);
  return (
    <Tabs tabs={TABS} active={tab} onChange={setTab} label="Signed reviews">
      {tab === "Audit trail review" && <AuditTrailReview />}
      {tab === "Access review" && <AccessReview />}
      {tab === "Configuration" && <ConfigurationReview />}
    </Tabs>
  );
}

const values = (value: Record<string, unknown> | null) => (value ? JSON.stringify(value) : "—");

/** Findings, the current password and (when signatures need it) the authenticator code; the server re-checks both. */
export function SignForm({
  path,
  body = {},
  label,
  onSigned,
  disabledWhy,
}: {
  path: string;
  body?: Record<string, unknown>;
  label: string;
  onSigned: () => void;
  disabledWhy?: string | false;
}) {
  const [findings, setFindings] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const result = await send<{ needs_second_reviewer?: boolean }>(path, "POST", {
        ...body,
        findings,
        password,
        mfa_code: code || null,
      });
      setFindings("");
      setPassword("");
      setCode("");
      setMessage(
        result?.needs_second_reviewer
          ? "Signed. Your own actions are among the flags: a second reviewer confirms them."
          : "Signed.",
      );
      onSigned();
    } catch (reason) {
      setMessage(errorText(reason, "It was not signed."));
    } finally {
      setBusy(false);
    }
  };
  const why =
    disabledWhy || (!findings.trim() && "Write your findings, or 'none'.") || (!password && "Enter your password.");
  return (
    <form className="ca-form" onSubmit={submit} aria-label={label}>
      <label className="ca-field">
        Findings
        <textarea value={findings} maxLength={4000} onChange={(e) => setFindings(e.target.value)} />
      </label>
      <div className="ca-action-row">
        <label className="ca-field">
          Your password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label className="ca-field">
          Authenticator code
          <input inputMode="numeric" maxLength={20} value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
        <button type="submit" className="ac-primary" disabled={busy || Boolean(why)}>
          {busy ? "Signing…" : label}
        </button>
      </div>
      {why && <small className="ac-muted">{why}</small>}
      {message && (
        <p role="status" className="ac-muted">
          {message}
        </p>
      )}
    </form>
  );
}

function Downloads({ reviewId }: { reviewId: string }) {
  return (
    <span className="ca-row-actions">
      <a className="ac-secondary" href={`${REVIEWS}/signed/${reviewId}/download?format=pdf`} download>
        <Download size={15} /> PDF
      </a>
      <a className="ac-secondary" href={`${REVIEWS}/signed/${reviewId}/download?format=json`} download>
        <Download size={15} /> JSON
      </a>
    </span>
  );
}

export function AuditTrailReview() {
  const [period, setPeriod] = useState({ from: "", to: "" });
  const query = period.from && period.to ? `?from=${period.from}&to=${period.to}` : "";
  const review = useResource<AuditReview>(`${REVIEWS}/audit-trail${query}`);
  const [open, setOpen] = useState<string | null>(null);
  const data = review.data;
  const flagged = data?.flags.find((flag) => flag.code === open);
  return (
    <Panel eyebrow="Audit trail review" title="Red flags first, then every event" source={review}>
      {data && (
        <>
          <p className="ac-muted">
            {formatDate(data.period.from)} to {formatDate(data.period.to)} · {plural(data.events, "event")} read from{" "}
            {data.planes.map((plane) => plane.plane).join(" and ")} · next review due {formatDate(data.next_due)}
            {data.last_signed ? ` · last signed ${formatDate(data.last_signed.signed_at)}` : " · never signed"}
          </p>
          <div className="ca-action-row">
            <label className="ca-field">
              From
              <input type="date" value={period.from} onChange={(e) => setPeriod({ ...period, from: e.target.value })} />
            </label>
            <label className="ca-field">
              To
              <input type="date" value={period.to} onChange={(e) => setPeriod({ ...period, to: e.target.value })} />
            </label>
          </div>
          <p role="status" className={data.chain_valid ? "ac-muted" : "ca-inline-error"}>
            {data.chain_valid
              ? "Audit chain check: intact."
              : `Audit chain check: broken (from event #${data.planes.find((p) => !p.chain_valid)?.first_broken_seq}). Contact MDARIX support.`}
            {data.incomplete.length
              ? " This period holds more events than one review reads: choose a shorter period."
              : ""}
          </p>
          <Table
            caption="Red flags"
            rows={data.flags}
            rowKey={(flag) => flag.code}
            empty={{ title: "No flags", detail: "Nothing to look at first." }}
            columns={[
              { key: "label", label: "Flag", render: (flag) => <strong>{flag.label}</strong> },
              { key: "count", label: "Count", render: (flag) => flag.count },
              {
                key: "open",
                label: "",
                render: (flag) =>
                  flag.count ? (
                    <button
                      type="button"
                      className="ac-link"
                      onClick={() => setOpen(open === flag.code ? null : flag.code)}
                    >
                      {open === flag.code ? "Hide" : "Show"}
                    </button>
                  ) : null,
              },
            ]}
          />
          {flagged && <EventTable caption={flagged.label} rows={flagged.events} />}
          {data.own_flags.length > 0 && (
            <p className="ac-muted">
              Your own actions are among the flags: a second reviewer confirms them after you sign.
            </p>
          )}
          {data.awaiting_confirmation.map((item) => (
            <div key={item.review_id} className="ca-form">
              <p>
                <strong>Second reviewer needed</strong> for the review signed {formatDate(item.signed_at)}.
              </p>
              <Downloads reviewId={item.review_id} />
              {data.may_sign && (
                <SignForm
                  path={`${REVIEWS}/audit-trail/${item.review_id}/confirm`}
                  label="Confirm as second reviewer"
                  onSigned={review.reload}
                />
              )}
            </div>
          ))}
          {data.may_sign ? (
            <SignForm
              path={`${REVIEWS}/audit-trail/sign`}
              body={{ period_from: data.period.from, period_to: data.period.to }}
              label="Sign the audit trail review"
              onSigned={review.reload}
            />
          ) : (
            <p className="ac-muted">A Leader or Quality Reviewer signs this review.</p>
          )}
          {data.last_signed && <Downloads reviewId={data.last_signed.review_id} />}
        </>
      )}
    </Panel>
  );
}

function EventTable({ caption, rows }: { caption: string; rows: AuditLine[] }) {
  return (
    <Table
      caption={caption}
      rows={rows}
      rowKey={(row) => row.id}
      pageSize={50}
      pageNoun="event"
      empty={{ title: "No events", detail: "" }}
      columns={[
        { key: "at", label: "When", render: (row) => formatDate(row.at) },
        { key: "action", label: "Action", render: (row) => row.action },
        { key: "record", label: "Record type", render: (row) => row.entity_type },
        { key: "reason", label: "Reason", render: (row) => row.reason ?? "—" },
        { key: "old", label: "Before", render: (row) => values(row.old_values) },
        { key: "new", label: "After", render: (row) => values(row.new_values) },
      ]}
    />
  );
}

type AccessRow = {
  user_id: string;
  name: string;
  email: string;
  role_label: string;
  other_roles: string[];
  mfa_on: boolean;
  last_active: string | null;
  invited_at: string | null;
  changes: unknown[];
  mark: { mark: string; by: string; at: string } | null;
};

export function AccessReview() {
  const review = useResource<{ rows: AccessRow[]; unmarked: number; next_due: string; may_sign: boolean }>(
    `${REVIEWS}/access`,
  );
  const [error, setError] = useState("");
  const mark = async (userId: string, value: string) => {
    setError("");
    try {
      await send(`${REVIEWS}/access/marks`, "POST", { user_id: userId, mark: value });
      review.reload();
    } catch (reason) {
      setError(errorText(reason, "The mark was not saved."));
    }
  };
  const data = review.data;
  return (
    <Panel eyebrow="Access review" title="Keep, change or remove each person's access" source={review}>
      {data && (
        <>
          <p className="ac-muted">
            Due {formatDate(data.next_due)} · {plural(data.unmarked, "row")} not marked yet. Change and Remove are done
            in Users; this review records what was decided.
          </p>
          {error && <p className="ca-inline-error">{error}</p>}
          <Table
            caption="Active users"
            rows={data.rows}
            rowKey={(row) => row.user_id}
            pageSize={50}
            pageNoun="person"
            empty={{ title: "No active users", detail: "" }}
            columns={[
              { key: "name", label: "Person", render: (row) => `${row.name} (${row.email})` },
              {
                key: "roles",
                label: "Roles",
                render: (row) => [row.role_label, ...row.other_roles].join(", "),
              },
              { key: "mfa", label: "MFA", render: (row) => (row.mfa_on ? "On" : "Off") },
              {
                key: "active",
                label: "Last active",
                render: (row) => (row.last_active ? formatDate(row.last_active) : "—"),
              },
              { key: "changes", label: "Changes", render: (row) => row.changes.length },
              {
                key: "mark",
                label: "Decision",
                render: (row) => (
                  <select
                    aria-label={`Decision for ${row.name}`}
                    value={row.mark?.mark ?? ""}
                    onChange={(e) => void mark(row.user_id, e.target.value)}
                  >
                    <option value="">Not marked</option>
                    <option value="KEEP">Keep</option>
                    <option value="CHANGE">Change</option>
                    <option value="REMOVE">Remove</option>
                  </select>
                ),
              },
            ]}
          />
          {data.may_sign ? (
            <SignForm
              path={`${REVIEWS}/access/sign`}
              label="Sign the access review"
              onSigned={review.reload}
              disabledWhy={data.unmarked > 0 && "Mark every row first."}
            />
          ) : (
            <p className="ac-muted">A customer administrator signs this review.</p>
          )}
        </>
      )}
    </Panel>
  );
}

type Change = {
  item: string;
  before: unknown;
  after: unknown;
  events: { who: string; when: string; why: string | null }[];
};

export function ConfigurationReview() {
  const signed = useResource<Signed[]>(`${REVIEWS}/configuration/signed`);
  const [before, setBefore] = useState("");
  const compared = useResource<{ changes: Change[] }>(
    before ? `${REVIEWS}/configuration/compare?before=${before}&after=now` : null,
  );
  const list = signed.data ?? [];
  return (
    <Panel eyebrow="Configuration" title="The configuration in force, signed and compared" source={signed}>
      <p className="ac-muted">
        A snapshot holds reporting windows and roles per market, rule versions and floors, switches, the calendar,
        intake and connector settings (never keys) and every user&apos;s roles.
      </p>
      <SignForm path={`${REVIEWS}/configuration/sign`} label="Sign a snapshot of now" onSigned={signed.reload} />
      <Table
        caption="Signed snapshots"
        rows={list}
        rowKey={(row) => row.review_id}
        empty={{ title: "No signed snapshot yet", detail: "Sign one above." }}
        columns={[
          { key: "when", label: "Signed", render: (row) => formatDate(row.signed_at) },
          { key: "findings", label: "Findings", render: (row) => row.findings },
          { key: "files", label: "Download", render: (row) => <Downloads reviewId={row.review_id} /> },
          {
            key: "compare",
            label: "",
            render: (row) => (
              <button type="button" className="ac-link" onClick={() => setBefore(row.review_id)}>
                Compare with now
              </button>
            ),
          },
        ]}
      />
      {before && compared.data && (
        <Table
          caption="Changes since the snapshot"
          rows={compared.data.changes}
          rowKey={(row) => row.item}
          empty={{ title: "Nothing changed", detail: "The configuration is as signed." }}
          columns={[
            { key: "item", label: "Item", render: (row) => row.item },
            { key: "before", label: "Before", render: (row) => JSON.stringify(row.before) },
            { key: "after", label: "After", render: (row) => JSON.stringify(row.after) },
            {
              key: "why",
              label: "Who, when, why",
              render: (row) =>
                row.events.map((event) => `${formatDate(event.when)}: ${event.why ?? "no reason given"}`).join("; ") ||
                "—",
            },
          ]}
        />
      )}
    </Panel>
  );
}
