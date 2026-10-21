// Support access as the customer reads it (backend/app/support_access.py): MDARIX staff reach the organization's
// data only under access one of its administrators approved. Pure wording and decisions, tested on their own.
import type { Tone } from "../admin/console/dashboardModel";

export type SupportArea = { code: string; label: string };

export type SupportGrant = {
  id: string;
  status: string;
  person?: string | null;
  person_email?: string | null;
  requested_by?: string | null;
  approved_for_mdarix_by?: string | null;
  reason: string;
  areas: SupportArea[];
  write: boolean;
  starts_at?: string | null;
  expires_at?: string | null;
  decided_by?: string | null;
  decided_at?: string | null;
  decision_reason?: string | null;
  revoked_at?: string | null;
  uses: number;
  last_used_at?: string | null;
  can_approve: boolean;
  can_deny: boolean;
  can_revoke: boolean;
};

export type SupportActivity = {
  at?: string | null;
  action: string;
  who?: string | null;
  area?: string | null;
  write?: boolean | null;
  method?: string | null;
  path?: string | null;
  reason?: string | null;
  /** What happened, in the organization's words (backend/app/support_access_api.py). */
  what?: string | null;
  /** On the request and the approval: what they cover ("Read only. People: the user directory, to read"). */
  covers?: string | null;
};

const STATUS: Record<string, { label: string; tone: Tone }> = {
  AWAITING_CUSTOMER: { label: "Waiting for your decision", tone: "warning" },
  APPROVED: { label: "Active", tone: "serious" },
  DENIED: { label: "Denied", tone: "neutral" },
  REVOKED: { label: "Revoked", tone: "neutral" },
  EXPIRED: { label: "Ended", tone: "neutral" },
};

/** Where a grant stands, in words, with the tone it is shown in. An approved grant past its end has ended. */
export function supportStatus(grant: Pick<SupportGrant, "status" | "expires_at">, now: Date = new Date()) {
  const ended = grant.expires_at ? new Date(grant.expires_at).getTime() <= now.getTime() : false;
  if (ended && (grant.status === "APPROVED" || grant.status === "AWAITING_CUSTOMER")) return STATUS.EXPIRED;
  return STATUS[grant.status] ?? { label: grant.status, tone: "neutral" as Tone };
}

/** Read-only or read-and-change, as the request asks. */
export const accessText = (write: boolean) => (write ? "Read and change" : "Read only");

/** The areas of the organization's data a grant opens, by their short names ("Configuration, Audit trail"). */
export function areaNames(areas: SupportArea[]) {
  return areas.map((area) => area.label.split(":")[0].trim()).join(", ") || "Nothing (deny this request)";
}

/**
 * The areas with what each covers, as the server words them for this grant ("People (the user directory, to read)"
 * when read only): what a decision maker approves.
 */
export function areaDetails(areas: SupportArea[]) {
  return (
    areas
      .map((area) => {
        const [name, ...rest] = area.label.split(":");
        const what = rest.join(":").trim();
        return what ? `${name.trim()} (${what})` : name.trim();
      })
      .join("; ") || "Nothing (deny this request)"
  );
}

const AREA_SHORT: Record<string, string> = {
  CONFIGURATION: "configuration",
  AUDIT: "the audit trail",
  PEOPLE: "people",
  RECORDS: "quality records",
  DATA_EXPORT: "a full export",
};

/** One line of a grant's history, from the organization's own audit trail. */
export function activityText(item: SupportActivity) {
  switch (item.action) {
    case "SUPPORT_ACCESS_REQUESTED":
      return "MDARIX requested the access";
    case "SUPPORT_ACCESS_APPROVED":
      return "A second MDARIX administrator approved the request for MDARIX";
    case "SUPPORT_ACCESS_CUSTOMER_APPROVED":
      return "Your administrator approved the access";
    case "SUPPORT_ACCESS_DENIED":
      return "Your administrator denied the access";
    case "SUPPORT_ACCESS_REVOKED":
      return "The access was revoked";
    case "SUPPORT_ACCESS_EXPIRED":
      return "The access ended on its own";
    case "SUPPORT_ACCESS_USED": {
      if (item.what) return item.what;
      const area = AREA_SHORT[String(item.area ?? "")] ?? "your data";
      return `${item.write ? "Changed" : "Viewed"} ${area}`;
    }
    default:
      return item.action;
  }
}

/** How many requests wait for a decision, for the tab's badge (none shows no badge). */
export const awaitingCount = (grants: SupportGrant[]) =>
  grants.filter((grant) => grant.can_approve || grant.can_deny).length || null;
