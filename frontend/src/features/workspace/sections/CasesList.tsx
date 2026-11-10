import { useState } from "react";
import { CheckCircle2, ClipboardList, Hourglass, Users } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { errorText, formatDate, send, useResource } from "../../customer-admin/shared";
import { useCan } from "../workspaceContext";
import { ChipFilter, InlineError } from "./boardParts";
import { CASE_VIEWS_FIRST, INTAKE, casesPath, type CaseHeader, type CasePage, type CaseRow } from "../intake";

const BULK_MAX = 200;

/**
 * The Cases list (0.10.93, B2 step 5; spec 4.3, A5): one page at a time, filtered and searched on the server; each row
 * says its owner, next action and due time (A3). Flat (G-2): no decoration beyond the tiles and the state chips.
 */
export function CasesList({ onOpen, reloadKey = 0 }: { onOpen: (id: string) => void; reloadKey?: number }) {
  const [view, setView] = useState("to_check");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [ticked, setTicked] = useState<string[]>([]);
  const list = useResource<CasePage>(`${casesPath(view, search, page)}&r=${reloadKey}`);
  const data = list.data;
  const counts = data?.counts;
  const items = data?.items ?? [];
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const choose = (next: string) => {
    setView(next);
    setPage(1);
    setTicked([]);
  };
  const views = data?.views ?? [];
  return (
    <>
      <div className="uw-cr-stats">
        <StatTile
          label="To check"
          value={counts ? counts.OPEN : null}
          detail="The Case check is due the same working day"
          icon={<ClipboardList size={18} />}
          tone={counts?.OPEN ? "warning" : undefined}
          onOpen={() => choose("to_check")}
        />
        <StatTile
          label="Waiting for the reporter"
          value={counts ? counts.PENDING : null}
          detail="A follow-up with the reporter is due"
          icon={<Hourglass size={18} />}
          onOpen={() => choose("waiting_reporter")}
        />
        <StatTile
          label="QA review"
          value={counts ? counts.IN_REVIEW : null}
          detail="Service only, inquiry or not a complaint"
          icon={<CheckCircle2 size={18} />}
          onOpen={() => choose("qa_review")}
        />
        <StatTile
          label="Waiting for internal team"
          value={counts ? counts.WAITING_INTERNAL : null}
          detail="An internal answer is awaited"
          icon={<Users size={18} />}
          onOpen={() => choose("waiting_internal")}
        />
      </div>
      <Panel eyebrow="Cases" title={views.find((item) => item.code === view)?.label ?? "Cases"} source={list}>
        <div className="uw-cr-toolbar">
          <ChipFilter
            label="Which cases"
            options={CASE_VIEWS_FIRST.map((code) => ({
              value: code,
              label: views.find((item) => item.code === code)?.label ?? code,
            }))}
            value={view}
            onChange={choose}
          />
          <label className="ca-field">
            More views
            <select
              value={CASE_VIEWS_FIRST.includes(view) ? "" : view}
              onChange={(event) => choose(event.target.value || "to_check")}
            >
              <option value="">Choose…</option>
              {views
                .filter((item) => !CASE_VIEWS_FIRST.includes(item.code))
                .map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
            </select>
          </label>
          <form
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(q);
              setPage(1);
            }}
          >
            <label className="ca-field">
              Search by reference, product, lot, serial or customer
              <input type="search" value={q} onChange={(event) => setQ(event.target.value)} />
            </label>
          </form>
        </div>
        {ticked.length > 0 && data && (
          <BulkAssign ids={ticked} people={data.people} onDone={() => (setTicked([]), list.reload())} />
        )}
        {items.length ? (
          <div className="uw-tr-scroll">
            <table className="uw-tr-table uw-cases-table">
              <thead>
                <tr>
                  <th scope="col">
                    <span className="sr-only">Choose</span>
                  </th>
                  <th scope="col">Case</th>
                  <th scope="col">Received</th>
                  <th scope="col">What was said</th>
                  <th scope="col">Product · lot</th>
                  <th scope="col">State</th>
                  <th scope="col">Owner</th>
                  <th scope="col">Next action · due</th>
                  <th scope="col">
                    <span className="sr-only">Open</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <CaseRowView
                    key={row.id}
                    row={row}
                    ticked={ticked.includes(row.id)}
                    onTick={(on) =>
                      setTicked((current) =>
                        on ? [...current, row.id].slice(0, BULK_MAX) : current.filter((id) => id !== row.id),
                      )
                    }
                    onOpen={() => onOpen(row.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No case here" detail="Log a case, or choose another view." />
        )}
        {data && data.total > data.size && (
          <nav className="ca-action-row" aria-label="Pages">
            <button type="button" className="ac-link" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span className="uw-cr-meta">
              Page {page} of {pages} · {data.total} cases
            </span>
            <button type="button" className="ac-link" disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </nav>
        )}
      </Panel>
    </>
  );
}

function CaseRowView({
  row,
  ticked,
  onTick,
  onOpen,
}: {
  row: CaseRow;
  ticked: boolean;
  onTick: (on: boolean) => void;
  onOpen: () => void;
}) {
  const header = row.header;
  return (
    <tr>
      <td>
        <input
          type="checkbox"
          aria-label={`Choose ${row.reference}`}
          checked={ticked}
          onChange={(event) => onTick(event.target.checked)}
        />
      </td>
      <th scope="row">
        {row.reference} {row.sample && <ToneBadge tone="neutral" label="SAMPLE" />}
      </th>
      <td>{formatDate(row.received_at)}</td>
      <td>
        <span className="uw-cr-clip">{row.words}</span>
      </td>
      <td>
        {[row.product_name, row.lot].filter(Boolean).join(" · ") || "—"}
        {row.not_in_master.length > 0 && <ToneBadge tone="warning" label="Not in master data" />}
      </td>
      <td>
        {row.status_label}
        {row.flagged && row.status !== "ESCALATED" && <ToneBadge tone="serious" label="Triage flag" />}
        {row.complaint_ref && <span className="uw-cr-meta"> · {row.complaint_ref}</span>}
      </td>
      <td>{header.owner ?? "Unassigned"}</td>
      <td>
        <NextAction header={header} />
      </td>
      <td>
        <button type="button" className="ac-secondary" onClick={onOpen}>
          {row.status === "OPEN" ? "Open the case check" : "Open"}
        </button>
      </td>
    </tr>
  );
}

/** A3 in one cell: the next action, its due time (overdue in red), and how much information is still missing. */
export function NextAction({ header }: { header: CaseHeader }) {
  if (!header.next_action) return <span className="uw-cr-meta">{header.escalation.label}</span>;
  return (
    <span>
      {header.next_action}
      {header.due_at && (
        <span className={header.overdue ? "uw-clock tone-critical" : "uw-cr-meta"}>
          {" "}
          · {header.overdue ? "overdue since" : "due"} {formatDate(header.due_at)}
        </span>
      )}
      {header.missing.length > 0 && <span className="uw-cr-meta"> · {header.missing.length} missing</span>}
    </span>
  );
}

function BulkAssign({ ids, people, onDone }: { ids: string[]; people: CasePage["people"]; onDone: () => void }) {
  const canAssign = useCan("case.log");
  const [owner, setOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!canAssign) return null;
  return (
    <div className="ca-action-row" role="region" aria-label="Chosen cases">
      <span>{ids.length} chosen</span>
      <label className="ca-field">
        Assign to…
        <select value={owner} onChange={(event) => setOwner(event.target.value)}>
          <option value="">Choose…</option>
          {people.map((person) => (
            <option key={person.id} value={person.id}>
              {person.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="ac-primary"
        disabled={!owner || busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await send(`${INTAKE}/bulk-assign`, "POST", { ids, owner_id: owner });
            onDone();
          } catch (failure) {
            setError(errorText(failure, "Not assigned"));
          } finally {
            setBusy(false);
          }
        }}
      >
        Assign
      </button>
      <span className="uw-cr-meta">Classifications are signed one by one.</span>
      <InlineError text={error} />
    </div>
  );
}

/**
 * The Case header (A3, spec 4.4): owner, next action, due, why, the missing information (unconfirmed identifiers
 * included) and the escalation state. A Case is never "done" because a form was sent.
 */
export function CaseHeaderView({ header, status }: { header: CaseHeader; status: string | null }) {
  const tone = header.escalation.state === "ESCALATED" || header.escalation.state === "URGENT" ? "serious" : "neutral";
  return (
    <section className="ca-drawer-section uw-case-header" aria-label="Where this case stands">
      <p>
        {status && <strong>{status}</strong>} <ToneBadge tone={tone} label={header.escalation.label} />
      </p>
      <dl className="uw-case-facts">
        <dt>Owner</dt>
        <dd>{header.owner ?? "Unassigned"}</dd>
        <dt>Next action</dt>
        <dd>
          <NextAction header={{ ...header, missing: [] }} />
        </dd>
        {header.reason && (
          <>
            <dt>Why</dt>
            <dd>{header.reason}</dd>
          </>
        )}
        <dt>Missing information</dt>
        <dd>
          {header.missing.length ? (
            <ul className="uw-cr-chips">
              {header.missing.map((item) => (
                <li key={item.code} className="uw-cr-chip tone-warning">
                  {item.label}
                </li>
              ))}
            </ul>
          ) : (
            "None"
          )}
        </dd>
      </dl>
    </section>
  );
}
