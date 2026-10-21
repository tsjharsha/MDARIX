import { useState } from "react";
import { Eye, History, LifeBuoy, ShieldCheck } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { useConsole } from "../context";
import { Table, formatDate, send, useResource } from "../shared";
import {
  accessText,
  activityText,
  areaDetails,
  areaNames,
  supportStatus,
  type SupportActivity,
  type SupportGrant,
} from "../supportAccessModel";

const REASON = { label: "Reason (kept in your audit trail)", min: 10 };
const LIST = "/api/v1/admin/support-access";

/**
 * MDARIX support reaches your organization's data only under access one of your administrators approved: for
 * named areas, read-only unless you allow changes, for a limited time. Every use is recorded in your audit trail
 * and listed here; you can revoke an access at any moment.
 */
export function SupportAccess() {
  const { confirm } = useConsole();
  const grants = useResource<{ items: SupportGrant[]; awaiting_decision: number }>(LIST);
  const [selected, setSelected] = useState<string | null>(null);
  const rows = grants.data?.items ?? [];
  const active = rows.filter((row) => supportStatus(row).label === "Active").length;
  const uses = rows.reduce((total, row) => total + row.uses, 0);
  const changed = () => grants.reload();

  const approve = (row: SupportGrant) =>
    confirm({
      title: `Give ${row.person ?? "MDARIX support"} access?`,
      body:
        `${accessText(row.write)} access until ${formatDate(row.expires_at)}, to: ${areaDetails(row.areas)}. ` +
        "Every use is recorded in your audit trail, and you can revoke it at any time.",
      confirmLabel: "Approve access",
      reason: REASON,
      mfaCode: true,
      done: "Access approved. MDARIX support has been told.",
      run: async (reason, _password, _acknowledged, mfaCode) => {
        await send(`${LIST}/${row.id}/approve`, "POST", { reason, mfa_code: mfaCode || undefined });
        changed();
      },
    });
  const deny = (row: SupportGrant) =>
    confirm({
      title: "Deny this request?",
      body: "MDARIX support gets no access. They can ask again with a new request.",
      confirmLabel: "Deny",
      reason: REASON,
      done: "Request denied.",
      run: async (reason) => {
        await send(`${LIST}/${row.id}/deny`, "POST", { reason });
        changed();
      },
    });
  const revoke = (row: SupportGrant) =>
    confirm({
      title: `End ${row.person ?? "MDARIX support"}'s access now?`,
      body: "The access ends immediately, whatever time it had left.",
      confirmLabel: "Revoke",
      danger: true,
      reason: REASON,
      done: "Access revoked.",
      run: async (reason) => {
        await send(`${LIST}/${row.id}/revoke`, "POST", { reason });
        changed();
      },
    });

  return (
    <>
      <section className="ac-stats ar-stats-3" aria-label="Support access">
        <StatTile
          label="Waiting for you"
          value={grants.data ? grants.data.awaiting_decision : null}
          detail="Requests from MDARIX support"
          icon={<LifeBuoy size={18} />}
          tone={grants.data ? (grants.data.awaiting_decision ? "warning" : "good") : undefined}
        />
        <StatTile
          label="Active now"
          value={grants.data ? active : null}
          detail="Access you approved that has not ended"
          icon={<ShieldCheck size={18} />}
          tone={grants.data ? (active ? "serious" : "good") : undefined}
        />
        <StatTile
          label="Uses recorded"
          value={grants.data ? uses : null}
          detail="Each time MDARIX opened your data"
          icon={<Eye size={18} />}
        />
      </section>
      <Panel eyebrow="Security" title="Support access" source={grants}>
        <p className="ac-muted">
          MDARIX support never sees your data unless one of your administrators approves it here: only the areas named,
          read-only unless you allow changes, and only until the time shown.
        </p>
        <Table
          caption="Support access"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "No requests", detail: "When MDARIX support asks for access, the request appears here." }}
          columns={[
            {
              key: "person",
              fields: ["person", "person_email", "requested_by", "approved_for_mdarix_by"],
              label: "Who",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.person ?? "MDARIX support"}</strong>
                  {row.person_email && <small>{row.person_email}</small>}
                </span>
              ),
            },
            {
              key: "access",
              fields: ["areas", "write"],
              label: "Access",
              render: (row) => (
                <span className="cc-stack">
                  <strong>{areaNames(row.areas)}</strong>
                  <small>{accessText(row.write)}</small>
                  <small>{areaDetails(row.areas)}</small>
                </span>
              ),
            },
            { key: "reason", label: "Why", render: (row) => row.reason },
            {
              key: "expires_at",
              fields: ["starts_at", "expires_at"],
              label: "Until",
              numeric: true,
              render: (row) => formatDate(row.expires_at),
            },
            {
              key: "status",
              fields: ["decided_by", "decided_at", "decision_reason", "uses", "last_used_at"],
              label: "Status",
              render: (row) => {
                const status = supportStatus(row);
                return (
                  <span className="cc-stack">
                    <ToneBadge tone={status.tone} label={status.label} />
                    {row.decided_by && <small>Decided by {row.decided_by}</small>}
                    {row.uses > 0 && <small>Used {row.uses} times</small>}
                  </span>
                );
              },
            },
            {
              key: "actions",
              label: "",
              render: (row) => (
                <span className="cc-actions">
                  {row.can_approve && (
                    <button type="button" className="ac-link" onClick={() => approve(row)}>
                      Approve
                    </button>
                  )}
                  {row.can_deny && (
                    <button type="button" className="ac-link" onClick={() => deny(row)}>
                      Deny
                    </button>
                  )}
                  {row.can_revoke && !row.can_deny && (
                    <button type="button" className="ac-link cc-danger-link" onClick={() => revoke(row)}>
                      Revoke
                    </button>
                  )}
                  <button
                    type="button"
                    className="ac-link"
                    aria-expanded={selected === row.id}
                    onClick={() => setSelected(selected === row.id ? null : row.id)}
                  >
                    {selected === row.id ? "Hide history" : "History"}
                  </button>
                </span>
              ),
            },
          ]}
        />
      </Panel>
      {selected && <Activity grantId={selected} />}
    </>
  );
}

/** Everything that happened under one grant, from the organization's own audit trail. */
function Activity({ grantId }: { grantId: string }) {
  const activity = useResource<{ items: SupportActivity[] }>(`${LIST}/${grantId}/activity`);
  const items = activity.data?.items ?? [];
  return (
    <Panel eyebrow="From your audit trail" title="History of this access" source={activity}>
      {items.length ? (
        <Table
          caption="History of this access"
          rows={items}
          rowKey={(item, index) => `${item.at}-${index}`}
          empty={{ title: "", detail: "" }}
          columns={[
            {
              key: "what",
              label: "What",
              render: (item) => (
                <span className="cc-stack">
                  <strong>{activityText(item)}</strong>
                  {item.covers && <small>{item.covers}</small>}
                  {item.reason && <small>{item.reason}</small>}
                </span>
              ),
            },
            { key: "who", label: "Who", render: (item) => item.who ?? "" },
            { key: "at", label: "When", numeric: true, render: (item) => formatDate(item.at) },
          ]}
        />
      ) : (
        <Empty title="Nothing yet" detail="The request, the decision and every use will appear here." />
      )}
      <p className="ac-muted">
        <History size={14} aria-hidden="true" /> The same events are in Audit, where they cannot be changed.
      </p>
    </Panel>
  );
}
