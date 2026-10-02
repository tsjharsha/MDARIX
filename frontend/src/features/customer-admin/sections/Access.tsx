import { useState } from "react";
import { Plus } from "lucide-react";
import { Panel, ToneBadge } from "../../admin/console/charts";
import { titleCase, type Tone } from "../../admin/console/dashboardModel";
import { ASSIGNABLE_ROLES, useConsole } from "../context";
import { Table, Tabs, errorText, listOf, send, useResource, type Confirmation } from "../shared";

const TABS = ["Roles", "Permission sets", "Approval rules"] as const;
type Tab = (typeof TABS)[number];

export const lifecycleTone = (status: unknown): Tone => {
  const value = String(status ?? "").toUpperCase();
  if (["ACTIVE", "RELEASED", "APPROVED"].includes(value)) return "good";
  if (["RETIRED", "SUPERSEDED"].includes(value)) return "neutral";
  if (["READY_FOR_APPROVAL", "VALIDATION"].includes(value)) return "warning";
  return "neutral";
};

export function LifecycleBadge({ status }: { status: unknown }) {
  return <ToneBadge tone={lifecycleTone(status)} label={titleCase(String(status ?? "Unknown"))} />;
}

/** Activate / retire buttons for any record that uses the shared lifecycle status. */
export function LifecycleActions({
  status,
  name,
  path,
  onDone,
}: {
  status: unknown;
  name: string;
  path: string;
  onDone: () => void;
}) {
  const { confirm } = useConsole();
  const current = String(status ?? "").toUpperCase();
  const change = (next: "ACTIVE" | "RETIRED"): Confirmation => ({
    title: `${next === "ACTIVE" ? "Activate" : "Retire"} ${name}?`,
    body:
      next === "ACTIVE"
        ? "It takes effect for everyone it applies to at their next request."
        : "It stops applying at once. The record is kept for audit and can be activated again.",
    confirmLabel: next === "ACTIVE" ? "Activate" : "Retire",
    danger: next === "RETIRED",
    done: `${name} is now ${next.toLowerCase()}.`,
    run: async () => {
      await send(path, "PATCH", { status: next });
      onDone();
    },
  });
  return (
    <span className="ca-row-actions">
      {current !== "ACTIVE" && (
        <button type="button" className="ac-link" onClick={() => confirm(change("ACTIVE"))}>
          Activate
        </button>
      )}
      {current !== "RETIRED" && (
        <button type="button" className="ac-link ca-link-danger" onClick={() => confirm(change("RETIRED"))}>
          Retire
        </button>
      )}
    </span>
  );
}

export function AccessSection({ tab }: { tab?: string }) {
  const [active, setActive] = useState<Tab>((TABS as readonly string[]).includes(tab ?? "") ? (tab as Tab) : "Roles");
  return (
    <>
      <p className="ca-lede">
        Deny wins. Access is the base role plus any active roles below; every check happens on the server.
      </p>
      <Tabs tabs={TABS} active={active} onChange={setActive} label="Roles and access sections" />
      {active === "Roles" && <Roles />}
      {active === "Permission sets" && <PermissionSets />}
      {active === "Approval rules" && <ApprovalRules />}
    </>
  );
}

function Roles() {
  const { notify } = useConsole();
  const roles = useResource<any[]>("/api/v1/admin/identity/roles");
  const permissionSets = useResource<any[]>("/api/v1/admin/identity/permission-sets");
  const links = useResource<any[]>("/api/v1/admin/identity/role-permission-sets");
  const assignments = useResource<any[]>("/api/v1/admin/identity/role-assignments");
  const [form, setForm] = useState({ code: "", name: "" });
  const [link, setLink] = useState({ role_id: "", permission_set_id: "" });
  const setName = (id: string) => listOf(permissionSets.data).find((set) => set.id === id)?.code ?? "Permission set";
  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await send("/api/v1/admin/identity/roles", "POST", {
        code: form.code.trim().toUpperCase(),
        name: form.name.trim(),
      });
      notify(`Role ${form.name} created as a draft. Activate it to make it assignable.`);
      setForm({ code: "", name: "" });
      roles.reload();
    } catch (reason) {
      notify(errorText(reason, "Role could not be created."), "critical");
    }
  };
  const addLink = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await send("/api/v1/admin/identity/role-permission-sets", "POST", link);
      notify("Permission set added to the role.");
      setLink({ role_id: "", permission_set_id: "" });
      links.reload();
    } catch (reason) {
      notify(errorText(reason, "Permission set could not be added."), "critical");
    }
  };
  return (
    <>
      <Panel eyebrow="Roles & access" title="Roles" state={roles.state} error={roles.error}>
        <Table
          caption="Roles"
          rows={listOf(roles.data)}
          rowKey={(row) => row.id}
          empty={{ title: "No custom roles yet", detail: "Create a role, add permission sets, then activate it." }}
          columns={[
            { key: "name", label: "Role", render: (row) => <strong>{row.name}</strong> },
            { key: "code", label: "Code", render: (row) => row.code },
            {
              key: "sets",
              label: "Permission sets",
              render: (row) =>
                listOf(links.data)
                  .filter((item) => item.role_id === row.id)
                  .map((item) => setName(item.permission_set_id))
                  .join(", ") || "—",
            },
            {
              key: "users",
              label: "Users",
              numeric: true,
              render: (row) =>
                listOf(assignments.data).filter(
                  (item) => item.role_id === row.id && String(item.status).toUpperCase() === "ACTIVE",
                ).length,
            },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
            {
              key: "actions",
              label: "",
              render: (row) => (
                <LifecycleActions
                  status={row.status}
                  name={row.name}
                  path={`/api/v1/admin/identity/roles/${row.id}/status`}
                  onDone={roles.reload}
                />
              ),
            },
          ]}
        />
      </Panel>
      <div className="ac-grid two">
        <Panel eyebrow="New" title="Create a role">
          <form className="ca-form" onSubmit={create}>
            <div className="ca-form-grid">
              <label className="ca-field">
                Name
                <input
                  required
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </label>
              <label className="ca-field">
                Code
                <input
                  required
                  pattern="[A-Za-z0-9_]+"
                  title="Letters, numbers and underscores"
                  value={form.code}
                  onChange={(event) => setForm({ ...form, code: event.target.value })}
                />
              </label>
            </div>
            <div className="ca-action-row">
              <button type="submit" className="ac-primary">
                <Plus size={16} /> Create role
              </button>
            </div>
          </form>
        </Panel>
        <Panel eyebrow="Compose" title="Add a permission set to a role">
          <form className="ca-form" onSubmit={addLink}>
            <div className="ca-form-grid">
              <label className="ca-field">
                Role
                <select
                  required
                  value={link.role_id}
                  onChange={(event) => setLink({ ...link, role_id: event.target.value })}
                >
                  <option value="">Choose a role</option>
                  {listOf(roles.data).map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="ca-field">
                Permission set
                <select
                  required
                  value={link.permission_set_id}
                  onChange={(event) => setLink({ ...link, permission_set_id: event.target.value })}
                >
                  <option value="">Choose a permission set</option>
                  {listOf(permissionSets.data).map((set) => (
                    <option key={set.id} value={set.id}>
                      {set.code} ({set.version})
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="ca-action-row">
              <button type="submit" className="ac-secondary">
                Add to role
              </button>
            </div>
          </form>
        </Panel>
      </div>
    </>
  );
}

const count = (value: unknown) => (value && typeof value === "object" ? Object.keys(value).length : 0);

function PermissionSets() {
  const { notify } = useConsole();
  const sets = useResource<any[]>("/api/v1/admin/identity/permission-sets");
  const [code, setCode] = useState("");
  const [objects, setObjects] = useState("{}");
  const [actions, setActions] = useState("{}");
  const [error, setError] = useState("");
  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    let object_permissions: unknown;
    let action_permissions: unknown;
    try {
      object_permissions = JSON.parse(objects || "{}");
      action_permissions = JSON.parse(actions || "{}");
    } catch {
      setError('Permissions must be valid JSON objects, for example {"Product": ["READ"]}.');
      return;
    }
    try {
      await send("/api/v1/admin/identity/permission-sets", "POST", {
        code: code.trim().toUpperCase(),
        object_permissions,
        action_permissions,
      });
      notify(`Permission set ${code} created as a draft.`);
      setCode("");
      setObjects("{}");
      setActions("{}");
      sets.reload();
    } catch (reason) {
      setError(errorText(reason, "Permission set could not be created."));
    }
  };
  return (
    <>
      <Panel eyebrow="Roles & access" title="Permission sets" state={sets.state} error={sets.error}>
        <Table
          caption="Permission sets"
          rows={listOf(sets.data)}
          rowKey={(row) => row.id}
          empty={{ title: "No permission sets yet", detail: "Create one below, then add it to a role." }}
          columns={[
            { key: "code", label: "Permission set", render: (row) => <strong>{row.code}</strong> },
            { key: "version", label: "Version", render: (row) => row.version },
            { key: "objects", label: "Objects", numeric: true, render: (row) => count(row.object_permissions) },
            { key: "fields", label: "Fields", numeric: true, render: (row) => count(row.field_permissions) },
            { key: "actions", label: "Actions", numeric: true, render: (row) => count(row.action_permissions) },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
            {
              key: "manage",
              label: "",
              render: (row) => (
                <LifecycleActions
                  status={row.status}
                  name={row.code}
                  path={`/api/v1/admin/identity/permission-sets/${row.id}/status`}
                  onDone={sets.reload}
                />
              ),
            },
          ]}
        />
      </Panel>
      <Panel eyebrow="New" title="Create a permission set">
        <form className="ca-form" onSubmit={create}>
          <label className="ca-field">
            Code
            <input
              required
              pattern="[A-Za-z0-9_]+"
              title="Letters, numbers and underscores"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <div className="ca-form-grid">
            <label className="ca-field">
              Object permissions (JSON)
              <textarea
                rows={4}
                className="ca-mono"
                value={objects}
                onChange={(event) => setObjects(event.target.value)}
              />
            </label>
            <label className="ca-field">
              Action permissions (JSON)
              <textarea
                rows={4}
                className="ca-mono"
                value={actions}
                onChange={(event) => setActions(event.target.value)}
              />
            </label>
          </div>
          {error && (
            <p className="ca-inline-error" role="alert">
              {error}
            </p>
          )}
          <div className="ca-action-row">
            <button type="submit" className="ac-primary">
              <Plus size={16} /> Create permission set
            </button>
          </div>
        </form>
      </Panel>
    </>
  );
}

/** What a rule governs. The server matches these exact codes, so they are chosen, never typed. */
const GOVERNED = [
  {
    object_type: "Decision",
    decision_type: "INVESTIGATION_REVIEW",
    label: "Investigation decisions: review and signature",
  },
];

function ApprovalRules() {
  const { notify } = useConsole();
  const policies = useResource<any>("/api/v1/admin/governance/policies");
  const tenantRoles = useResource<any[]>("/api/v1/admin/identity/roles");
  // Business roles first, then the organization's own active roles; administrators manage, they do not approve.
  const roleChoices = [
    ...ASSIGNABLE_ROLES.filter((role) => role.value !== "CUSTOMER_ADMIN"),
    ...listOf(tenantRoles.data)
      .filter((role) => String(role.status).toUpperCase() === "ACTIVE")
      .map((role) => ({ value: String(role.name), label: String(role.name) })),
  ].filter(
    (role, index, all) => all.findIndex((other) => other.value.toUpperCase() === role.value.toUpperCase()) === index,
  );
  const [authority, setAuthority] = useState({
    role_name: "APPROVER",
    object_type: GOVERNED[0].object_type,
    decision_type: GOVERNED[0].decision_type,
  });
  const [sod, setSod] = useState({
    name: "",
    object_type: GOVERNED[0].object_type,
    decision_type: GOVERNED[0].decision_type,
    creator_cannot_approve: true,
    last_material_editor_cannot_approve: true,
  });
  const submit = async (path: string, body: unknown, done: string, reset: () => void) => {
    try {
      await send(path, "POST", body);
      notify(done);
      reset();
      policies.reload();
    } catch (reason) {
      notify(errorText(reason, "The rule could not be created."), "critical");
    }
  };
  return (
    <>
      <Panel eyebrow="Governance" title="Who may approve what" state={policies.state} error={policies.error}>
        <Table
          caption="Approval authorities"
          rows={listOf(policies.data?.approval_authorities)}
          rowKey={(row) => row.id}
          empty={{ title: "No approval authorities", detail: "Add one below to allow a role to approve a decision." }}
          columns={[
            { key: "role", label: "Role", render: (row) => <strong>{row.role_name}</strong> },
            { key: "object", label: "Object", render: (row) => titleCase(row.object_type) },
            { key: "decision", label: "Decision", render: (row) => titleCase(row.decision_type) },
            { key: "authority", label: "Authority", render: (row) => titleCase(row.authority) },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
            {
              key: "manage",
              label: "",
              render: (row) => (
                <LifecycleActions
                  status={row.status}
                  name={`${row.role_name} approval`}
                  path={`/api/v1/admin/governance/policies/authority/${row.id}/status`}
                  onDone={policies.reload}
                />
              ),
            },
          ]}
        />
        <h3 className="ca-subhead">Segregation of duties</h3>
        <Table
          caption="Segregation of duties policies"
          rows={listOf(policies.data?.sod_policies)}
          rowKey={(row) => row.id}
          empty={{ title: "No segregation rules", detail: "Add one below so authors cannot approve their own work." }}
          columns={[
            { key: "name", label: "Policy", render: (row) => <strong>{row.name}</strong> },
            { key: "object", label: "Object", render: (row) => titleCase(row.object_type) },
            {
              key: "rules",
              label: "Rules",
              render: (row) =>
                [
                  row.creator_cannot_approve && "Creator cannot approve",
                  row.last_material_editor_cannot_approve && "Last editor cannot approve",
                ]
                  .filter(Boolean)
                  .join(" · ") || "—",
            },
            { key: "status", label: "Status", render: (row) => <LifecycleBadge status={row.status} /> },
            {
              key: "manage",
              label: "",
              render: (row) => (
                <LifecycleActions
                  status={row.status}
                  name={row.name}
                  path={`/api/v1/admin/governance/policies/sod/${row.id}/status`}
                  onDone={policies.reload}
                />
              ),
            },
          ]}
        />
      </Panel>
      <div className="ac-grid two">
        <Panel eyebrow="New" title="Add an approval authority">
          <form
            className="ca-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submit(
                "/api/v1/admin/governance/approval-authorities",
                authority,
                "Approval authority added as a draft. Activate it in the list above to put it into effect.",
                () => setAuthority({ ...authority, role_name: "APPROVER" }),
              );
            }}
          >
            <p className="ac-muted">
              Approvers and Leaders may approve and sign decisions by default. New rules start as drafts: activate them
              in the list above.
            </p>
            <label className="ca-field">
              Role
              <select
                required
                value={authority.role_name}
                onChange={(event) => setAuthority({ ...authority, role_name: event.target.value })}
              >
                {roleChoices.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-field">
              May approve
              <select
                value={`${authority.object_type}|${authority.decision_type}`}
                onChange={(event) => {
                  const [object_type, decision_type] = event.target.value.split("|");
                  setAuthority({ ...authority, object_type, decision_type });
                }}
              >
                {GOVERNED.map((item) => (
                  <option key={item.decision_type} value={`${item.object_type}|${item.decision_type}`}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="ca-action-row">
              <button type="submit" className="ac-secondary">
                Add authority
              </button>
            </div>
          </form>
        </Panel>
        <Panel eyebrow="New" title="Add a segregation-of-duties rule">
          <form
            className="ca-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submit(
                "/api/v1/admin/governance/sod-policies",
                sod,
                "Segregation rule added as a draft. Activate it in the list above to put it into effect.",
                () => setSod({ ...sod, name: "" }),
              );
            }}
          >
            <label className="ca-field">
              Name
              <input
                required
                maxLength={120}
                value={sod.name}
                onChange={(event) => setSod({ ...sod, name: event.target.value })}
              />
            </label>
            <label className="ca-field">
              Applies to
              <select
                value={`${sod.object_type}|${sod.decision_type}`}
                onChange={(event) => {
                  const [object_type, decision_type] = event.target.value.split("|");
                  setSod({ ...sod, object_type, decision_type });
                }}
              >
                {GOVERNED.map((item) => (
                  <option key={item.decision_type} value={`${item.object_type}|${item.decision_type}`}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="ca-check">
              <input
                type="checkbox"
                checked={sod.creator_cannot_approve}
                onChange={(event) => setSod({ ...sod, creator_cannot_approve: event.target.checked })}
              />
              The creator cannot approve
            </label>
            <label className="ca-check">
              <input
                type="checkbox"
                checked={sod.last_material_editor_cannot_approve}
                onChange={(event) => setSod({ ...sod, last_material_editor_cannot_approve: event.target.checked })}
              />
              The last material editor cannot approve
            </label>
            <div className="ca-action-row">
              <button type="submit" className="ac-secondary">
                Add rule
              </button>
            </div>
          </form>
        </Panel>
      </div>
    </>
  );
}
