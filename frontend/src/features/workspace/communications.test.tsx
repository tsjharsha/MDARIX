import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import {
  attemptsText,
  communicationsTab,
  entryBody,
  entryProblem,
  parseCommunicationsTab,
  s4Text,
  statusTone,
  type CommunicationList,
  type Entry,
  type EntryForm,
} from "./communications";
import { taskDestination } from "./tasks";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));

vi.mock("../customer-admin/shared", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../customer-admin/shared")>();
  return {
    ...actual,
    useResource: (path: string | null) => ({
      data: path ? (resources.data[path] ?? null) : null,
      error: null,
      state: "ready",
      loading: false,
      reload: vi.fn(),
    }),
  };
});

const { Communications, EntryDrawer } = await import("./sections/Communications");

function workspace(permissions: string[]): WorkspaceApi {
  return {
    session: { allowed_menu: ["products"], business_permissions: permissions },
    open: vi.fn(),
    notify: vi.fn(),
    work: { products: [] },
  } as unknown as WorkspaceApi;
}

const render = (node: ReactNode, permissions: string[] = ["signal.triage"]) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={workspace(permissions)}>{node}</WorkspaceContext.Provider>);

const party = {
  id: "p1",
  type: "HOSPITAL",
  type_label: "Hospital",
  name: "St. Sample General Hospital",
  complaint_id: null,
  primary: { name: "Biomed desk", details: "biomed@stsample.invalid" },
  second: { name: "Head of biomed", details: null },
  note: null,
  sample: true,
};

const attempt = (number: number, contact: "PRIMARY" | "SECOND", outcome = "NO_ANSWER") => ({
  number,
  at: "2026-10-20T10:00:00+00:00",
  channel: "PHONE",
  channel_label: "Phone",
  contact,
  contact_name: contact === "PRIMARY" ? "Biomed desk" : "Head of biomed",
  outcome,
  outcome_label: outcome === "SENT" ? "Sent, waiting for a reply" : "No answer",
  unanswered: true,
  note: null,
  logged_at: "2026-10-20T10:30:00+00:00",
  logged_by: "MDARIX sample author",
  in_mdarix: number !== 5,
});

const entry = (patch: Partial<Entry> = {}): Entry => ({
  id: "e1",
  complaint_id: "c1",
  complaint_ref: "CMP-0001",
  intake_reference: null,
  party,
  direction: "SENT",
  direction_label: "Sent",
  purpose: "INFORMATION_REQUEST",
  purpose_label: "Information request",
  subject: "Ask for the alarm log",
  note: null,
  channel: "EMAIL",
  channel_label: "E-mail",
  occurred_at: "2026-10-12T10:00:00+00:00",
  logged_at: "2026-10-12T10:15:00+00:00",
  logged_by: "MDARIX sample author",
  in_mdarix: true,
  owner_id: "u1",
  owner: "Asha",
  reply_due_on: "2026-10-17",
  overdue: false,
  status: "UNRESOLVED",
  status_label: "Unresolved after attempts",
  is_request: true,
  not_sent_yet: false,
  current_contact: "SECOND",
  contact_now: party.second,
  attempts: [1, 2, 3].map((n) => attempt(n, "PRIMARY")).concat([4, 5, 6].map((n) => attempt(n, "SECOND"))),
  unanswered: 3,
  attempts_limit: 3,
  evidence: [],
  qms_reference: null,
  in_reply_to: null,
  origin: null,
  closed_at: "2026-10-24T10:00:00+00:00",
  closed_by: "MDARIX sample author",
  close_note: "No answer after 3 attempts to each contact",
  sample: true,
  replies: [],
  never_sends: "MDARIX sends nothing to your contacts.",
  ...patch,
});

const form: EntryForm = {
  partyId: "p1",
  direction: "SENT",
  purpose: "INFORMATION_REQUEST",
  subject: "Ask for the log",
  channel: "EMAIL",
  occurredAt: "2026-11-01T10:00",
  ownerId: "",
  replyDueOn: "",
  note: "",
  evidence: "Hospital e-mail\n\nQMS-1",
  qmsReference: "",
};

describe("communications rules", () => {
  it("needs an owner and a reply date for a request, and sends evidence one per line", () => {
    expect(entryProblem(form)).toMatch("owner");
    expect(entryProblem({ ...form, purpose: "UPDATE" })).toBeNull();
    const body = entryBody({ ...form, ownerId: "u1", replyDueOn: "2026-11-05" }, "c1");
    expect(body.evidence).toEqual(["Hospital e-mail", "QMS-1"]);
    expect(entryBody({ ...form, purpose: "UPDATE" }, "c1").owner_id).toBeNull();
  });

  it("reads attempts, tones and the S4 count", () => {
    const open = entry({ status: "OPEN", current_contact: "PRIMARY", unanswered: 2, overdue: true });
    expect(attemptsText(open)).toBe("2 of 3 attempts to the primary contact unanswered");
    expect(attemptsText(entry({ status: "OPEN", not_sent_yet: true }))).toMatch("Not sent yet");
    expect(statusTone(open)).toBe("critical");
    expect(statusTone(entry({ status: "ANSWERED" }))).toBe("good");
    expect(s4Text({ in_mdarix: 9, outside: 1 })).toMatch("9 of 10 messages");
  });

  it("opens one complaint's log from a link and from a reply-due task", () => {
    expect(parseCommunicationsTab(communicationsTab("c 1"))).toEqual({ isLog: true, complaintId: "c 1" });
    expect(parseCommunicationsTab("Reports")).toEqual({ isLog: false, complaintId: null });
    expect(
      taskDestination({ task_type: "EXTERNAL_REPLY_DUE", investigation: null, details: { complaint_id: "c1" } }),
    ).toEqual({
      section: "Complaints",
      tab: "Communications?complaint=c1",
    });
  });
});

describe("the communications screens", () => {
  it("shows one complaint's log with its counts, S4 and the record form", () => {
    resources.data["/api/v1/communications?complaint_id=c1"] = {
      complaint: {
        id: "c1",
        ref: "CMP-0001",
        identifier: "SAMPLE-RV-01",
        description: "SpO2 dropped out",
        sample: true,
      },
      items: [
        entry(),
        entry({
          id: "e2",
          status: "OPEN",
          overdue: true,
          status_label: "Open",
          current_contact: "PRIMARY",
          unanswered: 2,
        }),
      ],
      counts: { open: 1, overdue: 1, unresolved: 1 },
      s4: { in_mdarix: 8, outside: 1 },
      parties: [party],
      colleagues: [{ id: "u1", name: "Asha" }],
      attempts_limit: 3,
      labels: {
        party_types: { HOSPITAL: "Hospital" },
        purposes: { INFORMATION_REQUEST: "Information request" },
        directions: { SENT: "Sent", RECEIVED: "Received" },
        statuses: {},
        channels: { EMAIL: "E-mail" },
        outcomes: { NO_ANSWER: "No answer" },
      },
      never_sends: "MDARIX sends nothing to your contacts.",
    } satisfies CommunicationList;
    const html = render(<Communications complaintId="c1" />);
    expect(html).toContain("1 open request, 1 overdue");
    expect(html).toContain("Unresolved after attempts");
    expect(html).toContain("Open, overdue");
    expect(html).toContain("Recorded in MDARIX: 8 of 9 messages");
    expect(html).toContain("Record a message sent or received");
    expect(html).toContain("MDARIX sends nothing");
  });

  it("lists every attempt with its contact and the late one", () => {
    resources.data["/api/v1/communications/e1"] = entry();
    const html = render(<EntryDrawer id="e1" onClose={vi.fn()} />);
    expect(html).toContain("Attempts (6)");
    expect(html).toContain("Head of biomed");
    expect(html).toContain("(late)");
    expect(html).toContain("No answer after 3 attempts to each contact");
  });
});
