import { useEffect, useRef, useState } from "react";
import { CalendarClock, ClipboardList, Hourglass, Inbox, LogOut, X } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../console/charts";
import { Table, formatDate, useResource } from "../../customer-admin/shared";
import { ColumnScopeProvider } from "../../tables/ColumnChooser";
import { DemoRequestsWorkspace } from "../DemoRequestsWorkspace";
import { MvpRequestsWorkspace } from "../MvpRequestsWorkspace";
import { TrialRequestsWorkspace } from "../TrialRequestsWorkspace";
import { TrialFeedbackWorkspace } from "../TrialFeedbackWorkspace";
import { TrialsOverview } from "../customers/TrialsOverview";
import { TrialExitRequests } from "../customers/TrialExitRequests";
import { SupportWorkspace } from "../customers/SupportWorkspace";
import { TrialDetailPage, type TrialAiPanel } from "./TrialDetail";
import { RunDeletionNow, type DueTrial } from "./RunDeletion";
import { STATE_LABELS, STRIP, TRIAL_ORGS_PATH, type TrialCounts, type TrialState } from "./model";
import "../../customer-admin/customer-admin.css";
import "../customers/customers.css";
import "./trials.css";

export type TrialSection = "Requests" | "Trials" | "Ending and deletion" | "Feedback";

type Open = { kind: "trial"; id: string } | { kind: "workspace"; id: string } | null;

const STRIP_ICONS = [Inbox, Hourglass, CalendarClock, ClipboardList, LogOut];

/** The trial named in the address (``?trial=<id>``), so a trial's page can be reloaded or bookmarked (F-T5). */
export function trialFromAddress(search = typeof window === "undefined" ? "" : window.location.search): string | null {
  return new URLSearchParams(search).get("trial") || null;
}

/** Keep the open trial in the address without adding a history step; anything else in it stays. */
function rememberTrial(id: string | null) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("trial", id);
  else url.searchParams.delete("trial");
  if (url.href !== window.location.href) window.history.replaceState(window.history.state, "", url);
}

/**
 * Trial organizations: every free-trial link in one place, and only those. Requests and their approval, the trials
 * with one detail page each (extend, end early, convert, support access, delete data), how trials end, and feedback.
 * Once approved, a trial is listed only here; the customer lists show pilot and paying customers.
 */
export function TrialOrganizations({
  section,
  onSection,
  websiteDemos = false,
  onOpenCustomers,
  trialAiPanel,
  onDetail,
  initialTrial = trialFromAddress(),
}: {
  section: TrialSection;
  onSection: (section: TrialSection) => void;
  websiteDemos?: boolean;
  /** Opens Customers & Tenants (from a converted trial). */
  onOpenCustomers?: () => void;
  /** Part 4 (AI and usage) on each trial's page, when the AI build provides it (TrialDetail ``TrialAiPanel``). */
  trialAiPanel?: TrialAiPanel;
  /** Told whether a trial's own page is open, so the console can leave out the list's heading and tabs (F-T1). */
  onDetail?: (open: boolean) => void;
  /** The trial whose page opens first (from the address). */
  initialTrial?: string | null;
}) {
  const counts = useResource<TrialCounts>(`${TRIAL_ORGS_PATH}/summary`);
  const [open, setOpen] = useState<Open>(initialTrial ? { kind: "trial", id: initialTrial } : null);
  const [trialState, setTrialState] = useState("");
  const [message, setMessage] = useState<{ text: string; tone: "good" | "critical" } | null>(null);
  // Another section closes the open page (not the first render, which may open a trial from the address).
  const shownSection = useRef(section);
  useEffect(() => {
    if (shownSection.current !== section) setOpen(null);
    shownSection.current = section;
  }, [section]);
  useEffect(() => rememberTrial(open?.kind === "trial" ? open.id : null), [open]);
  const detailOpen = open?.kind === "trial";
  useEffect(() => onDetail?.(detailOpen), [onDetail, detailOpen]);
  useEffect(() => () => onDetail?.(false), [onDetail]);
  const notify = (text: string, tone: "good" | "critical" = "good") => setMessage({ text, tone });

  return (
    <ColumnScopeProvider scope="admin:Trial organizations">
      <div className="cc-area">
        {!detailOpen && (
          <section className="to-strip" aria-label="Trials at a glance">
            {STRIP.map((item, index) => {
              const Icon = STRIP_ICONS[index];
              const value = counts.data ? counts.data[item.key] : null;
              return (
                <StatTile
                  key={item.key}
                  label={item.label}
                  value={value}
                  detail={item.section === "Trials" ? "Show these trials" : `Open ${item.section}`}
                  tone={item.key === "ending_soon" && value ? "warning" : undefined}
                  icon={<Icon size={18} />}
                  onOpen={() => {
                    setTrialState(item.state);
                    setOpen(null);
                    onSection(item.section as TrialSection);
                  }}
                />
              );
            })}
          </section>
        )}
        {message && (
          <div className={`ac-message tone-${message.tone}`} role="status">
            {message.text}
            <button type="button" className="ac-link" onClick={() => setMessage(null)} aria-label="Dismiss message">
              <X size={14} />
            </button>
          </div>
        )}
        {open?.kind === "trial" ? (
          <TrialDetailPage
            tenantId={open.id}
            onBack={() => setOpen(null)}
            onOpenWorkspace={(id) => setOpen({ kind: "workspace", id })}
            onOpenCustomers={onOpenCustomers}
            onChanged={() => {
              counts.reload();
            }}
            onMessage={notify}
            aiPanel={trialAiPanel}
          />
        ) : open?.kind === "workspace" ? (
          <SupportWorkspace tenantId={open.id} onBack={() => setOpen(null)} onMessage={notify} />
        ) : section === "Requests" ? (
          <TrialRequests websiteDemos={websiteDemos} />
        ) : section === "Trials" ? (
          <TrialsOverview
            key={trialState}
            initialState={trialState}
            showExitRequests={false}
            onOpenTenant={(id) => setOpen({ kind: "trial", id })}
            onOpenWorkspace={(id) => setOpen({ kind: "workspace", id })}
          />
        ) : section === "Ending and deletion" ? (
          <EndingAndDeletion
            onOpenTrial={(id) => setOpen({ kind: "trial", id })}
            onChanged={counts.reload}
            onOpenCustomers={onOpenCustomers}
            onMessage={notify}
          />
        ) : (
          <div className="cc-page">
            <div className="cc-title">
              <div>
                <p className="ac-eyebrow">Feedback</p>
                <h2>Trial feedback and website quotes</h2>
              </div>
            </div>
            <TrialFeedbackWorkspace />
          </div>
        )}
      </div>
    </ColumnScopeProvider>
  );
}

/**
 * Free-trial requests (approve, approve "sample only", decline, resend the invitation), and the pilot and one-to-one
 * demo requests made from free trials; website demo requests too while the website offers them.
 */
export function TrialRequests({ websiteDemos = false }: { websiteDemos?: boolean }) {
  return (
    <div className="cc-page">
      <div className="cc-title">
        <div>
          <p className="ac-eyebrow">Requests</p>
          <h2>{websiteDemos ? "Demo and trial requests" : "Trial requests"}</h2>
          <p className="ac-muted">
            {websiteDemos
              ? "The people who asked for a demo, a free trial or, from a trial, a pilot conversation."
              : "The people who asked for a free trial and, from their trial, for a pilot conversation or a one-to-one demo."}{" "}
            Requests from company addresses are approved automatically; the others wait here for review. An approved
            trial is listed under Trials, never in the customer lists.
          </p>
        </div>
      </div>
      <TrialRequestsWorkspace />
      <MvpRequestsWorkspace />
      <DemoRequestsWorkspace websiteRequests={websiteDemos} />
    </div>
  );
}

type FormerTrial = {
  tenant_id: string;
  tenant_business_id: string | null;
  name: string;
  state: TrialState;
  conversion?: { kind: string | null; plan_code: string | null; at: string | null } | null;
  updated_at: string | null;
};

/**
 * How trials end: requests to end early, trials due for deletion with "Run deletion now", and the former trials
 * (read-only).
 */
export function EndingAndDeletion({
  onOpenTrial,
  onChanged,
  onOpenCustomers,
  onMessage = () => undefined,
}: {
  onOpenTrial: (id: string) => void;
  onChanged: () => void;
  onOpenCustomers?: () => void;
  onMessage?: (text: string, tone: "good" | "critical") => void;
}) {
  const due = useResource<{ due: DueTrial[] }>("/api/v1/platform-admin/trial-retention");
  const [former, setFormer] = useState<"CONVERTED" | "DATA_DELETED">("CONVERTED");
  const formerList = useResource<{ items: FormerTrial[]; total: number }>(`${TRIAL_ORGS_PATH}?state=${former}`);
  const dueItems = due.data?.due ?? [];
  return (
    <div className="cc-page">
      <div className="cc-title">
        <div>
          <p className="ac-eyebrow">Ending and deletion</p>
          <h2>How trials end</h2>
          <p className="ac-muted">
            A trial ended early keeps its data for 30 days unless its owner asked for deletion. Data is deleted 30 days
            after the end; open a due trial to delete its data now.
          </p>
        </div>
      </div>
      <TrialExitRequests onChanged={onChanged} />
      <Panel
        eyebrow="Retention"
        title="Trials due for deletion"
        source={due}
        action={
          <RunDeletionNow
            due={dueItems}
            onDone={(text, tone) => {
              onMessage(text, tone);
              due.reload();
              formerList.reload();
              onChanged();
            }}
          />
        }
      >
        {dueItems.length ? (
          <ul className="to-list">
            {dueItems.map((item) => (
              <li key={item.tenant_id}>
                <button type="button" className="ac-link" onClick={() => onOpenTrial(item.tenant_id)}>
                  {item.name}
                </button>
                <span>
                  Ended {formatDate(item.trial_ended_at)}
                  {item.legal_hold ? " · under a legal hold" : item.hold_reason ? ` · ${item.hold_reason}` : ""}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty
            title="No trial is due for deletion"
            detail="A trial's data is due 30 days after it ends. The nightly run deletes it; it appears here first, and Run deletion now deletes it at once."
          />
        )}
      </Panel>
      <Panel
        eyebrow="Former trials"
        title={former === "CONVERTED" ? "Converted to a pilot or paid plan" : "Trials whose data was deleted"}
        source={formerList}
        action={
          <select
            aria-label="Former trials"
            value={former}
            onChange={(event) => setFormer(event.target.value as "CONVERTED" | "DATA_DELETED")}
          >
            <option value="CONVERTED">Converted</option>
            <option value="DATA_DELETED">Data deleted</option>
          </select>
        }
      >
        <Table
          rows={formerList.data?.items ?? []}
          rowKey={(row) => row.tenant_id}
          caption={former === "CONVERTED" ? "Converted trials" : "Trials whose data was deleted"}
          onRowClick={(row) => onOpenTrial(row.tenant_id)}
          empty={
            former === "CONVERTED"
              ? {
                  title: "No trial has been converted yet",
                  detail: "A trial converted to a pilot or paid plan moves to Customers & Tenants and is listed here.",
                }
              : { title: "No trial's data has been deleted yet", detail: "Trials whose data was deleted appear here." }
          }
          columns={[
            {
              key: "name",
              label: "Organization",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => onOpenTrial(row.tenant_id)}>
                  {row.name}
                </button>
              ),
            },
            { key: "tenant_business_id", label: "MDARIX ID", render: (row) => row.tenant_business_id ?? "—" },
            {
              key: "state",
              label: "State",
              render: (row) => <ToneBadge tone="neutral" label={STATE_LABELS[row.state] ?? row.state} />,
            },
            {
              key: "conversion",
              label: "Converted",
              render: (row) =>
                row.conversion
                  ? `${row.conversion.kind === "PAID" ? "Paid" : row.conversion.kind === "PILOT" ? "Pilot" : "Plan change"} · ${formatDate(row.conversion.at)}`
                  : "—",
            },
            {
              key: "open",
              label: "",
              render: (row) =>
                row.state === "CONVERTED" && onOpenCustomers ? (
                  <button type="button" className="ac-link" onClick={onOpenCustomers}>
                    Open in Customers
                  </button>
                ) : null,
            },
          ]}
        />
      </Panel>
    </div>
  );
}
