// 0.10.88 (DEV-10): what the browser journeys found, as rendered from the server's answers.
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceContext, type WorkspaceApi } from "./workspaceContext";
import { ComplaintPage } from "./sections/ComplaintPage";
import { ReportPage, openSubmission } from "./sections/ReportsTab";
import { eventPath } from "./oversight";
import { REPORTS } from "./authorityReports";
import { latestSaves } from "./treeAnswer";
import { INVITE_TIMEOUT_MS, unansweredInvite } from "./sections/TrialTeam";
import { ApiError } from "../../app/apiClient";
import { ReportingFacts } from "./sections/ReportingFacts";

const resources = vi.hoisted(() => ({ data: {} as Record<string, unknown> }));
vi.mock("../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../customer-admin/shared")>()),
  useResource: (path: string | null) => {
    const value = (path && resources.data[path.split("?")[0]]) ?? null;
    // A refusal as the server sends it: its message, code and the reference for support.
    return value instanceof Error
      ? { state: "error", data: null, error: value.message, code: value.name, requestId: "req-1", reload: () => {} }
      : { state: "ready", data: value, reload: () => undefined };
  },
}));

const api = () =>
  ({
    session: { user_id: "u1", business_permissions: ["records.write", "signal.triage", "regulatory.review"] },
    work: { products: [], investigations: [] },
    open: vi.fn(),
    notify: vi.fn(),
    navigation: "new",
    isTrial: true,
    persona: "admin",
  }) as unknown as WorkspaceApi;

const render = (node: ReactNode) =>
  renderToStaticMarkup(<WorkspaceContext.Provider value={api()}>{node}</WorkspaceContext.Provider>);

const refused = (message: string, code: string) => Object.assign(new Error(message), { name: code });

describe("a record that is not there (removed, or a mistyped link) offers the way back, not a Retry", () => {
  it("on a complaint's page", () => {
    resources.data[eventPath("SAMPLE-RV-99")] = refused("No such complaint", "COMPLAINT_NOT_FOUND");
    resources.data["/api/v1/triage"] = { items: [] };
    const html = render(<ComplaintPage tab="Summary?ref=SAMPLE-RV-99" />);
    expect(html).toContain("This complaint could not be opened");
    expect(html).toContain("Open the complaint list");
    expect(html).not.toContain(">Retry<");
  });

  it("on a report's page", () => {
    resources.data[`${REPORTS}/r-gone`] = refused("No such report in your organization", "REPORT_NOT_FOUND");
    const html = render(<ReportPage id="r-gone" onBack={() => undefined} />);
    expect(html).toContain("This report could not be opened");
    expect(html).toContain("All reports");
    expect(html).not.toContain(">Retry<");
  });
});

describe("the decision tree's saves (0.10.88): answering quickly never leaves the outcome behind", () => {
  it("sends the newest answers once the save in flight is answered, skipping the ones in between", async () => {
    const saves = latestSaves<number>();
    const sent: number[] = [];
    let release = () => undefined as void;
    const first = new Promise<void>((resolve) => (release = resolve));
    const send = (answer: number) => async () => {
      sent.push(answer);
      if (answer === 1) await first;
      return answer;
    };
    const runs = [saves.run(send(1))];
    await vi.waitFor(() => expect(sent).toEqual([1]));
    runs.push(...[2, 3, 4, 5, 6].map((answer) => saves.run(send(answer))));
    expect(saves.pending()).toBe(true);
    release();
    const results = await Promise.all(runs);
    // One save was in flight, five were asked for meanwhile: only the newest of them is sent.
    expect(sent).toEqual([1, 6]);
    expect(results[5]).toBe(6);
    expect(saves.pending()).toBe(false);
  });
});

describe("Record the submission, from the report's rail (0.10.88)", () => {
  it("opens the folded part that holds the form, scrolls to it and puts the keyboard on its first field", () => {
    const field = { focus: vi.fn() };
    const folded = { open: false };
    const part = {
      closest: vi.fn(() => folded),
      scrollIntoView: vi.fn(),
      querySelector: vi.fn(() => field),
    } as unknown as HTMLElement;
    openSubmission(part);
    expect(folded.open).toBe(true);
    expect(part.scrollIntoView).toHaveBeenCalled();
    expect(field.focus).toHaveBeenCalledWith({ preventScroll: true });
  });
});

describe("inviting a colleague while the e-mail provider is slow (0.10.88)", () => {
  it("waits longer than a usual request, since the invitation is sent while it waits", () => {
    expect(INVITE_TIMEOUT_MS).toBeGreaterThanOrEqual(30_000);
  });

  it("never says 'try again' when the answer was lost: the invitation may have been sent", () => {
    for (const code of ["TIMEOUT", "NETWORK_ERROR"])
      expect(unansweredInvite(new ApiError("MDARIX took too long", 0, code))).toMatch(/check the list below/);
    expect(unansweredInvite(new ApiError("That colleague is already invited", 409, "ALREADY_INVITED"))).toBeNull();
  });
});

describe("OD-2: the United Kingdom is asked, Great Britain or Northern Ireland (0.10.88)", () => {
  it("offers the two parts to choose from, not a free text field", () => {
    const html = render(
      <ReportingFacts
        complaintId="c1"
        needs={[
          {
            fact: "COUNTRY",
            label: "Incident country",
            given: "United Kingdom",
            choices: ["Great Britain", "Northern Ireland"],
            message: '"United Kingdom" is two markets: choose Great Britain or Northern Ireland.',
            rule: "UK MDR 2002; EU MDR Art. 87",
          },
        ]}
        onSaved={() => undefined}
      />,
    );
    expect(html).toMatch(/<select[^>]*>.*<option value="Great Britain">Great Britain<\/option>/);
    expect(html).toContain('<option value="Northern Ireland">Northern Ireland</option>');
    expect(html).not.toContain('placeholder="For example India');
  });
});
