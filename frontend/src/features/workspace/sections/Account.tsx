import { useState, type FormEvent } from "react";
import { CheckCircle2, KeyRound, LogOut } from "lucide-react";
import { Panel } from "../../admin/console/charts";
import { TwoFactorPanel } from "../../shared/TwoFactorSettings";
import { titleCase } from "../../admin/console/dashboardModel";
import { Tabs, errorText, send, useResource } from "../../customer-admin/shared";
import { signOut } from "../../shared/session";
import { TRIAL_ONLY_SECTIONS, WORKSPACE_SECTIONS, sectionAllowed, useWorkspace } from "../workspaceContext";
import { hideUuid, safeText } from "../../../app/displayId";
import { roleLabel, rolesSummary } from "../../../app/roles";
import { PUBLISHED_CONTACT, useSiteInfo } from "../../../site/legal";

const TABS = ["Profile", "Security", "Access"] as const;
type Tab = (typeof TABS)[number];

export function AccountSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>((TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Profile");
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Account sections">
        {active === "Profile" && (
          <>
            <Profile />
            <EmailChoices />
          </>
        )}
        {active === "Security" && <Security />}
        {active === "Access" && <Access />}
      </Tabs>
    </>
  );
}

/**
 * Who you are in MDARIX. A free trial has no administrator, and its people never need the internal user or organization
 * IDs: there the panel names neither and says whom to write to instead (UX-27). Exported for its test.
 */
export function Profile() {
  const { session, isTrial } = useWorkspace();
  const support = useSiteInfo()?.support_email || PUBLISHED_CONTACT.support;
  return (
    <Panel eyebrow="My account" title={session?.display_name ?? "Your profile"}>
      <dl className="ca-facts">
        {!isTrial && (
          <div>
            <dt>User ID</dt>
            <dd>{hideUuid(session?.business_id)}</dd>
          </div>
        )}
        <div>
          <dt>Email</dt>
          <dd>{session?.email ?? "—"}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{rolesSummary(session, "—")}</dd>
        </div>
        <div>
          <dt>Organization</dt>
          <dd>
            {session?.current_tenant?.tenant_name ?? "—"}
            {!isTrial && safeText(session?.tenant_business_id) ? ` · ${session?.tenant_business_id}` : ""}
          </dd>
        </div>
        <div>
          <dt>Workspace type</dt>
          <dd>{titleCase(session?.environment ?? "—")}</dd>
        </div>
      </dl>
      {isTrial ? (
        <p className="ac-muted">
          This is a free trial workspace. To change your name or email, write to{" "}
          <a href={`mailto:${support}`}>{support}</a>.
        </p>
      ) : (
        <p className="ac-muted">
          Your name, email and role are managed by your organization's administrator. Ask them if anything is wrong.
        </p>
      )}
    </Panel>
  );
}

type EmailPreferences = {
  weekly_readiness: boolean;
  weekly_readiness_eligible: boolean;
  weekly_readiness_about: string;
};

/** The weekly readiness email, on or off for oneself (GET/PUT /api/v1/me/email-preferences). Exported for its test. */
export function EmailChoices() {
  const preferences = useResource<EmailPreferences>("/api/v1/me/email-preferences");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = preferences.data;
  const change = async (on: boolean) => {
    setBusy(true);
    setError("");
    try {
      await send("/api/v1/me/email-preferences", "PUT", { weekly_readiness: on });
      preferences.reload();
    } catch (failure) {
      setError(errorText(failure, "Your email choice was not saved."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel eyebrow="Email" title="Weekly readiness email" source={preferences}>
      {data && (
        <>
          <p>{data.weekly_readiness_about}</p>
          {data.weekly_readiness_eligible && (
            <label className="ca-check">
              <input
                type="checkbox"
                checked={data.weekly_readiness}
                disabled={busy}
                onChange={(event) => void change(event.target.checked)}
              />{" "}
              Send me the weekly readiness email
            </label>
          )}
          {error && (
            <p className="uw-flag-critical" role="alert">
              {error}
            </p>
          )}
        </>
      )}
    </Panel>
  );
}

function Security() {
  const { session, notify } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [problem, setProblem] = useState("");
  const requestReset = async () => {
    if (!session?.email) return;
    setBusy(true);
    try {
      await send("/api/v1/auth/forgot-password", "POST", { email: session.email });
      notify(`We have emailed a reset link to ${session.email}. It works once and expires in one hour.`);
    } catch (reason) {
      notify(errorText(reason, "The reset link could not be requested."), "critical");
    } finally {
      setBusy(false);
    }
  };
  const changePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setProblem("");
    if (next !== confirm) {
      setProblem("The new password and its confirmation do not match.");
      return;
    }
    setBusy(true);
    try {
      const result = await send<{ other_sessions_signed_out: number }>("/api/v1/auth/change-password", "POST", {
        current_password: current,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      const others = result?.other_sessions_signed_out ?? 0;
      notify(
        others
          ? `Password changed. ${others} other session${others === 1 ? " was" : "s were"} signed out.`
          : "Password changed.",
      );
    } catch (reason) {
      setProblem(errorText(reason, "The password could not be changed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="ac-grid two">
      <TwoFactorPanel account={session?.email} />
      <Panel eyebrow="Sign-in" title="Change your password">
        <form className="uw-password-form" onSubmit={(event) => void changePassword(event)}>
          <label>
            Current password
            <input
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
            />
          </label>
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={128}
              value={next}
              onChange={(event) => setNext(event.target.value)}
            />
            <small>At least 12 characters. A phrase of several words works well.</small>
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={128}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
            />
          </label>
          {problem && (
            <p className="uw-trial-message is-bad" role="alert">
              {problem}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary" disabled={busy}>
              <KeyRound size={16} /> {busy ? "Saving…" : "Change password"}
            </button>
            <button
              type="button"
              className="ac-link"
              disabled={busy || !session?.email}
              onClick={() => void requestReset()}
            >
              Forgot it? Email me a reset link
            </button>
          </div>
          <p className="ac-muted">Your other sessions are signed out when the password changes.</p>
        </form>
      </Panel>
      <Panel eyebrow="Sessions" title="How your session is protected">
        <ul className="ca-check-list">
          <li>You are signed out after 30 minutes without activity.</li>
          <li>No session lasts longer than 12 hours, even when active.</li>
          <li>If your administrator suspends your account, you are signed out everywhere immediately.</li>
        </ul>
        <div className="ca-action-row">
          <button type="button" className="ca-danger-outline" onClick={() => void signOut()}>
            <LogOut size={16} /> Sign out now
          </button>
        </div>
      </Panel>
      <Panel eyebrow="Data boundary" title="Your organization's data stays separate">
        <ul className="ca-check-list">
          <li>Your organization is set by your sign-in. The browser cannot choose it.</li>
          <li>Every record you see belongs to {session?.current_tenant?.tenant_name ?? "your organization"}.</li>
          <li>AI answers use only your organization's authorized records.</li>
        </ul>
      </Panel>
    </div>
  );
}

function Access() {
  const { session } = useWorkspace();
  const me = useResource<any>("/api/v1/me/context");
  const permissions = me.data?.permissions;
  const actions: string[] = Array.isArray(permissions?.actions)
    ? permissions.actions
    : Array.isArray(permissions)
      ? permissions
      : permissions && typeof permissions === "object"
        ? Object.keys(permissions)
        : [];
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Access" title="Sections you can open">
        <ul className="ca-boundary">
          {WORKSPACE_SECTIONS.filter(
            (section) => section !== "My Account" && !TRIAL_ONLY_SECTIONS.includes(section),
          ).map((section) => {
            const allowed = sectionAllowed(section, session?.allowed_menu, session?.business_permissions);
            return (
              <li key={section} className={allowed ? "" : "ac-muted"}>
                <CheckCircle2
                  size={15}
                  className={`ac-tone-icon ${allowed ? "tone-good" : "tone-neutral"}`}
                  aria-hidden="true"
                />{" "}
                {section} {allowed ? "" : "· not included in your role"}
              </li>
            );
          })}
        </ul>
      </Panel>
      <Panel eyebrow="Access" title="Your role" source={me}>
        <dl className="ca-facts">
          <div>
            <dt>Active role</dt>
            <dd>{roleLabel(me.data?.active_role ?? session?.active_role) || "—"}</dd>
          </div>
        </dl>
        <h3 className="ca-subhead">Personas</h3>
        <ul className="ca-pill-list">
          {(me.data?.personas ?? session?.personas ?? []).map((persona: { code: string; label: string }) => (
            <li key={persona.code}>{persona.label}</li>
          ))}
          {!(me.data?.personas ?? session?.personas ?? []).length && <li className="ac-muted">No personas assigned</li>}
        </ul>
        {actions.length > 0 && (
          <details className="uw-more">
            <summary>What your role allows you to do ({actions.length})</summary>
            <ul className="ca-pill-list">
              {actions.slice(0, 40).map((action) => (
                <li key={String(action)}>{titleCase(String(action).replace(/\./g, " "))}</li>
              ))}
            </ul>
          </details>
        )}
        <p className="ac-muted">
          Your access is checked each time you open or change a record. To change it, ask your administrator.
        </p>
      </Panel>
    </div>
  );
}
