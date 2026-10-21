import { useCallback, useEffect, useRef, useState } from "react";
import { DialogBehaviour } from "../shared/DialogBehaviour";
import { Check, Copy, MailCheck, RefreshCw, Trash2, X } from "lucide-react";
import { requestJson } from "../../app/apiClient";
import { sortParams, useServerSort, type SortState } from "../../app/tableSort";
import { formatUtc } from "../../app/dates";
import { SearchBox, Table, idColumn } from "../customer-admin/shared";
import { Pager } from "./areas/common";

type TrialRequest = {
  id: string;
  email: string;
  display_name: string;
  organization: string;
  status: "PENDING_REVIEW" | "APPROVED" | "DECLINED" | string;
  created_at: string | null;
  reviewed_at: string | null;
  /** Who approved or declined it: a Platform Administrator, or "Automatic approval (company email)". */
  reviewed_by_name?: string | null;
  decision_reason: string | null;
  tenant_key: string | null;
  tenant_identifier: string | null;
  trial_expires_at: string | null;
  data_delete_after: string | null;
  data_deleted: boolean;
  owner_status: string | null;
  // The latest invitation email: SENT, FAILED (retried by MDARIX, resend here), NOT_CONFIGURED; null before 0.10.29.
  invitation_delivery?: string | null;
  invitation_attempted_at?: string | null;
  // What the requester told MDARIX about their company and trial, as readable lines (trial/request_profile.py).
  profile?: { job_title?: string; country?: string; [key: string]: unknown };
  profile_lines?: { label: string; value: string }[];
  /** Which legal texts sending the request accepted, and when (md48); null for requests sent before 0.10.33. */
  legal_acceptance?: LegalAcceptance | null;
};

type LegalVersion = { available: boolean; last_updated: string | null; sha256: string | null };
type LegalAcceptance = { accepted_at: string; documents: Record<string, LegalVersion> };

const LEGAL_TEXT_NAMES: [string, string][] = [
  ["terms", "Terms of Service"],
  ["trial-agreement", "Free Trial Agreement"],
  ["privacy", "Privacy Policy"],
];

/** The legal texts a request accepted, as review lines: each text's version ("Last updated" date and its full SHA-256
 * fingerprint, which wraps), then when it was accepted, to the second in UTC (DEV-027). Empty for a request sent
 * before the versions were recorded. */
export function legalAcceptanceLines(
  acceptance: LegalAcceptance | null | undefined,
): { label: string; value: string }[] {
  if (!acceptance?.documents) return [];
  const lines = LEGAL_TEXT_NAMES.map(([key, name]) => {
    const version = acceptance.documents[key];
    const value = !version?.available
      ? "not published when the request was sent"
      : `${version.last_updated ? `last updated ${version.last_updated}` : "no date in the text"}${
          version.sha256 ? ` · SHA-256 ${version.sha256}` : ""
        }`;
    return { label: name, value };
  });
  return [...lines, { label: "Accepted", value: formatUtc(acceptance.accepted_at) }];
}

/** Everything "About the request" lists: the requester's answers, the legal texts accepted and who reviewed it. */
export const requestLines = (row: TrialRequest) => [
  ...(row.profile_lines ?? []),
  ...legalAcceptanceLines(row.legal_acceptance),
  ...reviewLines(row),
];

/** Who approved or declined the request, and when in UTC (DEV-027); nothing while it waits for review. */
export function reviewLines(
  row: Pick<TrialRequest, "status" | "reviewed_at" | "reviewed_by_name">,
): { label: string; value: string }[] {
  const decided = row.status === "APPROVED" ? "Approved" : row.status === "DECLINED" ? "Declined" : null;
  if (!decided || !row.reviewed_at) return [];
  return [{ label: decided, value: `${row.reviewed_by_name ?? "—"}, ${formatUtc(row.reviewed_at)}` }];
}
/** A closed trial past its 30 days (backend/app/trial/retention.py trials_due); a held one is kept by the run. */
type DueTrial = {
  tenant_id: string;
  tenant_key: string;
  name: string;
  trial_ended_at: string;
  delete_after: string;
  legal_hold?: boolean;
  held_for_mvp_request?: boolean;
  hold_until?: string;
};
/** Why a due trial is kept by the run, or null when it is deleted. */
export const keptBecause = (trial: Pick<DueTrial, "legal_hold" | "held_for_mvp_request" | "hold_until">) =>
  trial.legal_hold
    ? "under a legal hold"
    : trial.held_for_mvp_request
      ? `held for its pilot request${trial.hold_until ? ` until ${new Date(trial.hold_until).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} at the latest` : ""}`
      : null;
type ReviewResult = TrialRequest & { email_delivery?: string; email_error?: string; activation_path?: string };

/** One page of the queue (backend/app/trial/service.py request_queue): counts per status for the tabs. */
export type TrialRequestPage = {
  items: TrialRequest[];
  counts: Record<string, number>;
  page?: number;
  pages?: number;
  total?: number;
};

const FILTERS: [string, string][] = [
  ["PENDING_REVIEW", "Pending"],
  ["APPROVED", "Approved"],
  ["DECLINED", "Declined"],
];

/** Columns the server orders every page by. */
export const TRIAL_REQUEST_SORT_KEYS = ["business_id", "organization", "requester", "requested"] as const;

/** The queue request for one tab's page: its status, page, order and search (company, requester, email, ID). */
export function trialRequestsPath({
  status,
  page,
  sort,
  q,
}: {
  status: string;
  page: number;
  sort: SortState;
  q: string;
}): string {
  const params = new URLSearchParams({ status, page: String(page), ...sortParams(sort) });
  if (q.trim()) params.set("q", q.trim());
  return `/api/v1/platform-admin/trial-requests?${params}`;
}

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—";

/**
 * Why an approved trial's owner has not activated yet, when it is the email: the invitation did not go out (MDARIX
 * retries it and alerts operations; Resend invitation sends it now) or this server sends no email. Null otherwise.
 */
export function invitationProblem(row: Pick<TrialRequest, "status" | "owner_status" | "invitation_delivery">) {
  if (row.status !== "APPROVED" || row.owner_status !== "INVITED") return null;
  if (row.invitation_delivery === "FAILED") return "Invitation not delivered";
  if (row.invitation_delivery === "NOT_CONFIGURED") return "Invitation not sent: email is not set up";
  return null;
}

// Free-trial requests from the website. Approve creates the private 30-day trial workspace and sends the invitation.
export function TrialRequestsWorkspace() {
  const [items, setItems] = useState<TrialRequest[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [listed, setListed] = useState({ page: 1, pages: 1, total: 0 });
  const [filter, setFilter] = useState("PENDING_REVIEW");
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const { sort, onSort } = useServerSort(() => setPage(1));
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<TrialRequest | null>(null);
  const [declining, setDeclining] = useState<TrialRequest | null>(null);
  const [retention, setRetention] = useState<DueTrial[] | null>(null);
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<{ tone: "good" | "bad"; text: string; link?: string } | null>(null);

  const path = trialRequestsPath({ status: filter, page, sort, q: query });
  // Only the answer to the latest request is shown (typing a search sends one request per keystroke).
  const latest = useRef(path);
  const load = useCallback(() => {
    latest.current = path;
    setState("loading");
    requestJson<TrialRequestPage>(path)
      .then((data) => {
        if (latest.current !== path) return;
        setItems(data.items);
        setCounts(data.counts);
        setListed({ page: data.page ?? 1, pages: data.pages ?? 1, total: data.total ?? data.items.length });
        setState("ready");
      })
      .catch(() => latest.current === path && setState("error"));
  }, [path]);
  useEffect(load, [load]);

  const act = async (row: TrialRequest, path: string, body?: object) => {
    setBusy(row.id);
    setResult(null);
    try {
      const data = await requestJson<ReviewResult>(`/api/v1/platform-admin/trial-requests/${row.id}/${path}`, {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      const link = data.activation_path ? `${window.location.origin}${data.activation_path}` : undefined;
      const sent = data.email_delivery === "SENT";
      const created = path === "approve" ? `Trial workspace ${data.tenant_key} created for ${row.organization}. ` : "";
      setResult(
        path === "decline"
          ? { tone: "good", text: `Declined ${row.organization}.` }
          : sent
            ? { tone: "good", text: `${created}Invitation emailed to ${row.email}.` }
            : link
              ? {
                  tone: "good",
                  text: `${created}Email is not configured on this development server. Send ${row.email} this one-time activation link (valid 48 hours):`,
                  link,
                }
              : {
                  tone: "bad",
                  text: `${created}The invitation email to ${row.email} could not be sent${
                    data.email_error ? `: ${data.email_error}` : "."
                  } Fix the email settings, then use Resend invitation.`,
                },
      );
      load();
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "The request could not be completed." });
    } finally {
      setBusy(null);
      setConfirming(null);
      setDeclining(null);
      setReason("");
    }
  };

  const openRetention = async () => {
    setResult(null);
    try {
      const data = await requestJson<{ due: DueTrial[] }>("/api/v1/platform-admin/trial-retention");
      setRetention(data.due);
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "Retention could not be checked." });
    }
  };
  const runRetention = async () => {
    setBusy("retention");
    try {
      const data = await requestJson<{ purged: number }>("/api/v1/platform-admin/trial-retention/run", {
        method: "POST",
      });
      setResult({
        tone: "good",
        text: `Deleted the data of ${data.purged} closed trial${data.purged === 1 ? "" : "s"}.`,
      });
      load();
    } catch (error) {
      setResult({ tone: "bad", text: error instanceof Error ? error.message : "Trial data could not be deleted." });
    } finally {
      setBusy(null);
      setRetention(null);
    }
  };

  // The server sends only the chosen tab's page (older answers may hold every status).
  const rows = items.filter((item) => item.status === filter);
  // Due trials a legal hold or an open pilot request keeps are listed apart: the run skips them.
  const deleting = (retention ?? []).filter((trial) => !keptBecause(trial));
  const kept = (retention ?? []).filter((trial) => keptBecause(trial));
  return (
    <section className="platform-admin-card trial-queue" aria-labelledby="trial-queue-title">
      <div className="platform-admin-card-title">
        <div>
          <span className="eyebrow">Free trial requests</span>
          <h3 id="trial-queue-title">Website sign-ups waiting for review</h3>
          <p>
            Approve to create a private 30-day trial workspace with sample data and email the requester an invitation.
            Decline with a reason; nothing is created.
          </p>
        </div>
        <div className="trial-queue-head-actions">
          <button className="platform-admin-secondary" onClick={openRetention} disabled={busy !== null}>
            <Trash2 size={15} /> Delete expired trial data
          </button>
          <button className="platform-admin-secondary" onClick={load} disabled={state === "loading"}>
            <RefreshCw size={15} /> Refresh
          </button>
        </div>
      </div>

      <div className="trial-queue-filters" role="tablist" aria-label="Trial request status">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={filter === value}
            className={filter === value ? "is-active" : ""}
            onClick={() => {
              setFilter(value);
              setPage(1);
            }}
          >
            {label} <span>{counts[value] ?? 0}</span>
          </button>
        ))}
      </div>
      <div className="cc-toolbar">
        <SearchBox
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
          label="Search company, requester, email or ID"
        />
      </div>

      {result && (
        <div className={`trial-queue-result is-${result.tone}`} role="status">
          <p>{result.text}</p>
          {result.link && (
            <div className="trial-queue-link">
              <code>{result.link}</code>
              <button
                className="platform-admin-secondary"
                onClick={() => navigator.clipboard?.writeText(result.link ?? "")}
                aria-label="Copy activation link"
              >
                <Copy size={14} /> Copy
              </button>
            </div>
          )}
        </div>
      )}

      {state === "error" ? (
        <p className="trial-queue-empty">Trial requests could not be loaded. Refresh to try again.</p>
      ) : state === "loading" && !items.length ? (
        <p className="trial-queue-empty">Loading trial requests…</p>
      ) : rows.length === 0 ? (
        <p className="trial-queue-empty">
          {query.trim()
            ? "No request matches the search."
            : filter === "PENDING_REVIEW"
              ? "No requests are waiting for review."
              : "Nothing here yet."}
        </p>
      ) : (
        <Table
          caption="Trial requests"
          rows={rows}
          rowKey={(row) => row.id}
          serverSort={{ sort, onSort, keys: TRIAL_REQUEST_SORT_KEYS }}
          empty={{ title: "Nothing here yet", detail: "Requests appear here as companies ask for a trial." }}
          columns={[
            idColumn("Request ID"),
            { key: "organization", label: "Company", render: (row) => <strong>{row.organization}</strong> },
            {
              key: "requester",
              label: "Requester",
              render: (row) => (
                <span className="cc-stack">
                  {row.display_name}
                  <small>{row.email}</small>
                  {Boolean(row.profile?.job_title || row.profile?.country) && (
                    <small>{[row.profile?.job_title, row.profile?.country].filter(Boolean).join(" · ")}</small>
                  )}
                </span>
              ),
            },
            {
              key: "answers",
              label: "About the request",
              render: (row) =>
                row.profile_lines?.length ? (
                  <details className="trial-queue-answers">
                    <summary>{row.profile_lines.length} answers</summary>
                    <dl>
                      {requestLines(row).map((line) => (
                        <div key={line.label}>
                          <dt>{line.label}</dt>
                          <dd>{line.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                ) : (
                  <small>Not given (requested before these questions)</small>
                ),
            },
            { key: "requested", label: "Requested", render: (row) => formatDate(row.created_at) },
            {
              key: "outcome",
              label: filter === "APPROVED" ? "Workspace" : filter === "DECLINED" ? "Reason" : "Status",
              render: (row) =>
                row.status === "APPROVED" ? (
                  <span className="cc-stack">
                    {invitationProblem(row) && (
                      <span className="trial-queue-pill is-problem" role="status">
                        {invitationProblem(row)}
                        {row.invitation_attempted_at ? ` · tried ${formatDate(row.invitation_attempted_at)}` : ""}
                      </span>
                    )}
                    {row.tenant_key}
                    {reviewLines(row).map((line) => (
                      <small key={line.label}>
                        {line.label} by {line.value}
                      </small>
                    ))}
                    {row.data_deleted ? (
                      <small>Trial data deleted</small>
                    ) : (
                      <small>
                        Trial ends {formatDate(row.trial_expires_at)} · data kept until{" "}
                        {formatDate(row.data_delete_after)}
                      </small>
                    )}
                  </span>
                ) : row.status === "DECLINED" ? (
                  (row.decision_reason ?? "—")
                ) : (
                  <span className="trial-queue-pill">Pending review</span>
                ),
            },
            {
              key: "actions",
              label: "",
              render: (row) => (
                <div className="trial-queue-actions">
                  {row.status === "PENDING_REVIEW" && (
                    <>
                      <button
                        className="platform-admin-primary"
                        disabled={busy !== null}
                        onClick={() => setConfirming(row)}
                      >
                        <Check size={14} /> Approve
                      </button>
                      <button
                        className="platform-admin-secondary"
                        disabled={busy !== null}
                        onClick={() => setDeclining(row)}
                      >
                        <X size={14} /> Decline
                      </button>
                    </>
                  )}
                  {row.status === "APPROVED" && row.owner_status === "INVITED" && !row.data_deleted && (
                    <button
                      className="platform-admin-secondary"
                      disabled={busy !== null}
                      onClick={() => act(row, "resend-invitation")}
                    >
                      <MailCheck size={14} /> Resend invitation
                    </button>
                  )}
                  {row.status === "APPROVED" && row.owner_status === "ACTIVE" && !row.data_deleted && (
                    <span className="trial-queue-pill is-active">Owner active</span>
                  )}
                </div>
              ),
            },
          ]}
        />
      )}
      {state !== "error" && listed.total > 0 && (
        <Pager page={listed.page} pages={listed.pages} total={listed.total} noun="request" onPage={setPage} />
      )}

      {confirming && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-approve-title">
          <DialogBehaviour onClose={() => setConfirming(null)} />
          <div>
            <h4 id="trial-approve-title">Approve a free trial for {confirming.organization}?</h4>
            <p>This creates, in one step:</p>
            <ul>
              <li>a private trial workspace on the Free Trial plan (3 users, 5,000 uploaded rows)</li>
              <li>a 30-day trial that closes automatically</li>
              <li>the sample dataset</li>
              <li>an account for {confirming.email} and a one-time invitation valid for 48 hours</li>
            </ul>
            <div className="trial-queue-dialog-actions">
              <button className="platform-admin-secondary" onClick={() => setConfirming(null)}>
                Cancel
              </button>
              <button
                className="platform-admin-primary"
                disabled={busy !== null}
                onClick={() => act(confirming, "approve")}
              >
                {busy ? "Creating workspace…" : "Approve and create workspace"}
              </button>
            </div>
          </div>
        </div>
      )}

      {retention && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-retention-title">
          <DialogBehaviour onClose={() => setRetention(null)} />
          <div>
            <h4 id="trial-retention-title">Delete expired trial data</h4>
            {deleting.length === 0 ? (
              <p>No closed trial is due for deletion. Nothing will be deleted.</p>
            ) : (
              <>
                <p>
                  These trials closed more than 30 days ago. Their records and uploads are deleted, their users can no
                  longer sign in, and the workspace is archived. The audit trail is kept. This cannot be undone.
                </p>
                <ul>
                  {deleting.map((trial) => (
                    <li key={trial.tenant_id}>
                      {trial.name} ({trial.tenant_key}), trial ended {formatDate(trial.trial_ended_at)}
                    </li>
                  ))}
                </ul>
              </>
            )}
            {kept.length > 0 && (
              <>
                <p>Kept for now:</p>
                <ul>
                  {kept.map((trial) => (
                    <li key={trial.tenant_id}>
                      {trial.name} ({trial.tenant_key}), {keptBecause(trial)}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <div className="trial-queue-dialog-actions">
              <button className="platform-admin-secondary" onClick={() => setRetention(null)}>
                {deleting.length ? "Cancel" : "Close"}
              </button>
              {deleting.length > 0 && (
                <button className="platform-admin-primary" disabled={busy !== null} onClick={runRetention}>
                  {busy ? "Deleting…" : `Delete data of ${deleting.length} trial${deleting.length === 1 ? "" : "s"}`}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {declining && (
        <div className="trial-queue-dialog" role="dialog" aria-modal="true" aria-labelledby="trial-decline-title">
          <DialogBehaviour onClose={() => setDeclining(null)} />
          <form
            onSubmit={(event) => {
              event.preventDefault();
              act(declining, "decline", { reason: reason.trim() });
            }}
          >
            <h4 id="trial-decline-title">Decline the request from {declining.organization}?</h4>
            <label>
              Reason (kept for audit)
              <textarea
                required
                minLength={3}
                maxLength={500}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="For example: not a medical-device organization"
              />
            </label>
            <div className="trial-queue-dialog-actions">
              <button type="button" className="platform-admin-secondary" onClick={() => setDeclining(null)}>
                Cancel
              </button>
              <button
                type="submit"
                className="platform-admin-primary"
                disabled={busy !== null || reason.trim().length < 3}
              >
                Decline request
              </button>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}
