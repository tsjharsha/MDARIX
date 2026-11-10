import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { EmailToCheck, firstLines, type EmailItem } from "./sections/EmailToCheck";

// B7b (0.10.97): Cases › E-mail to check. Shown only while the server has e-mail intake switched on; each card shows
// the sender's domain marked unverified, the masked words, the flags and the files, and offers Make it a case, Add to
// the Case it answers, Not a case and the original message.

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => ({
    state: "ready",
    data: (path && resources.data[path.split("?")[0]]) ?? null,
    reload: () => undefined,
  }),
}));

const api = (permissions: string[], emailIntake: boolean) =>
  ({
    session: { allowed_menu: ["home"], business_permissions: permissions, email_intake: emailIntake },
    work: {},
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
  }) as unknown as WorkspaceApi;

const item: EmailItem = {
  id: "m1",
  state: "NEW",
  received_at: "2026-11-11T09:40:00Z",
  from_domain: "citycare-hospital.example",
  sender_verified: false,
  subject: "PulseWatch monitor alarm keeps sounding",
  words: "Our PulseWatch monitor gave a low battery alarm three times. Serial number: PW-20931.",
  identifiers: { serial: { text: "PW-20931" } },
  note: null,
  checked: true,
  harm_words: [],
  fault_words: ["alarm"],
  may_not_be_english: false,
  add_to_case: { id: "c1", reference: "CALL-1A2B3C" },
  possible_duplicate: null,
  possibly_known_earlier: ["2026-11-10T08:00:00Z"],
  attachments: [
    { id: "f1", file_name: "log.txt", size: 9, usable: true, reason: null },
    { id: "f2", file_name: "run.txt", size: 18, usable: false, reason: "Refused: virus found" },
  ],
  message_id: "<SAMPLE-EMAIL-1@intake.mdarix.com>",
  sample: true,
};

const render = (value: WorkspaceApi) =>
  renderToStaticMarkup(
    <WorkspaceContext.Provider value={value}>
      <EmailToCheck onMakeCase={() => undefined} onChanged={() => undefined} />
    </WorkspaceContext.Provider>,
  );

describe("E-mail to check (B7b)", () => {
  resources.data["/api/v1/email-intake/messages"] = { items: [item], reasons: ["SPAM", "AUTO_REPLY", "OTHER"] };

  it("shows nothing while e-mail intake is switched off", () => {
    expect(render(api(["case.log"], false))).toBe("");
  });

  it("shows a card with the unverified sender domain, flags, files and the three decisions", () => {
    const html = render(api(["case.log"], true));
    expect(html).toContain("E-mail to check");
    expect(html).toContain("citycare-hospital.example");
    expect(html).toContain("(unverified)");
    expect(html).toContain("SAMPLE");
    expect(html).toContain("Fault words: alarm");
    expect(html).toContain("Possibly known earlier");
    expect(html).toContain("serial: PW-20931 (unconfirmed, source: E-mail)");
    expect(html).toContain("Refused: virus found");
    expect(html).toContain("Make it a case");
    expect(html).toContain("Add to CALL-1A2B3C");
    expect(html).toContain("Not a case");
    expect(html).toContain("Open the original");
  });

  it("offers no decision to someone who cannot log cases", () => {
    const html = render(api(["records.write"], true));
    expect(html).toContain("E-mail to check");
    expect(html).not.toContain("Make it a case");
  });

  it("cuts long words for the card", () => {
    expect(firstLines("a ".repeat(300), 20)).toHaveLength(20);
    expect(firstLines("short  text")).toBe("short text");
  });
});
