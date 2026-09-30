import { CalendarClock } from "lucide-react";
import { Empty, Panel, RingMeter, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { seatUsage } from "../customerAdminModel";
import { licensedSeatLimit, useConsole } from "../context";
import { Table, listOf, send, useResource } from "../shared";

const SEAT_STATUSES = ["ACTIVE", "INVITED", "PENDING_VERIFICATION"];

const formatLimits = (limits: unknown) => {
  if (!limits || typeof limits !== "object") return "—";
  const entries = Object.entries(limits as Record<string, unknown>);
  return entries.length ? entries.map(([key, value]) => `${titleCase(key)}: ${String(value)}`).join(" · ") : "—";
};

export function SubscriptionSection() {
  const { context, confirm } = useConsole();
  const entitlements = useResource<any[]>("/api/v1/admin/governance/entitlements");
  const lifecycle = useResource<any>("/api/v1/admin/tenant/lifecycle");
  const users = useResource<any[]>("/api/v1/admin/identity/users");
  const used = listOf(users.data).filter((user) => SEAT_STATUSES.includes(String(user.status).toUpperCase())).length;
  const seats = seatUsage(used, licensedSeatLimit(context));
  const customerAdmins = listOf(users.data).filter(
    (user) =>
      String(user.role).toUpperCase() === "CUSTOMER_ADMIN" && SEAT_STATUSES.includes(String(user.status).toUpperCase()),
  ).length;

  return (
    <>
      <div className="ac-grid two">
        <Panel eyebrow="Plan" title={context?.plan?.name ?? "No active plan"}>
          <dl className="ca-facts">
            <div>
              <dt>Plan code</dt>
              <dd>{context?.plan?.code ?? "—"}</dd>
            </div>
            <div>
              <dt>Version</dt>
              <dd>{context?.plan?.version ?? "—"}</dd>
            </div>
            <div>
              <dt>Licence</dt>
              <dd>
                <ToneBadge
                  tone={context?.license?.effective ? "good" : "critical"}
                  label={context?.license?.effective ? "Active" : "Inactive"}
                />
              </dd>
            </div>
            <div>
              <dt>Organization status</dt>
              <dd>{lifecycle.data ? titleCase(lifecycle.data.lifecycle_status ?? lifecycle.data.status) : "—"}</dd>
            </div>
          </dl>
          <p className="ac-muted">
            Plan limits are set in your contract. Only MDARIX can change them; you can request a renewal below.
          </p>
        </Panel>
        <Panel eyebrow="Usage" title="Seats" state={users.state} error={users.error}>
          <div className="ca-meter-row">
            {seats.limit !== null ? (
              <RingMeter value={seats.used} total={seats.limit} label="Seats used" />
            ) : (
              <p className="ac-muted">This plan does not declare a seat limit.</p>
            )}
            <dl className="ca-facts">
              <div>
                <dt>Seats in use</dt>
                <dd>
                  {seats.used}
                  {seats.limit !== null ? ` of ${seats.limit}` : ""}
                </dd>
              </div>
              <div>
                <dt>Customer Administrators</dt>
                <dd>{customerAdmins}</dd>
              </div>
              <div>
                <dt>Counts toward seats</dt>
                <dd>Active, invited and pending users</dd>
              </div>
            </dl>
          </div>
          {seats.limit !== null && seats.tone !== "good" && (
            <p className="ca-note-box">Offboard accounts that no longer need access to release seats.</p>
          )}
        </Panel>
      </div>

      <Panel eyebrow="Plan" title="What your plan includes" state={entitlements.state} error={entitlements.error}>
        <Table
          caption="Entitlements"
          rows={listOf(entitlements.data)}
          rowKey={(row, index) => `${row.feature}-${index}`}
          empty={{ title: "No entitlements", detail: "Your plan's features appear here once assigned." }}
          columns={[
            { key: "feature", label: "Feature", render: (row) => <strong>{titleCase(row.feature ?? "")}</strong> },
            {
              key: "enabled",
              label: "Included",
              render: (row) => <ToneBadge tone={row.enabled ? "good" : "neutral"} label={row.enabled ? "Yes" : "No"} />,
            },
            { key: "limits", label: "Limits", render: (row) => formatLimits(row.limits) },
          ]}
        />
      </Panel>

      <Panel eyebrow="Subscription" title="Renewal" state={lifecycle.state} error={lifecycle.error}>
        {lifecycle.data?.customer_admin_actions?.includes("REQUEST_RENEWAL") ? (
          <div className="ca-action-row">
            <p className="ac-muted">
              Ask MDARIX to renew your subscription. Suspension, reactivation and termination are handled by MDARIX.
            </p>
            <button
              type="button"
              className="ac-primary"
              onClick={() =>
                confirm({
                  title: "Request a subscription renewal?",
                  body: "MDARIX receives your request and contacts your account owner. Repeat requests are not duplicated.",
                  confirmLabel: "Send request",
                  reason: { label: "Anything MDARIX should know", min: 10 },
                  done: "Renewal request sent.",
                  run: (reason) => send("/api/v1/admin/tenant/lifecycle/renewal-request", "POST", { reason }),
                })
              }
            >
              <CalendarClock size={16} /> Request renewal
            </button>
          </div>
        ) : (
          <Empty title="Renewal not available" detail="Contact your MDARIX account team." />
        )}
      </Panel>
    </>
  );
}
