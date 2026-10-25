import { useMemo, useState } from "react";
import { Download, KeyRound, Mail, ShieldOff, UserPlus } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { readable } from "../labels";
import { userStatusLabel, userTone, type TenantUser } from "../customerAdminModel";
import { ASSIGNABLE_ROLES, useConsole } from "../context";
import {
  Drawer,
  SearchBox,
  Table,
  Tabs,
  errorText,
  formatDate,
  idColumn,
  listOf,
  matches,
  send,
  useResource,
  type Confirmation,
} from "../shared";
import { downloadFile } from "../../reports/download";
import { safeText } from "../../../app/displayId";
import { roleLabel } from "../../../app/roles";
import { isCustomerAdminRole } from "../../../app/navigationPolicy";

/** The answer to an invitation or re-invitation, as the administrator should read it. When the account exists but
 * the email could not be delivered (201, delivery FAILED), MDARIX support issues an activation link to pass on. */
export function invitationNotice(
  result: { email_delivery?: string; delivery?: string; invitation_status?: string; message?: string } | null,
  email: string,
): { text: string; tone: "good" | "critical" } {
  if (result?.delivery === "FAILED" || result?.invitation_status === "NOT_SENT")
    return {
      tone: "critical",
      text:
        result.message ||
        "The account was created, but the invitation email could not be delivered. Ask MDARIX support for an activation link to pass on to the person.",
    };
  if (result?.email_delivery === "SENT")
    return { tone: "good", text: `Invitation sent to ${email}. They will create their own password.` };
  return {
    tone: "good",
    text: `Invitation created. Email delivery: ${readable(result?.email_delivery ?? "NOT_CONFIGURED").toLowerCase()}.`,
  };
}

/** The file a person's data export is saved as when the server does not name it: after their User ID, never the UUID. */
export const personExportName = (user: { business_id?: string | null }) =>
  `mdarix-person-${safeText(user.business_id) ?? "export"}.json`;

/** A person's account role as people read it: the server's label, else the known label for the code. */
export const accountRoleText = (user: { role?: string | null; role_label?: string | null }) =>
  user.role || user.role_label ? roleLabel(user.role, user.role_label) : "—";

/** GET/PUT /api/v1/admin/identity/users/{id}/roles: the account role and the additional workflow roles. */
export type UserWorkflowRoles = {
  user_id: string;
  business_id?: string | null;
  account_role?: { code: string; label?: string | null } | null;
  additional_roles?: Array<{
    code: string;
    label?: string | null;
    granted_at?: string | null;
    granted_by_name?: string | null;
  }>;
  available_roles?: Array<{ code: string; label?: string | null }>;
};

export const WORKFLOW_REASON_MIN = 10;
export const WORKFLOW_REASON_MAX = 500;

/** The roles that can be added on top of the account role (the account role itself is never offered twice). */
export function workflowRoleChoices(data: UserWorkflowRoles | null | undefined) {
  const account = data?.account_role?.code;
  return (data?.available_roles ?? []).filter((role) => role.code && role.code !== account);
}

/** Whether the chosen workflow roles differ from the ones the person holds now (order does not matter). */
export function workflowRolesChanged(current: string[], chosen: string[]) {
  const a = [...new Set(current)].sort();
  const b = [...new Set(chosen)].sort();
  return a.length !== b.length || a.some((code, index) => code !== b[index]);
}

/** Why the change cannot be saved yet, or null; the server checks the same rules (and which roles are allowed). */
export function workflowRolesProblem(current: string[], chosen: string[], reason: string): string | null {
  if (!workflowRolesChanged(current, chosen)) return "Change at least one role.";
  const text = reason.trim();
  if (text.length < WORKFLOW_REASON_MIN) return `Give a reason of at least ${WORKFLOW_REASON_MIN} characters.`;
  if (text.length > WORKFLOW_REASON_MAX) return `Keep the reason to ${WORKFLOW_REASON_MAX} characters.`;
  return null;
}

/** The body of PUT .../roles: the complete list of additional roles (without repeats) and the reason. */
export const workflowRolesBody = (chosen: string[], reason: string) => ({
  additional_roles: [...new Set(chosen)],
  reason: reason.trim(),
});

const FILTERS = ["All", "Active", "Invited", "Suspended", "Offboarded"] as const;
// Same role spellings the server treats as MDARIX platform roles; those accounts are managed by MDARIX only.
const PLATFORM_ROLES = new Set(["PLATFORM_ADMIN", "MDARIX_ADMINISTRATOR", "ADMINISTRATOR", "ADMIN"]);
const isPlatformRole = (role: unknown) =>
  PLATFORM_ROLES.has(
    String(role ?? "")
      .trim()
      .toUpperCase()
      .replace(/ /g, "_"),
  );
type Filter = (typeof FILTERS)[number];
const TABS = ["People", "Invite"] as const;
// What the confirmation says once a status change is made.
const STATUS_DONE = { ACTIVE: "can sign in again", SUSPENDED: "is suspended", OFFBOARDED: "is offboarded" } as const;
type Tab = (typeof TABS)[number];

export function UsersSection({ tab = "People" }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(tab === "Invite" ? "Invite" : "People");
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Users sections">
        {active === "People" ? (
          <People users={users} />
        ) : (
          <InviteForm
            onInvited={() => {
              users.reload();
              setActive("People");
            }}
          />
        )}
      </Tabs>
    </>
  );
}

function People({ users }: { users: ReturnType<typeof useResource<TenantUser[]>> }) {
  const { context } = useConsole();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("All");
  const [selected, setSelected] = useState<TenantUser | null>(null);
  const rows = useMemo(
    () =>
      (listOf(users.data) as TenantUser[])
        .filter((user) => filter === "All" || String(user.status).toUpperCase() === filter.toUpperCase())
        .filter((user) => matches(user, query)),
    [users.data, filter, query],
  );
  return (
    <Panel eyebrow="People" title="Users in your organization" source={users}>
      <div className="ca-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search name, email, ID or role" />
        <div className="ca-chips" role="group" aria-label="Filter by status">
          {FILTERS.map((option) => (
            <button
              type="button"
              key={option}
              aria-pressed={filter === option}
              className={filter === option ? "selected" : ""}
              onClick={() => setFilter(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <Table
        caption="Users in your organization"
        rows={rows}
        rowKey={(row) => row.id}
        empty={{ title: "No matching users", detail: "Change the filter or invite someone new." }}
        columns={[
          idColumn("User ID"),
          {
            key: "name",
            label: "Name",
            render: (row) => (
              <span className="ca-person">
                <strong>{row.display_name ?? row.email}</strong>
                <small>{row.email}</small>
              </span>
            ),
          },
          {
            key: "role",
            label: "Base role",
            fields: ["role", "role_label"],
            sortValue: (row) => accountRoleText(row),
            render: (row) => accountRoleText(row),
          },
          {
            key: "status",
            label: "Status",
            render: (row) => <ToneBadge tone={userTone(row.status)} label={userStatusLabel(row.status)} />,
          },
          {
            key: "manage",
            label: "",
            render: (row) => (
              <button type="button" className="ac-link" onClick={() => setSelected(row)}>
                {row.id === context?.user_id ? "View (you)" : isPlatformRole(row.role) ? "View" : "Manage"}
              </button>
            ),
          },
        ]}
      />
      {selected && (
        <UserDrawer
          user={selected}
          isSelf={selected.id === context?.user_id}
          onClose={() => setSelected(null)}
          onChanged={() => {
            users.reload();
            setSelected(null);
          }}
        />
      )}
    </Panel>
  );
}

function UserDrawer({
  user,
  isSelf,
  onClose,
  onChanged,
}: {
  user: TenantUser;
  isSelf: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { confirm, notify } = useConsole();
  const access = useResource<any>(`/api/v1/admin/identity/users/${user.id}/effective-access`);
  const roles = useResource<any[]>("/api/v1/admin/identity/roles");
  const personas = useResource<any[]>("/api/v1/admin/identity/personas");
  const roleAssignments = useResource<any[]>("/api/v1/admin/identity/role-assignments");
  const personaAssignments = useResource<any[]>("/api/v1/admin/identity/persona-assignments");
  const [baseRole, setBaseRole] = useState(String(user.role ?? "VIEWER").toUpperCase());
  const [roleId, setRoleId] = useState("");
  const [personaCode, setPersonaCode] = useState("");
  const status = String(user.status ?? "").toUpperCase();
  const name = user.display_name ?? user.email ?? "this user";
  const managedByMdarix = isPlatformRole(user.role);
  const administratorAccount = managedByMdarix || isCustomerAdminRole(user.role);
  const activeRoles = listOf(roles.data).filter((role) => String(role.status).toUpperCase() === "ACTIVE");
  const myRoleAssignments = listOf(roleAssignments.data).filter(
    (row) => row.user_id === user.id && String(row.status).toUpperCase() === "ACTIVE",
  );
  const myPersonaAssignments = listOf(personaAssignments.data).filter(
    (row) => row.user_id === user.id && String(row.status).toUpperCase() === "ACTIVE",
  );
  const roleName = (id: string) => listOf(roles.data).find((role) => role.id === id)?.name ?? "Role";
  const refreshAccess = () => {
    access.reload();
    roleAssignments.reload();
    personaAssignments.reload();
  };

  const setStatus = (next: "ACTIVE" | "SUSPENDED" | "OFFBOARDED", verb: string, body: string) =>
    confirm({
      title: `${verb} ${name}?`,
      body,
      confirmLabel: verb,
      danger: next !== "ACTIVE",
      done: `${name} ${STATUS_DONE[next]}.`,
      run: async () => {
        await send(`/api/v1/admin/identity/users/${user.id}/status`, "PATCH", { status: next });
        onChanged();
      },
    });

  const resetPassword = async () => {
    try {
      const result = await send<any>("/api/v1/admin/identity/users/password-reset", "POST", { email: user.email });
      notify(
        result.email_delivery === "SENT"
          ? `Password reset email sent to ${user.email}.`
          : `Reset requested. Email delivery: ${readable(result.email_delivery ?? "NOT_CONFIGURED").toLowerCase()}.`,
      );
    } catch (reason) {
      notify(errorText(reason, "Password reset could not be requested."), "critical");
    }
  };

  // Answers a person's access request: their account, memberships, sign-in history, audit events and feedback.
  const exportPerson = async () => {
    try {
      const file = await downloadFile(`/api/v1/admin/people/${user.id}/export`, {
        fallbackName: personExportName(user),
      });
      notify(`${name}'s data was exported as ${file}. The export is recorded in the audit trail.`);
    } catch (reason) {
      notify(errorText(reason, "The export could not be prepared."), "critical");
    }
  };

  return (
    <Drawer title={name} onClose={onClose}>
      <dl className="ca-facts">
        <div>
          <dt>Email</dt>
          <dd>{user.email}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>
            <ToneBadge tone={userTone(user.status)} label={userStatusLabel(user.status)} />
          </dd>
        </div>
        <div>
          <dt>Base role</dt>
          <dd>{accountRoleText(user)}</dd>
        </div>
      </dl>

      {managedByMdarix && (
        <p className="ca-note-box">
          This account holds an MDARIX platform role. Only MDARIX can change it; it is shown here for transparency.
        </p>
      )}

      {isSelf && (
        <p className="ca-note-box">
          This is your own account. To protect against lock-out, another administrator must change your role or status.
        </p>
      )}

      <section className="ca-drawer-section">
        <h3>What they can access now</h3>
        {access.state === "ready" ? (
          <ul className="ca-pill-list">
            {listOf(access.data?.roles).map((role) => (
              <li key={role.id}>Role · {role.name}</li>
            ))}
            {listOf(access.data?.personas).map((persona) => (
              <li key={persona.code}>Persona · {readable(persona.code)}</li>
            ))}
            {!listOf(access.data?.roles).length && !listOf(access.data?.personas).length && (
              <li className="ac-muted">Their base role only. No extra roles or personas.</li>
            )}
          </ul>
        ) : (
          <p className="ac-muted">
            {access.state === "loading" ? "Loading…" : "This could not be loaded. Try again later."}
          </p>
        )}
      </section>

      {!isSelf && !managedByMdarix && (
        <section className="ca-drawer-section">
          <h3>Base role</h3>
          <div className="ca-inline-form">
            <select aria-label="Base role" value={baseRole} onChange={(event) => setBaseRole(event.target.value)}>
              {ASSIGNABLE_ROLES.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="ac-secondary"
              disabled={baseRole === String(user.role ?? "").toUpperCase()}
              onClick={() =>
                confirm({
                  title: `Change ${name}'s base role?`,
                  body: `The base role becomes ${roleLabel(baseRole)}. It applies at their next request.`,
                  confirmLabel: "Change role",
                  done: `${name} now has the ${roleLabel(baseRole)} base role.`,
                  run: async () => {
                    await send(`/api/v1/admin/control-plane/users/${user.id}`, "PATCH", { values: { role: baseRole } });
                    onChanged();
                  },
                })
              }
            >
              Save role
            </button>
          </div>
        </section>
      )}

      {!managedByMdarix && <WorkflowRoles user={user} name={name} />}

      {!managedByMdarix && (
        <>
          <section className="ca-drawer-section">
            <h3>Custom roles</h3>
            <ul className="ca-assignment-list">
              {myRoleAssignments.map((row) => (
                <li key={row.id}>
                  <span>{roleName(row.role_id)}</span>
                  <button
                    type="button"
                    className="ac-link"
                    onClick={() =>
                      confirm({
                        title: `Remove ${roleName(row.role_id)} from ${name}?`,
                        body: "Permissions granted by this role end at their next request.",
                        confirmLabel: "Remove role",
                        danger: true,
                        done: "Role removed.",
                        run: async () => {
                          await send(`/api/v1/admin/identity/role-assignments/${row.id}/status`, "PATCH", {
                            status: "RETIRED",
                          });
                          refreshAccess();
                        },
                      })
                    }
                  >
                    Remove
                  </button>
                </li>
              ))}
              {!myRoleAssignments.length && <li className="ac-muted">None assigned.</li>}
            </ul>
            {/* The server refuses these too (R11): nobody gives themselves a role, and an administrator account keeps
                its administrator role, so a custom role never lets an administrator sign. */}
            {isSelf || administratorAccount ? (
              <p className="ac-muted">
                {isSelf
                  ? "Another administrator must change your roles."
                  : "An administrator's role is set on the account. Custom roles do not change it."}
              </p>
            ) : (
              <div className="ca-inline-form">
                <select aria-label="Role to assign" value={roleId} onChange={(event) => setRoleId(event.target.value)}>
                  <option value="">{activeRoles.length ? "Choose an active role" : "No active roles yet"}</option>
                  {activeRoles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name} ({role.version})
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="ac-secondary"
                  disabled={!roleId}
                  onClick={async () => {
                    try {
                      await send("/api/v1/admin/identity/role-assignments", "POST", {
                        user_id: user.id,
                        role_id: roleId,
                      });
                      notify(`${roleName(roleId)} assigned to ${name}.`);
                      setRoleId("");
                      refreshAccess();
                    } catch (reason) {
                      notify(errorText(reason, "Role could not be assigned."), "critical");
                    }
                  }}
                >
                  Assign
                </button>
              </div>
            )}
          </section>

          <section className="ca-drawer-section">
            <h3>Personas</h3>
            <p className="ac-muted">Personas shape the user's workspace. They do not grant permissions.</p>
            <ul className="ca-assignment-list">
              {myPersonaAssignments.map((row) => (
                <li key={row.id}>
                  <span>{readable(row.persona_code)}</span>
                  <button
                    type="button"
                    className="ac-link"
                    onClick={async () => {
                      try {
                        await send(`/api/v1/admin/identity/persona-assignments/${row.id}/status`, "PATCH", {
                          status: "RETIRED",
                        });
                        notify("Persona removed.");
                        refreshAccess();
                      } catch (reason) {
                        notify(errorText(reason, "Persona could not be removed."), "critical");
                      }
                    }}
                  >
                    Remove
                  </button>
                </li>
              ))}
              {!myPersonaAssignments.length && <li className="ac-muted">None assigned.</li>}
            </ul>
            <div className="ca-inline-form">
              <select
                aria-label="Persona to assign"
                value={personaCode}
                onChange={(event) => setPersonaCode(event.target.value)}
              >
                <option value="">Choose a persona</option>
                {listOf(personas.data).map((persona) => (
                  <option key={persona.code} value={persona.code}>
                    {persona.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="ac-secondary"
                disabled={!personaCode}
                onClick={async () => {
                  try {
                    await send("/api/v1/admin/identity/persona-assignments", "POST", {
                      user_id: user.id,
                      persona_code: personaCode,
                    });
                    notify("Persona assigned.");
                    setPersonaCode("");
                    refreshAccess();
                  } catch (reason) {
                    notify(errorText(reason, "Persona could not be assigned."), "critical");
                  }
                }}
              >
                Assign
              </button>
            </div>
          </section>

          <section className="ca-drawer-section">
            <h3>Account actions</h3>
            <div className="ca-action-row">
              {status !== "ERASED" && (
                <button type="button" className="ac-secondary" onClick={() => void exportPerson()}>
                  <Download size={15} /> Export this person&apos;s data
                </button>
              )}
              {user.email && (status === "ACTIVE" || status === "SUSPENDED") && (
                <button type="button" className="ac-secondary" onClick={() => void resetPassword()}>
                  <KeyRound size={15} /> Send password reset
                </button>
              )}
              {!isSelf && status === "ACTIVE" && (
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() =>
                    confirm({
                      title: `Reset multi-factor authentication for ${name}?`,
                      body: "Use this when they lost their authenticator app and recovery codes. Their authenticator is removed, they are signed out, and they set up a new one at their next sign-in.",
                      confirmLabel: "Reset MFA",
                      reason: { label: "Why is the authenticator being reset?", min: 5 },
                      done: `${name} sets up a new authenticator at their next sign-in.`,
                      run: async (reason) => {
                        await send(`/api/v1/admin/identity/users/${user.id}/mfa-reset`, "POST", { reason });
                        onChanged();
                      },
                    })
                  }
                >
                  <ShieldOff size={15} /> Reset MFA
                </button>
              )}
              {!isSelf && status === "ACTIVE" && (
                <button
                  type="button"
                  className="ca-danger-outline"
                  onClick={() =>
                    setStatus(
                      "SUSPENDED",
                      "Suspend",
                      "They are signed out everywhere at once and cannot sign in until restored. Their data and assignments are kept.",
                    )
                  }
                >
                  Suspend
                </button>
              )}
              {!isSelf && status === "SUSPENDED" && (
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() => setStatus("ACTIVE", "Restore", "They can sign in again with their existing password.")}
                >
                  Restore access
                </button>
              )}
              {!isSelf && status !== "OFFBOARDED" && (
                <button
                  type="button"
                  className="ca-danger-outline"
                  onClick={() =>
                    setStatus(
                      "OFFBOARDED",
                      "Offboard",
                      "They are signed out and their seat is released. The account is kept for audit and can be re-invited later.",
                    )
                  }
                >
                  Offboard
                </button>
              )}
              {!isSelf && status === "OFFBOARDED" && (
                <button
                  type="button"
                  className="ac-secondary"
                  onClick={() => {
                    const request: Confirmation = {
                      title: `Re-invite ${name}?`,
                      body: "A new activation email is sent. They set a new password; the old one no longer works.",
                      confirmLabel: "Re-invite",
                      done: `${name} has been re-invited.`,
                      run: async () => {
                        const result = await send<any>(`/api/v1/admin/identity/users/${user.id}/reactivate`, "POST");
                        // The dialog reports `done` once this returns: say so when the email did not go out.
                        const notice = invitationNotice(result, user.email ?? name);
                        if (notice.tone === "critical") request.done = `${name} has been re-invited. ${notice.text}`;
                        onChanged();
                      },
                    };
                    confirm(request);
                  }}
                >
                  <Mail size={15} /> Re-invite
                </button>
              )}
              {!isSelf && status === "OFFBOARDED" && (
                <button
                  type="button"
                  className="ca-danger-outline"
                  onClick={() =>
                    confirm({
                      title: `Erase ${name}'s personal data?`,
                      body: "Use this when the person asks for their data to be erased. Their name, email and sign-in details are removed for good and the account can no longer be re-invited. Records they created stay, linked to an anonymous account. This cannot be undone.",
                      confirmLabel: "Erase personal data",
                      danger: true,
                      reason: { label: "The person's request (and how you verified it)", min: 10 },
                      done: `${name}'s personal data has been erased.`,
                      run: async (reason) => {
                        await send(`/api/v1/admin/identity/users/${user.id}/erase`, "POST", { reason });
                        onChanged();
                      },
                    })
                  }
                >
                  Erase personal data
                </button>
              )}
            </div>
          </section>
        </>
      )}
    </Drawer>
  );
}

/** The additional workflow roles a person holds on top of their account role, and the editor to change them. */
function WorkflowRoles({ user, name }: { user: TenantUser; name: string }) {
  const { notify } = useConsole();
  const path = `/api/v1/admin/identity/users/${encodeURIComponent(user.id)}/roles`;
  const roles = useResource<UserWorkflowRoles>(path);
  const [editing, setEditing] = useState(false);
  const [chosen, setChosen] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const held = roles.data?.additional_roles ?? [];
  const current = held.map((role) => role.code);
  const choices = workflowRoleChoices(roles.data);
  const problem = workflowRolesProblem(current, chosen, reason);
  const account = roles.data?.account_role;
  const toggle = (code: string) =>
    setChosen((list) => (list.includes(code) ? list.filter((item) => item !== code) : [...list, code]));
  const startEditing = () => {
    setChosen(current);
    setReason("");
    setError("");
    setEditing(true);
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (problem) return;
    setBusy(true);
    setError("");
    try {
      await send(path, "PUT", workflowRolesBody(chosen, reason));
      notify(`${name}: workflow roles updated. They apply at their next request.`);
      setEditing(false);
      roles.reload();
    } catch (failure) {
      setError(errorText(failure, "The workflow roles could not be changed."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ca-drawer-section">
      <h3>Workflow roles</h3>
      <p className="ac-muted">
        Additional roles route work (triage, investigations, reviews and decisions) to this person on top of their base
        role{account ? ` (${roleLabel(account.code, account.label)})` : ""}.
      </p>
      {roles.state === "ready" ? (
        <ul className="ca-assignment-list">
          {held.map((role) => (
            <li key={role.code}>
              <span className="ca-person">
                <strong>{roleLabel(role.code, role.label)}</strong>
                <small>
                  Granted {formatDate(role.granted_at)}
                  {safeText(role.granted_by_name) ? ` by ${role.granted_by_name}` : ""}
                </small>
              </span>
            </li>
          ))}
          {!held.length && <li className="ac-muted">No additional roles.</li>}
        </ul>
      ) : (
        <p className="ac-muted">
          {roles.state === "loading" ? "Loading…" : (roles.error ?? "Workflow roles are unavailable.")}
        </p>
      )}
      {roles.state === "ready" && !editing && (
        <div className="ca-action-row">
          <button type="button" className="ac-secondary" onClick={startEditing} disabled={!choices.length}>
            Change workflow roles
          </button>
        </div>
      )}
      {roles.state === "ready" && editing && (
        <form className="ca-form" onSubmit={save}>
          <fieldset className="ca-fieldset">
            <legend>Additional roles</legend>
            {choices.map((role) => (
              <label key={role.code} className="ca-check">
                <input type="checkbox" checked={chosen.includes(role.code)} onChange={() => toggle(role.code)} />
                {roleLabel(role.code, role.label)}
              </label>
            ))}
          </fieldset>
          <label className="ca-field">
            Why are the roles changing?
            <textarea
              required
              rows={3}
              minLength={WORKFLOW_REASON_MIN}
              maxLength={WORKFLOW_REASON_MAX}
              value={reason}
              placeholder={`At least ${WORKFLOW_REASON_MIN} characters, recorded in the audit trail`}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          {error && (
            <p className="ca-inline-error" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="button" className="ac-secondary" onClick={() => setEditing(false)} disabled={busy}>
              Cancel
            </button>
            <button type="submit" className="ac-primary" disabled={busy || !!problem}>
              {busy ? "Saving…" : "Save workflow roles"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function InviteForm({ onInvited }: { onInvited: () => void }) {
  const { context, notify } = useConsole();
  const [invite, setInvite] = useState({
    firstName: "",
    lastName: "",
    email: "",
    company: context?.current_tenant?.tenant_name ?? "",
    role: "VIEWER",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Tenant context is server-derived: the request carries no tenant id, so an invite can only land in this tenant.
  const submitInvite = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await send<any>("/api/v1/admin/identity/users", "POST", {
        email: invite.email.trim(),
        display_name: `${invite.firstName} ${invite.lastName}`.trim(),
        company: invite.company.trim(),
        role: invite.role,
      });
      const notice = invitationNotice(result, invite.email);
      notify(notice.text, notice.tone);
      onInvited();
    } catch (reason) {
      setError(errorText(reason, "The invitation could not be sent."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel eyebrow="People" title="Invite a user">
      <form className="ca-form" onSubmit={submitInvite}>
        <p className="ac-muted">
          They receive an email to activate their account and choose their own password. You never see or type it.
        </p>
        <div className="ca-form-grid">
          <label className="ca-field">
            First name
            <input
              required
              value={invite.firstName}
              onChange={(event) => setInvite({ ...invite, firstName: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Last name
            <input
              required
              value={invite.lastName}
              onChange={(event) => setInvite({ ...invite, lastName: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Work email
            <input
              required
              type="email"
              autoComplete="off"
              value={invite.email}
              onChange={(event) => setInvite({ ...invite, email: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Company
            <input
              required
              value={invite.company}
              onChange={(event) => setInvite({ ...invite, company: event.target.value })}
            />
          </label>
          <label className="ca-field">
            Base role
            <select value={invite.role} onChange={(event) => setInvite({ ...invite, role: event.target.value })}>
              {ASSIGNABLE_ROLES.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {invite.role === "CUSTOMER_ADMIN" && (
          <p className="ca-note-box">
            Customer Administrators can manage every user, connection and setting in your organization.
          </p>
        )}
        {error && (
          <p className="ca-inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="ca-action-row">
          <button type="submit" className="ac-primary" disabled={busy}>
            <UserPlus size={16} /> {busy ? "Sending…" : "Send invitation"}
          </button>
        </div>
      </form>
      {!context && <Empty title="Organization context unavailable" detail="Reload the page and try again." />}
    </Panel>
  );
}
