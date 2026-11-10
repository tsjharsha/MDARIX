// 0.10.93 (B2 step 5, spec 4.6): the complaint page's origin line, "The case" card, the Service card and the stage
// "Case" of a complaint a Case became.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage, originText } from "./sections/ComplaintPage";
import { eventPath, type EventView } from "./oversight";
import { rv11 } from "../../test/rv11";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    return { state: "ready", data: value, reload: () => undefined };
  },
}));

const render = () =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider
      value={
        {
          session: { user_id: "u1", business_permissions: ["records.write"] },
          work: { products: [], investigations: [] },
          open: vi.fn(),
          notify: vi.fn(),
          navigation: "new",
          isTrial: true,
          persona: "admin",
        } as unknown as WorkspaceApi
      }
    >
      <ComplaintPage tab="Summary?ref=SAMPLE-RV-11" />
    </WorkspaceContext.Provider>,
  );

const ORIGIN = {
  from_case: true,
  case_ref: "CASE-2026-000123",
  created_at: "2026-11-07T10:00:00Z",
  record_owner: "MDARIX" as const,
  qms_ref: null,
  last_synced_at: null,
};

describe("the complaint page of a complaint a Case became (spec 4.6)", () => {
  it("says where it came from: a Case (Complete or Connect) or the QMS", () => {
    expect(originText(ORIGIN)).toBe("Created in MDARIX from case CASE-2026-000123");
    expect(originText({ ...ORIGIN, record_owner: "EXTERNAL" })).toMatch(
      /^Created in MDARIX from case CASE-2026-000123 on .+ · QMS ID: not yet$/,
    );
    const qms = {
      ...ORIGIN,
      from_case: false,
      case_ref: null,
      qms_ref: "QMS-4411",
      last_synced_at: "2026-11-06T09:12:00Z",
    };
    expect(originText(qms)).toMatch(/^From your QMS · ID QMS-4411 · last synced /);
    expect(originText({ ...qms, qms_ref: null, last_synced_at: null })).toBeNull();
  });

  it("shows the origin line, 'The case' card with its addenda and check, and the Service card's lines", () => {
    const view: EventView = {
      ...rv11(),
      origin: ORIGIN,
      case: {
        id: "e1",
        reference: "CASE-2026-000123",
        words: "The pump stopped during an infusion",
        addenda: [
          { kind: "STATEMENT", said_by_role: "TECHNICIAN", said_at: "2026-11-08T10:00:00Z", text: "Seal worn" },
        ],
        channel: "PHONE",
        channel_ref: "call 4471",
        received_at: "2026-11-07T09:00:00Z",
        signed: { outcome: "Complaint and service", by: "Priya", at: "2026-11-07T10:00:00Z" },
        escalation: "CREATED",
        escalated_at: "2026-11-07T10:00:00Z",
        troubleshooting: "Restarted the pump; the alarm came back",
        service_ticket: "SVC-1",
      },
    };
    resources.data[eventPath("SAMPLE-RV-11")] = view;
    const html = render();
    for (const text of [
      "Created in MDARIX from case CASE-2026-000123",
      "The case · CASE-2026-000123",
      "The pump stopped during an infusion",
      "A technician",
      "Seal worn",
      "phone · call 4471",
      "Complaint and service · signed by Priya",
      "Open the case check",
      "<h2>Service</h2>",
      "What was tried on the call:",
      "Restarted the pump; the alarm came back",
      "Service work never closes the complaint.",
    ])
      expect(html).toContain(text);
  });

  it("shows no case card and no origin line on a complaint that came from neither", () => {
    resources.data[eventPath("SAMPLE-RV-11")] = rv11();
    const html = render();
    expect(html).not.toContain("The case ·");
    expect(html).not.toContain("uw-cp-origin");
    expect(html).not.toContain("Service work never closes the complaint.");
  });
});
