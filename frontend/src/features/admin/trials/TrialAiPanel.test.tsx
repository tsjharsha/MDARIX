import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const list = vi.hoisted(() => ({ data: null as unknown }));
vi.mock("../../customer-admin/shared", async (original) => ({
  ...(await original<typeof import("../../customer-admin/shared")>()),
  useResource: (path: string) => ({
    state: "ready",
    data: path.endsWith("/ai-access") ? list.data : null,
    reload: () => undefined,
  }),
}));

import {
  TrialAiPanel,
  aiGates,
  aiAccessReasonProblem,
  aiAccessRequest,
  peopleToChange,
  trialAiPanel,
  type TrialAiPerson,
} from "./TrialAiPanel";

const PEOPLE: TrialAiPerson[] = [
  { user_id: "u1", display_name: "Asha", active: true },
  { user_id: "u2", display_name: "Ravi", active: false },
  { user_id: "u3", display_name: "Meena", active: true },
];

describe("TO-1 part 4: AI per person in a trial", () => {
  it("changes only the people whose switch differs", () => {
    expect(peopleToChange(PEOPLE, false).map((person) => person.user_id)).toEqual(["u1", "u3"]);
    expect(peopleToChange(PEOPLE, true, "u2").map((person) => person.user_id)).toEqual(["u2"]);
    expect(peopleToChange(PEOPLE, true, "u1")).toEqual([]);
  });

  it("needs a reason of at least 10 characters", () => {
    expect(aiAccessReasonProblem("No AI pls")).toMatch(/at least 10/);
    expect(aiAccessReasonProblem("  Asked for no AI  ")).toBeNull();
  });

  it("sends one user to the single route and 'set all' to the trial's bulk route (TO-1 3.6.1 names)", () => {
    expect(aiAccessRequest("t-1", true, " Back on for the trial ", "u2")).toEqual({
      path: "/api/v1/platform-admin/trial-organizations/t-1/users/u2/ai-access",
      body: { active: true, reason: "Back on for the trial" },
    });
    expect(aiAccessRequest("t-1", false, "Trial owner asked")).toEqual({
      path: "/api/v1/platform-admin/trial-organizations/t-1/ai-access",
      body: { active: false, reason: "Trial owner asked" },
    });
  });

  it("fits the trial page slot and shows the server's AI line", () => {
    const detail = { tenant_id: "t-1", ai: { line: "AI is off for free trials" } };
    const html = renderToStaticMarkup(trialAiPanel({ detail, onChanged: () => undefined }));
    expect(html).toContain("AI is off for free trials");
    expect(renderToStaticMarkup(<TrialAiPanel detail={detail} onChanged={() => undefined} />)).toContain(
      "AI for this trial",
    );
  });

  it("always shows the three gates, and each person's AI as one real switch", () => {
    list.data = { organization_on: true, trial_chain_on: true, items: PEOPLE };
    expect(aiGates(list.data as never).map((gate) => `${gate.label}: ${gate.value}`)).toEqual([
      "Trial AI services: Ready",
      "Organization: Switched on",
      "People: 2 of 3 with AI",
    ]);
    const html = renderToStaticMarkup(<TrialAiPanel detail={{ tenant_id: "t-1" }} onChanged={() => undefined} />);
    expect(html).toContain("Trial AI services");
    expect(html).toContain("2 of 3 with AI");
    expect(html.match(/role="switch"/g)).toHaveLength(3);
    expect(html).toMatch(/role="switch" aria-checked="true" aria-label="AI for Asha"/);
    expect(html).toMatch(/role="switch" aria-checked="false" aria-label="AI for Ravi"/);
    expect(html).not.toContain("AI: Active");
    list.data = null;
  });
});
