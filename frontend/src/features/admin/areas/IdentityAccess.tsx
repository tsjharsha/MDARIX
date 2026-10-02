import { useState } from "react";
import { Panel } from "../console/charts";
import { SearchBox, Table, listOf, matches, useResource } from "../../customer-admin/shared";
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

export function IdentityAccess({ section }: { section: string }) {
  if (section === "Roles & permissions") return <RolesAndPermissions />;
  if (section === "Effective access") return <EffectiveAccess />;
  return <PlatformUsers />;
}

/** The people who work in the MDARIX platform tenant (customer users are managed by each Customer Administrator). */
function PlatformUsers() {
  const users = useResource<User[]>("/api/v1/admin/identity/users");
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
    <Panel eyebrow="MDARIX platform tenant" title="Platform users" state={users.state} error={users.error}>
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
        ]}
      />
      <Pager page={Math.min(page, pages)} pages={pages} total={filtered.length} noun="user" onPage={setPage} />
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
      <Panel eyebrow="Who can do what" title="Roles" state={roles.state} error={roles.error}>
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
      <Panel eyebrow="Check one person" title="Effective access" state={users.state} error={users.error}>
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
          <Panel eyebrow="Granted" title="Roles" state={access.state} error={access.error}>
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
          <Panel eyebrow="Working as" title="Personas" state={access.state} error={access.error}>
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
