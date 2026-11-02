import { useId, type ReactNode } from "react";
import { ROLE_LABELS } from "../../../app/roles";
import type { BusinessPermission } from "../workspaceContext";

/**
 * The views of one list (the new navigation, 0.10.68): the same list filtered, so they are a choice of view, not tabs.
 * A row of buttons on a computer; a single "View" choice on a phone (CSS, ≤640 px), so six rows of pills never come
 * before the content (J20).
 */
export function ViewChooser<T extends string>({
  views,
  active,
  onChange,
  label,
  labels = {},
  children,
}: {
  views: readonly T[];
  active: T;
  onChange: (view: T) => void;
  label: string;
  /** A view's name as shown, where it differs from its address name. */
  labels?: Partial<Record<T, string>>;
  children?: ReactNode;
}) {
  const id = useId();
  const text = (view: T) => labels[view] ?? view;
  return (
    <>
      <div className="uw-views" role="group" aria-label={label}>
        <div className="uw-views-row">
          {views.map((view) => (
            <button
              type="button"
              key={view}
              aria-pressed={active === view}
              className={active === view ? "selected" : ""}
              onClick={() => onChange(view)}
            >
              {text(view)}
            </button>
          ))}
        </div>
        <label className="ca-field uw-views-select" htmlFor={id}>
          View
          <select id={id} value={active} onChange={(event) => onChange(event.target.value as T)}>
            {views.map((view) => (
              <option key={view} value={view}>
                {text(view)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {children}
    </>
  );
}

/**
 * Who holds each permission a setting needs (backend/app/access/permissions.py ROLE_PERMISSIONS; Leader holds every
 * one). Kept beside the screens that say it; the server still decides every change.
 */
const HOLDERS: Partial<Record<BusinessPermission, readonly string[]>> = {
  "signal.triage": ["TRIAGE_LEAD", "LEADER"],
  "regulatory.review": ["REGULATORY_REVIEWER", "LEADER"],
  "regulatory.approve": ["REGULATORY_REVIEWER", "APPROVER", "LEADER"],
  "quality.review": ["REVIEWER", "LEADER"],
  "records.write": ["TRIAGE_LEAD", "INVESTIGATOR", "REVIEWER", "APPROVER", "LEADER", "CUSTOMER_ADMIN"],
};

/** "Triage lead or Leader": the roles that hold any of these permissions, in a readable list. */
export function holdersText(permissions: readonly BusinessPermission[]): string {
  const codes = [...new Set(permissions.flatMap((permission) => HOLDERS[permission] ?? []))];
  const names = codes.map((code) => ROLE_LABELS[code] ?? code);
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}` : (names[0] ?? "");
}

/** "Who can change this" above a setting: everyone reads it; only the roles named change it (7.7). */
export function WhoCanChange({
  permissions,
  canChange,
}: {
  permissions: readonly BusinessPermission[];
  canChange: boolean;
}) {
  return (
    <p className="uw-who-can" data-setting="who-can-change">
      <strong>Who can change this:</strong> {holdersText(permissions)}.{" "}
      {canChange ? "You can." : "You can read it; ask one of them to change it."}
    </p>
  );
}
