import { useState } from "react";
import { Check, Minus } from "lucide-react";
import { Panel } from "../console/charts";
import {
  ConfirmDialog,
  SearchBox,
  Table,
  idColumn,
  listOf,
  matches,
  send,
  useResource,
  type Confirmation,
} from "../../customer-admin/shared";
import { isPlatformAdminRole } from "../../../app/navigationPolicy";
import { sortParams, useServerSort } from "../../../app/tableSort";
import { titleCase } from "../customers/model";
import { StatusBadge } from "../customers/StatusBadge";
import { CustomerAdmins } from "../customers/CustomerAdmins";
import { DemoRequestsWorkspace } from "../DemoRequestsWorkspace";
import { MvpRequestsWorkspace } from "../MvpRequestsWorkspace";
import { TrialRequestsWorkspace } from "../TrialRequestsWorkspace";
import "../../customer-admin/customer-admin.css";
import "../customers/customers.css";
import { Banner, Intro, Pager, type BannerMessage } from "./common";
import { ChangeNameDialog, canChangeName } from "./ChangeName";

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

/** An account status as the lists name it: an INACTIVE account is retired (listed only when asked for). */
const accountStatusLabel = (status: unknown) =>
  String(status ?? "").toUpperCase() === "INACTIVE" ? "Retired" : undefined;

/** MFA of another platform administrator can be reset here; one's own never (another administrator must do it). */
export const canResetMfa = (user: User, currentUserId: string | undefined) =>
  !!currentUserId && user.id !== currentUserId && isPlatformAdminRole(user.role);

export function IdentityAccess({ section, websiteDemos = false }: { section: string; websiteDemos?: boolean }) {
  if (section === "Roles & permissions") return <RolesAndPermissions />;
  if (section === "Effective access") return <EffectiveAccess />;
  if (section === "Customer administrators") return <CustomerAdministrators />;
  if (section === "Customer users") return <CustomerUsers />;
  if (section === "Onboarding") return <Onboarding websiteDemos={websiteDemos} />;
  return <PlatformUsers />;
}

/** An account as the platform account lists return it (backend/app/access/platform_accounts.py). */
type Account = User & {
  tenant_id?: string | null;
  role_label?: string | null;
  tenant_name?: string | null;
  tenant_business_id?: string | null;
  customer_name?: string | null;
};

/** The customer and tenant an account belongs to. */
const organizationColumn = {
  key: "organization",
  label: "Organization",
  fields: ["customer_name", "tenant_name", "tenant_business_id"],
  render: (row: Account) => (
    <span className="cc-stack">
      <strong>{row.customer_name ?? row.tenant_name ?? "—"}</strong>
      <small>
        {row.tenant_name ?? "—"}
        {row.tenant_business_id ? ` · ${row.tenant_business_id}` : ""}
      </small>
    </span>
  ),
};

const userColumn = {
  key: "user",
  fields: ["display_name", "email"],
  label: "User",
  render: (row: Account) => (
    <span className="cc-stack">
      <strong>{name(row)}</strong>
      <small>{row.email}</small>
    </span>
  ),
};

/** Platform administrators only: MDARIX staff, whichever organization their account signs in to. */
function PlatformUsers() {
  const me = useResource<{ user_id?: string; tenant_id?: string }>("/api/v1/auth/session");
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [renaming, setRenaming] = useState<Account | null>(null);
  const [notice, setNotice] = useState<BannerMessage>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  // Retired accounts are listed only when asked for by status.
  const users = useResource<{ items: Account[] }>(
    `/api/v1/platform-admin/platform-users${status ? `?status=${status}` : ""}`,
  );
  const all = listOf(users.data) as Account[];
  const filtered = all.filter(
    (user) => matches(user, query) && (!status || String(user.status).toUpperCase() === status),
  );
  return (
    <Panel eyebrow="MDARIX staff" title="Platform users" source={users}>
      <Banner message={notice} onDismiss={() => setNotice(null)} />
      <Intro>
        People with platform administration access. Customer accounts are listed separately, under Customer
        administrators and Customer users.
      </Intro>
      <div className="cc-toolbar">
        <SearchBox value={query} onChange={setQuery} label="Search name, email or organization" />
        <select aria-label="Status" value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="">Current accounts</option>
          <option value="ACTIVE">Active</option>
          <option value="INVITED">Invited</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="INACTIVE">Retired</option>
        </select>
      </div>
      <Table
        caption="Platform users"
        rows={filtered}
        rowKey={(row) => row.id}
        pageSize={25}
        pageNoun="user"
        empty={{ title: "No matching platform users", detail: "Change the search or status." }}
        columns={[
          idColumn("User ID"),
          userColumn,
          { key: "role", label: "Role", render: (row) => row.role_label ?? titleCase(row.role ?? "—") },
          organizationColumn,
          {
            key: "status",
            label: "Status",
            render: (row) => <StatusBadge status={row.status} label={accountStatusLabel(row.status)} />,
          },
          {
            key: "mfa",
            label: "",
            render: (row) => (
              <span className="cc-actions">
                {/* The name of an account of one's own organization, one's own included (a name is not access). */}
                {canChangeName(row, me.data?.tenant_id) && (
                  <button
                    type="button"
                    className="ac-link"
                    aria-label={`Change name of ${name(row)}`}
                    onClick={() => setRenaming(row)}
                  >
                    Change name
                  </button>
                )}
                {canResetMfa(row, me.data?.user_id) && (
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
                )}
              </span>
            ),
          },
        ]}
      />
      {renaming && (
        <ChangeNameDialog
          account={renaming}
          onClose={() => setRenaming(null)}
          onDone={(text) => {
            setRenaming(null);
            setNotice({ text, tone: "good" });
            users.reload();
          }}
        />
      )}
      <ConfirmDialog
        request={confirm}
        onClose={() => setConfirm(null)}
        onDone={(text) => {
          setConfirm(null);
          setNotice({ text, tone: "good" });
          users.reload();
        }}
      />
    </Panel>
  );
}

/** Every customer's administrators, with the actions a platform administrator may take (also under Customers). */
function CustomerAdministrators() {
  const [message, setMessage] = useState<BannerMessage>(null);
  return (
    <>
      <Banner message={message} onDismiss={() => setMessage(null)} />
      <CustomerAdmins onMessage={(text, tone = "good") => setMessage({ text, tone })} />
    </>
  );
}

/**
 * People asking to use MDARIX: free-trial requests, and requests from free trials for a pilot conversation or a
 * one-to-one demo; demo requests from the website too while the website offers them (`websiteDemos`; it has offered
 * only the free trial since 0.10.5, and the MVP parks their route). Approving a trial creates its customer and tenant
 * (under Customers & Tenants) and the requester's account.
 */
export function Onboarding({ websiteDemos = false }: { websiteDemos?: boolean }) {
  return (
    <div className="cc-page">
      <div className="cc-title">
        <div>
          <h2>{websiteDemos ? "Demo and trial requests" : "Trial requests"}</h2>
          <p className="ac-muted">
            {websiteDemos
              ? "The people who asked for a demo, a free trial or, from a trial, a pilot conversation."
              : "The people who asked for a free trial and, from their trial, for a pilot conversation or a one-to-one demo."}{" "}
            Approving a trial creates the requester&apos;s account, and the customer and tenant it belongs to, which are
            then managed under Customers &amp; Tenants.
          </p>
        </div>
      </div>
      <DemoRequestsWorkspace websiteRequests={websiteDemos} />
      <MvpRequestsWorkspace />
      <TrialRequestsWorkspace />
    </div>
  );
}

/** The roles customer users can hold, for the filter (Customer Administrators have their own list). */
const CUSTOMER_ROLES: [string, string][] = [
  ["VIEWER", "Viewer"],
  ["TRIAGE_LEAD", "PMS / Signal Triage Lead"],
  ["INVESTIGATOR", "Quality Investigator"],
  ["RISK_REVIEWER", "Risk Reviewer"],
  ["REGULATORY_REVIEWER", "Regulatory Reviewer"],
  ["REVIEWER", "Quality Reviewer"],
  ["APPROVER", "Authorized Decision Maker"],
  ["LEADER", "Leader (Quality Manager)"],
];

type TenantOption = {
  id: string;
  display_name?: string | null;
  tenant_name?: string | null;
  business_id?: string | null;
};

/** Columns the server can order every page by (backend platform_accounts.py list_customer_users). */
const CUSTOMER_USER_SORT_KEYS = [
  "business_id",
  "user",
  "organization",
  "role",
  "status",
  "display_name",
  "email",
  "customer_name",
  "tenant_name",
  "tenant_business_id",
  "customer_business_id",
  "role_label",
  "created_at",
] as const;

/** The people of every customer organization, read-only: each customer's own administrators manage them. */
function CustomerUsers() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [role, setRole] = useState("");
  const [tenant, setTenant] = useState("");
  const [page, setPage] = useState(1);
  const { sort, onSort } = useServerSort(() => setPage(1));
  const params = new URLSearchParams({ page: String(page), page_size: "50", ...sortParams(sort) });
  if (query.trim()) params.set("q", query.trim());
  if (status) params.set("status", status);
  if (role) params.set("role", role);
  if (tenant) params.set("tenant_id", tenant);
  const users = useResource<{ items: Account[]; total: number; page: number; pages: number }>(
    `/api/v1/platform-admin/customer-users?${params}`,
  );
  const tenants = useResource<{ items: TenantOption[] }>("/api/v1/platform-admin/customer-admin-tenants");
  // Any change of filter starts again from the first page.
  const filter = (set: (value: string) => void) => (value: string) => {
    set(value);
    setPage(1);
  };
  return (
    <Panel eyebrow="Customer organizations" title="Customer users" source={users}>
      <Intro>
        Everyone with an account in a customer organization, apart from its administrators (see Customer
        administrators). Each customer&apos;s own administrators add, change and remove these accounts.
      </Intro>
      <div className="cc-toolbar">
        <SearchBox value={query} onChange={filter(setQuery)} label="Search name, email, customer or tenant" />
        <select aria-label="Tenant" value={tenant} onChange={(event) => filter(setTenant)(event.target.value)}>
          <option value="">All tenants</option>
          {(tenants.data?.items ?? []).map((option) => (
            <option key={option.id} value={option.id}>
              {option.display_name ?? option.tenant_name ?? option.business_id}
              {option.tenant_name && option.tenant_name !== option.display_name ? ` · ${option.tenant_name}` : ""}
            </option>
          ))}
        </select>
        <select aria-label="Role" value={role} onChange={(event) => filter(setRole)(event.target.value)}>
          <option value="">All roles</option>
          {CUSTOMER_ROLES.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
        <select aria-label="Status" value={status} onChange={(event) => filter(setStatus)(event.target.value)}>
          <option value="">Current accounts</option>
          <option value="ACTIVE">Active</option>
          <option value="INVITED">Invited</option>
          <option value="PENDING_VERIFICATION">Pending verification</option>
          <option value="SUSPENDED">Suspended</option>
          <option value="INACTIVE">Retired</option>
        </select>
      </div>
      <Table
        caption="Customer users"
        rows={users.data?.items ?? []}
        rowKey={(row) => row.id}
        serverSort={{ sort, onSort, keys: CUSTOMER_USER_SORT_KEYS }}
        empty={{ title: "No matching customer users", detail: "Change the search or filters." }}
        columns={[
          idColumn("User ID"),
          userColumn,
          organizationColumn,
          { key: "role", label: "Role", render: (row) => row.role_label ?? titleCase(row.role ?? "—") },
          {
            key: "status",
            label: "Status",
            render: (row) => <StatusBadge status={row.status} label={accountStatusLabel(row.status)} />,
          },
        ]}
      />
      <Pager
        page={users.data?.page ?? page}
        pages={users.data?.pages ?? 1}
        total={users.data?.total ?? 0}
        noun="user"
        onPage={setPage}
      />
    </Panel>
  );
}

/** A built-in role as /platform-admin/role-catalog describes it. */
type CatalogRole = {
  code: string;
  label: string;
  scope: string;
  description: string;
  permissions: string[];
  account_holders: number;
  additional_holders: number;
  can_be_additional: boolean;
};
type CatalogPermission = { code: string; label: string; description: string; roles: string[] };

/**
 * The roles built into MDARIX and what each allows, in plain words: choose a role to see its permissions and how many
 * people hold it across every customer. Roles are part of the product, so this is read-only; an organization's own
 * custom roles, if it defines any, are listed below.
 */
function RolesAndPermissions() {
  const catalog = useResource<{ roles: CatalogRole[]; permissions: CatalogPermission[] }>(
    "/api/v1/platform-admin/role-catalog",
  );
  const custom = useResource<Role[]>("/api/v1/admin/identity/roles");
  const roles = catalog.data?.roles ?? [];
  const permissions = catalog.data?.permissions ?? [];
  const [chosen, setChosen] = useState("");
  const role = roles.find((item) => item.code === chosen) ?? roles[0];
  const labelOf = (code: string) => roles.find((item) => item.code === code)?.label ?? titleCase(code);
  return (
    <>
      <div className="ac-grid two">
        <Panel eyebrow="Who can do what" title="Roles" source={catalog}>
          <Intro>The roles built into MDARIX. Choose a role to see what it allows.</Intro>
          <Table
            caption="Roles"
            rows={roles}
            rowKey={(row) => row.code}
            empty={{ title: "No roles", detail: "The role catalogue could not be read." }}
            columns={[
              {
                key: "label",
                label: "Role",
                render: (row) => (
                  <button
                    type="button"
                    className={`ac-link cc-stack${row.code === role?.code ? " ar-selected" : ""}`}
                    aria-pressed={row.code === role?.code}
                    onClick={() => setChosen(row.code)}
                  >
                    <strong>{row.label}</strong>
                    <small>{row.scope}</small>
                  </button>
                ),
              },
              {
                key: "permissions",
                label: "Permissions",
                numeric: true,
                sortValue: (row) => row.permissions.length,
                render: (row) => row.permissions.length,
              },
              {
                key: "account_holders",
                label: "People",
                numeric: true,
                sortValue: (row) => row.account_holders + row.additional_holders,
                render: (row) => row.account_holders + row.additional_holders,
              },
            ]}
          />
        </Panel>
        <Panel
          eyebrow={role ? role.scope : "Role"}
          title={role ? role.label : "What a role allows"}
          state={catalog.state}
          error={catalog.error}
        >
          {role && (
            <div className="ar-role">
              <p className="ar-intro">{role.description}</p>
              <p className="ac-muted">
                Held by {role.account_holders} {role.account_holders === 1 ? "account" : "accounts"} as their role
                {role.can_be_additional
                  ? `, and by ${role.additional_holders} ${role.additional_holders === 1 ? "person" : "people"} as an additional role`
                  : ""}
                .
              </p>
              <ul className="ar-permission-list" aria-label={`What ${role.label} allows`}>
                {permissions.map((permission) => {
                  const granted = role.permissions.includes(permission.code);
                  return (
                    <li key={permission.code} className={granted ? "granted" : "not-granted"}>
                      <span className={granted ? "ar-yes" : "ar-no"}>
                        {granted ? <Check size={14} aria-hidden="true" /> : <Minus size={14} aria-hidden="true" />}
                        <strong>{permission.label}</strong>
                        <span className="ca-sr-only">{granted ? "(allowed)" : "(not allowed)"}</span>
                      </span>
                      <small>{permission.description}</small>
                    </li>
                  );
                })}
              </ul>
              {role.permissions.length === 0 && <p className="ac-muted">Read-only: this role changes nothing.</p>}
            </div>
          )}
        </Panel>
      </div>
      <Panel eyebrow="Every permission" title="Permissions" source={catalog}>
        <Intro>
          What each permission allows, and which roles grant it. A person holding several roles has all of them.
        </Intro>
        <Table
          caption="Permissions"
          rows={permissions}
          rowKey={(row) => row.code}
          empty={{ title: "No permissions", detail: "The role catalogue could not be read." }}
          columns={[
            {
              key: "label",
              label: "Permission",
              fields: ["label", "description"],
              render: (row) => (
                <span className="cc-stack">
                  <strong>{row.label}</strong>
                  <small>{row.description}</small>
                </span>
              ),
            },
            {
              key: "roles",
              label: "Granted by",
              sortValue: (row) => row.roles.length,
              render: (row) => row.roles.map(labelOf).join(", ") || "—",
            },
          ]}
        />
      </Panel>
      {listOf(custom.data).length > 0 && <CustomRoles />}
    </>
  );
}

/** Custom roles an organization defined, and the permission sets each grants (shown only when there are any). */
function CustomRoles() {
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
      <Panel eyebrow="Defined by an organization" title="Custom roles" source={roles}>
        <Intro>A custom role groups permission sets. Choose a role to see what it grants.</Intro>
        <Table
          caption="Custom roles"
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

/** What one person can actually do: their roles and job profiles (personas), as the server evaluates them. */
function EffectiveAccess() {
  const users = useResource<User[]>("/api/v1/admin/identity/users");
  const [userId, setUserId] = useState("");
  const access = useResource<{ status?: string; roles: Role[]; personas: Array<Record<string, any>> }>(
    userId ? `/api/v1/admin/identity/users/${userId}/effective-access` : null,
  );
  const rows = listOf(users.data) as User[];
  const chosen = rows.find((user) => user.id === userId);
  return (
    <div className="ac-grid">
      <Panel eyebrow="Check one person" title="Effective access" source={users}>
        <Intro>Choose a person to see the roles and job profiles that decide what they can do.</Intro>
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
              empty={{
                title: "No extra roles",
                detail: chosen?.role
                  ? `Only their account role applies: ${titleCase(chosen.role)}.`
                  : "Only their account role applies.",
              }}
              columns={[
                { key: "role", label: "Role", render: (row) => <strong>{row.name ?? titleCase(row.code)}</strong> },
                { key: "status", label: "Status", render: (row) => <StatusBadge status={row.status} /> },
              ]}
            />
          </Panel>
          <Panel eyebrow="Working as" title="Job profiles" source={access}>
            <Table
              caption="Job profiles"
              rows={access.data?.personas ?? []}
              rowKey={(row, index) => String(row.id ?? index)}
              empty={{ title: "No job profiles", detail: "No job profile (persona) is assigned to this person." }}
              columns={[
                {
                  key: "persona",
                  label: "Job profile",
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
