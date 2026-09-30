import { useMemo, useState } from "react";
import { BadgeCheck, ShieldCheck } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { useConsole } from "../context";
import { Table, Tabs, formatDate, listOf, send, useResource } from "../shared";

const TABS = ["Posture", "Single sign-on", "Security events"] as const;
type Tab = (typeof TABS)[number];

const SECURITY_ACTIONS = [
  "DENIED",
  "UNAUTHORIZED",
  "SECURITY",
  "AUTHENTICATION_FAILED",
  "ISOLATION",
  "USER_STATUS_CHANGED",
  "PASSWORD_RESET",
  "MFA",
  "IDP",
  "ROLE_ASSIGNMENT",
];

export function SecuritySection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>((TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Posture");
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Security sections" />
      {active === "Posture" && <Posture />}
      {active === "Single sign-on" && <SingleSignOn />}
      {active === "Security events" && <SecurityEvents />}
    </>
  );
}

function Posture() {
  const summary = useResource<any>("/api/v1/admin/security-summary");
  const retention = useResource<any>("/api/v1/admin/retention-status");
  const metrics = summary.data?.metrics ?? {};
  return (
    <>
      <section className="ac-stats three" aria-label="Security figures">
        <StatTile
          label="Security events"
          value={summary.state === "ready" ? (metrics.security_events ?? 0) : null}
          detail="In the latest 200 audit events"
          tone={summary.state === "ready" ? (metrics.security_events ? "serious" : "good") : undefined}
          icon={<ShieldCheck size={18} />}
        />
        <StatTile
          label="Policy denials"
          value={summary.state === "ready" ? (metrics.policy_denials ?? 0) : null}
          detail="Requests the server refused"
          icon={<ShieldCheck size={18} />}
        />
        <StatTile
          label="Audit retention"
          value={retention.state === "ready" ? titleCase(retention.data?.status ?? "Unknown") : null}
          detail={retention.data ? `${retention.data.policy} · ${retention.data.total_events} events` : "Unavailable"}
          tone={retention.state === "ready" ? (retention.data?.status === "HEALTHY" ? "good" : "serious") : undefined}
          icon={<BadgeCheck size={18} />}
        />
      </section>
      <div className="ac-grid two">
        <Panel eyebrow="Your account" title="Multi-factor authentication">
          <p>
            Protect your administrator account with a second factor. You are asked for a 6-digit code when you sign in.
          </p>
          <div className="ca-action-row">
            <a className="ac-primary" href="/mfa?setup=1">
              <ShieldCheck size={16} /> Set up MFA
            </a>
          </div>
          <p className="ac-muted">
            To require MFA for everyone, set single sign-on to <strong>SSO with MFA</strong> or{" "}
            <strong>Password with MFA</strong>.
          </p>
        </Panel>
        <Panel eyebrow="Sessions" title="How sign-in sessions are protected">
          <ul className="ca-check-list">
            <li>Sessions expire automatically after 60 minutes.</li>
            <li>Suspending or offboarding a user signs them out everywhere immediately.</li>
            <li>Session cookies are HTTP-only and never readable by page scripts.</li>
            <li>Every administrative change is recorded in the audit trail.</li>
          </ul>
        </Panel>
      </div>
      <Panel eyebrow="Controls · declared by the security service" title="Protections in place" state={summary.state}>
        <ul className="ac-posture-list">
          {listOf(summary.data?.controls).map((control: string) => (
            <li key={control}>
              <BadgeCheck size={16} aria-hidden="true" /> {control}
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}

function SingleSignOn() {
  const { confirm } = useConsole();
  const providers = useResource<any>("/api/v1/admin/security/identity-provider");
  const [form, setForm] = useState({ provider_type: "OIDC", issuer: "", client_reference: "", login_mode: "SSO_MFA" });
  return (
    <>
      <Panel eyebrow="Security" title="Identity providers" state={providers.state} error={providers.error}>
        <Table
          caption="Identity providers"
          rows={listOf(providers.data?.providers)}
          rowKey={(row) => row.id}
          empty={{ title: "Single sign-on is not set up", detail: "Users sign in with their MDARIX password." }}
          columns={[
            { key: "type", label: "Type", render: (row) => <strong>{row.provider_type}</strong> },
            { key: "issuer", label: "Issuer", render: (row) => row.issuer },
            { key: "mode", label: "Sign-in", render: (row) => titleCase(row.login_mode) },
            {
              key: "status",
              label: "Status",
              render: (row) => (
                <ToneBadge
                  tone={row.status === "VERIFIED" || row.status === "ACTIVE" ? "good" : "warning"}
                  label={titleCase(row.status)}
                />
              ),
            },
            { key: "verified", label: "Verified", numeric: true, render: (row) => formatDate(row.verified_at) },
          ]}
        />
      </Panel>
      <Panel eyebrow="Configure" title="Set up or change single sign-on">
        <form
          className="ca-form"
          onSubmit={(event) => {
            event.preventDefault();
            confirm({
              title: "Save single sign-on settings?",
              body: "The provider is saved as pending. MDARIX verifies it before users are moved to single sign-on, so nobody is locked out.",
              confirmLabel: "Save settings",
              reason: { label: "Reason for the change", min: 10 },
              done: "Single sign-on saved and pending verification.",
              run: async (reason) => {
                await send("/api/v1/admin/security/identity-provider", "PUT", {
                  ...form,
                  client_reference: form.client_reference || undefined,
                  reason,
                });
                providers.reload();
              },
            });
          }}
        >
          <div className="ca-form-grid">
            <label className="ca-field">
              Provider type
              <select
                value={form.provider_type}
                onChange={(event) => setForm({ ...form, provider_type: event.target.value })}
              >
                <option value="OIDC">OpenID Connect</option>
                <option value="SAML">SAML 2.0</option>
              </select>
            </label>
            <label className="ca-field">
              Issuer URL (https)
              <input
                required
                type="url"
                pattern="https://.*"
                placeholder="https://login.example.com"
                value={form.issuer}
                onChange={(event) => setForm({ ...form, issuer: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Client reference
              <input
                placeholder="Application / client id (not a secret)"
                value={form.client_reference}
                onChange={(event) => setForm({ ...form, client_reference: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Sign-in mode
              <select
                value={form.login_mode}
                onChange={(event) => setForm({ ...form, login_mode: event.target.value })}
              >
                <option value="SSO_MFA">SSO with MFA (recommended)</option>
                <option value="SSO">SSO only</option>
                <option value="PASSWORD_MFA">Password with MFA</option>
              </select>
            </label>
          </div>
          <div className="ca-action-row">
            <button type="submit" className="ac-primary">
              Save settings
            </button>
          </div>
        </form>
      </Panel>
    </>
  );
}

function SecurityEvents() {
  const audit = useResource<any[]>("/api/v1/admin/audit-history");
  const rows = useMemo(
    () =>
      listOf(audit.data).filter((row) =>
        SECURITY_ACTIONS.some((token) =>
          String(row.action ?? "")
            .toUpperCase()
            .includes(token),
        ),
      ),
    [audit.data],
  );
  return (
    <Panel eyebrow="Security" title="Security events" state={audit.state} error={audit.error}>
      <p className="ac-muted">
        Denied access, sign-in failures, account status changes, password resets and access changes from the latest 200
        audit events.
      </p>
      {rows.length ? (
        <Table
          caption="Security events"
          rows={rows}
          rowKey={(row) => row.id}
          empty={{ title: "", detail: "" }}
          columns={[
            { key: "action", label: "Event", render: (row) => <strong>{titleCase(row.action ?? "")}</strong> },
            { key: "object", label: "Object", render: (row) => titleCase(row.entity_type ?? "—") },
            { key: "source", label: "Source IP", render: (row) => row.source_ip ?? "—" },
            { key: "when", label: "When", numeric: true, render: (row) => formatDate(row.created_at) },
          ]}
        />
      ) : (
        <Empty title="No security events" detail="Denied or suspicious activity will appear here." />
      )}
    </Panel>
  );
}
