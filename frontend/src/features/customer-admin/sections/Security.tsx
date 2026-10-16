import { useMemo, useState } from "react";
import { MASKING_SUMMARY, aiAcknowledgement, aiSettingsPayload, providerLabel } from "../aiSettings";
import { BadgeCheck, Bot, Gauge } from "lucide-react";
import { Empty, Panel, StatTile, ToneBadge } from "../../admin/console/charts";
import { TwoFactorPanel } from "../../shared/TwoFactorSettings";
import { useConsole } from "../context";
import { Table, Tabs, formatDate, listOf, send, useResource } from "../shared";
import { plural, readable } from "../labels";
import { awaitingCount, type SupportGrant } from "../supportAccessModel";
import { SupportAccess } from "./SupportAccess";
import { AiReleaseGate, gateBlocksSwitchOn, type ReleaseGate } from "./AiReleaseGate";

const TABS = ["Posture", "Support access", "AI processing", "Single sign-on", "Security events"] as const;
type Tab = (typeof TABS)[number];

// How a single sign-on setup reads while MDARIX checks it ("Pending verification" alone says nothing about who acts).
const SSO_STATUS: Record<string, string> = {
  PENDING: "Waiting for MDARIX to verify",
  PENDING_VERIFICATION: "Waiting for MDARIX to verify",
};

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
  "AI_PROCESSING",
];

export function SecuritySection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>((TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Posture");
  // Requests from MDARIX support that wait for a decision show on the tab, wherever the administrator is.
  const support = useResource<{ items: SupportGrant[] }>("/api/v1/admin/support-access");
  return (
    <>
      <Tabs
        tabs={TABS}
        active={active}
        onChange={setActive}
        label="Security sections"
        counts={{ "Support access": awaitingCount(support.data?.items ?? []) }}
      >
        {active === "Posture" && <Posture />}
        {active === "Support access" && <SupportAccess />}
        {active === "AI processing" && <AiProcessing />}
        {active === "Single sign-on" && <SingleSignOn />}
        {active === "Security events" && <SecurityEvents />}
      </Tabs>
    </>
  );
}

function Posture() {
  const { context } = useConsole();
  const summary = useResource<any>("/api/v1/admin/security-summary");
  const retention = useResource<any>("/api/v1/admin/retention-status");
  return (
    <>
      <div className="ac-grid two">
        <TwoFactorPanel
          eyebrow="Your account"
          account={context?.email}
          notOnText="Protect your administrator account with a second factor. You are asked for a 6-digit code when you sign in."
        >
          <p className="ac-muted">
            MFA (multi-factor authentication) is required for administrators and before every electronic signature.
            Other users can turn it on from their account.
          </p>
        </TwoFactorPanel>
        <Panel eyebrow="Sessions" title="How sign-in sessions are protected">
          <ul className="ca-check-list">
            <li>
              Users are signed out after 30 minutes without activity (warned two minutes before) and must sign in again
              after 12 hours at most.
            </li>
            <li>Suspending or offboarding a user signs them out everywhere immediately.</li>
            <li>Sign-in details are stored where web page code cannot read or copy them.</li>
            <li>Every administrative change is recorded in the audit trail.</li>
          </ul>
        </Panel>
      </div>
      <Panel eyebrow="Security" title="Protections in place" state={summary.state}>
        <ul className="ac-posture-list">
          {listOf(summary.data?.controls).map((control: string) => (
            <li key={control}>
              <BadgeCheck size={16} aria-hidden="true" /> {control}
            </li>
          ))}
        </ul>
        {retention.state === "ready" && retention.data && (
          <p className="ac-muted">
            Audit trail: {readable(retention.data.status, "Unknown").toLowerCase()}
            {retention.data.policy ? ` · ${retention.data.policy}` : ""} ·{" "}
            {plural(Number(retention.data.total_events ?? 0), "event")} kept.
          </p>
        )}
      </Panel>
    </>
  );
}

type AiSettings = {
  ai_processing_allowed: boolean;
  monthly_token_budget: number;
  tokens_used: number;
  requests: number;
  refused: number;
  month: string;
  models: { provider: string; model: string }[];
  /** The provider content is sent to when AI is on (named in the acknowledgement); null when none is configured. */
  provider_name: string | null;
  masking: boolean;
  /** The four bars AI must pass before a pilot; production refuses switching AI on until they are met. */
  release_gate?: ReleaseGate;
};

/** Whether this organization's content may be sent to an AI model, and how much of the monthly allowance is used. */
function AiProcessing() {
  const { confirm } = useConsole();
  const settings = useResource<AiSettings>("/api/v1/admin/ai-settings");
  const data = settings.data;
  const on = data?.ai_processing_allowed ?? false;
  const share =
    data && data.monthly_token_budget ? Math.min(100, (data.tokens_used / data.monthly_token_budget) * 100) : 0;
  const change = () =>
    confirm({
      title: on ? "Turn AI processing off?" : "Turn AI processing on?",
      body: on
        ? "Nothing from your organization will be sent to an AI model. Ask MDARIX, hypotheses and briefs answer from rules only, and say so."
        : `AI features (Ask MDARIX, hypotheses, challenges and briefs) will send the records an answer needs to ${providerLabel(data?.provider_name)}. ${MASKING_SUMMARY}`,
      confirmLabel: on ? "Turn AI off" : "Turn AI on",
      reason: { label: "Reason for the change", min: 10 },
      ...(on ? {} : { acknowledge: aiAcknowledgement(data?.provider_name) }),
      done: on ? "AI processing is off for your organization." : "AI processing is on for your organization.",
      run: async (reason, _password, acknowledged) => {
        await send("/api/v1/admin/ai-settings", "PUT", aiSettingsPayload(!on, reason, acknowledged));
        settings.reload();
      },
    });
  return (
    <>
      <section className="ac-stats three" aria-label="AI processing figures">
        <StatTile
          label="AI processing"
          value={data ? (on ? "On" : "Off") : null}
          detail={on ? "AI features may use a model" : "Rule-based answers only"}
          tone={data ? (on ? "good" : "warning") : undefined}
          icon={<Bot size={18} />}
        />
        <StatTile
          label="AI allowance used this month"
          value={data ? data.tokens_used.toLocaleString() : null}
          detail={
            data ? `of ${data.monthly_token_budget.toLocaleString()} units (${share.toFixed(0)}%)` : "Unavailable"
          }
          tone={data ? (share >= 90 ? "serious" : share >= 75 ? "warning" : "good") : undefined}
          icon={<Gauge size={18} />}
        />
        <StatTile
          label="AI requests this month"
          value={data ? data.requests.toLocaleString() : null}
          detail={data ? `${data.refused.toLocaleString()} answered from rules instead` : "Unavailable"}
          icon={<Bot size={18} />}
        />
      </section>
      <div className="ac-grid two">
        <Panel eyebrow="Your organization" title="AI processing" source={settings}>
          <p>
            {on
              ? "AI features (Ask MDARIX, hypotheses, challenges and briefs) may send the records an answer needs to the model below. A person reviews every AI suggestion."
              : "AI processing is off: nothing from your organization is sent to an AI model, and every feature answers from rules."}
          </p>
          <div className="ca-action-row">
            <button
              type="button"
              className={on ? "ac-secondary" : "ac-primary"}
              onClick={change}
              disabled={!data || (!on && gateBlocksSwitchOn(data.release_gate))}
            >
              {on ? "Turn AI off" : "Turn AI on"}
            </button>
          </div>
          {!on && gateBlocksSwitchOn(data?.release_gate) && (
            <p className="ac-muted" role="note">
              AI can be turned on once the AI release gate below is met.
            </p>
          )}
          <p className="ac-muted">
            When the monthly allowance is used up, features answer from rules until next month.
          </p>
        </Panel>
        <Panel eyebrow="What is sent" title="How your data is protected">
          <ul className="ca-check-list">
            <li>{MASKING_SUMMARY}</li>
            <li>Only providers under a contract that forbids training on your data, or models we host, are used.</li>
            <li>Every AI request is counted against your organization&apos;s monthly allowance.</li>
            <li>Changing this setting is recorded in the audit trail with your reason.</li>
          </ul>
          <p className="ac-muted">
            {data?.models.length
              ? `Model in use: ${data.models.map((item) => `${readable(item.provider)} (${item.model})`).join(", ")}${
                  data.provider_name ? ` · provider: ${data.provider_name}` : ""
                }.`
              : "No AI model is configured on this server, so every answer comes from rules."}
          </p>
        </Panel>
      </div>
      <AiReleaseGate gate={data?.release_gate} />
    </>
  );
}

function SingleSignOn() {
  const { confirm } = useConsole();
  const providers = useResource<any>("/api/v1/admin/security/identity-provider");
  const [form, setForm] = useState({ provider_type: "OIDC", issuer: "", client_reference: "", login_mode: "SSO_MFA" });
  return (
    <>
      <p className="ca-lede" role="note">
        Single sign-on is not available yet: everyone signs in with their MDARIX password and an authenticator app. You
        can record your identity provider here so it is ready when single sign-on is switched on for your organization.
        Saving it does not change how anyone signs in.
      </p>
      <Panel eyebrow="Security" title="Identity providers" source={providers}>
        <Table
          caption="Identity providers"
          rows={listOf(providers.data?.providers)}
          rowKey={(row) => row.id}
          empty={{ title: "Single sign-on is not set up", detail: "Users sign in with their MDARIX password." }}
          columns={[
            { key: "type", label: "Type", render: (row) => <strong>{readable(row.provider_type)}</strong> },
            { key: "issuer", label: "Sign-in address", render: (row) => row.issuer },
            { key: "mode", label: "Sign-in", render: (row) => readable(row.login_mode) },
            {
              key: "status",
              label: "Status",
              render: (row) => (
                <ToneBadge
                  tone={row.status === "VERIFIED" || row.status === "ACTIVE" ? "good" : "warning"}
                  label={SSO_STATUS[String(row.status ?? "").toUpperCase()] ?? readable(row.status)}
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
              Sign-in address (issuer URL, https)
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
              Application (client) ID
              <input
                placeholder="Not a secret"
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
    <Panel eyebrow="Security" title="Security events" source={audit}>
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
            { key: "action", label: "Event", render: (row) => <strong>{readable(row.action)}</strong> },
            { key: "object", label: "Applies to", render: (row) => readable(row.entity_type) },
            { key: "source", label: "IP address", render: (row) => row.source_ip ?? "—" },
            { key: "when", label: "When", numeric: true, render: (row) => formatDate(row.created_at) },
          ]}
        />
      ) : (
        <Empty title="No security events" detail="Denied or suspicious activity will appear here." />
      )}
    </Panel>
  );
}
