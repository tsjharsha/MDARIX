import { useMemo, useState } from "react";
import { KeyRound, Mail, UserPlus } from "lucide-react";
import { Empty, Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase } from "../../admin/console/dashboardModel";
import { userTone, type TenantUser } from "../customerAdminModel";
import { ASSIGNABLE_ROLES, useConsole } from "../context";
import { Drawer, SearchBox, Table, Tabs, errorText, listOf, matches, send, useResource } from "../shared";

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
type Tab = (typeof TABS)[number];

export function UsersSection({ tab = "People" }: { tab?: string }) {
  const [active, setActive] = useState<Tab>(tab === "Invite" ? "Invite" : "People");
  const users = useResource<TenantUser[]>("/api/v1/admin/identity/users");
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Users sections" />
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
    <Panel eyebrow="People" title="Users in your organization" state={users.state} error={users.error}>
      <div className="ca-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search name, email or role" />
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
          { key: "role", label: "Base role", render: (row) => (row.role ? titleCase(row.role) : "—") },
          {
            key: "status",
            label: "Status",
            render: (row) => <ToneBadge tone={userTone(row.status)} label={titleCase(row.status ?? "Unknown")} />,
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
      done: `${name}: ${verb.toLowerCase()} complete.`,
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
          : `Reset requested. Email delivery: ${titleCase(result.email_delivery ?? "not configured")}.`,
      );
    } catch (reason) {
      notify(errorText(reason, "Password reset could not be requested."), "critical");
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
            <ToneBadge tone={userTone(user.status)} label={titleCase(user.status ?? "Unknown")} />
          </dd>
        </div>
        <div>
          <dt>Base role</dt>
          <dd>{user.role ? titleCase(user.role) : "—"}</dd>
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
        <h3>Effective access</h3>
        {access.state === "ready" ? (
          <ul className="ca-pill-list">
            {listOf(access.data?.roles).map((role) => (
              <li key={role.id}>Role · {role.name}</li>
            ))}
            {listOf(access.data?.personas).map((persona) => (
              <li key={persona.code}>Persona · {titleCase(persona.code)}</li>
            ))}
            {!listOf(access.data?.roles).length && !listOf(access.data?.personas).length && (
              <li className="ac-muted">Base role only — no assigned roles or personas.</li>
            )}
          </ul>
        ) : (
          <p className="ac-muted">{access.state === "loading" ? "Loading…" : "Effective access is unavailable."}</p>
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
                  body: `The base role becomes ${titleCase(baseRole)}. It applies at their next request.`,
                  confirmLabel: "Change role",
                  done: `${name} now has the ${titleCase(baseRole)} base role.`,
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

      {!managedByMdarix && (
        <>
          <section className="ca-drawer-section">
            <h3>Assigned roles</h3>
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
              {!myRoleAssignments.length && <li className="ac-muted">No roles assigned.</li>}
            </ul>
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
          </section>

          <section className="ca-drawer-section">
            <h3>Personas</h3>
            <p className="ac-muted">Personas shape the user's workspace. They do not grant permissions.</p>
            <ul className="ca-assignment-list">
              {myPersonaAssignments.map((row) => (
                <li key={row.id}>
                  <span>{titleCase(row.persona_code)}</span>
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
              {!myPersonaAssignments.length && <li className="ac-muted">No personas assigned.</li>}
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
              {user.email && (status === "ACTIVE" || status === "SUSPENDED") && (
                <button type="button" className="ac-secondary" onClick={() => void resetPassword()}>
                  <KeyRound size={15} /> Send password reset
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
                  onClick={() =>
                    confirm({
                      title: `Re-invite ${name}?`,
                      body: "A new activation email is sent. They set a new password; the old one no longer works.",
                      confirmLabel: "Re-invite",
                      done: `${name} has been re-invited.`,
                      run: async () => {
                        await send(`/api/v1/admin/identity/users/${user.id}/reactivate`, "POST");
                        onChanged();
                      },
                    })
                  }
                >
                  <Mail size={15} /> Re-invite
                </button>
              )}
            </div>
          </section>
        </>
      )}
    </Drawer>
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
      notify(
        result?.email_delivery === "SENT"
          ? `Invitation sent to ${invite.email}. They will create their own password.`
          : `Invitation created. Email delivery: ${titleCase(result?.email_delivery ?? "not configured")}.`,
      );
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
          The user receives an activation email and sets their own password. You never see or type it.
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
