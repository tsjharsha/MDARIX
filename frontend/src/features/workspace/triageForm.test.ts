import { describe, expect, it } from "vitest";
import { triageBody, triageDowngrade, triageProblem, triageSpeed, type Guide, type TriageForm } from "./intake";

// 0.10.93 (B2 step 5): the triage form asks before saving what the server would refuse with a 422 (potential harm,
// the backup, the threat answer, containment), and sends every field the two-speed triage needs.

const LEVELS: Guide["levels"] = ["NEGLIGIBLE", "MINOR", "SERIOUS", "CRITICAL", "CATASTROPHIC"].map((code) => ({
  code,
  label: code,
}));
const FORM: TriageForm = {
  severity: "MINOR",
  potential: "SERIOUS",
  threat: false,
  threatReason: "",
  remedial: false,
  remedialReason: "",
  eventOwner: "u1",
  triageOwner: "u1",
  backup: "u2",
  containment: ["USER_TOLD"],
  text: "Told the nurse to use a spare monitor",
  aware: "",
  awareNote: "",
  changeReason: "",
  password: "",
  mfa: "",
};
const FACTS = { malfunction: true, death: false } as never;
const ITEM = { speed: "FAST" as const, facts: FACTS, severity_floor: null, record: null };
const ctx = { people: 2, needsAwareness: false, laterAware: false, signs: false };

describe("the triage form (B2)", () => {
  it("is ready when every field the server asks for is there", () => {
    expect(triageProblem(ITEM, LEVELS, FORM, ctx)).toBeNull();
  });

  it("asks for the harm if it happened again when a malfunction is alleged", () => {
    expect(triageProblem(ITEM, LEVELS, { ...FORM, potential: "" }, ctx)).toMatch(/Harm if it happened again/);
  });

  it("asks for a backup on the fast track when two people are active, not in a one-person trial", () => {
    expect(triageProblem(ITEM, LEVELS, { ...FORM, backup: "" }, ctx)).toMatch(/Name a backup/);
    expect(triageProblem(ITEM, LEVELS, { ...FORM, backup: "" }, { ...ctx, people: 1 })).toBeNull();
  });

  it("keeps the floor and asks the threat question when a death is recorded", () => {
    const death = { ...ITEM, facts: { malfunction: false, death: true } as never, severity_floor: "CATASTROPHIC" };
    expect(triageProblem(death, LEVELS, FORM, ctx)).toMatch(/At least CATASTROPHIC/);
    expect(triageProblem(death, LEVELS, { ...FORM, severity: "CATASTROPHIC" }, ctx)).toMatch(/public health threat/);
    expect(
      triageProblem(
        death,
        LEVELS,
        { ...FORM, severity: "CATASTROPHIC", threatReason: "Single device, no pattern" },
        ctx,
      ),
    ).toBeNull();
  });

  it("is fast for Not known yet or a serious potential, and sees a downgrade of a saved fast triage", () => {
    const routine = { speed: "ROUTINE" as const };
    expect(triageSpeed(routine, LEVELS, { ...FORM, potential: "MINOR" })).toBe("ROUTINE");
    expect(triageSpeed(routine, LEVELS, { ...FORM, severity: "NOT_KNOWN", potential: "" })).toBe("FAST");
    const saved = { completed_at: "x", speed: "FAST", severity: "SERIOUS", potential_severity: "SERIOUS" } as never;
    expect(triageDowngrade(saved, LEVELS, { ...FORM, severity: "MINOR" }, "FAST")).toBe(true);
    expect(triageDowngrade(saved, LEVELS, { ...FORM, severity: "SERIOUS" }, "FAST")).toBe(false);
  });

  it("sends the potential harm, the backup and the containment; None needed alone is the reason for no action", () => {
    const body = triageBody(FORM, null, null);
    expect(body).toMatchObject({ potential_severity: "SERIOUS", backup_owner: "u2", containment: ["USER_TOLD"] });
    expect(body.immediate_action).toBe(FORM.text);
    const none = triageBody({ ...FORM, containment: ["NONE_NEEDED"] }, null, null);
    expect([none.immediate_action, none.no_action_reason]).toEqual(["", FORM.text]);
  });
});
