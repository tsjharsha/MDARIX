import { useState } from "react";
import { Panel } from "../console/charts";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  listOf,
  matches,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { isPlatformAdminRole } from "../../../app/navigationPolicy";
import { titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { Intro, Pager } from "./common";

type User = { id: string; email: string; display_name?: string | null; role?: string | null; status?: string | null };
type Role = { id: string; code: string; name?: string | null; version?: string | null; status?: string | null };
type PermissionSet = {
  id: string;
  code: string;
  version?: string | null;
  status?: string | null;
  object_permissions?: unknown;
  field_permissions?: unknown;
  action_permissions?: unknown;
};

const size = (value: unknown) =>
  Array.isArray(value) ? value.length : value && typeof value === "object" ? Object.keys(value).length : 0;

const name = (user: User) => user.display_name || user.email;

/** MFA of another platform administrator can be reset here; one's own never (another administrator must do it). */
export const canResetMfa = (user: User, currentUserId: string | undefined) =>
  !!currentUserId && user.id !== currentUserId && isPlatformAdminRole(user.role);

export function IdentityAccess({ section }: { section: string }) {
  if (section === "Roles & permissions") return <RolesAndPermissions />;
  if (section === "Effective access") return <EffectiveAccess />;
  return <PlatformUsers />;
}

/** The people who work in the MDARIX platform tenant (customer users are managed by each Customer Administrator). */
function PlatformUsers() {
  const users = useResource<User[]>("/api/v1/admin/identity/users");
  const me = useResource<{ user_id?: string }>("/api/v1/auth/session");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const all = listOf(users.data) as User[];
  const filtered = all.filter(
    (user) => matches(user, query) && (!status || String(user.status).toUpperCase() === status),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 25));
  const shown = filtered.slice((Math.min(page, pages) - 1) * 25, Math.min(page, pages) * 25);
  return (
    <Panel eyebrow="MDARIX platform tenant" title="Platform users" source={users}>
      <Intro>
        People with an account in the MDARIX platform tenant. Customer users are managed by each customer&apos;s own
        administrators; Customer Administrators are under Customers &amp; Tenants.
      </Intro>
      <div className="cc-toolbar">
        <SearchBox
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
          label="Search name, email or role"
        />
        <select
          aria-label="Status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setPage(1);
          }}
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INVITED">Invited</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>
      <Table
        caption="Platform users"
        rows={shown}
        rowKey={(row) => row.id}
        empty={{ title: "No matching users", detail: "Change the search or status." }}
        columns={[
          {
            key: "user",
            fields: ["display_name", "email"],
            label: "User",
            render: (row) => (
              <span className="cc-stack">
                <strong>{name(row)}</strong>
                <small>{row.email}</small>
              </span>
            ),
          },
          { key: "role", label: "Role", render: (row) => titleCase(row.role ?? "—") },
          { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          {
            key: "mfa",
            label: "",
            render: (row) =>
              canResetMfa(row, me.data?.user_id) ? (
                <button
                  type="button"
                  className="ac-link"
                  onClick={() =>
                    setConfirm({
                      title: `Reset multi-factor authentication for ${name(row)}?`,
                      body: "Their authenticator and recovery codes stop working and they are signed out everywhere. At their next sign-in they set up a new authenticator. Do this only after confirming who is asking, for example by a call to a known number.",
                      confirmLabel: "Reset MFA",
                      danger: true,
                      reason: { label: "Reason (kept in the audit trail)", min: 5 },
                      run: (reason) => send(`/api/v1/platform-admin/users/${row.id}/mfa-reset`, "POST", { reason }),
                      done: `MFA reset for ${name(row)}. They set up a new authenticator at their next sign-in.`,
                    })
                  }
                >
                  Reset MFA
                </button>
              ) : null,
          },
        ]}
      />
      <Pager page={Math.min(page, pages)} pages={pages} total={filtered.length} noun="user" onPage={setPage} />
      {notice && (
        <p className="ac-message tone-good" role="status">
          {notice}
        </p>
      )}
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          setNotice(text);
          users.reload();
        }}
      />
    </Panel>
  );
}

/** Roles, and the permission sets each role grants. */
function RolesAndPermissions() {
  const roles = useResource<Role[]>("/api/v1/admin/identity/roles");
  const sets = useResource<PermissionSet[]>("/api/v1/admin/identity/permission-sets");
  const [roleId, setRoleId] = useState("");
  const granted = useResource<{ permission_sets: PermissionSet[] }>(
    roleId ? `/api/v1/admin/identity/roles/${roleId}/permission-sets` : null,
  );
  const roleRows = listOf(roles.data) as Role[];
  const setRows = listOf(sets.data) as PermissionSet[];
  const role = roleRows.find((item) => item.id === roleId);
  const permissionColumns = [
    { key: "set", label: "Permission set", render: (row: PermissionSet) => <strong>{titleCase(row.code)}</strong> },
    { key: "objects", label: "Records", numeric: true, render: (row: PermissionSet) => size(row.object_permissions) },
    { key: "fields", label: "Fields", numeric: true, render: (row: PermissionSet) => size(row.field_permissions) },
    { key: "actions", label: "Actions", numeric: true, render: (row: PermissionSet) => size(row.action_permissions) },
    { key: "status", label: "Status", render: (row: PermissionSet) => <StatusBadge status={row.status} /> },
  ];
  return (
    <div className="ac-grid two">
      <Panel eyebrow="Who can do what" title="Roles" source={roles}>
        <Intro>A role groups permission sets. Choose a role to see what it grants.</Intro>
        <Table
          caption="Roles"
          rows={roleRows}
          rowKey={(row) => row.id}
          empty={{ title: "No roles defined", detail: "Roles of the platform tenant appear here once defined." }}
          columns={[
            {
              key: "role",
              label: "Role",
              render: (row) => (
                <button
                  type="button"
                  className={`ac-link cc-stack${row.id === roleId ? " ar-selected" : ""}`}
                  onClick={() => setRoleId(row.id)}
                >
                  <strong>{row.name ?? titleCase(row.code)}</strong>
                  <small>
                    {row.code} · {row.version ?? "v1"}
                  </small>
                </button>
              ),
            },
            { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
          ]}
        />
      </Panel>
      <Panel
        eyebrow={role ? `Granted by ${role.name ?? role.code}` : "All permission sets"}
        title="Permission sets"
        state={roleId ? granted.state : sets.state}
        error={roleId ? granted.error : sets.error}
        action={
          roleId ? (
            <button type="button" className="ac-link" onClick={() => setRoleId("")}>
              Show all
            </button>
          ) : undefined
        }
      >
        <Table
          caption="Permission sets"
          rows={roleId ? (granted.data?.permission_sets ?? []) : setRows}
          rowKey={(row) => row.id}
          empty={{
            title: "No permission sets",
            detail: roleId ? "This role grants no permission set yet." : "None are defined yet.",
          }}
          columns={permissionColumns}
        />
      </Panel>
    </div>
  );
}

/** What one person can actually do: their roles and personas, as the server evaluates them. */
function EffectiveAccess() {
  const users = useResource<User[]>("/api/v1/admin/identity/users");
  const [userId, setUserId] = useState("");
  const access = useResource<{ status?: string; roles: Role[]; personas: Array<Record<string, any>> }>(
    userId ? `/api/v1/admin/identity/users/${userId}/effective-access` : null,
  );
  const rows = listOf(users.data) as User[];
  return (
    <div className="ac-grid">
      <Panel eyebrow="Check one person" title="Effective access" source={users}>
        <Intro>Choose a person to see the roles and personas that decide what they can do.</Intro>
        <label className="ca-field ar-picker">
          Person
          <select value={userId} onChange={(event) => setUserId(event.target.value)}>
            <option value="">Choose a person</option>
            {[...rows]
              .sort((a, b) => name(a).localeCompare(name(b)))
              .map((user) => (
                <option key={user.id} value={user.id}>
                  {name(user)} ({user.email})
                </option>
              ))}
          </select>
        </label>
      </Panel>
      {userId && (
        <div className="ac-grid two">
          <Panel eyebrow="Granted" title="Roles" source={access}>
            <Table
              caption="Roles"
              rows={access.data?.roles ?? []}
              rowKey={(row) => row.id}
              empty={{ title: "No roles assigned", detail: "Their account role alone applies." }}
              columns={[
                { key: "role", label: "Role", render: (row) => <strong>{row.name ?? titleCase(row.code)}</strong> },
                { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
              ]}
            />
          </Panel>
          <Panel eyebrow="Working as" title="Personas" source={access}>
            <Table
              caption="Personas"
              rows={access.data?.personas ?? []}
              rowKey={(row, index) => String(row.id ?? index)}
              empty={{ title: "No personas", detail: "No persona is assigned." }}
              columns={[
                {
                  key: "persona",
                  label: "Persona",
                  render: (row) => <strong>{row.name ?? titleCase(row.code ?? row.persona_code ?? "—")}</strong>,
                },
                { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
              ]}
            />
          </Panel>
        </div>
      )}
    </div>
  );
}
