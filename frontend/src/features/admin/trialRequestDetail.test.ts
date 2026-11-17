import { describe, expect, it } from "vitest";
import {
  approvedResult,
  legalAcceptanceLines,
  requestLines,
  reviewLines,
  waitForApproval,
} from "./TrialRequestsWorkspace";

// 0.10.41 (DEV-027): Platform Admin > Onboarding shows the acceptance time in UTC, each text's full fingerprint and
// who approved the trial and when, from what the request already records.

const SHA = "479317105fb4a3ad4f85ee48688c926fbfff0123456789abcdef0123456789ab";
const acceptance = {
  accepted_at: "2026-10-19T10:42:03.512000+00:00",
  documents: {
    terms: { available: true, last_updated: "16 October 2026", sha256: SHA },
    "trial-agreement": { available: true, last_updated: "19 October 2026", sha256: SHA.replace("4", "5") },
    privacy: { available: false, last_updated: null, sha256: null },
  },
};

describe("a trial request's review detail", () => {
  it("shows each text's full fingerprint and the acceptance time in UTC", () => {
    const lines = legalAcceptanceLines(acceptance);
    expect(lines).toEqual([
      { label: "Terms of Service", value: `last updated 16 October 2026 · SHA-256 ${SHA}` },
      { label: "Free Trial Agreement", value: `last updated 19 October 2026 · SHA-256 ${SHA.replace("4", "5")}` },
      { label: "Privacy Policy", value: "not published when the request was sent" },
      { label: "Accepted", value: "2026-10-19 10:42:03 UTC" },
    ]);
    expect(SHA).toHaveLength(64);
    expect(legalAcceptanceLines(null)).toEqual([]);
  });

  it("names who approved or declined the request, and when", () => {
    const approved = {
      status: "APPROVED",
      reviewed_at: "2026-10-19T10:42:05+00:00",
      reviewed_by_name: "Automatic approval (company email)",
    };
    expect(reviewLines(approved)).toEqual([
      { label: "Approved", value: "Automatic approval (company email), 2026-10-19 10:42:05 UTC" },
    ]);
    // A personal address's automatic approval is named as such (0.10.48), so the two rules read apart.
    expect(reviewLines({ ...approved, reviewed_by_name: "Automatic approval (personal email)" })).toEqual([
      { label: "Approved", value: "Automatic approval (personal email), 2026-10-19 10:42:05 UTC" },
    ]);
    expect(reviewLines({ ...approved, status: "DECLINED", reviewed_by_name: "Priya Nair" })).toEqual([
      { label: "Declined", value: "Priya Nair, 2026-10-19 10:42:05 UTC" },
    ]);
    expect(reviewLines({ status: "PENDING_REVIEW", reviewed_at: null, reviewed_by_name: null })).toEqual([]);
    const all = requestLines({
      ...approved,
      profile_lines: [{ label: "Job title", value: "Quality Manager" }],
      legal_acceptance: acceptance,
    } as unknown as Parameters<typeof requestLines>[0]);
    expect(all.map((line) => line.label)).toEqual([
      "Job title",
      "Terms of Service",
      "Free Trial Agreement",
      "Privacy Policy",
      "Accepted",
      "Approved",
    ]);
  });
});

describe("a background trial approval", () => {
  const row = { id: "r1", email: "a@example.com" };
  const base = { organization: "Acme", tenant_key: "acme", email: "a@example.com" };
  it("follows the request list until it is approved", async () => {
    const pages = [[{ ...base, id: "r1", status: "PENDING_REVIEW" }], [{ ...base, id: "r1", status: "APPROVED" }]];
    const paths: string[] = [];
    const done = await waitForApproval(
      row,
      async (path) => {
        paths.push(path);
        return { items: pages.shift() as never };
      },
      async () => {},
    );
    expect(done?.status).toBe("APPROVED");
    expect(paths[0]).toContain("q=a%40example.com");
  });
  it("gives up when the request still waits for review (the approval failed, nothing saved)", async () => {
    const done = await waitForApproval(
      row,
      async () => ({ items: [{ ...base, id: "r1", status: "PENDING_REVIEW" } as never] }),
      async () => {},
      3,
    );
    expect(done).toBeNull();
  });
  it("words the invitation outcome", () => {
    const approved = { ...base, id: "r1", status: "APPROVED" } as never as Parameters<typeof approvedResult>[0];
    expect(approvedResult({ ...approved, invitation_delivery: "SENT" }).text).toMatch(/Invitation emailed/);
    expect(approvedResult({ ...approved, invitation_delivery: "NOT_CONFIGURED" }).text).toMatch(/Resend invitation/);
    expect(approvedResult({ ...approved, invitation_delivery: "FAILED" }).tone).toBe("bad");
  });
});
