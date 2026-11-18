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
 * "List view ▾" (0.10.74, Release C part C2): one choice of the list's views, the persona's own first and the rest
 * under "More views", with a line on what the chosen view holds. The same on a computer and a phone.
 */
export function ListViewPicker({
  mine,
  more = [],
  active,
  onChange,
  forLabel,
  detail,
  count,
  noun = "record",
  labels = {},
}: {
  mine: readonly string[];
  more?: readonly string[];
  active: string;
  onChange: (view: string) => void;
  /** Whose views come first ("Quality Leader"). */
  forLabel?: string;
  /** What the chosen view holds. */
  detail?: string;
  /** How many records the chosen view holds, once read. */
  count?: number | null;
  /** What the list holds, in the singular ("complaint"). */
  noun?: string;
  /** A view's shown name where it differs from its address name (Cases' "To log" for "Calls to check", UX2). */
  labels?: Readonly<Record<string, string>>;
}) {
  const id = useId();
  const option = (view: string) => (
    <option key={view} value={view}>
      {labels[view] ?? view}
    </option>
  );
  return (
    <div className="uw-listbar">
      <label className="uw-lv" htmlFor={id}>
        <span>List view</span>
        <select id={id} value={active} onChange={(event) => onChange(event.target.value)}>
          {more.length ? (
            <>
              <optgroup label={forLabel ? `For ${forLabel}` : "Your views"}>{mine.map(option)}</optgroup>
              <optgroup label="More views">{more.map(option)}</optgroup>
            </>
          ) : (
            mine.map(option)
          )}
        </select>
      </label>
      {(detail || count != null) && (
        <p className="uw-listbar-note">
          {count != null && (
            <strong>
              {count} {count === 1 ? noun : `${noun}s`}
            </strong>
          )}
          {count != null && detail ? " · " : ""}
          {detail}
        </p>
      )}
    </div>
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
