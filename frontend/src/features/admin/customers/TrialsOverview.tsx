import { useState } from "react";
import { CalendarCheck, CalendarClock, MessageSquare, Rocket, Sparkles, Upload, Users } from "lucide-react";
import { BarList, Panel, StatTile, ToneBadge } from "../console/charts";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  formatDate,
  send,
  useResource,
  type Confirmation,
  type Resource,
} from "../../customer-admin/shared";
import { useServerSort, type SortState } from "../../../app/tableSort";
import { Pager } from "../areas/common";
import {
  TRIAL_SORT_KEYS,
  TRIAL_STATE_FILTERS,
  attentionList,
  chapterFunnel,
  nextChapterTitle,
  storyStage,
  teamChangeText,
  trialStateOf,
  trialsPath,
  type TrialItem,
  type TrialOverview,
  type TrialPerson,
} from "./trials";
import { TrialExitRequests } from "./TrialExitRequests";

/**
 * Trials: every free trial still holding data, as MDARIX staff need to see it to help a prospect succeed. How many
 * days are left, how much of the trial's limits is used, how far into the story (the quality loop, chapter by
 * chapter) it went and which chapter it should try next, when someone last did something, and what it told us. A
 * chapter counts only when the trial acted in it (a record it created), never on page views. The figures cover every
 * trial; the table shows one page at a time, searched, filtered and sorted by the server.
 */
export function TrialsOverview({ onOpenTenant }: { onOpenTenant: (tenantId: string) => void }) {
  const [page, setPage] = useState(1);
  const [state, setState] = useState("");
  const [query, setQuery] = useState("");
  const { sort, onSort } = useServerSort(() => setPage(1));
  const overview = useResource<TrialOverview>(trialsPath({ page, sort, state, q: query }));
  return (
    <TrialsOverviewView
      overview={overview}
      onOpenTenant={onOpenTenant}
      table={{
        page,
        onPage: setPage,
        state,
        onState: (value) => {
          setState(value);
          setPage(1);
        },
        query,
        onQuery: (value) => {
          setQuery(value);
          setPage(1);
        },
        sort,
        onSort,
      }}
    />
  );
}

export type TrialTableControls = {
  page: number;
  onPage: (page: number) => void;
  state: string;
  onState: (state: string) => void;
  query: string;
  onQuery: (query: string) => void;
  sort: SortState;
  onSort: (key: string) => void;
};

/** The screen for one answer of the overview (separate from the requests, so it renders on its own in tests). */
export function TrialsOverviewView({
  overview,
  onOpenTenant,
  table,
}: {
  overview: Resource<TrialOverview>;
  onOpenTenant: (tenantId: string) => void;
  table: TrialTableControls;
}) {
  const data = overview.data;
  const summary = data?.summary;
  const engagedAt = data?.engaged_chapters ?? 4;
  const items = data?.items ?? [];
  const attention = attentionList(data, engagedAt);
  const filtered = Boolean(table.state || table.query.trim());
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [notice, setNotice] = useState("");
  return (
    <div className="cc-page">
      <div className="cc-title">
        <div>
          <p className="ac-eyebrow">Trials</p>
          <h2>Free trials and how far into the story they went</h2>
          <p className="ac-muted">
            Each trial starts with sample data that tells the whole story; a chapter counts once the trial acts in it
            (decides, records, runs or signs), so this shows what prospects actually tried.
          </p>
        </div>
      </div>
      <section className="ac-stats" aria-label="Trial figures">
        <StatTile
          label="Active trials"
          value={summary ? summary.active : null}
          detail={summary ? `${summary.trials} holding data in all` : "Unavailable"}
          icon={<Rocket size={18} />}
        />
        <StatTile
          label="Ending within 7 days"
          value={summary ? summary.ending_soon : null}
          detail="Talk to them before the trial closes"
          tone={summary?.ending_soon ? "warning" : undefined}
          icon={<CalendarClock size={18} />}
        />
        <StatTile
          label="Acted in the story"
          value={summary ? summary.acted : null}
          detail={summary ? `${summary.engaged} engaged (${engagedAt}+ chapters)` : "Unavailable"}
          icon={<Sparkles size={18} />}
        />
        <StatTile
          label="Uploaded their own data"
          value={summary ? summary.own_data : null}
          detail="The strongest sign of intent"
          icon={<Upload size={18} />}
        />
        <StatTile
          label="Booked a demo"
          value={summary ? (summary.demo_requested ?? 0) : null}
          detail="From Getting started; contact them under Onboarding"
          tone={summary?.demo_requested ? "good" : undefined}
          icon={<CalendarCheck size={18} />}
        />
        <StatTile
          label="Gave feedback"
          value={summary ? summary.feedback : null}
          detail="Read it under Feedback"
          icon={<MessageSquare size={18} />}
        />
      </section>
      <div className="ac-grid two">
        <Panel eyebrow="Where trials stop" title="Active trials that acted in each chapter" source={overview}>
          <BarList items={chapterFunnel(data)} colour="series" />
          <p className="ac-note">
            Read it as a funnel: a chapter many trials skip is where the story needs a better first step.
          </p>
        </Panel>
        <Panel eyebrow="Help them succeed" title="Who needs attention first" source={overview}>
          <ul className="cc-trial-attention">
            {attention.map((item) => (
              <li key={item.tenant_id}>
                <button type="button" className="ac-link" onClick={() => onOpenTenant(item.tenant_id)}>
                  {item.name}
                </button>
                <span>
                  {item.days_left} days left · {item.story.acted_count} of {item.story.total} chapters · next:{" "}
                  {nextChapterTitle(item, data?.chapters ?? [])}
                </span>
              </li>
            ))}
          </ul>
          {!attention.length && <p className="ac-muted">No active trial.</p>}
        </Panel>
      </div>
      <TrialExitRequests onChanged={overview.reload} />
      <Panel eyebrow="Every trial" title="Trials holding data" source={overview}>
        <div className="cc-toolbar">
          <SearchBox value={table.query} onChange={table.onQuery} label="Search organization, tenant or owner email" />
          <select aria-label="Trial state" value={table.state} onChange={(event) => table.onState(event.target.value)}>
            {TRIAL_STATE_FILTERS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <Table<TrialItem>
          caption="Free trials"
          rows={items}
          rowKey={(row) => row.tenant_id}
          serverSort={{ sort: table.sort, onSort: table.onSort, keys: TRIAL_SORT_KEYS }}
          empty={
            filtered
              ? { title: "No matching trials", detail: "Change the search or the trial state." }
              : { title: "No free trials", detail: "Approved trial requests appear here with their progress." }
          }
          columns={[
            {
              key: "name",
              label: "Organization",
              render: (row) => (
                <span className="cc-trial-org">
                  <strong>{row.name}</strong>
                  <small>{row.tenant_key}</small>
                </span>
              ),
            },
            {
              key: "owner",
              label: "Trial owner",
              render: (row) =>
                row.owner ? (
                  <TrialPeople
                    row={row}
                    onReset={(person) => setConfirm(trialMfaReset(person, row, overview.reload))}
                  />
                ) : (
                  "—"
                ),
            },
            {
              key: "state",
              label: "Trial",
              render: (row) => {
                const state = trialStateOf(row.state);
                return (
                  <span className="cc-trial-org">
                    <ToneBadge tone={state.tone} label={state.label} />
                    <small>
                      {row.state === "ENDED"
                        ? `Data deleted ${formatDate(row.data_deleted_at)}`
                        : `${row.days_left} days left`}
                    </small>
                  </span>
                );
              },
            },
            {
              key: "story",
              label: "Story",
              render: (row) => {
                const stage = storyStage(row, engagedAt);
                return (
                  <span className="cc-trial-org">
                    <span
                      className="cc-trial-progress"
                      role="img"
                      aria-label={`${row.story.acted_count} of ${row.story.total} chapters tried`}
                    >
                      {Array.from({ length: row.story.total }, (_, index) => (
                        <span
                          key={index}
                          className={
                            data?.chapters[index] && row.story.acted.includes(data.chapters[index].code) ? "is-on" : ""
                          }
                        />
                      ))}
                    </span>
                    <small>
                      <ToneBadge tone={stage.tone} label={stage.label} /> {row.story.acted_count} of {row.story.total}
                    </small>
                  </span>
                );
              },
            },
            {
              key: "next",
              label: "Next chapter",
              render: (row) => nextChapterTitle(row, data?.chapters ?? []),
            },
            {
              key: "usage",
              label: "Usage",
              render: (row) => (
                <span className="cc-trial-org">
                  <span>
                    <Users size={13} aria-hidden="true" /> {row.users.used} of {row.users.limit} users
                  </span>
                  <small>
                    {row.rows.used.toLocaleString()} of {row.rows.limit.toLocaleString()} rows uploaded
                  </small>
                </span>
              ),
            },
            {
              key: "last_activity",
              label: "Last activity",
              render: (row) => (row.story.last_activity ? formatDate(row.story.last_activity) : "None yet"),
            },
            {
              key: "demo",
              label: "Demo",
              render: (row) =>
                row.demo_request
                  ? `${row.demo_request.status === "NEW" ? "Requested" : row.demo_request.status === "CONTACTED" ? "Contacted" : "Closed"} ${formatDate(row.demo_request.created_at)}`
                  : "Not yet",
            },
            {
              key: "cited",
              label: "Cited for",
              render: (row) => (row.cited_for?.length ? row.cited_for.join("; ") : "—"),
            },
            {
              key: "feedback",
              label: "Feedback",
              render: (row) =>
                row.feedback
                  ? `${row.feedback.overall ?? "—"}/5 overall · ${row.feedback.recommend ?? "—"}/10 recommend`
                  : "None yet",
            },
            {
              key: "open",
              label: " ",
              render: (row) => (
                <button type="button" className="ac-link" onClick={() => onOpenTenant(row.tenant_id)}>
                  Open tenant
                </button>
              ),
            },
          ]}
        />
        <Pager
          page={data?.page ?? table.page}
          pages={data?.pages ?? 1}
          total={data?.total ?? items.length}
          noun="trial"
          onPage={table.onPage}
        />
        {notice && (
          <p className="ac-note" role="status">
            {notice}
          </p>
        )}
      </Panel>
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(message) => {
          setConfirm(null);
          setNotice(message);
        }}
      />
    </div>
  );
}

/**
 * Resetting a trial person's MFA after they lost their authenticator and recovery codes. A trial has no administrator
 * (and nobody inside it can reset its owner's), so MDARIX does it without a support grant; the reason is audited in the
 * trial's own trail (backend/app/access/platform_customer_admins.py).
 */
export function trialMfaReset(person: TrialPerson, trial: Pick<TrialItem, "name">, onDone: () => void): Confirmation {
  const name = person.name || person.email;
  return {
    title: `Reset multi-factor authentication for ${name}?`,
    body: `${name} (${trial.name}) lost their authenticator app and recovery codes. Their authenticator is removed, they are signed out, and they set up a new one at their next sign-in. Check who is asking before you do this.`,
    confirmLabel: "Reset MFA",
    reason: { label: "Why is the authenticator being reset? (kept in the trial's audit trail)", min: 5 },
    done: `${name} sets up a new authenticator at their next sign-in.`,
    run: async (reason) => {
      await send(`/api/v1/platform-admin/users/${person.id}/mfa-reset`, "POST", { reason });
      onDone();
    },
  };
}

/**
 * The trial's owner, then its colleagues, each with Reset MFA once they have activated their account, then the team
 * changes the owner made (removals, withdrawn invitations, MFA resets), newest first.
 */
function TrialPeople({ row, onReset }: { row: TrialItem; onReset: (person: TrialPerson) => void }) {
  const owner = row.owner;
  const others = (row.people ?? []).filter((person) => person.id !== owner?.id);
  const reset = (person: TrialPerson) =>
    person.id && person.status === "ACTIVE" ? (
      <button type="button" className="ac-link" onClick={() => onReset(person)}>
        Reset MFA
      </button>
    ) : null;
  return (
    <span className="cc-trial-org">
      {owner?.name || owner?.email}
      <small>
        {owner?.email} · {owner?.status === "INVITED" ? "invitation not accepted" : "active"}
      </small>
      {owner && reset(owner)}
      {others.map((person) => (
        <small key={person.id ?? person.email}>
          {person.name || person.email} · {person.status === "INVITED" ? "invited" : "colleague"} {reset(person)}
        </small>
      ))}
      {row.team_changes?.length ? (
        <>
          <small className="cc-trial-changes">Team changes</small>
          {row.team_changes.map((item, index) => (
            <small key={`${item.at}-${index}`}>
              {teamChangeText(item)} · {formatDate(item.at)}
            </small>
          ))}
        </>
      ) : null}
    </span>
  );
}
