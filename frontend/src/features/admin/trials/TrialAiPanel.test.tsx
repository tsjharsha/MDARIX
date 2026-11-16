import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  TrialAiPanel,
  aiAccessReasonProblem,
  aiAccessRequest,
  peopleToChange,
  trialAiPanel,
  type TrialAiPerson,
} from "./TrialAiPanel";

const PEOPLE: TrialAiPerson[] = [
  { user_id: "u1", display_name: "Asha", ai_access: "ACTIVE" },
  { user_id: "u2", display_name: "Ravi", ai_access: "INACTIVE" },
  { user_id: "u3", display_name: "Meena", ai_access: "ACTIVE" },
];

describe("TO-1 part 4: AI per person in a trial", () => {
  it("changes only the people whose switch differs", () => {
    expect(peopleToChange(PEOPLE, "INACTIVE").map((person) => person.user_id)).toEqual(["u1", "u3"]);
    expect(peopleToChange(PEOPLE, "ACTIVE", "u2").map((person) => person.user_id)).toEqual(["u2"]);
    expect(peopleToChange(PEOPLE, "ACTIVE", "u1")).toEqual([]);
  });

  it("needs a reason of at least 10 characters", () => {
    expect(aiAccessReasonProblem("No AI pls")).toMatch(/at least 10/);
    expect(aiAccessReasonProblem("  Asked for no AI  ")).toBeNull();
  });

  it("sends one person to the single route and several to the bulk route", () => {
    expect(aiAccessRequest("t-1", [PEOPLE[1]], "ACTIVE", " Back on for the trial ")).toEqual({
      path: "/api/v1/platform-admin/tenants/t-1/users/u2/ai-access",
      body: { ai_access: "ACTIVE", reason: "Back on for the trial" },
    });
    expect(aiAccessRequest("t-1", [PEOPLE[0], PEOPLE[2]], "INACTIVE", "Trial owner asked")).toEqual({
      path: "/api/v1/platform-admin/tenants/t-1/users/ai-access",
      body: { ai_access: "INACTIVE", reason: "Trial owner asked", user_ids: ["u1", "u3"] },
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
});
