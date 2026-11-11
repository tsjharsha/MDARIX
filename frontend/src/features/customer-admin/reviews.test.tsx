import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ConsoleContext, SECTIONS, type ConsoleApi } from "./context";
import { AccessReview, AuditTrailReview, ConfigurationReview } from "./sections/Reviews";

// B6a C6: the signed review screens (flat, G-2). The server decides who reads and signs; the screens show its answer.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("./shared", async (original) => ({
  ...(await original<typeof import("./shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path]) ?? null,
    reload: () => undefined,
  }),
}));

const render = (node: ReactElement) =>
  renderToStaticMarkup(
    <ConsoleContext.Provider
      value={{ context: {}, open: vi.fn(), confirm: vi.fn(), notify: vi.fn() } as unknown as ConsoleApi}
    >
      {node}
    </ConsoleContext.Provider>,
  );

const flag = (code: string, label: string, count: number) => ({ code, label, count, actors: [], events: [] });
const audit = (extra: Record<string, unknown>) => ({
  period: { from: "2026-10-05", to: "2026-10-11" },
  flags: [flag("EDIT_WITHOUT_REASON", "Edits without a reason", 1), flag("BULK_CHANGE", "Bulk changes", 0)],
  chain_valid: true,
  planes: [{ plane: "control", events: 66, chain_valid: true, first_broken_seq: null }],
  events: 66,
  incomplete: [],
  own_flags: [],
  may_sign: true,
  last_signed: null,
  next_due: "2026-11-12",
  awaiting_confirmation: [],
  ...extra,
});

describe("Signed reviews", () => {
  it("lists Reviews in the customer administration menu", () => {
    expect(SECTIONS).toContain("Reviews");
  });

  it("shows the audit trail flags first with counts, and the sign form to a reviewer", () => {
    resources.data["/api/v1/reviews/audit-trail"] = audit({});
    const html = render(<AuditTrailReview />);
    expect(html).toContain("Edits without a reason");
    expect(html).toContain("Audit chain check: intact.");
    expect(html).toContain("Sign the audit trail review");
    expect(html).toContain("Authenticator code");
    expect(html).not.toMatch(/gradient|glass|glow/);
  });

  it("tells a customer administrator who signs, says when the chain is broken and asks for a second reviewer", () => {
    resources.data["/api/v1/reviews/audit-trail"] = audit({
      may_sign: false,
      chain_valid: false,
      planes: [{ plane: "control", events: 66, chain_valid: false, first_broken_seq: 41 }],
      own_flags: ["EDIT_WITHOUT_REASON"],
      awaiting_confirmation: [
        { review_id: "r1", signed_at: "2026-11-10T09:00:00Z", signed_by: "u", findings: "x", fingerprint: "f" },
      ],
    });
    const html = render(<AuditTrailReview />);
    expect(html).toContain("A Leader or Quality Reviewer signs this review.");
    expect(html).not.toContain("Sign the audit trail review");
    expect(html).toContain("broken (from event #41)");
    expect(html).toContain("Second reviewer needed");
    expect(html).toContain("a second reviewer confirms them");
  });

  it("asks for every access row to be marked before signing", () => {
    resources.data["/api/v1/reviews/access"] = {
      rows: [
        {
          user_id: "u1",
          name: "Asha",
          email: "asha@example.invalid",
          role_label: "Leader (Quality Manager)",
          other_roles: [],
          mfa_on: true,
          last_active: null,
          invited_at: null,
          changes: [],
          mark: null,
        },
      ],
      unmarked: 1,
      next_due: "2026-11-12",
      may_sign: true,
    };
    const html = render(<AccessReview />);
    expect(html).toContain("Not marked");
    expect(html).toContain("Mark every row first.");
    expect(html).toContain("Sign the access review");
  });

  it("lists signed configuration snapshots with their downloads", () => {
    resources.data["/api/v1/reviews/configuration/signed"] = [
      { review_id: "s1", signed_at: "2026-11-10T09:00:00Z", signed_by: "u", findings: "Baseline", fingerprint: "f" },
    ];
    const html = render(<ConfigurationReview />);
    expect(html).toContain("Baseline");
    expect(html).toContain("/api/v1/reviews/signed/s1/download?format=pdf");
    expect(html).toContain("Compare with now");
    expect(html).toContain("never keys");
  });
});
