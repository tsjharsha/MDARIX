import { CalendarCheck, CalendarClock, MessageSquare, Rocket, Sparkles, Upload, Users } from "lucide-react";
import { BarList, Panel, StatTile, ToneBadge } from "../console/charts";
import { Table, formatDate, useResource } from "../../customer-admin/shared";
import {
  TRIALS_PATH,
  attentionOrder,
  chapterFunnel,
  nextChapterTitle,
  storyStage,
  trialStateOf,
  type TrialItem,
  type TrialOverview,
} from "./trials";
import { TrialExitRequests } from "./TrialExitRequests";

/**
 * Trials: every free trial still holding data, as MDARIX staff need to see it to help a prospect succeed. How many
 * days are left, how much of the trial's limits is used, how far into the story (the quality loop, chapter by
 * chapter) it went and which chapter it should try next, when someone last did something, and what it told us. A
 * chapter counts only when the trial acted in it (a record it created), never on page views.
 */
export function TrialsOverview({ onOpenTenant }: { onOpenTenant: (tenantId: string) => void }) {
  const overview = useResource<TrialOverview>(TRIALS_PATH);
  const data = overview.data;
  const summary = data?.summary;
  const engagedAt = data?.engaged_chapters ?? 4;
  const items = attentionOrder(data?.items ?? [], engagedAt);
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
            {items
              .filter((item) => item.state !== "ENDED")
              .slice(0, 5)
              .map((item) => (
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
          {!items.some((item) => item.state !== "ENDED") && <p className="ac-muted">No active trial.</p>}
        </Panel>
      </div>
      <TrialExitRequests onChanged={overview.reload} />
      <Panel eyebrow="Every trial" title="Trials holding data" source={overview}>
        <Table<TrialItem>
          caption="Free trials"
          rows={items}
          rowKey={(row) => row.tenant_id}
          empty={{ title: "No free trials", detail: "Approved trial requests appear here with their progress." }}
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
                  <span className="cc-trial-org">
                    {row.owner.name || row.owner.email}
                    <small>
                      {row.owner.email} · {row.owner.status === "INVITED" ? "invitation not accepted" : "active"}
                    </small>
                  </span>
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
      </Panel>
    </div>
  );
}
